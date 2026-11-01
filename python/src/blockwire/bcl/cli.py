"""BCL-only terminal REPL and complete-file sender over the existing TLS gateway."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
import stat
from pathlib import Path
import sys
from uuid import uuid4

from .client import BCLClient

HELP = """Blockwire BCL/1 (not Python). Ordinary lines execute immediately.
:begin / :end / :abort  collect, submit or discard one complete frame (:send = :end)
:load PATH              load UTF-8 text into the buffer; does NOT execute
:run PATH               execute one complete UTF-8 file (spaces in paths are literal)
:tasks / :status        known task IDs / connection and authoritative modal snapshot
:cancel TASK_ID         request cancellation; await terminal result for confirmation
:wait TASK_ID           wait for a known task's terminal result
:help / :quit           help / disconnect and cancel connection-owned work
F8 remains the Minecraft stop switch. No automatic reconnect or replay."""


def _interactive_terminal():
    return sys.stdin.isatty() and sys.stdout.isatty()


def emit(value):
    print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)


def readable(value):
    """Only render actual wire fields, escaping untrusted terminal control data."""
    if value.get('type') == 'event':
        print('[event] ' + json.dumps(value.get('event_type'), ensure_ascii=True), flush=True)
        emit(value.get('data'))
        return
    status = value.get('status')
    if status:
        ids = {k: value[k] for k in ('request_id', 'task_id') if k in value}
        print(json.dumps(str(status).upper(), ensure_ascii=True)[1:-1] +
              (' ' + json.dumps(ids, ensure_ascii=True) if ids else ''), flush=True)
    for key in ('outputs', 'result', 'diagnostics', 'error', 'tasks', 'modal', 'coordinate_context', 'session_id', 'connection', 'buffer_characters'):
        if key in value:
            print(key + ': ' + json.dumps(value[key], ensure_ascii=True, allow_nan=False), flush=True)
    if not status and not any(k in value for k in ('outputs', 'result', 'diagnostics', 'error', 'tasks', 'modal', 'coordinate_context', 'session_id', 'connection', 'buffer_characters')):
        emit(value)


def check_source(source):
    if len(source) > 16384:
        raise ValueError('BCL source exceeds 16384 characters')
    frame = {'type': 'bcl', 'source': source, 'request_id': 9007199254740991}
    if len(json.dumps(frame, allow_nan=False).encode('utf-8')) > 32768:
        raise ValueError('Encoded BCL frame exceeds 32768 bytes')
    return source


def read_source(path):
    with Path(path).open('rb') as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError('BCL file exceeds 65536 UTF-8 bytes')
    return check_source(data.decode('utf-8'))


def read_token(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Gateway token file must not be a symlink')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError('Gateway token must be a regular file')
        if os.name == 'posix' and metadata.st_mode & 0o077:
            raise ValueError('Gateway token permissions must be private (chmod 600)')
        data = os.read(descriptor, 1025)
    finally:
        os.close(descriptor)
    if len(data) > 1024:
        raise ValueError('Gateway token file is unexpectedly large')
    return data.decode('utf-8').strip()


async def send_file(client, source, output=emit):
    result = await client.send(check_source(source))
    output(result)
    if result.get('status') == 'accepted':
        result = await client.wait(result['task_id'])
        output(result)
    return 0 if result.get('status') == 'completed' else 1


@asynccontextmanager
async def notifications(client, output):
    async def display(queue):
        while True:
            output(await queue.get())
    tasks = [asyncio.create_task(display(q)) for q in (client.events, client.progress)]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@asynccontextmanager
async def terminal_input():
    if _interactive_terminal():
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
        from prompt_toolkit.patch_stdout import patch_stdout
        session = PromptSession(history=InMemoryHistory(), enable_history_search=True)
        # Redraw the current edit buffer around events, progress and terminal replies.
        with patch_stdout():
            yield session.prompt_async
    else:
        # A blocked executor readline would delay asyncio.run shutdown after a
        # gateway disconnect. POSIX pipes/TTYs use cancellable event-loop I/O.
        try:
            mode = os.fstat(sys.stdin.fileno()).st_mode
            is_cancellable_stream = os.name == 'posix' and not stat.S_ISREG(mode)
        except (OSError, ValueError, AttributeError):
            is_cancellable_stream = False
        if is_cancellable_stream:
            reader = asyncio.StreamReader()
            pipe = os.fdopen(os.dup(sys.stdin.fileno()), 'rb', buffering=0)
            transport, _ = await asyncio.get_running_loop().connect_read_pipe(
                lambda: asyncio.StreamReaderProtocol(reader), pipe)
            async def pipe_line(_prompt):
                line = await reader.readline()
                if not line:
                    raise EOFError
                return line.decode(sys.stdin.encoding or 'utf-8').rstrip('\r\n')
            try:
                yield pipe_line
            finally:
                transport.close()
        else:
            async def file_line(_prompt):
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    raise EOFError
                return line.rstrip('\r\n')
            yield file_line


async def repl(client, read_line=None, output=emit):
    if read_line is None:
        async with terminal_input() as read_line:
            return await repl(client, read_line, output)
    if _interactive_terminal():
        print(HELP)
    pending = set()
    buffer = None
    input_task = None
    failed = False

    async def submit(source):
        nonlocal failed
        code = await send_file(client, source, output)
        failed = failed or code != 0

    async with notifications(client, output):
        try:
            while True:
                input_task = asyncio.create_task(read_line('... ' if buffer is not None else 'bcl> '))
                # Keep input alive while replies arrive. A transport failure stops the
                # session immediately, even when the user has not pressed Enter.
                while True:
                    reader = getattr(client, 'reader', None)
                    watched = {input_task, *pending}
                    if reader is not None:
                        watched.add(reader)
                    await asyncio.wait(watched, return_when=asyncio.FIRST_COMPLETED)
                    if reader is not None and reader.done():
                        raise ConnectionError('Gateway connection closed; no reconnect or replay')
                    for task in list(pending):
                        if task.done():
                            pending.remove(task)
                            task.result()
                    if input_task.done():
                        break
                try:
                    line = input_task.result()
                except EOFError:
                    # Pipelines finish submitted work before closing; explicit :quit
                    # and Ctrl+C instead request cancellation immediately.
                    if pending:
                        await asyncio.gather(*pending)
                    break
                command, _, argument = line.strip().partition(' ')
                if command == ':quit':
                    break
                try:
                    source = None
                    if command == ':help':
                        print(HELP)
                    elif command == ':begin':
                        if buffer is not None:
                            raise ValueError('Already collecting a frame; :end or :abort first')
                        buffer = ''
                    elif command == ':abort':
                        buffer = None
                    elif command in {':end', ':send'}:
                        if buffer is None:
                            raise ValueError('Use :begin or :load first')
                        source = check_source(buffer)
                        buffer = None
                    elif command in {':load', ':run'}:
                        if buffer is not None:
                            raise ValueError(':end or :abort the collected frame first')
                        try:
                            loaded = read_source(argument)
                        except (OSError, UnicodeError) as error:
                            raise ValueError(str(error)) from error
                        if command == ':load':
                            buffer = loaded
                            output({'buffer_characters': len(buffer)})
                        else:
                            source = loaded
                    elif command == ':tasks':
                        output({'tasks': list(client.tasks)})
                    elif command == ':status':
                        output({'connection': 'established' if client.ws is not None else 'closed',
                                'session_id': client.bind['session_id'], 'modal': client.modal,
                                'coordinate_context': client.coordinate_context})
                    elif command in {':cancel', ':wait'} and argument:
                        if argument not in client.tasks:
                            raise ValueError('Unknown task ID')
                        output(await (client.cancel(argument) if command == ':cancel' else client.wait(argument)))
                    elif command.startswith(':'):
                        raise ValueError('Unknown or incomplete terminal command; :help')
                    elif buffer is not None:
                        separator = '\n' if buffer and not buffer.endswith(('\n', '\r')) else ''
                        buffer = check_source(buffer + separator + line + '\n')
                    elif line.strip():
                        source = check_source(line)
                    if source is not None:
                        if len(pending) >= 16:
                            raise ValueError('16 pending submissions; wait or cancel first')
                        pending.add(asyncio.create_task(submit(source)))
                except ValueError as error:
                    failed = True
                    output({'error': str(error)})
        finally:
            unfinished = any(not task.done() for task in pending)
            for task in [*pending, input_task]:
                if task is not None:
                    task.cancel()
            await asyncio.gather(*pending, *([input_task] if input_task else []), return_exceptions=True)
    return 1 if failed or unfinished else 0


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='wss://127.0.0.1:8880/v1', help='BCL gateway, not the native mod endpoint')
    p.add_argument('--certificate', required=True, type=Path, help='Trusted public gateway certificate')
    p.add_argument('--token-file', required=True, type=Path, help='Private gateway token file')
    p.add_argument('--session-id', default=None, help='Default: fresh session; no implicit rebind')
    p.add_argument('--agent-id', default='human')
    p.add_argument('--world-id', required=True, help='Operator-selected world label')
    p.add_argument('--player-uuid', required=True)
    p.add_argument('--actor-session', required=True, help='Fresh native actor_session')
    p.add_argument('--timeout', type=float, default=120., help='Response wait, not an operation-budget override')
    p.add_argument('--file', type=Path, help='Send one complete BCL file and wait')
    p.add_argument('--verbose', '--json', action='store_true', help='Full JSON protocol responses')
    return p


async def run(args):
    source = read_source(args.file) if args.file else None
    token = read_token(args.token_file)
    output = emit if args.verbose or not sys.stdout.isatty() else readable
    async with BCLClient(args.url, token, args.certificate,
                         session_id=args.session_id or 'human-' + uuid4().hex,
                         agent_id=args.agent_id, world_id=args.world_id,
                         player_uuid=args.player_uuid, actor_session=args.actor_session,
                         timeout=args.timeout) as client:
        if source is not None:
            async with notifications(client, output):
                return await send_file(client, source, output)
        if _interactive_terminal():
            print('Blockwire BCL/1 - Connection: established; Session: bound')
        return await repl(client, output=output)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Both public entry points use the same parser and transport implementation.
    if argv and argv[0] == 'repl':
        argv = argv[1:]
    elif argv and argv[0] == 'run':
        if len(argv) < 2 or argv[1].startswith('-'):
            parser().error('run requires a BCL file path before connection options')
        argv = ['--file', argv[1], *argv[2:]]
    args = parser().parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print('Disconnected; cancellation requested. Check Minecraft / F8.', file=sys.stderr)
        return 130
    except (OSError, UnicodeError, ValueError) as error:
        # Connection/authentication exceptions may include credentials: never echo
        # their raw messages. Local-file errors can be identified by exception type.
        print(f'BCL stopped ({type(error).__name__}): check file encoding/paths, gateway '
              'availability and trusted configuration. Outcome unconfirmed; no retry.', file=sys.stderr)
        return 1
    except Exception as error:
        print(f'BCL session stopped ({type(error).__name__}). Check gateway authentication/'
              'binding diagnostics. Outcome unconfirmed; no retry. Inspect Minecraft / F8.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
