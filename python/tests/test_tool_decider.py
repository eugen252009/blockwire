"""Tool-shaped model boundary contracts; no paid model or Minecraft connection."""
import io
import json
import unittest
from unittest.mock import patch
from blockwire.skills import default_registry
from blockwire.tool_decider import OpenAIToolDecider


def reply(name='gather_wood', arguments='{"count":1}'):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
        {'id': 'call_fixture', 'type': 'function', 'function': {'name': name, 'arguments': arguments}}]}}]}


class Tools(unittest.TestCase):
    def model(self):
        return OpenAIToolDecider('http://127.0.0.1:11434/v1/chat/completions', 'fixture',
            registry=default_registry(), allowed_skills={'gather_wood', 'walk_to'})

    def decide(self, value):
        model = self.model()
        with patch.object(model, '_request', return_value=value) as request:
            result = model.decide({'goal': 'fixture', 'skills': [{'name': 'run_command'}]})
            return result, request.call_args.args[0]

    def test_named_call_and_schema_no_bcl_or_text_json(self):
        decision, payload = self.decide(reply())
        self.assertEqual(decision, {'kind': 'act', 'skill': 'gather_wood', 'parameters': {'count': 1}})
        self.assertFalse(payload['parallel_tool_calls'])
        self.assertEqual(payload['tool_choice'], 'required')
        self.assertNotIn('response_format', payload)
        tools = {t['function']['name']: t['function'] for t in payload['tools']}
        schema = next(d['parameters'] for d in default_registry().describe() if d['name'] == 'gather_wood')
        self.assertEqual(tools['gather_wood']['parameters'], schema)
        self.assertNotIn('run_command', tools)

    def test_invalid_calls_never_dispatch(self):
        for name, args in [('run_command', '{}'), ('gather_wood', '{"count":"1"}'),
                           ('gather_wood', '{"count":true}'), ('gather_wood', '{"count":999}'),
                           ('gather_wood', '{"count":1,"extra":2}'),
                           ('gather_wood', '{"count":1,"count":2}'),
                           ('gather_wood', '[]'), ('gather_wood', '{"count":NaN}'),
                           ('finish_session', '{"success":true}'),
                           ('wait_for_observation', '{"seconds":99}')]:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                self.decide(reply(name, args))

    def test_refusal_truncation_and_parallel_calls_fail_closed(self):
        for reason in ['length', 'content_filter', 'stop']:
            value = reply(); value['choices'][0]['finish_reason'] = reason
            with self.assertRaises(RuntimeError): self.decide(value)
        value = reply(); value['choices'][0]['message']['refusal'] = 'refused'
        with self.assertRaises(RuntimeError): self.decide(value)
        value = reply(); value['choices'][0]['message']['tool_calls'] *= 2
        with self.assertRaises(ValueError): self.decide(value)

    def test_out_of_band_controls_require_explicit_host_opt_in(self):
        with self.assertRaises(ValueError):self.decide(reply('interrupt','{}'))
        model=OpenAIToolDecider('http://127.0.0.1:11434/v1/chat/completions','fixture',
            registry=default_registry(),allowed_skills={'gather_wood'},control_tools=True)
        with patch.object(model,'_request',return_value=reply('interrupt','{}')):
            self.assertEqual(model.decide({}),{'kind':'control','control':'interrupt'})
        with patch.object(model,'_request',return_value=reply('resume','{"arbitrary":true}')):
            with self.assertRaises(ValueError):model.decide({})

    def test_finish_is_not_success_and_wait_is_bounded(self):
        self.assertEqual(self.decide(reply('finish_session', '{}'))[0], {'kind': 'finish'})
        self.assertEqual(self.decide(reply('wait_for_observation', '{"seconds":0.2}'))[0]['kind'], 'wait')

    def test_existing_runtime_executes_once_and_returns_evidence_to_next_call(self):
        import tempfile
        from pathlib import Path
        from blockwire import Player, CallableBackend
        from blockwire.agent import AgentRuntime, SessionStore
        from test_agent import Native, registry
        native = Native()
        model = OpenAIToolDecider('http://127.0.0.1:11434/v1/chat/completions', 'fixture',
            registry=registry(), allowed_skills={'effect'})
        with tempfile.TemporaryDirectory() as folder, patch.object(model, '_request',
                side_effect=[reply('effect', '{}'), reply('finish_session', '{}')]) as request:
            runtime = AgentRuntime(Player(CallableBackend(native.call)), model,
                SessionStore(Path(folder)/'state.sqlite',
                    {'agent_id': 'a', 'world_id': 'w', 'player_id': 'player-a'}), 'fixture',
                registry=registry(), allowed_skills={'effect'})
            result = runtime.run()
            self.assertEqual(result['reason'], 'planner_finished_unverified')
            self.assertFalse(result['objective_verified'])
            self.assertEqual(sum(q['op'] == 'action' for q in native.calls), 1)
            context = json.loads(request.call_args_list[1].args[0]['messages'][1]['content'])
            self.assertEqual(context['history'][-1]['reason'], 'fixture_verified')
            self.assertEqual(context['observation']['inventory']['minecraft:wooden_pickaxe'], 1)

    def test_machine_search_is_typed_perception_not_composition(self):
        from blockwire.machine_actions import action_registry
        from pydantic import ValidationError
        registry=action_registry()
        model=OpenAIToolDecider('http://127.0.0.1/unused','fixture',registry=registry,
            allowed_skills=set(registry._definitions),control_tools=True,composition_tools=True)
        with patch.object(model,'_request',return_value=reply('search','{"target":"logs","range":32}')):
            decision=model.decide({})
        self.assertEqual(decision['kind'],'perception');self.assertEqual(decision['parameters']['range'],32)
        with patch.object(model,'_request',return_value=reply('search','{"range":true}')):
            with self.assertRaises(ValidationError):model.decide({})
        with patch.object(model,'_request',return_value=reply('compose','{"actions":[{"name":"search","parameters":{}}]}')):
            with self.assertRaises(ValidationError):model.decide({})
        with patch.object(model,'_request',return_value=reply('look_around','{}')):
            self.assertEqual(model.decide({})['kind'],'perception')

    def test_machine_goal_is_preserved_and_stop_requires_a_reason(self):
        from blockwire.machine_actions import action_registry
        registry=action_registry()
        model=OpenAIToolDecider('http://127.0.0.1/unused','fixture',registry=registry,
            allowed_skills=set(registry._definitions),control_tools=True,composition_tools=True)
        with patch.object(model,'_request',return_value=reply('finish_session','{"reason":"Blocked by observed terrain; objective not met"}')) as request:
            decision=model.decide({'goal':'Collect 64 logs'})
        self.assertEqual(decision['kind'],'finish');self.assertIn('objective not met',decision['reason'])
        payload=request.call_args.args[0]
        self.assertIn("operator's requested objective",payload['messages'][0]['content'])
        stop=next(t['function']for t in payload['tools']if t['function']['name']=='finish_session')
        self.assertEqual(stop['parameters']['required'],['reason'])
        with patch.object(model,'_request',return_value=reply('finish_session','{}')):
            with self.assertRaises(ValueError):model.decide({})

    def test_actual_http_shape_and_no_retry(self):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        with patch('blockwire.llm.build_opener') as factory:
            factory.return_value.open.return_value = Response(json.dumps(reply()).encode())
            self.model().decide({})
            payload = json.loads(factory.return_value.open.call_args.args[0].data)
            self.assertEqual(payload['tools'][0]['type'], 'function')
            self.assertEqual(factory.return_value.open.call_count, 1)
        with patch('blockwire.llm.build_opener') as factory:
            factory.return_value.open.side_effect = TimeoutError('unknown')
            with self.assertRaises(TimeoutError): self.model().decide({})
            self.assertEqual(factory.return_value.open.call_count, 1)


if __name__ == '__main__': unittest.main()
