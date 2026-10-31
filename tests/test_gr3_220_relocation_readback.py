"""A repaired receipt cannot conceal missing references or changed artwork."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from scripts.verify_gr3_native_target_candidate import verify,read_candidate,ROOT


@unittest.skipUnless(os.environ.get('M10V_GR3_220_CANDIDATE'),'requires a delivered 2.20 candidate folder')
class TargetReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=Path(os.environ['M10V_GR3_220_CANDIDATE'])
        cls.rtos,cls.directory=read_candidate(cls.folder)

    def test_delivered_bin_and_all_typed_regions_match_independent_instruction_decoding(self):
        verify(self.folder,ROOT/'node/gr3-220-native-target.json',self.rtos,self.directory)

    def copy(self,folder):
        for name in ('M10V-reference-runtime-arm.bin','M10V-runtime-arm.bin',
                     'M10V-reference-runtime-manifest.json','M10V-runtime-manifest.json',
                     'M10V-build-receipt.json','M10V-target-relocations.json','M10V-target-coverage.json'):
            shutil.copyfile(self.folder/name,folder/name)

    def test_missing_branch_is_rejected_even_when_trace_count_and_digest_are_repaired(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);self.copy(folder)
            refs=json.loads((folder/'M10V-target-relocations.json').read_text())
            index=next(i for i,r in enumerate(refs) if r['kind']=='branch')
            del refs[index]
            manifest=json.loads((folder/'M10V-reference-runtime-manifest.json').read_text())
            manifest['target_relocations']['count']=len(refs)
            manifest['target_relocations']['sha256']=hashlib.sha256(json.dumps(refs,separators=(',',':')).encode()).hexdigest()
            (folder/'M10V-target-relocations.json').write_text(json.dumps(refs))
            (folder/'M10V-reference-runtime-manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(AssertionError,'missing external branch'):
                verify(folder,ROOT/'node/gr3-220-native-target.json',self.rtos,self.directory)

    def test_artwork_change_is_rejected_even_when_runtime_receipts_and_bin_slice_agree(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);self.copy(folder)
            manifest=json.loads((folder/'M10V-runtime-manifest.json').read_text())
            receipt=json.loads((folder/'M10V-build-receipt.json').read_text())
            raw=bytearray((folder/'M10V-runtime-arm.bin').read_bytes())
            offset=manifest['icons']['pixels']-manifest['base']
            raw[offset]^=1
            digest=hashlib.sha256(raw).hexdigest()
            manifest['code_sha256']=digest;receipt['runtime_sha256']=digest
            receipt['native_target']['runtime_sha256']=digest
            (folder/'M10V-runtime-arm.bin').write_bytes(raw)
            (folder/'M10V-runtime-manifest.json').write_text(json.dumps(manifest))
            (folder/'M10V-build-receipt.json').write_text(json.dumps(receipt))
            rtos=bytearray(self.rtos);rtos[manifest['base']-0x53000000:]=raw
            with self.assertRaisesRegex(AssertionError,'untyped code/data/art byte modified'):
                verify(folder,ROOT/'node/gr3-220-native-target.json',rtos,self.directory)


if __name__=='__main__':unittest.main()
