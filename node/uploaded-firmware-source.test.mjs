import {test} from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {resolveBuildSource} from './firmware-build-source.mjs';
import {inspectFirmwareImport} from './firmware.mjs';
import {stockPresetCapabilities} from './gr3-stock-presets.mjs';
import {prepareNative} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {prepareCustomization,buildCustomization} from './gr3-customization.mjs';
import {decodeFrameMap} from './gr3-frames.mjs';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createServer} from './server.mjs';
import {Store} from './storage.mjs';

for (const [model, variable, version] of [
  ['GR III', 'M10V_GR3_220_FIXTURE', '2.20'],
  ['GR IIIx', 'M10V_GR3X_170_FIXTURE', '1.70'],
]) {
  const fixture = process.env[variable];
  test(`${model} ${version} uses the uploaded executable and version without substitution`,
    {skip: !fixture || !existsSync(fixture)}, async () => {
      const uploaded = readFileSync(fixture);
      const {source, report} = await resolveBuildSource(uploaded);
      assert.ok(source.equals(uploaded), 'the build must use the uploaded firmware bytes');
      assert.equal(report.model, model);
      assert.equal(report.build_source.public_version, version);
      assert.equal(report.build_source.sha256, inspectFirmwareImport(uploaded).sha256);
      assert.equal(report.build_source.normalized, false);
      assert.equal(report.build_source.update_compatibility, undefined);
    });
  test(`${model} ${version} reads factory presets from its own startup copy layout`,
    {skip: !fixture || !existsSync(fixture)}, () => {
      const presets = stockPresetCapabilities(readFileSync(fixture));
      assert.equal(presets.length, 12);
      assert.equal(presets[0].factoryName, 'Standard');
      assert.ok(presets.every(preset => Buffer.from(preset.iconPixelsBase64, 'base64').length === 6400));
    });
  test(`${model} ${version} only declares a reviewed native target ready`,
    {skip: !fixture || !existsSync(fixture)}, () => {
      if(model==='GR III')assert.equal(prepareNative(readFileSync(fixture),defaultConfiguration()).ready,true);
      else assert.throws(()=>prepareNative(readFileSync(fixture),defaultConfiguration()),
        error=>error.code==='M10V_NATIVE_ABI_NOT_PORTED'&&/不会改用旧版/.test(error.message));
    });
  test(`${model} ${version} factory data edits preserve all uploaded components and versions`,
    {skip: !fixture || !existsSync(fixture)}, async () => {
      const source=readFileSync(fixture),pixels=Buffer.from(stockPresetCapabilities(source)[1].iconPixelsBase64,'base64');
      pixels[(2*40+2)*4]^=1;
      const selection={variant:'street',features:['presets'],stockPresets:[{slot:2,name:'Clear',iconPixelsBase64:pixels.toString('base64')}]};
      const plan=await prepareCustomization(source,selection);
      assert.equal(plan.ready,true);
      const {candidate,receipt}=await buildCustomization(source,selection,plan.configuration_sha256);
      assert.equal(receipt.source_sha256,inspectFirmwareImport(source).sha256);
      assert.equal(inspectFirmwareImport(candidate).internal_version,inspectFirmwareImport(source).internal_version);
      assert.ok(candidate.subarray(0,128).equals(source.subarray(0,128)));
      const before=decodeFrameMap(source).decoded,after=decodeFrameMap(candidate).decoded;
      assert.equal(before.length,after.length);
      let offset=0;
      for(const section of inspectFirmwareImport(source).sections){
        if(!['RTOS','ICONBIN'].includes(section.name))assert.ok(before.subarray(offset,offset+section.size).equals(after.subarray(offset,offset+section.size)),section.name);
        offset+=section.size;
      }
      // The exported name is read independently through the candidate's pointers.
      // inspectFirmwareImport verifies CPU, RTOS and both outer version copies.
      assert.equal(receipt.audit.stockIntent.verified,true);
    });
  test(`${model} ${version} HTTP export retains the source identity and never runs the old version-spoofing pass`,
    {skip: !fixture || !existsSync(fixture)}, async () => {
      const source=readFileSync(fixture),folder=await mkdtemp(path.join(os.tmpdir(),'m10v-source-http-'));
      const server=createServer(new Store(folder));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
      const base=`http://127.0.0.1:${server.address().port}`;
      try{
        const {session_token:token}=await(await fetch(base+'/api/status')).json();
        const post=(url,body)=>fetch(base+url,{method:'POST',headers:{'X-M10V-Token':token},body:Buffer.isBuffer(body)?body:JSON.stringify(body)});
        const imported=await post('/api/import',source);assert.equal(imported.status,200);
        const report=await imported.json(),route='/api/projects/'+report.project_id;
        assert.equal(report.build_source.sha256,report.sha256);
        const selection={variant:'street',features:['presets'],stockPresets:[{slot:2,name:'Clear'}]};
        const prepared=await post(route+'/edit/prepare',{selection});assert.equal(prepared.status,200,await prepared.clone().text());
        const plan=await prepared.json();
        const built=await post(route+'/edit/build',{selection,accepted_configuration_sha256:plan.configuration_sha256});
        assert.equal(built.status,200,await built.clone().text());
        const candidate=Buffer.from(await built.arrayBuffer());
        assert.equal(built.headers.get('X-M10V-Update-Compatibility'),null);
        const receipt=JSON.parse(Buffer.from(built.headers.get('X-M10V-Build-Receipt'),'base64'));
        assert.equal(receipt.source_sha256,report.sha256);
        assert.equal(receipt.update_compatibility,undefined);
        assert.equal(inspectFirmwareImport(candidate).internal_version,report.internal_version);
        const native=await post(route+'/native-library/prepare',{configuration:defaultConfiguration()});
        if(model==='GR III'){assert.equal(native.status,200,await native.clone().text());assert.equal((await native.json()).ready,true);}
        else{assert.equal(native.status,400);assert.match((await native.json()).error,/原生 ABI 尚未适配/);}
      }finally{await new Promise(resolve=>server.close(resolve));await rm(folder,{recursive:true,force:true});}
    });
}
