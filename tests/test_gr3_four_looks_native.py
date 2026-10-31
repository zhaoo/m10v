"""Four-look model gates and persistent-state boundaries; no ISP hardware claim."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import build, ROOT
from tests.test_gr3_isp_base import StockISP


def state_bytes(films):
    state=bytearray(184)
    struct.pack_into('<IHHI',state,0,0x5630314d,5,184,42)
    for i,film in enumerate(films):
        struct.pack_into('<H6B',state,12+i*8,film,0,0,0,3,5,2)
        state[96+i*8]=i%3
    struct.pack_into('<I',state,180,zlib.crc32(state[:180]))
    return state


class FourLooksNativeBoundaryTests(unittest.TestCase):
    def test_initial_four_looks_require_verified_model_and_owned_pipeline(self):
        state=state_bytes([318])
        struct.pack_into('<I',state,8,0)
        struct.pack_into('<I',state,180,zlib.crc32(state[:180]))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'ISP still ownership'):
                build(d,initial_state_hex=state.hex())
            with self.assertRaisesRegex(ValueError,'verified GR III'):
                build(d,initial_state_hex=state.hex(),camera_model='gr3x',
                      native_color=True,native_grain=True,recipe_snapshot=True,lifecycle_trace=True)

    def test_unverified_model_rejects_native_profile_and_compacts_imported_journal_without_writes(self):
        with tempfile.TemporaryDirectory() as d:
            manifest=build(d,camera_model='gr3x',sd_library=True,native_color=True,
                native_grain=True,recipe_snapshot=True,lifecycle_trace=True,live_color=False)
            code=(Path(d)/'m10v-library-arm.bin').read_bytes()
        # Execute the model-gated ARM code against its source GR III anchors.
        # This proves rejection, and does not claim a verified IIIx ISP path.
        rom=bytearray((ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes())
        offset=manifest['base']-0x53000000
        rom.extend(bytes(max(0,offset+len(code)-len(rom))))
        rom[offset:offset+len(code)]=code
        e=StockISP(rom)
        def call(name,*args):
            e.call(manifest['symbols'][name],*args)
            return e.u.reg_read(A.UC_ARM_REG_R0)
        native=e.alloc(1600)
        for film in range(318,322):
            self.assertEqual(call('m10v_isp_native_look_prepare',native,film,0,42),0)
            self.assertEqual(call('m10v_camera_library_select',0,0,film),0xffffffff)
        saved=state_bytes([34,318,66,319,321])
        out=e.alloc(184);manager=e.alloc(12);app=e.alloc(4);fs=e.alloc(0x24)
        e.w32(manager+8,app);e.w32(app,fs);e.u.mem_write(fs+0x20,b'\1')
        e.w32(0x55063910,0)
        reads=[]
        def storage(u,at,n,d):
            if at==0x53828014:u.reg_write(A.UC_ARM_REG_R0,manager)
            elif at==0x53825648:
                self.assertEqual(u.reg_read(A.UC_ARM_REG_R2),184)
                reads.append(at);u.mem_write(u.reg_read(A.UC_ARM_REG_R3),bytes(saved))
                u.reg_write(A.UC_ARM_REG_R0,1)
            elif at in (0x538258d0,0x53825a70):
                raise AssertionError('reading an imported journal must not write storage')
            else:return
            u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
        hook=e.u.hook_add(UC_HOOK_CODE,storage)
        try:self.assertEqual(call('m10v_camera_library_load',out),0)
        finally:e.u.hook_del(hook)
        self.assertEqual(len(reads),2)
        actual=bytes(e.u.mem_read(out,184))
        self.assertEqual([struct.unpack_from('<H',actual,12+i*8)[0] for i in range(10)],[34,66]+[0]*8)
        self.assertEqual(actual[12:20],saved[12:20])
        self.assertEqual(actual[20:28],saved[28:36])
        self.assertEqual(actual[96:104],saved[96:104])
        self.assertEqual(actual[104:112],saved[112:120])
        self.assertEqual(struct.unpack_from('<I',actual,8)[0],42)
        self.assertEqual(call('m10v_library_valid',out),1)


if __name__=='__main__':unittest.main()
