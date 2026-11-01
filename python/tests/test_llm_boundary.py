"""Local model handoff/network-shape contracts; no external inference request."""
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from blockwire.llm import OpenAIJSONDecider, strict_json, _NoRedirect
from blockwire.mailbox import MailboxDecider


class LLMBoundaryContracts(unittest.TestCase):
    def handoff(self, response):
        with tempfile.TemporaryDirectory() as folder:
            box = Path(folder)/'mailbox'
            model = MailboxDecider(box, timeout=.8)
            result = []
            def run():
                try: result.append(model.decide({'goal':'fixture','observation':{}}))
                except Exception as exc: result.append(exc)
            t = threading.Thread(target=run);t.start()
            end = time.monotonic()+.5
            while not list(box.glob('request-*.json')) and time.monotonic()<end: time.sleep(.01)
            request = json.loads(next(box.glob('request-*.json')).read_text())
            (box/request['reply_file']).write_text(json.dumps(response(request)))
            t.join(1)
            self.assertFalse(t.is_alive())
            self.assertEqual(box.stat().st_mode & 0o077, 0)
            return result[0], request

    def test_LB01_nonce_bound_json_handoff_without_executable_code(self):
        result, request = self.handoff(lambda r:{'request_id':r['request_id'],'decision':{'kind':'finish'}})
        self.assertEqual(result,{'kind':'finish'})
        self.assertIn('ONE next action',request['system'])
        self.assertNotIn('api_key',request)

    def test_LB02_old_or_unmatched_reply_cannot_be_replayed(self):
        result, _ = self.handoff(lambda r:{'request_id':'old','decision':{'kind':'act','skill':'command'}})
        self.assertIsInstance(result,ValueError)

    def test_LB03_ambiguous_or_nonfinite_model_json_is_rejected(self):
        for text in ['{"kind":"finish","kind":"act"}', '{"parameters":{"n":NaN}}', '{"x":Infinity}']:
            with self.assertRaises(ValueError): strict_json(text)

    def test_LB04_http_adapter_bounds_payload_uses_schema_prompt_and_no_redirects(self):
        response = {'choices':[{'message':{'content':'{"kind":"finish"}'}}]}
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        class Opener:
            def open(_, request, timeout):
                payload=json.loads(request.data)
                self.assertEqual(payload['messages'][0]['role'],'system')
                self.assertIn('untrusted',payload['messages'][0]['content'])
                self.assertEqual(request.headers['Authorization'],'Bearer fixture-secret')
                self.assertEqual(timeout,2.)
                return Response(json.dumps(response).encode())
        with patch('blockwire.llm.build_opener',return_value=Opener()) as factory:
            result=OpenAIJSONDecider('http://127.0.0.1:11434/v1/chat/completions','fixture',api_key='fixture-secret',timeout=2.).decide({'observation':{}})
            self.assertEqual(result,{'kind':'finish'})
            self.assertTrue(any(isinstance(arg,_NoRedirect) for arg in factory.call_args.args))

    def test_LB05_offline_catalogue_does_not_connect_or_load_environment_providers(self):
        from blockwire.agent_cli import main
        with patch('blockwire.agent_cli.Bridge.from_env',side_effect=AssertionError('No bridge')), patch('sys.stdout'):
            self.assertEqual(main(['--describe']),0)


if __name__=='__main__':unittest.main()
