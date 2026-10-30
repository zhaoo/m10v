// Authentic prior artwork bytes, independent of the current artwork generator.
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
const pack=gunzipSync(readFileSync(new URL('../../tests/fixtures/gr3-pre-square-art-films.m10.gz',import.meta.url)));
if(createHash('sha256').update(pack).digest('hex')!=='d62f5aa5782467f0a99eadabe85439b4857cc865f635bb512b481d9dbfddafd9')throw Error('prior artwork fixture changed');
const records=new Map(Array.from({length:pack.readUInt32LE(16)},(_,i)=>{const record=pack.subarray(4096+i*12288,4096+(i+1)*12288);return [record.readUInt32LE(8),record];}));
export function preSquareArtRecord(id){
 const record=records.get(id);if(!record)throw Error('prior fixture has no film '+id);
 return Buffer.from(record);
}
