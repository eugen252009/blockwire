"""Benchmark-only process/display authority; no graphical success is simulated."""
from dataclasses import replace
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from building.display_guard import ProcessProof,inspect_process,require_hidden_game,require_no_foreign_launcher


class BenchmarkDisplayGuard(unittest.TestCase):
    def proof(self,**changes):
        base=ProcessProof(123,os.getuid(),'42',Path('/owned/game'),':99',('java','org.prismlauncher.EntryPoint'))
        return replace(base,**changes)

    def test_DG01_actual_child_not_launcher_display_is_required(self):
        accepted=self.proof();self.assertIs(require_hidden_game(accepted,Path('/owned/game')),accepted)
        for value in (':0',None,':98'):
            with self.subTest(display=value),self.assertRaises(RuntimeError):
                require_hidden_game(self.proof(display=value),Path('/owned/game'))
        with self.assertRaises(ValueError):require_hidden_game(accepted,Path('/owned/game'),display=':0')

    def test_DG02_identity_and_exact_instance_are_required(self):
        for change in ({'uid':os.getuid()+1},{'cwd':Path('/unrelated/game')},{'argv':('java','other.Main')}):
            with self.subTest(change=change),self.assertRaises(RuntimeError):
                require_hidden_game(self.proof(**change),Path('/owned/game'))

    def test_DG03_foreign_launcher_is_rejected_without_killing_it(self):
        launcher=self.proof(cwd=Path('/launcher'),display=':0',argv=('/app/bin/prismlauncher',))
        with patch('os.kill') as killed:
            with self.assertRaises(RuntimeError):require_no_foreign_launcher([launcher],Path('/launcher'))
            killed.assert_not_called()
        with self.assertRaises(RuntimeError):
            require_no_foreign_launcher([replace(launcher,argv=('/app/bin/prismrun',))],Path('/launcher'))
        require_no_foreign_launcher([replace(launcher,display=':99')],Path('/launcher'))
        require_no_foreign_launcher([replace(launcher,cwd=Path('/another/home'))],Path('/launcher'))

    def test_DG04_unreadable_or_vanished_process_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):inspect_process(123,proc_root=Path(d))
        for value in (True,0,-1,'123'):
            with self.assertRaises(ValueError):inspect_process(value)

    def test_DG05_only_required_environment_field_is_exposed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'123';p.mkdir();game=Path(d)/'game';game.mkdir();(p/'cwd').symlink_to(game)
            (p/'stat').write_text('123 (game process) '+' '.join(['S']+['0']*18+['42'])+'\n')
            (p/'cmdline').write_bytes(b'java\0org.prismlauncher.EntryPoint\0')
            (p/'environ').write_bytes(b'DISPLAY=:99\0SECRET=not-for-evidence\0')
            proof=inspect_process(123,proc_root=Path(d));self.assertEqual(proof.display,':99');self.assertEqual(proof.start_time,'42')
            self.assertNotIn('SECRET',repr(proof));require_hidden_game(proof,game)
            (p/'environ').write_bytes(b'DISPLAY=:99\0DISPLAY=:0\0')
            with self.assertRaises(RuntimeError):inspect_process(123,proc_root=Path(d))

if __name__=='__main__':unittest.main()
