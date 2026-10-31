import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {resolveIspEffectOptions} from './gr3-isp-effect-options.mjs';
import {readNativeOfficial,prepareNative} from './gr3-native-library.mjs';
import {defaultConfiguration,defaultExtensions} from '../web/gr3/native-library-state.mjs';
import {createServer} from './server.mjs';
import {Store} from './storage.mjs';
import {updateWorkbenchFeature,normalizeWorkbenchDraft} from '../web/gr3/workbench-state.mjs';
import {modelCapabilities} from '../web/gr3/model-capabilities.mjs';

test('production film-only defaults preserve excluded HDF and border for both exact sources',async()=>{
 for(const [model,name] of [['gr3','GR III'],['gr3x','GR IIIx']]){
  const source=await readNativeOfficial(model),configuration=defaultConfiguration(model),extensions=defaultExtensions();
  const input={configuration,extensions,live_color:false,hdf_enabled:false,border_enabled:false},before=structuredClone(input);
  const options=resolveIspEffectOptions(source,input,name),plan=prepareNative(source,configuration,options);
  assert.equal(options.pure_isp_effects,false);assert.equal(options.hdf_enabled,false);assert.equal(options.border_enabled,false);
  assert.equal(Object.hasOwn(plan,'pure_isp_effects'),false);assert.equal(plan.live_color,false);
  assert.equal(plan.configuration.hdf,0);assert.equal(plan.extensions.aspect,false);assert.equal(plan.ab_enabled,false);
  assert.deepEqual(plan.configuration,configuration);assert.deepEqual(plan.extensions,extensions);assert.deepEqual(input,before);
 }
});

test('explicit effects opt-in requires explicit HDF and border inclusion without changing strengths or preview',async()=>{
 for(const [model,name] of [['gr3','GR III'],['gr3x','GR IIIx']]){
  const source=await readNativeOfficial(model),configuration=defaultConfiguration(model);
  const input={pure_isp_effects:true,hdf_enabled:true,border_enabled:true,live_color:false,extensions:defaultExtensions()};
  const options=resolveIspEffectOptions(source,input,name),plan=prepareNative(source,configuration,options);
  assert.equal(plan.pure_isp_effects,true);assert.equal(plan.capture_pipeline,'gr3-native-v8');assert.equal(plan.live_color,false);
  assert.equal(plan.configuration.hdf,0);assert.equal(plan.extensions.aspect,false);assert.deepEqual(plan.configuration,configuration);
  for(const missing of [{hdf_enabled:false},{border_enabled:false},{hdf_enabled:undefined},{border_enabled:undefined}])assert.throws(()=>resolveIspEffectOptions(source,{...input,...missing},name),/明确同时开启/);
 }
});

test('explicit opt-out retains caller flags and low-level default plans remain opt-in',async()=>{
 const source=await readNativeOfficial('gr3'),configuration=defaultConfiguration();
 const input={pure_isp_effects:false,live_color:false,hdf_enabled:false,border_enabled:false,extensions:defaultExtensions()};
 const options=resolveIspEffectOptions(source,input,'GR III');
 assert.equal(options.pure_isp_effects,false);assert.equal(options.hdf_enabled,false);assert.equal(options.border_enabled,false);assert.equal(options.live_color,false);
 assert.deepEqual(prepareNative(source,configuration,options),prepareNative(source,configuration,input));
 assert.equal(Object.hasOwn(prepareNative(source,configuration),'pure_isp_effects'),false);
 assert.equal(resolveIspEffectOptions(source,{film_library:false},'GR III').pure_isp_effects,false);
});

test('invalid switches reject and unsupported source/model never enables or rewrites uploaded bytes',async()=>{
 const source=await readNativeOfficial('gr3');
 for(const value of [null,1,'true',{},[]])assert.throws(()=>resolveIspEffectOptions(source,{pure_isp_effects:value},'GR III'),/ISP/);
 for(const name of ['hdf_enabled','border_enabled'])assert.throws(()=>resolveIspEffectOptions(source,{[name]:'false'},'GR III'),/布尔/);
 for(const model of ['GR IIIx','GR IV','gr3',undefined])assert.equal(resolveIspEffectOptions(source,{},model).pure_isp_effects,false);
 for(const model of ['GR IIIx','GR IV','gr3',undefined])assert.throws(()=>resolveIspEffectOptions(source,{pure_isp_effects:true,hdf_enabled:true,border_enabled:true},model),/仅支持/);
 assert.throws(()=>resolveIspEffectOptions(source,{pure_isp_effects:true,film_library:false,hdf_enabled:true,border_enabled:true},'GR III'),/仅支持/);
 const uploaded=Buffer.from(source);uploaded[0x38]^=1;
 const before=createHash('sha256').update(uploaded).digest('hex');
 assert.equal(resolveIspEffectOptions(uploaded,{},'GR III').pure_isp_effects,false);
 assert.throws(()=>resolveIspEffectOptions(uploaded,{pure_isp_effects:true,hdf_enabled:true,border_enabled:true},'GR III'),/仅支持/);
 assert.equal(createHash('sha256').update(uploaded).digest('hex'),before);
});

test('HTTP prepare preserves old exclusions and enables effects only with all three explicit choices',async()=>{
 const folder=await mkdtemp(path.join(os.tmpdir(),'m10v-isp-options-')),server=createServer(new Store(folder));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const {session_token}=await(await fetch(base+'/api/status')).json();
  const post=async(route,body)=>{
   const response=await fetch(base+route,{method:'POST',headers:{'Content-Type':'application/json','X-M10V-Token':session_token},body:JSON.stringify(body)});
   return {status:response.status,data:await response.json()};
  };
  for(const model of ['gr3','gr3x']){
   const imported=await post('/api/gr3/native-library/import-official',{model});assert.equal(imported.status,200);
   const route=`/api/projects/${imported.data.project_id}/native-library/prepare`;
   const input={configuration:defaultConfiguration(model),extensions:defaultExtensions(),live_color:false,hdf_enabled:false,border_enabled:false};
   const old=await post(route,input);assert.equal(old.status,200);assert.equal(old.data.pure_isp_effects,undefined);assert.equal(old.data.hdf_enabled,false);assert.equal(old.data.border_enabled,false);
   const enabled=await post(route,{...input,pure_isp_effects:true,hdf_enabled:true,border_enabled:true});assert.equal(enabled.status,200);assert.equal(enabled.data.pure_isp_effects,true);
   assert.equal(enabled.data.live_color,false);assert.equal(enabled.data.hdf_enabled,true);assert.equal(enabled.data.border_enabled,true);assert.equal(enabled.data.extensions.aspect,false);assert.equal(enabled.data.configuration.hdf,0);
   const disabled=await post(route,{...input,pure_isp_effects:false});assert.equal(disabled.status,200);assert.equal(disabled.data.pure_isp_effects,undefined);assert.equal(disabled.data.hdf_enabled,false);assert.equal(disabled.data.border_enabled,false);
   assert.equal((await post(route,{...input,pure_isp_effects:'true'})).status,400);
   assert.equal((await post(route,{...input,pure_isp_effects:true})).status,400);
  }
 }finally{await new Promise(resolve=>server.close(resolve));await rm(folder,{recursive:true,force:true});}
});

test('workbench effects selection visibly includes dependencies and removing either dependency removes effects',()=>{
 for(const model of ['gr3','gr3x']){
  assert.equal(modelCapabilities(model).ispEffects,true);
  const off=new Set(['film']),on=updateWorkbenchFeature(off,'ispEffects',true,model);
  assert.deepEqual([...off],['film']);assert.deepEqual([...on],['film','digitalHdf','border','ispEffects']);
  const disabled=updateWorkbenchFeature(on,'ispEffects',false,model);
  assert.deepEqual([...disabled],['film','digitalHdf','border']);
  for(const dependency of ['digitalHdf','border','film'])assert.equal(updateWorkbenchFeature(on,dependency,false,model).has('ispEffects'),false);
  const draft={profile:'native',features:[...on],nativeConfiguration:defaultConfiguration(model)};
  assert.ok(normalizeWorkbenchDraft(draft,[],draft.nativeConfiguration,model).features.includes('ispEffects'));
  for(const missing of ['digitalHdf','border'])assert.ok(!normalizeWorkbenchDraft({...draft,features:[...on].filter(id=>id!==missing)}).features.includes('ispEffects'));
 }
 for(const model of ['gr2','gr4']){assert.equal(modelCapabilities(model).ispEffects,false);assert.throws(()=>updateWorkbenchFeature(new Set(['film']),'ispEffects',true,model),/需要/);}
 assert.deepEqual(normalizeWorkbenchDraft().features,['film']);
 assert.ok(!normalizeWorkbenchDraft({features:['film','ispEffects','digitalHdf','border']},[],defaultConfiguration(),'gr4').features.includes('ispEffects'));
});
