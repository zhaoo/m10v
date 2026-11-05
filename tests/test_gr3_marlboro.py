"""Real shared C kernel/default/state contracts, not camera timing evidence."""
import ctypes as C
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tests.test_gr3_universal_halation import UniversalHalationTests, State, OK, BAD


class MarlboroKernelTests(unittest.TestCase):
    setUpClass = classmethod(UniversalHalationTests.setUpClass.__func__)
    state = UniversalHalationTests.state
    scene = UniversalHalationTests.scene

    def test_defaults_and_reset_are_identical_to_800t_without_changing_other_slots(self):
        for lib in self.libs:
            states = []
            for film in (33, 327):
                s = State()
                lib.m10v_library_init(C.byref(s))
                for i in range(4, 0, -1):
                    self.assertEqual(lib.m10v_library_remove(C.byref(s), i, OK, None), 0)
                self.assertEqual(lib.m10v_library_select(C.byref(s), 0, film, OK, None), 0)
                states.append(s)
            self.assertEqual(bytes(states[0].slots[0])[2:], bytes(states[1].slots[0])[2:])
            self.assertEqual((states[1].slots[0].halo_gain, states[1].slots[0].halo_spread, states[1].slots[0].halo_threshold), (7, 7, 5))
            s = states[1]
            self.assertEqual(lib.m10v_library_halation(C.byref(s), 0, 1, 8, 0, 2, OK, None), 0)
            saved = bytes(s)
            self.assertEqual(lib.m10v_library_reset(C.byref(s), 0, BAD, None), -2)
            self.assertEqual(bytes(s), saved)
            self.assertEqual(lib.m10v_library_reset(C.byref(s), 0, OK, None), 0)
            self.assertEqual(bytes(s.slots[0])[2:], bytes(states[0].slots[0])[2:])

    def test_same_800t_kernel_is_byte_identical_for_every_slider_edge_and_padding(self):
        for lib, profile in zip(self.libs, (2, 4)):
            for gain, spread, gate in ((0, 0, 0), (1, 0, 0), (7, 7, 5), (8, 8, 8), (8, 1, 0)):
                with self.subTest(profile=profile, gain=gain, spread=spread, gate=gate):
                    a = self.state(lib, 33, profile, gain, spread, gate)
                    b = self.state(lib, 327, profile, gain, spread, gate)
                    self.assertEqual(self.scene(lib, a, randomize=True)[:3], self.scene(lib, b, randomize=True)[:3])

    def test_missing_native_color_rejects_marlboro_without_mutating_any_pixels(self):
        for lib, profile in zip(self.libs, (2, 4)):
            s = self.state(lib, 327, profile, 7, 7, 5)
            result, y, uv, before, _ = self.scene(lib, s, done=0, randomize=True)
            self.assertEqual(result, -1)
            self.assertEqual((y, uv), before)

    def test_disabled_halo_requires_no_workspace_and_no_remaining_cpu_stage(self):
        for lib, profile in zip(self.libs, (2, 4)):
            s = self.state(lib, 327, profile, 0, 7, 5)
            self.assertEqual(lib.stages(C.byref(s), 0, 1), 0)
            result, y, uv, before, _ = self.scene(lib, s, workspace=False, randomize=True)
            self.assertEqual(result, 0)
            self.assertEqual((y, uv), before)

    def test_ab_caption_uses_its_appended_resource(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'caption.c';binary=Path(d)/'caption.dylib'
            source.write_text('#include "m10v_ab.h"\nunsigned caption(void){return m10v_ab_caption(1,327);}\n')
            subprocess.run(['clang','-O2','-dynamiclib','-I',str(root/'native/gr3'),str(source),'-o',str(binary)],check=True,capture_output=True)
            self.assertEqual(C.CDLL(str(binary)).caption(),1202)

    def test_native_sd_accepts_old_and_new_records_and_rejects_repaired_edits(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            binary=Path(d)/'sd.dylib'
            subprocess.run(['clang','-O2','-dynamiclib',str(root/'native/gr3/m10v_sd_library.c'),'-o',str(binary)],check=True,capture_output=True)
            lib=C.CDLL(str(binary));lib.m10v_sd_record.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32]
            js="""import{readFileSync}from'node:fs';import{sdFilmRecord,sdCrc}from'./node/gr3-sd-film-pack.mjs';
const old=JSON.parse(readFileSync('node/gr3-sd-pre-marlboro-contract.json'));
const records=old.ids.map(id=>{const r=sdFilmRecord(id);Buffer.from(old.renderer,'hex').copy(r,8448);r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);return r;});
process.stdout.write(Buffer.concat([...records,sdFilmRecord(327)]));"""
            records=subprocess.check_output(['node','--input-type=module','-e',js],cwd=root)
            ids=json.loads((root/'node/gr3-sd-pre-marlboro-contract.json').read_text())['ids']+[327]
            for i,film in enumerate(ids):
                r=records[i*12288:(i+1)*12288]
                self.assertEqual(lib.m10v_sd_record(r,len(r),film),film)
            damaged=bytearray(records[-12288:]);damaged[100]^=1
            import struct,zlib
            struct.pack_into('<I',damaged,12284,zlib.crc32(damaged[:-4]))
            self.assertEqual(lib.m10v_sd_record(bytes(damaged),len(damaged),327),0)


if __name__ == '__main__':
    unittest.main()
