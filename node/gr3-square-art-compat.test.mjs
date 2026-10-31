import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {auditSdFilmPack,sdCrc,SD_FILM_IDS} from './gr3-sd-film-pack.mjs';

test('the exact preceding47 film pack remains readable after artwork replacement',()=>{
 const pack=gunzipSync(readFileSync(new URL('../tests/fixtures/gr3-pre-square-art-films.m10.gz',import.meta.url)));
 assert.deepEqual(auditSdFilmPack(pack).ids,SD_FILM_IDS.filter(id=>id<318));
 // Keep the full-record binding: CRC repair cannot authorize altered artwork.
 pack[4096+2048+200]^=1;
 const record=pack.subarray(4096,4096+12288);
 record.writeUInt32LE(sdCrc(record.subarray(0,-4)),12284);
 pack.writeUInt32LE(record.readUInt32LE(12284),68);
 pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);
 assert.throws(()=>auditSdFilmPack(pack),/校验失败|不兼容/);
});
