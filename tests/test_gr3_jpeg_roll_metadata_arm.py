"""Exercise all real GR III MakerNote constructor variants with generated hooks."""
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest

from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_film_slot_extension import build_appended_slots
from tests.test_gr3_isp_base import ROOT, StockISP


class JpegRollMetadataArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidate = os.environ.get('M10V_ROLL_DEVICE_CANDIDATE')
        if not candidate:
            raise unittest.SkipTest('requires an explicitly selected roll/live candidate')
        directory = Path(candidate)
        cls.manifest = json.loads((directory/'M10V-runtime-manifest.json').read_text())
        original = "import{readFileSync}from'node:fs';import{officialResources}from'./node/gr3-stock-presets.mjs';const{decoded:d,sections:s}=officialResources(readFileSync('bin/fwdc239b-gr3-official.bin'));process.stdout.write(d.subarray(s.RTOS.offset,s.RTOS.offset+s.RTOS.size));"
        cls.stock = subprocess.check_output(['node','--input-type=module','-e',original],cwd=ROOT)
        decode = "import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
        image = bytearray(subprocess.check_output(['node','--input-type=module','-e',decode,str(directory/'fwdc239b.bin')],cwd=ROOT))
        # This test regenerates only the metadata/tone hook module against the
        # audited original preimages; it does not export or relabel firmware.
        base = 0x54400000
        code,report = build_appended_slots(base,cls.manifest['base'],cls.stock,cls.manifest['symbols'])
        image[base-0x53000000:base-0x53000000+len(code)] = code
        for patch in report['patches']:
            struct.pack_into('<I',image,patch['address']-0x53000000,patch['replacement'])
        cls.image = bytes(image)

    def test_camera_jpeg_86_tag_constructor_gets_enabled_metadata_slots(self):
        self.check_constructor(0x53601a50,86,0x538f1034,True)

    def test_previous_jpeg_and_dng_variants_remain_extended(self):
        self.check_constructor(0x536094e4,88,0x538f1180,True)
        self.check_constructor(0x535f9b54,91,0x538f0f38,False)

    def test_camera_jpeg_constructor_preimage_is_checked(self):
        changed=bytearray(self.stock)
        struct.pack_into('<I',changed,0x53601ad0-0x53000000,0)
        with self.assertRaisesRegex(ValueError,'0x53601ad0'):
            build_appended_slots(0x54400000,self.manifest['base'],changed,self.manifest['symbols'])

    def check_constructor(self,constructor,count,table,jpeg):
        e=StockISP(self.image)
        service,methods,creator,creator_methods=[e.alloc(n) for n in (4,24,4,24)]
        e.w32(0x5536c7c8,service);e.w32(service,methods);e.w32(methods+8,0x5e000010)
        e.w32(creator,creator_methods);e.w32(creator_methods+0x10,0x5e000014)
        def resource(u,at,_size,_context):
            if at==0x535d0d6c: result=creator
            elif at==0x5e000010: result=e.alloc(u.reg_read(A.UC_ARM_REG_R1))
            elif at==0x5e000014:
                result=e.alloc(24)
                u.mem_write(result+4,struct.pack('<H',u.reg_read(A.UC_ARM_REG_R1)))
            else: return
            u.reg_write(A.UC_ARM_REG_R0,result)
            u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE,resource)
        writer,vector=e.alloc(0x2a0),e.alloc(122*4)
        ifd=writer+0x134
        for at,value in ((ifd+0xc,vector),(ifd+0x10,vector),(ifd+0x14,vector+122*4)):e.w32(at,value)
        e.call(constructor,writer)
        word=lambda at:struct.unpack('<I',e.u.mem_read(at,4))[0]
        live = self.manifest['companion']['extensions']['features'].get('live', False)
        extras=[(0xc7f1,176),(0xc7f2,32)]+([(0xc7f3,24)] if jpeg and live else [])
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_SP),0x5effff00)
        self.assertEqual(word(writer+0x128),ifd)
        self.assertEqual(word(ifd+0x10),vector+(count+len(extras))*4)
        observed=[word(word(vector+i*4)+4)&65535 for i in range(count)]
        self.assertEqual(observed,list(struct.unpack_from('<'+'H'*count,self.stock,table-0x53000000)))
        for index,(tag,size) in enumerate(extras,count):
            entry=word(vector+index*4)
            self.assertEqual(word(entry+4),(7<<16)|tag)
            self.assertEqual(word(entry+8),size)
            self.assertNotEqual(word(entry+16),0)
