"""Execute the delivered 2.20 task producer, Still Make and encoder bridge.

OS services are the same boundaries as the established 2.10 harness. Pixel
planes remain unmapped; a new CPU fallback therefore fails rather than hiding
behind image buffers or fabricated native completion bits.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
from unittest.mock import patch
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests.test_gr3_isp_base import StockISP, ROOT
from tests import test_gr3_film_pipeline_current as current_pipeline

PROFILE=json.loads((ROOT/'node/gr3-220-native-target.json').read_text())
MAP={int(a,16):int(b,16) for a,b in PROFILE['addresses'].items()}
# Independently checked instruction entry/stop pairs, not inferred from a
# public version number. These are harness boundaries, not runtime patches.
MAP.update({0x5350eb10:0x5350ec00,0x5350eb38:0x5350ec28,
            0x53501d68:0x53501e58,0x53501d6c:0x53501e5c,
            0x536dd8f0:0x536dd8c8,0x536da1fc:0x536da1d4,0x536da62c:0x536da604,
            0x536af31c:0x536af40c,0x536af358:0x536af448,
            0x536b82d4:0x536b83c4,0x5313fbb8:0x5313fc48,
            0x5383c8a8:0x5383c8b8,0x5351e888:0x5351e978,
            0x5350e624:0x5350e714,0x536abd28:0x536abe18,
            0x536decb4:0x536dec8c,0x536e4634:0x536e460c,
            0x536e4de4:0x536e4dbc,0x536e5070:0x536e5048,
            0x536e7348:0x536e7320,0x536eaf80:0x536eaf58,
            0x536ec3e0:0x536ec3b8,0x536eb0b0:0x536eb088,
            0x536e9d1c:0x536e9cf4})
REVERSE={b:a for a,b in MAP.items()}


def target(address):
    if 0x53000000<=address<0x540b5740:
        if address not in MAP:raise AssertionError(f'Unproved test entry {address:#x}')
        return MAP[address]
    return address


class TargetUc:
    def __init__(self,u):self.raw=u
    def __getattr__(self,key):return getattr(self.raw,key)
    def emu_start(self,begin,until,*args,**kwargs):
        return self.raw.emu_start(target(begin),target(until),*args,**kwargs)
    def reg_write(self,register,value):
        return self.raw.reg_write(register,MAP.get(value,value))
    def hook_add(self,kind,callback,*args,**kwargs):
        if kind==UC_HOOK_CODE:
            actual=callback
            callback=lambda u,at,n,data:actual(u,REVERSE.get(at,at),n,data)
        return self.raw.hook_add(kind,callback,*args,**kwargs)


class TargetISP(StockISP):
    def __init__(self,rom):
        super().__init__(rom)
        source,destination,length=struct.unpack_from('<III',rom,0x450)
        self.u.mem_write(destination,rom[source-0x53000000:source-0x53000000+length])
        self.u=TargetUc(self.u)
    def service(self,u,address,size,data):
        return super().service(u,REVERSE.get(address,address),size,data)
    def w32(self,address,value):
        super().w32(MAP.get(address,address),MAP.get(value,value))


@unittest.skipUnless(os.environ.get('M10V_GR3_220_CANDIDATE'),'requires a delivered 2.20 candidate folder')
class Gr3220PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=Path(os.environ['M10V_GR3_220_CANDIDATE'])
        cls.manifest=json.loads((folder/'M10V-runtime-manifest.json').read_text())
        cls.receipt=json.loads((folder/'M10V-build-receipt.json').read_text())
        binary=folder/'fwdc239b.bin'
        assert hashlib.sha256(binary.read_bytes()).hexdigest()==cls.receipt['candidate_sha256']
        script="import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
        cls.image=subprocess.check_output(['node','--input-type=module','-e',script,str(binary)],cwd=ROOT)
        raw=(folder/'M10V-runtime-arm.bin').read_bytes()
        assert cls.image[cls.manifest['base']-0x53000000:]==raw
        assert hashlib.sha256(raw).hexdigest()==cls.manifest['code_sha256']==cls.receipt['runtime_sha256']

    def test_real_220_producer_still_and_unmapped_24mp_encoder(self):
        self.assertEqual(MAP[0x5351ea9c],0x5351eb8c)
        self.assertEqual(MAP[0x536dd8f0],0x536dd8c8)
        support=current_pipeline.CurrentFilmPipelineTests()
        support.manifest=self.manifest;support.image=self.image
        for film in (34,62,66,312,318):
            for stage in (0,1):
                with self.subTest(film=film,stage=stage),patch('tests.test_gr3_film_pipeline_current.StockISP',TargetISP):
                    e,recipe,obj,frame,si,request,data=support.fixture(film,stage=stage)
                    support.publish_owner(e,data)
                    # Erase the setup snapshot: only the actual task producer
                    # can freeze this recipe before the original Still Make.
                    e.u.mem_write(recipe+0x4a08,bytes(1796))
                    support.enqueue(e,recipe,19)
                    for reg,value in ((0,obj),(1,frame),(3,0x536dd8f0),(6,recipe+0x96c)):
                        e.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(reg)),value)
                    e.u.reg_write(A.UC_ARM_REG_SP,0x5effff00)
                    e.u.reg_write(A.UC_ARM_REG_LR,0x53501d6c)
                    e.u.emu_start(0x53501d68,0x53501d6c,count=5000000)
                    self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC),0x53501e5c)
                    self.assertEqual(support.call(e,'m10v_isp_frame_recipe_completed',recipe,si,25,data),1)
                    self.assertEqual(support.capture(e,recipe,si,request),0)


if __name__=='__main__':unittest.main()
