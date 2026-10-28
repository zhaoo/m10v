"""Scalar border shot ownership; this does not substitute real ingress tests."""
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.build_gr3_m10v_library import FLAGS, link_object
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parents[1]


class BorderShotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.tmp.cleanup)
        obj = Path(cls.tmp.name) / 'shot.o'
        subprocess.run(['clang', *FLAGS, '-c', str(ROOT/'native/gr3/m10v_border_shot.c'),
                        '-o', str(obj)], check=True, capture_output=True)
        # Explicit isolated exports; does not alter the production strict registry.
        cls.code, cls.syms = link_object(obj.read_bytes(), 0x54160000,
            {'m10v_border_camera_snapshot': 0x53000100}, 'm10v_zoom_',
            additional_exports=('m10v_border_shot_freeze', 'm10v_border_shot_read', 'm10v_border_shot_orientation',
                                'm10v_border_shot_phase','m10v_border_shot_transition'))

    def setUp(self):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.mem_map(0x53000000, 0x1500000); self.u.mem_write(0x54160000, self.code)
        self.u.mem_map(0x55000000, 0x100000)
        self.recipe = 0x55010000; self.style = 1; self.available = True; self.calls = 0
        self.put(self.recipe, 0x53d0fc90)
        self.put(self.recipe+0x4778, 0x31545653)
        self.si=0x55030000;self.put(self.recipe+0x44c8,self.si)
        self.u.mem_write(self.recipe+0x5110, b'\xa5'*48)
        self.raw = bytes(self.u.mem_read(self.recipe+0x5110, 48))
        def hook(u, pc, size, data):
            if pc == 0x53000100:
                self.calls += 1
                if self.available: self.put(u.reg_read(A.UC_ARM_REG_R0), self.style)
                u.reg_write(A.UC_ARM_REG_R0, int(self.available)); u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
            elif pc in (0x53828014,0x53825648,0x53825fa8,0x536af2a8,0x536a9e8c):
                self.fail('capture freeze performed filesystem/allocation/wait work')
        self.u.hook_add(UC_HOOK_CODE, hook)

    def put(self, p, v): self.u.mem_write(p, struct.pack('<I', v))
    def get(self, p): return struct.unpack('<I', self.u.mem_read(p, 4))[0]
    def call(self, name, *args):
        for i in range(4): self.u.reg_write(getattr(A,f'UC_ARM_REG_R{i}'),args[i] if i<len(args) else 0)
        self.u.reg_write(A.UC_ARM_REG_SP,0x550ff000); self.u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
        self.u.emu_start(self.syms[name],0x550ff800,count=100000)
        self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff800)
        self.assertEqual(bytes(self.u.mem_read(self.recipe+0x5110,48)),self.raw)
        return self.u.reg_read(A.UC_ARM_REG_R0)

    def test_freeze_once_preserves_queued_style_across_menu_changes(self):
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),1)
        self.style=2
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),1)
        out=0x55009000; self.put(out,99)
        self.assertEqual(self.call('m10v_border_shot_read',self.recipe,out),1)
        self.assertEqual(self.get(out),1); self.assertEqual(self.calls,1)

    def test_unavailable_is_frozen_as_error_and_never_replaced_by_later_ui(self):
        self.available=False
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),0)
        self.available=True;self.style=2
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),0)
        out=0x55009000;self.put(out,99)
        self.assertEqual(self.call('m10v_border_shot_read',self.recipe,out),0)
        self.assertEqual(self.get(out),99);self.assertEqual(self.calls,1)

    def test_off_and_two_recipes_have_independent_valid_snapshots(self):
        self.style=0;self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),1)
        other=0x55020000;self.put(other,0x53d0fc90);self.put(other+0x4778,0x31545653)
        self.put(other+0x44c8,self.si)
        self.style=2;self.assertEqual(self.call('m10v_border_shot_freeze',other),1)
        for recipe,expected in ((self.recipe,0),(other,2)):
            self.assertEqual(self.call('m10v_border_shot_read',recipe,0x55009000),1)
            self.assertEqual(self.get(0x55009000),expected)

    def test_wrong_owner_rejects_without_writes_or_cache_read(self):
        self.put(self.recipe,0)
        before=bytes(self.u.mem_read(self.recipe,0x5140))
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),0)
        self.assertEqual(bytes(self.u.mem_read(self.recipe,0x5140)),before)
        self.assertEqual(self.calls,0)

    def test_saved_si_orientation_is_frozen_with_style_and_override(self):
        for internal,expected in ((0,1),(1,8),(2,3),(3,6),(4,1)):
            self.put(self.recipe+0x510c,0)
            self.u.mem_write(self.si+0xc8,bytes([internal]))
            self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),1)
            self.u.mem_write(self.si+0xc8,b'\x02')
            self.assertEqual(self.call('m10v_border_shot_orientation',self.recipe,0x55009000),1)
            self.assertEqual(self.get(0x55009000),expected)
        self.put(self.recipe+0x510c,0);self.u.mem_write(self.si+0x71e03,b'\x01\x03')
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),1)
        self.assertEqual(self.call('m10v_border_shot_orientation',self.recipe,0x55009000),1)
        self.assertEqual(self.get(0x55009000),6)

    def test_on_requires_saved_si_but_off_does_not_dereference_it(self):
        self.put(self.recipe+0x44c8,0);self.put(0x55009000,99)
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),0)
        self.assertEqual(self.call('m10v_border_shot_orientation',self.recipe,0x55009000),0)
        self.assertEqual(self.get(0x55009000),99)
        self.put(self.recipe+0x510c,0);self.style=0
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),1)

    def test_once_only_stage_transitions_preserve_frozen_style_and_orientation(self):
        self.u.mem_write(self.si+0xc8,b'\x03')
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),1)
        self.assertEqual(self.call('m10v_border_shot_phase',self.recipe),0)
        self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,0,3),0)
        for old,new in ((0,1),(1,2),(2,3)):
            self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,old,new),1)
            self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,old,new),0)
            self.assertEqual(self.call('m10v_border_shot_phase',self.recipe),new)
            self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),1)
            self.call('m10v_border_shot_read',self.recipe,0x55009000);self.assertEqual(self.get(0x55009000),1)
            self.call('m10v_border_shot_orientation',self.recipe,0x55009000);self.assertEqual(self.get(0x55009000),6)
        self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,3,0),0)

    def test_off_invalid_and_failed_stages_cannot_reenter_processing(self):
        self.assertEqual(self.call('m10v_border_shot_phase',self.recipe),255)
        self.style=0;self.call('m10v_border_shot_freeze',self.recipe)
        self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,0,1),0)
        for failed_from,failed_to in ((1,5),(2,4)):
            self.put(self.recipe+0x510c,0);self.style=2;self.call('m10v_border_shot_freeze',self.recipe)
            self.call('m10v_border_shot_transition',self.recipe,0,1)
            if failed_from==2:self.call('m10v_border_shot_transition',self.recipe,1,2)
            self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,failed_from,failed_to),1)
            self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,failed_to,0),0)

    def test_prepared_is_separate_from_completion_and_survives_later_producers(self):
        self.call('m10v_border_shot_freeze',self.recipe)
        self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,0,6),1)
        self.assertEqual(self.call('m10v_border_shot_phase',self.recipe),6)
        self.assertEqual(self.call('m10v_border_shot_freeze',self.recipe),1)
        self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,6,3),0)
        self.assertEqual(self.call('m10v_border_shot_transition',self.recipe,6,1),1)


if __name__=='__main__': unittest.main()
