"""Trusted model-command boundary tests; no provider/network/Minecraft requests."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from blockwire.command_decider import CommandJSONDecider


class CommandDeciderContracts(unittest.TestCase):
    def test_CD01_explicit_no_shell_json_and_native_env_scrubbing(self):
        program="import os,json,sys;d=json.load(sys.stdin);print(json.dumps({'kind':'finish','reason':str('BLOCKWIRE_CONFIG' in os.environ)}))"
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'BLOCKWIRE_CONFIG':'private-native-path'}):
            model=CommandJSONDecider([sys.executable,'-c',program,';not-a-shell-command'],audit_directory=Path(directory)/'audit')
            answer=model.decide({'goal':'fixture'})
            self.assertEqual(answer,{'kind':'finish','reason':'False'})
            self.assertEqual((Path(directory)/'audit/001-request.json').stat().st_mode & 0o077,0)
    def test_CD02_duplicate_and_oversized_output_are_rejected(self):
        for program in ['print(\'{"kind":"finish","kind":"act"}\')','import json;s=json.dumps({"kind":"finish"});print(s+" "*(16385-len(s)),end="")']:
            with self.assertRaises(ValueError):CommandJSONDecider([sys.executable,'-c',program]).decide({})
    def test_CD03_timeout_nonzero_exit_and_invalid_operator_config_fail_closed(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            CommandJSONDecider([sys.executable,'-c','import time;time.sleep(1)'],timeout=.1).decide({})
        with self.assertRaises(RuntimeError):CommandJSONDecider([sys.executable,'-c','raise SystemExit(2)']).decide({})
        for argv in ['pi --print',[],[''],['a\0b']]:
            with self.assertRaises(ValueError):CommandJSONDecider(argv)


if __name__=='__main__':unittest.main()
