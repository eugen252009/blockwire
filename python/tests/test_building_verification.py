"""Geometry acceptance fixtures, NOT real building evidence or action generation."""
import unittest
from blockwire.bcl.verification import verify_shelter

class BuildingAcceptance(unittest.TestCase):
    def fixture(self):
        expected=[]
        for x in range(3):
            for z in range(3):
                expected.append({'position':[x,66,z],'block':'minecraft:cobblestone'})
                if (x,z)!=(1,0) and (x in {0,2} or z in {0,2}):
                    for y in (64,65):expected.append({'position':[x,y,z],'block':'minecraft:cobblestone'})
        observed=[{'position':r['position'],'id':r['block']} for r in expected]
        nav={'ready':True,'profile':'stepped_full_blocks_v1','cells':[{'position':[1,64,0],'hazards':[]},{'position':[1,64,1],'hazards':[]}],'edges':[[0,1]]}
        return expected,observed,nav
    def test_BU01_complete_shell_and_native_doorway_required_not_compiler_receipt(self):
        e,o,n=self.fixture();r=verify_shelter(e,o,n)
        self.assertTrue(r['verified']);self.assertEqual((r['wall_blocks'],r['roof_blocks']),(14,9))
        self.assertFalse(verify_shelter(e,o[:-1],n)['verified'])
        self.assertFalse(verify_shelter(e,o,{**n,'edges':[]})['verified'])
        self.assertFalse(verify_shelter(e,o,{**n,'ready':False})['verified'])
    def test_BU03_natural_earth_shelter_still_requires_native_entrance_and_headroom(self):
        from blockwire.bcl.verification import verify_usable_shelter
        expected=[{'position':[0,66,0],'block':'minecraft:dirt'},{'position':[0,63,0],'block':'minecraft:stone'}]
        for x,z in [(-1,0),(1,0),(0,-1)]:
            for y in (64,65):expected.append({'position':[x,y,z],'block':'minecraft:dirt'})
        observed=[{'position':r['position'],'id':r['block']} for r in expected]
        nav={'profile':'stepped_full_blocks_v1','ready':True,'current_cell':[0,64,1],'current_center_access':True,
             'cells':[{'position':[0,64,1],'hazards':[]},{'position':[0,64,0],'hazards':[]}],'edges':[[0,1]]}
        self.assertTrue(verify_usable_shelter(expected,observed,nav)['verified'])
        self.assertFalse(verify_usable_shelter(expected,observed,{**nav,'edges':[]})['verified'])
        self.assertFalse(verify_usable_shelter(expected,observed[1:],nav)['verified'])
        broken=observed[:-1];self.assertFalse(verify_usable_shelter(expected,broken,nav)['verified'])
        self.assertFalse(verify_usable_shelter(expected[:1],broken,nav)['verified'])  # No third full side wall.
        self.assertFalse(verify_usable_shelter(expected[1:],observed,nav)['verified'])  # Incidental undeclared roof is not the model's construction.

    def test_BU02_partial_roof_wrong_block_and_blocked_entrance_are_not_success(self):
        e,o,n=self.fixture()
        self.assertFalse(verify_shelter(e[1:],o,n)['verified'])
        o[0]={**o[0],'id':'minecraft:air'};self.assertFalse(verify_shelter(e,o,n)['verified'])
        self.assertFalse(verify_shelter(e,[],n)['verified'])
