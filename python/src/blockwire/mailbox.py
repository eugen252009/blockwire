"""Private bounded JSON handoff for an external LLM host (not a script planner).

The external host reads a request and returns ONE typed decision with its nonce.
No Python code, bridge credentials, stale reply replay or strategic rules here.
"""
import json
import os
from pathlib import Path
import time
from uuid import uuid4
from .llm import SYSTEM, strict_json


class MailboxDecider:
    def __init__(self, directory, *, timeout=60.):
        if not .1 <= timeout <= 180: raise ValueError('Bounded decision timeout required')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.directory.is_symlink() or self.directory.stat().st_mode & 0o077:
            raise ValueError('Mailbox must be a private non-symlink directory')
        self.timeout = timeout

    def decide(self, context):
        identifier = uuid4().hex
        request = {'request_id': identifier, 'system': SYSTEM, 'context': context,
                   'reply_file': 'reply-'+identifier+'.json', 'timeout_seconds': self.timeout}
        data = json.dumps(request, allow_nan=False).encode()
        if len(data) > 128*1024: raise ValueError('Mailbox context bound exceeded')
        path = self.directory/('request-'+identifier+'.json')
        temporary = path.with_name('.'+path.name+'.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb') as out: out.write(data)
            os.link(temporary, path, follow_symlinks=False)  # Atomic publication, never replace an existing nonce.
        finally:
            temporary.unlink(missing_ok=True)
        reply = self.directory/request['reply_file']
        deadline = time.monotonic()+self.timeout
        while time.monotonic() < deadline:
            if reply.exists():
                fd = os.open(reply, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as source: body = source.read(16385)
                if len(body) > 16384: raise ValueError('Decision reply bound exceeded')
                result = strict_json(body)
                if set(result) != {'request_id', 'decision'} or result['request_id'] != identifier:
                    raise ValueError('Wrong/stale model decision nonce')
                return result['decision']
            time.sleep(.05)
        raise TimeoutError('External model decision timed out')
