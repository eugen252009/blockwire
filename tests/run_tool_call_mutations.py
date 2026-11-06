#!/usr/bin/env python3
"""Isolated tool-boundary mutations. No models, credentials or game clients."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('strict_arguments', 'tool_decider.py', 'self.registry.prepare(name, arguments)', 'pass # validation removed', 'test_invalid_calls_never_dispatch'),
    ('single_call', 'tool_decider.py', 'len(calls) != 1', 'len(calls) < 1', 'test_refusal_truncation_and_parallel_calls_fail_closed'),
    ('refusal', 'tool_decider.py', "if message.get('refusal'):", 'if False:', 'test_refusal_truncation_and_parallel_calls_fail_closed'),
    ('complete_reply', 'tool_decider.py', "choices[0].get('finish_reason') != 'tool_calls'", 'False', 'test_refusal_truncation_and_parallel_calls_fail_closed'),
    ('tool_choice', 'tool_decider.py', "'tool_choice': 'required'", "'tool_choice': 'auto'", 'test_named_call_and_schema_no_bcl_or_text_json'),
    ('parallel', 'tool_decider.py', "'parallel_tool_calls': False", "'parallel_tool_calls': True", 'test_named_call_and_schema_no_bcl_or_text_json'),
]


def main():
    failures = []
    for name, filename, before, after, test in CASES:
        with tempfile.TemporaryDirectory(prefix='blockwire-tool-mutation-') as directory:
            path = Path(directory)
            shutil.copytree(ROOT/'python/src', path/'src')
            file = path/'src/blockwire'/filename
            source = file.read_text()
            assert source.count(before) == 1, name
            mutated = source.replace(before, after)
            compile(mutated, str(file), 'exec')  # Invalid setup is not a killed mutation.
            file.write_text(mutated)
            env = {**os.environ, 'PYTHONPATH': str(path/'src')+os.pathsep+str(ROOT/'python/tests')}
            result = subprocess.run([sys.executable, '-m', 'unittest',
                'test_tool_decider.Tools.'+test], cwd=directory, env=env,
                capture_output=True, text=True, timeout=30)
            killed = result.returncode != 0 and ('FAIL: '+test) in result.stderr
            print(name, 'KILLED' if killed else 'NOT_KILLED', flush=True)
            if not killed:
                failures.append(name)
                print(result.stdout+result.stderr)
    return bool(failures)


if __name__ == '__main__': sys.exit(main())
