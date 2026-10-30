"""Original FileWriteMacroProcess record -> original EXIF dimension writers.

No image-info/dimension service is replaced. The hardware encoder is outside
this metadata-only proof; paired descriptor shapes are explicit input fixtures.
"""
from pathlib import Path
import struct
import unittest
from scripts.probe_gr3_border_encoded_bank import setup, RECIPE, SI


class HalfPairMetadataTests(unittest.TestCase):
    def test_capture_file_setup_and_real_exif_writers_read_final_pair_descriptor(self):
        rom=Path('builds/gr3-extension-validation/official-rtos.bin').read_bytes()
        for w,h in ((5984,4000),(2992,8000),(4800,3200),(2400,6400),
                    (3360,2240),(1680,4480),(1920,1280),(960,2560)):
            with self.subTest(dimensions=(w,h)):
                p=setup(rom,0,6000,4000)
                # Original FileWrite Setup8 fragment binds live descriptor
                # pointers. Deliberately bind a single-Half shape first.
                main=bytearray(32);main[0]=1;main[28]=2
                struct.pack_into('<6H',main,16,w//2 if w>2992 else w,h if w>2992 else h//2,
                                 (w+63)&~63,h,0,0)
                p.u.mem_write(RECIPE+0xb0,bytes(main))
                p.u.mem_write(SI+0x7b6,b'\x06')
                p.words(RECIPE+0x954,0)
                p.u.reg_write(p.A.UC_ARM_REG_R0,RECIPE)
                p.u.reg_write(p.A.UC_ARM_REG_R4,RECIPE)
                p.u.reg_write(p.A.UC_ARM_REG_R11,0x55ffdf00)
                p.u.reg_write(p.A.UC_ARM_REG_SP,0x55ffde80)
                p.u.emu_start(0x5350e93c,0x5350e6f0,count=10000)
                self.assertEqual(p.u.reg_read(p.A.UC_ARM_REG_PC),0x5350e6f0)
                config=RECIPE+0xb4c
                self.assertEqual(p.read_words(config+0x40,1),[RECIPE+0xb0])
                # Pair publication happens later, at JPEG pre-submit. No file
                # config is rebuilt here; its pointer must observe new shape.
                p.u.mem_write(RECIPE+0xb0+16,struct.pack('<2H',w,h))
                p.words(RECIPE+0x130,0x70000000,1234,16000000,1234)
                record,meta,writer,ifd=0x552a0000,0x552b0000,0x552c0000,0x552d0000
                p.call(0x5350afec,0x55280000,record,config,0)
                self.assertEqual(p.read_words(record,2),[w,h])
                self.assertEqual(p.read_words(record+8,4),[0,0,w,h])
                self.assertEqual(bytes(p.u.mem_read(SI+0x7b6,1)),b'\x06')
                # Original type2 binding/getter and both original EXIF class
                # initializers resolve that very image record, not frozen SI.
                p.call(0x535fc234,meta)
                p.call(0x535fc2e0,meta,2,record)
                for initialize,write in ((0x535fe8c4,0x535fe9b4),(0x535ffae4,0x535ffbd4)):
                    p.words(writer+4,meta)
                    p.call(initialize,writer)
                    self.assertEqual(p.read_words(writer+0x24,1),[record])
                    for tag,value in ((0xa002,w),(0xa003,h)):
                        p.u.mem_write(ifd,bytes(24))
                        p.u.mem_write(ifd+4,struct.pack('<H',tag))
                        self.assertEqual(p.call(write,writer,ifd),1)
                        self.assertEqual(p.read_words(ifd+12,1),[value])
                self.assertFalse(p.assertions)
