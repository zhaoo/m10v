import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {generateNative, prepareNative} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {inspectFirmwareImport} from './firmware.mjs';
import {decodeFrameMap,repackWithTarget} from './gr3-frames.mjs';

const fixture = process.env.M10V_GR3_220_FIXTURE;

test('GR III 2.20 cannot enter the native planner or generator', {skip: !fixture}, async () => {
 const source = readFileSync(fixture);
 const configuration = defaultConfiguration();
 assert.throws(() => prepareNative(source, configuration), /2\.20.*永久停用/);
 await assert.rejects(generateNative(source, configuration, 'old-plan'), /2\.20.*永久停用/);
 assert.equal(inspectFirmwareImport(source).public_version, '2.20');
 const {decoded}=decodeFrameMap(source);
 assert.throws(()=>repackWithTarget(source,decoded),/2\.20.*永久停用/);
});
