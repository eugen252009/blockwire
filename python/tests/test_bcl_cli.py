"""Terminal contracts: simulated gateway; no Minecraft gameplay qualification."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blockwire.bcl.cli import check_source, main, read_source, repl, send_file, terminal_input, readable
from unittest.mock import AsyncMock
from contextlib import nullcontext


class Client:
    def __init__(self):
        self.events = asyncio.Queue()
        self.progress = asyncio.Queue()
        self.tasks = {}
        self.sources = []
        self.cancelled = []
        self.release = asyncio.Event()
        self.ws = object()
        self.bind = {'session_id': 'test'}
        self.modal = {'execution_mode': 'sync'}

    async def send(self, source):
        self.sources.append(source)
        return {'status': 'completed', 'source': source}

    async def cancel(self, task):
        self.cancelled.append(task)
        self.release.set()
        return {'status': 'cancelled'}

    async def wait(self, task):
        return {'status': 'completed', 'task_id': task}


class FileContracts(unittest.TestCase):
    def test_utf8_bom_multiline_and_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'my program.bcl'
            path.write_bytes(b'\xef\xbb\xbfS0 sync\nS2 sneak\n')
            self.assertEqual(read_source(path), '\ufeffS0 sync\nS2 sneak\n')
            path.write_bytes(b'\xff')
            with self.assertRaises(UnicodeError):
                read_source(path)
            path.write_bytes(b'x' * 65537)
            with self.assertRaises(ValueError):
                read_source(path)
        with self.assertRaises(ValueError):
            check_source('x' * 16385)
        with self.assertRaises(ValueError):
            check_source('\u2603' * 6000)  # JSON escaping exceeds frame size

    def test_required_identity_and_no_plaintext_switch(self):
        with self.assertRaises(SystemExit):
            main([])


class TerminalContracts(unittest.IsolatedAsyncioTestCase):
    async def terminal(self, client, lines):
        lines = iter(lines)
        output = []

        async def read_line(prompt):
            await asyncio.sleep(.01)
            try:
                return next(lines)
            except StopIteration:
                raise EOFError

        with patch('builtins.print'):
            await repl(client, read_line, output.append)
        return output

    async def test_lines_and_whole_multiline_frames(self):
        client = Client()
        await self.terminal(client, ['S2 sneak', ':begin', 'S0 sync', 'S1 relative', ':send', ':quit'])
        self.assertEqual(client.sources, ['S2 sneak', 'S0 sync\nS1 relative\n'])

    async def test_discard_eof_and_python_is_only_data(self):
        client = Client()
        await self.terminal(client, [':begin', 'M0 1 0 0', ':abort', 'print(123)', ':begin', 'M0 2 0 0'])
        self.assertEqual(client.sources, ['print(123)'])

    async def test_load_space_path_and_local_errors_do_not_send(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'my program.bcl'
            path.write_text('S2 sneak\nS2 ?', encoding='utf-8')
            client = Client()
            output = await self.terminal(client, [':send', ':unknown', ':load /nonexistent/bcl', ':load ' + str(path), ':end'])
        self.assertEqual(client.sources, ['S2 sneak\nS2 ?'])
        self.assertEqual(sum('error' in item for item in output), 3)

    async def test_sync_request_does_not_block_cancel(self):
        client = Client()

        async def send(source):
            client.sources.append(source)
            client.tasks['bcl:1'] = True
            await client.release.wait()
            return {'status': 'cancelled'}

        client.send = send
        await self.terminal(client, ['M0 1 0 0', ':tasks', ':cancel bcl:1', ':quit'])
        self.assertEqual(client.cancelled, ['bcl:1'])

    async def test_uncertain_transport_stops_without_replay(self):
        client = Client()

        async def send(source):
            client.sources.append(source)
            raise ConnectionError('fixture')

        client.send = send
        with self.assertRaises(ConnectionError):
            await self.terminal(client, ['M0 1 0 0', 'M0 2 0 0'])
        self.assertEqual(len(client.sources), 1)

    async def test_file_waits_for_async_terminal_and_failure_exit(self):
        client = Client()

        async def send(source):
            return {'status': 'accepted', 'task_id': 'bcl:1'}

        client.send = send
        output = []
        self.assertEqual(await send_file(client, 'S0 async\nI0', output.append), 0)
        self.assertEqual([r['status'] for r in output], ['accepted', 'completed'])

        async def wait(task):
            return {'status': 'failed'}

        client.wait = wait
        self.assertEqual(await send_file(client, 'I0', output.append), 1)

    async def test_disconnect_cancels_local_waiters(self):
        client = Client()
        finished = asyncio.Event()

        async def send(source):
            try:
                await asyncio.Event().wait()
            finally:
                finished.set()

        client.send = send
        await self.terminal(client, ['I0', ':quit'])
        self.assertTrue(finished.is_set())

    async def test_load_never_executes_without_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recorded.bcl'
            path.write_bytes(b'S0 sync\r\nS2 sneak\r\n')
            client = Client()
            await self.terminal(client, [':load ' + str(path), ':quit'])
            self.assertEqual(client.sources, [])
            await self.terminal(client, [':run ' + str(path)])
            self.assertEqual(client.sources, ['S0 sync\r\nS2 sneak\r\n'])

    async def test_eof_waits_for_submitted_pipeline_commands(self):
        client = Client()
        async def slow(source):
            await asyncio.sleep(.05)
            return {'status': 'failed', 'diagnostics': [{'code': 'FIXTURE'}]}
        client.send = slow
        lines = iter(['I0'])
        async def read_line(prompt):
            try:
                return next(lines)
            except StopIteration:
                raise EOFError
        self.assertEqual(await repl(client, read_line, lambda _: None), 1)

    async def test_event_received_while_input_is_pending(self):
        client = Client()
        received = asyncio.Event()
        def output(value):
            if value.get('type') == 'event':
                received.set()
        async def read_line(prompt):
            await client.events.put({'type': 'event', 'event_type': 'player.health', 'data': {'health': 20}})
            await asyncio.wait_for(received.wait(), 1)
            return ':quit'
        self.assertEqual(await repl(client, read_line, output), 0)

    async def test_reader_disconnect_interrupts_idle_prompt(self):
        client = Client()
        async def reader():
            await asyncio.sleep(.01)
        client.reader = asyncio.create_task(reader())
        async def read_line(prompt):
            await asyncio.Event().wait()
        with self.assertRaises(ConnectionError):
            await repl(client, read_line, lambda _: None)

    async def test_idle_pipe_input_can_be_cancelled_on_disconnect(self):
        import os
        if os.name != 'posix':
            self.skipTest('POSIX pipe transport')
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, 'r') as stream:
            try:
                with patch('sys.stdin', stream):
                    async with terminal_input() as read_line:
                        task = asyncio.create_task(read_line(''))
                        await asyncio.sleep(.01)
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                        self.assertTrue(task.cancelled())
            finally:
                os.close(write_fd)

    async def test_prompt_editing_and_session_history_survive_output(self):
        from prompt_toolkit import PromptSession
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        from prompt_toolkit.history import InMemoryHistory
        with create_pipe_input() as pipe:
            history = InMemoryHistory()
            session = PromptSession(input=pipe, output=DummyOutput(), history=history)
            with patch('sys.stdin.isatty', return_value=True), patch('sys.stdout.isatty', return_value=True), \
                 patch('prompt_toolkit.PromptSession', return_value=session), \
                 patch('prompt_toolkit.patch_stdout.patch_stdout', return_value=nullcontext()) as redraw:
                async with terminal_input() as read_line:
                    line = asyncio.create_task(read_line('bcl> '))
                    pipe.send_text('S2 sn')
                    await asyncio.sleep(.02)
                    with patch('builtins.print'):
                        readable({'type': 'event', 'event_type': 'player.health', 'data': {'health': 20}})
                    pipe.send_text('eak\n')
                    self.assertEqual(await asyncio.wait_for(line, 1), 'S2 sneak')
                redraw.assert_called_once()
            self.assertEqual(history.get_strings(), ['S2 sneak'])


class EntryContracts(unittest.TestCase):
    def test_unified_cli_dispatch_and_legacy_alias(self):
        from blockwire.cli import main as unified
        with patch('blockwire.bcl.cli.main', return_value=7) as dispatch:
            self.assertEqual(unified(['run', 'house.bcl', '--world-id', 'fixture']), 7)
            dispatch.assert_called_once_with(['run', 'house.bcl', '--world-id', 'fixture'])

    def test_mode_parser_and_observable_exit_codes(self):
        common = ['--certificate', 'public.pem', '--token-file', 'token', '--world-id', 'fixture',
                  '--player-uuid', 'player', '--actor-session', 'actor']
        with patch('blockwire.bcl.cli.run', new_callable=AsyncMock, return_value=1) as run:
            self.assertEqual(main(['run', 'house.bcl', *common]), 1)
            self.assertEqual(run.call_args.args[0].file, Path('house.bcl'))
        with patch('blockwire.bcl.cli.run', new_callable=AsyncMock, return_value=0):
            self.assertEqual(main(['repl', *common]), 0)
        for failure in (ConnectionError('secret credential'), TimeoutError('secret credential'),
                        RuntimeError('secret credential'), UnicodeError('secret credential')):
            with patch('blockwire.bcl.cli.run', new_callable=AsyncMock, side_effect=failure), \
                 patch('sys.stderr') as stderr:
                self.assertEqual(main(['repl', *common]), 1)
                self.assertNotIn('secret credential', str(stderr.write.call_args_list))
