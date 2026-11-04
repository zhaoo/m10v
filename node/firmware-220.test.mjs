import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {inspectFirmwareImport,readOfficialSection} from './firmware.mjs';
import {inspectModelFirmware} from './model-firmware.mjs';
import {decodeFrameMap} from './gr3-frames.mjs';
const fixture=process.env.M10V_GR3_220_FIXTURE;
test('official GR III 2.20 imports with its own identity and section sizes',{skip:!fixture||!existsSync(fixture)},async()=>{
 const data=readFileSync(fixture),report=inspectFirmwareImport(data);
 assert.equal(report.public_version,'2.20');assert.equal(report.internal_version,'2.20.20.28');
 assert.equal(report.sections.length,14);assert.equal(readOfficialSection(data,'RTOS').length,17520384);
 assert.equal((await inspectModelFirmware(data)).workspace_url,'/gr3/');
 const changed=Buffer.from(data);changed[200]^=1;assert.throws(()=>inspectFirmwareImport(changed),/checksum/);
});
test('2.20 read-only decoding uses its own frame extent',{skip:!fixture||!existsSync(fixture)},()=>{
 const data=readFileSync(fixture),{decoded}=decodeFrameMap(data);
 assert.equal(decoded.length,59798532);
 assert.throws(()=>decodeFrameMap(data,59718388),/frame sizes/);
});
