"""Exact main-era records stay readable; CRC repair alone never authorizes edits."""
import ctypes as C
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]

class ISPSdCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        lib = Path(cls.temp.name) / 'sd.so'
        subprocess.run(['clang', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
            str(ROOT / 'native/gr3/m10v_sd_library.c'), '-o', str(lib)], check=True, capture_output=True)
        cls.lib = C.CDLL(str(lib))
        cls.lib.m10v_sd_record.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32]
        cls.prior = json.loads((ROOT / 'node/gr3-sd-pre-isp-still-contract.json').read_text())
        # Recipe data is unchanged, but current square artwork is different.
        # Pin historical artwork from immutable packs; the later pack includes
        # the final Velvia artwork and D-76 identities absent from the first.
        cls.prior_artwork = {}
        for name in ('gr3-pre-directory-films.m10.gz', 'gr3-pre-c41-films.m10.gz'):
            pack = gzip.decompress((ROOT / 'tests/fixtures' / name).read_bytes())
            for index in range(struct.unpack_from('<I', pack, 16)[0]):
                record = pack[4096+index*12288:4096+(index+1)*12288]
                cls.prior_artwork[struct.unpack_from('<I', record, 8)[0]] = record[2048:8448]
        # Require each complete reconstructed record to match the immutable
        # origin/main digest, including artwork, recipe, name and renderer.
        js = """import {sdFilmRecord,customFilmRecord} from './node/gr3-sd-film-pack.mjs';
        import {readFileSync} from 'node:fs';
        const p=JSON.parse(readFileSync('node/gr3-sd-pre-isp-still-contract.json'));
        process.stdout.write(Buffer.concat([...p.ids.map(sdFilmRecord),customFilmRecord({name:'Identity',rgb:Buffer.alloc(6591,128)},79)]));"""
        cls.records = subprocess.check_output(['node', '--input-type=module', '-e', js], cwd=ROOT)

    def old_record(self, index):
        record = bytearray(self.records[index*12288:(index+1)*12288])
        if index < len(self.prior['ids']):
            record[2048:8448] = self.prior_artwork[self.prior['ids'][index]]
        if index<63 and self.prior['ids'][index]==294:
            record[16:40]=b'Fujifilm Velvia 50'.ljust(24,b'\0')
        record[8448:8480] = bytes.fromhex(self.prior['renderer'])
        struct.pack_into('<I', record, 12284, zlib.crc32(record[:-4]))
        return record

    def test_user_validated_rc1_all_44_records_survive_lossless_storage_change(self):
        pack=gzip.decompress((ROOT/'tests/fixtures/gr3-anime-e6-rc1-films.m10.gz').read_bytes())
        self.assertEqual(struct.unpack_from('<I',pack,16)[0],44)
        for i in range(44):
            record=bytearray(pack[4096+i*12288:4096+(i+1)*12288]);film=struct.unpack_from('<I',record,8)[0]
            self.assertEqual(self.lib.m10v_sd_record(bytes(record),len(record),film),film)
            record[100]^=1;struct.pack_into('<I',record,12284,zlib.crc32(record[:-4]))
            self.assertEqual(self.lib.m10v_sd_record(bytes(record),len(record),film),0)

    def test_pre_four_looks_records_and_new_native_identities_remain_authenticated(self):
        prior=json.loads((ROOT/'node/gr3-sd-pre-four-looks-contract.json').read_text())
        js="""import{sdFilmRecord}from'./node/gr3-sd-film-pack.mjs';
import{readFileSync}from'node:fs';const p=JSON.parse(readFileSync('node/gr3-sd-pre-four-looks-contract.json'));
process.stdout.write(Buffer.concat([...p.ids,318,319,320,321].map(sdFilmRecord)));"""
        records=subprocess.check_output(['node','--input-type=module','-e',js],cwd=ROOT)
        for index,film in enumerate([*prior['ids'],318,319,320,321]):
            with self.subTest(film=film):
                record=bytearray(records[index*12288:(index+1)*12288])
                if index<len(prior['ids']):
                    record[8448:8480]=bytes.fromhex(prior['renderer'])
                    struct.pack_into('<I',record,12284,zlib.crc32(record[:-4]))
                    self.assertEqual(hashlib.sha256(record).hexdigest(),prior['hashes'][index])
                self.assertEqual(self.lib.m10v_sd_record(bytes(record),len(record),film),film)
                record[100]^=1
                struct.pack_into('<I',record,12284,zlib.crc32(record[:-4]))
                self.assertEqual(self.lib.m10v_sd_record(bytes(record),len(record),film),0)

    def test_native_accepts_all_63_exact_main_records_and_rejects_repaired_edits(self):
        for index, film in enumerate(self.prior['ids']):
            r = self.old_record(index)
            self.assertEqual(hashlib.sha256(r).hexdigest(), self.prior['hashes'][index])
            self.assertEqual(self.lib.m10v_sd_record(bytes(r), len(r), film), film)
            r[100] ^= 1
            struct.pack_into('<I', r, 12284, zlib.crc32(r[:-4]))
            self.assertEqual(self.lib.m10v_sd_record(bytes(r), len(r), film), 0)

    def test_native_preserves_custom_record_and_reserved_byte_validation(self):
        r = self.old_record(63)
        self.assertEqual(self.lib.m10v_sd_record(bytes(r), len(r), 79), 79)
        r[7000] = 1
        struct.pack_into('<I', r, 12284, zlib.crc32(r[:-4]))
        self.assertEqual(self.lib.m10v_sd_record(bytes(r), len(r), 79), 0)

    def test_node_accepts_main_builtin_and_mixed_packs_and_rejects_repaired_edits(self):
        js = """import assert from 'node:assert/strict';
        import {readFileSync} from 'node:fs';
        import {createHash} from 'node:crypto';
        import {auditSdFilmPack,sdCrc} from './node/gr3-sd-film-pack.mjs';
        const prior=JSON.parse(readFileSync('node/gr3-sd-pre-isp-still-contract.json'));
        const records=readFileSync(0),builtinCount=prior.ids.length;
        assert.equal(records.length,(builtinCount+1)*12288);
        for(let i=0;i<builtinCount;i++)assert.equal(createHash('sha256').update(records.subarray(i*12288,(i+1)*12288)).digest('hex'),prior.hashes[i]);
        for(const custom of [false,true]){
          const n=builtinCount+Number(custom),header=Buffer.alloc(4096);
          header.write(custom?'M10VSD2\\0':'M10VSD1\\0');header.writeUInt32LE(custom?2:1,8);
          header.writeUInt32LE(4096+n*12288,12);header.writeUInt32LE(n,16);
          header.writeUInt32LE(12288,20);header.writeUInt32LE(239,24);header.writeUInt32LE(1,28);
          for(let i=0;i<n;i++){
            const r=records.subarray(i*12288,(i+1)*12288);
            header.writeUInt32LE(r.readUInt32LE(8),64+i*12);header.writeUInt32LE(r.readUInt32LE(12284),68+i*12);header.writeUInt32LE(1,72+i*12);
          }
          header.writeUInt32LE(sdCrc(header.subarray(0,4092)),4092);
          const b=Buffer.concat([header,records.subarray(0,n*12288)]);assert.equal(auditSdFilmPack(b).count,n);
          const r=b.subarray(4096,4096+12288);r[100]^=1;r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);
          b.writeUInt32LE(r.readUInt32LE(12284),68);b.writeUInt32LE(sdCrc(b.subarray(0,4092)),4092);
          assert.throws(()=>auditSdFilmPack(b));
        }"""
        records = b''.join(self.old_record(index) for index in range(len(self.prior['ids'])+1))
        result = subprocess.run(['node','--input-type=module','-e',js],cwd=ROOT,input=records,capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
