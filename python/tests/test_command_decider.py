"""Trusted model-command boundary tests; no provider/network/Minecraft requests."""
import json
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
    def test_CD04_private_audit_retains_bounded_nonzero_exit_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            audit=Path(directory)/'audit';model=CommandJSONDecider([sys.executable,'-c','raise SystemExit(7)'],audit_directory=audit)
            with self.assertRaisesRegex(RuntimeError,'model_command_failed'):model.decide({})
            self.assertTrue((audit/'001-failure.json').exists())
            self.assertEqual(json.loads((audit/'001-failure.json').read_text()),{'kind':'nonzero_exit','returncode':7})
            self.assertFalse((audit/'001-reply.json').exists())
    def test_CD05_private_audit_retains_malformed_bounded_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            audit=Path(directory)/'audit';model=CommandJSONDecider([sys.executable,'-c',"print('{not json')"],audit_directory=audit)
            with self.assertRaises(ValueError):model.decide({})
            self.assertTrue((audit/'001-reply.json').exists())
            self.assertEqual((audit/'001-reply.json').read_bytes(),b'{not json\n')


if __name__=='__main__':unittest.main()
