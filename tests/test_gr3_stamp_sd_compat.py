"""The new renderer must read unchanged cards from the last delivered main."""
import ctypes as C
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class OrientedStampSdCompatibility(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  lib=Path(cls.tmp.name)/'sd.dylib'
  subprocess.run(['clang','-O2','-Wall','-Wextra','-Werror','-dynamiclib',str(ROOT/'native/gr3/m10v_sd_library.c'),'-o',str(lib)],check=True,capture_output=True)
  cls.lib=C.CDLL(str(lib));cls.lib.m10v_sd_record.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32]
  source="""import{readFileSync}from'node:fs';import{sdFilmRecord,sdCrc}from'./node/gr3-sd-film-pack.mjs';import{createHash}from'node:crypto';
const c=JSON.parse(readFileSync('node/gr3-sd-pre-oriented-stamp-contract.json'));const records=[33,314,316].map(id=>{const r=sdFilmRecord(id);Buffer.from(c.renderer,'hex').copy(r,8448);r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);if(createHash('sha256').update(r).digest('hex')!==c.hashes[c.ids.indexOf(id)])throw Error('not exact previous record');return r;});process.stdout.write(Buffer.concat(records));"""
  cls.records=subprocess.check_output(['node','--input-type=module','-e',source],cwd=ROOT)
 def test_exact_delivered_records_survive_orientation_only_renderer_change(self):
  for i,id in enumerate((33,314,316)):
   r=self.records[i*12288:(i+1)*12288]
   self.assertEqual(self.lib.m10v_sd_record(r,len(r),id),id)
 def test_repaired_crc_does_not_authorize_changed_previous_recipe(self):
  import zlib
  r=bytearray(self.records[:12288]);r[64]^=1;struct.pack_into('<I',r,12284,zlib.crc32(r[:-4]))
  self.assertEqual(self.lib.m10v_sd_record(bytes(r),len(r),33),0)
