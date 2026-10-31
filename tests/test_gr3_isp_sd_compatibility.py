"""Exact main-era records stay readable; CRC repair alone never authorizes edits."""
import ctypes as C
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
        # Reconstruct records from unchanged recipe data, then require their
        # FULL SHA to match the immutable origin/main contract, independently.
        js = """import {sdFilmRecord,customFilmRecord} from './node/gr3-sd-film-pack.mjs';
        import {readFileSync} from 'node:fs';
        const p=JSON.parse(readFileSync('node/gr3-sd-pre-isp-still-contract.json'));
        process.stdout.write(Buffer.concat([...p.ids.map(sdFilmRecord),customFilmRecord({name:'Identity',rgb:Buffer.alloc(6591,128)},79)]));"""
        cls.records = subprocess.check_output(['node', '--input-type=module', '-e', js], cwd=ROOT)

    def old_record(self, index):
        record = bytearray(self.records[index*12288:(index+1)*12288])
        if index<63 and self.prior['ids'][index]==294:
            record[16:40]=b'Fujifilm Velvia 50'.ljust(24,b'\0')
        record[8448:8480] = bytes.fromhex(self.prior['renderer'])
        struct.pack_into('<I', record, 12284, zlib.crc32(record[:-4]))
        return record

    def test_user_validated_rc1_all_44_records_survive_lossless_storage_change(self):
        import gzip
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
        import {buildSdFilmPack,auditSdFilmPack,sdCrc} from './node/gr3-sd-film-pack.mjs';
        const prior=JSON.parse(readFileSync('node/gr3-sd-pre-isp-still-contract.json'));
        const old=Buffer.from(prior.renderer,'hex');
        for(const custom of [[],[{name:'Identity',rgb:Buffer.alloc(6591,128),sha256:'identity'}]]){
          const b=buildSdFilmPack(auditSdFilmPack(buildSdFilmPack()).ids.filter(id=>prior.ids.includes(id)&&id!==294),custom),n=b.readUInt32LE(16);
          for(let i=0;i<n;i++){
            const r=b.subarray(4096+i*12288,4096+(i+1)*12288);old.copy(r,8448);
            r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);b.writeUInt32LE(r.readUInt32LE(12284),68+i*12);
          }
          b.writeUInt32LE(sdCrc(b.subarray(0,4092)),4092);assert.equal(auditSdFilmPack(b).count,n);
          const r=b.subarray(4096,4096+12288);r[100]^=1;r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);
          b.writeUInt32LE(r.readUInt32LE(12284),68);b.writeUInt32LE(sdCrc(b.subarray(0,4092)),4092);
          assert.throws(()=>auditSdFilmPack(b));
        }"""
        subprocess.run(['node','--input-type=module','-e',js],cwd=ROOT,check=True,capture_output=True)
