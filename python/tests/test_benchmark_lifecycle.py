"""Simulated benchmark I/O/actor contracts; NOT graphical acceptance."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from building.reference import House
from building.live import independent_native,native_proof
from building.fixture import load,NAME
from building.evidence import write_json
from blockwire.client import BridgeError

class Native:
    def __init__(self):self.calls=0;self.replaced=False
    def observe(self):
        self.calls+=1
        return {'alive':True,'in_world':True,'on_ground':True,'health':20,'dimension':'minecraft:overworld',
                'actor_session':'old' if self.replaced and self.calls==1 else 'a'}
    def navigation(self,*,terrain=False):
        assert terrain
        h=House();cells=sorted(h.interior()|{h.entrance,h.point(2,0,-1)})
        return {'ready':True,'profile':'stepped_full_blocks_v1','actor_session':'a','dimension':'minecraft:overworld',
                'current_center_access':True,'current_cell':list(h.point(2,0,2)),'on_fire':False,'nearby_hostiles':[],
                'cells':[{'position':list(p),'hazards':[]} for p in cells],'edges':[[0,i] for i in range(1,len(cells))]}

class BenchmarkLifecycle(unittest.TestCase):
    def test_full_native_metadata_is_required_not_invented_from_compact_v0(self):
        p=Native();self.assertTrue(independent_native(p,House(),'a')['safe_player'])
        full=p.navigation(terrain=True)
        compact={k:v for k,v in full.items() if k not in {'actor_session','dimension','on_fire','nearby_hostiles'}}
        self.assertFalse(native_proof(p.observe(),compact,House(),'a')['safe_player'])
    def test_native_inspection_is_actor_bracketed(self):
        p=Native();p.replaced=True
        r=independent_native(p,House(),'a');self.assertFalse(r['safe_player']);self.assertFalse(r['interior_accessible'])
    def test_uncertain_fixture_load_requires_fresh_read_never_click_replay(self):
        class UI:
            state='TitleScreen';plays=0
            def menu(self):
                labels=['Singleplayer'] if self.state=='TitleScreen' else [NAME,'Play Selected World']
                return {'type':self.state,'screen_id':'screen','screen_open':self.state!='game',
                        'widgets':[{'label':s,'active':True,'widget_id':s} for s in labels]}
            def click_widget(self,screen,widget):
                if widget=='Singleplayer':self.state='SelectWorldScreen'
                if widget=='Play Selected World':
                    self.plays+=1;self.state='game';raise BridgeError('uncertain receipt')
            def observe(self):return {'alive':True,'on_ground':True,'actor_session':'fresh'}
        p=UI();audit=[]
        with patch('building.fixture.time.sleep'):result=load(p,audit=audit.append)
        self.assertEqual(p.plays,1);self.assertEqual(result['actor_session'],'fresh')
        self.assertEqual(len(audit),2);self.assertTrue(all(x['action_replayed'] is False for x in audit))
        self.assertEqual(audit[-1]['follow_up'],'fresh_native_actor_observed')
    def test_async_world_list_population_is_awaited_before_selection(self):
        class UI:
            state='TitleScreen';select_reads=0;plays=0;premature=False
            def menu(self):
                if self.state=='TitleScreen':widgets=[{'label':'Singleplayer','active':True,'widget_id':'Singleplayer'}]
                elif self.state=='SelectWorldScreen':
                    self.select_reads+=1
                    entries=[{'label':f'Selected {NAME}, last played: ready','active':True,'widget_id':'fixture'}] if self.select_reads>=3 else [
                        {'label':f'Selected {NAME}, last played: loading-a','active':True,'widget_id':'loading-a'},
                        {'label':f'Selected {NAME}, last played: loading-b','active':True,'widget_id':'loading-b'}]
                    widgets=[{'label':'Play Selected World','active':True,'widget_id':'Play Selected World'},*entries]
                else:widgets=[]
                return {'type':self.state,'screen_id':'screen','screen_open':self.state!='game','widgets':widgets}
            def click_widget(self,screen,widget):
                if widget=='Singleplayer':self.state='SelectWorldScreen'
                if widget.startswith('loading-'):self.premature=True
                if widget=='Play Selected World':self.plays+=1;self.state='game'
            def observe(self):return {'alive':True,'on_ground':True,'actor_session':'fresh'}
        p=UI()
        with patch('building.fixture.time.sleep'):result=load(p)
        self.assertGreaterEqual(p.select_reads,3);self.assertFalse(p.premature);self.assertEqual(p.plays,1)
        self.assertEqual(result['actor_session'],'fresh')
    def test_failed_evidence_publication_preserves_last_complete_record(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'event.json';write_json(p,{'completed':1})
            with patch('building.evidence.os.replace',side_effect=OSError(28,'disk full')):
                with self.assertRaises(OSError):write_json(p,{'completed':2})
            self.assertEqual(json.loads(p.read_text()),{'completed':1})
            self.assertEqual(len(list(Path(d).glob('*.partial'))),1)

if __name__=='__main__':unittest.main()
