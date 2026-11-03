import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import vm from 'node:vm';
import {resolveIspEffectOptions} from './gr3-isp-effect-options.mjs';
import {readNativeOfficial,prepareNative} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {normalizeWorkbenchDraft,updateWorkbenchFeature} from '../web/gr3/workbench-state.mjs';

for(const [model,label] of [['gr3','GR III'],['gr3x','GR IIIx']]){
 test(`GRemote defaults off and leaves ordinary ${label} plans unchanged`,{skip:!existsSync(new URL(`../bin/${model==='gr3'?'fwdc239b-gr3':'fwdc243b-gr3x'}-official.bin`,import.meta.url))},async()=>{
  const source=await readNativeOfficial(model),input={configuration:defaultConfiguration(model)};
  const plain=resolveIspEffectOptions(source,input,label),off=resolveIspEffectOptions(source,{...input,gremote_enabled:false},label);
  assert.equal(Object.hasOwn(off,'companion_identity'),false);
  assert.deepEqual(off,plain);
  assert.deepEqual(prepareNative(source,input.configuration,off),prepareNative(source,input.configuration,plain));
 });
}

test('GRemote opt-in binds current App metadata and deterministic source/configuration identity',async()=>{
 const source=await readNativeOfficial(),input={gremote_enabled:true,configuration:defaultConfiguration()},before=structuredClone(input);
 const options=resolveIspEffectOptions(source,input,'GR III'),identity=options.companion_identity;
 assert.ok(identity,'GRemote opt-in must include the resident owner');
 assert.equal(identity.catalogHash,'5d3ec9b649a410b0ec988d09d7107872ce8fa67520a9502fc6ef840318d8f9fb');
 assert.equal(identity.rendererHash,'7595208a0cf061d661fd90ab0b8233fd0cf5d5090a2209dff38c9c47a7f21995');
 assert.match(identity.buildId,/^[a-f0-9]{64}$/);
 assert.deepEqual(resolveIspEffectOptions(source,structuredClone(input),'GR III'),options);
 assert.deepEqual(input,before);
 const plan=prepareNative(source,input.configuration,options);
 assert.deepEqual(plan.companion_identity,identity);
 assert.equal(plan.preserve_existing,undefined);
 for(const change of [
  {configuration:{...input.configuration,stamp:1}},
  {ab_enabled:true},
  {power_images:{startup:{jpeg_base64:'different-build-image'}}},
 ])assert.notEqual(resolveIspEffectOptions(source,{...input,...change},'GR III').companion_identity.buildId,identity.buildId);
 assert.notEqual(plan.configuration_sha256,prepareNative(source,input.configuration,resolveIspEffectOptions(source,{...input,gremote_enabled:false},'GR III')).configuration_sha256);
});

test('public GRemote rejects malformed switches and private identity/policy injection even when off',async()=>{
 const source=await readNativeOfficial(),input={configuration:defaultConfiguration()};
 for(const gremote_enabled of [null,1,'true',{},[]])assert.throws(()=>resolveIspEffectOptions(source,{...input,gremote_enabled},'GR III'),/GRemote.*布尔/);
 for(const field of ['companion_identity','preserve_existing']){
  for(const value of [undefined,false,{},null])assert.throws(()=>resolveIspEffectOptions(source,{...input,[field]:value},'GR III'),/公开|public/i);
 }
});

test('public GRemote rejects changed sources, mismatched models and incompatible component choices',async()=>{
 const source=await readNativeOfficial(),input={gremote_enabled:true,configuration:defaultConfiguration()};
 for(const model of ['GR IIIx','GR IV','gr3',undefined])assert.throws(()=>resolveIspEffectOptions(source,input,model),/GRemote/);
 const changed=Buffer.from(source);changed[0x38]^=1;
 assert.throws(()=>resolveIspEffectOptions(changed,input,'GR III'),/GRemote/);
 for(const flags of [{film_library:false},{appended_slots:false},{live_color:false}])assert.throws(()=>resolveIspEffectOptions(source,{...input,...flags},'GR III'),/GRemote/);
});

test('exact official IIIx remains bridge-off and rejects public GRemote opt-in',{skip:!existsSync(new URL('../bin/fwdc243b-gr3x-official.bin',import.meta.url))},async()=>{
 const source=await readNativeOfficial('gr3x'),input={configuration:defaultConfiguration('gr3x')};
 assert.equal(Object.hasOwn(resolveIspEffectOptions(source,input,'GR IIIx'),'companion_identity'),false);
 assert.throws(()=>resolveIspEffectOptions(source,{...input,gremote_enabled:true},'GR IIIx'),/GRemote.*GR III 2.10/);
});

test('workbench GRemote is opt-in, survives GR III drafts, and cannot leak to IIIx or HDF-only builds',()=>{
 assert.ok(!normalizeWorkbenchDraft().features.includes('gremote'));
 const selected=new Set(['film']),on=updateWorkbenchFeature(selected,'gremote',true,'gr3');
 assert.deepEqual([...selected],['film']);assert.deepEqual([...on],['film','gremote']);
 assert.ok(normalizeWorkbenchDraft({profile:'native',features:[...on]}).features.includes('gremote'));
 for(const model of ['gr3x','gr4','gr2']){
  assert.throws(()=>updateWorkbenchFeature(selected,'gremote',true,model),/GRemote/);
  assert.ok(!normalizeWorkbenchDraft({profile:'native',features:[...on]},[],defaultConfiguration(),model).features.includes('gremote'));
 }
 assert.throws(()=>updateWorkbenchFeature(new Set(),'gremote',true,'gr3'),/胶卷库/);
 assert.ok(!updateWorkbenchFeature(on,'film',false,'gr3').has('gremote'));
 assert.ok(!normalizeWorkbenchDraft({profile:'native',features:['digitalHdf','gremote']}).features.includes('gremote'));
});

test('studio preflight sends the explicit GRemote choice and never sends private identity or upgrade policy',async()=>{
 const app=readFileSync(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 const method=app.slice(app.indexOf('async function prepare()'),app.indexOf('async function build('));
 for(const enabled of [false,true]){
  const state={projectId:'a'.repeat(64),profile:'native',features:new Set(['film',...(enabled?['gremote']:[])]),nativeConfig:defaultConfiguration(),revision:1};
  let sent;
  const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);};
  const context=vm.createContext({state,$:node,structuredClone,AbortController,validateZoomControls(){},prepareZoomConfigurationForBuild:c=>c,
   nativeExtensions:()=>({}),debugEnabled:()=>false,versionUnlockSnapshot:()=>({enabled:false}),selectedPowerImages:()=>({}),renderLedger(){},
   api:async(path,options)=>{sent=JSON.parse(options.body);return {json:async()=>({ready:true})};}});
  vm.runInContext("let chosenModel='gr3',activeBuildController=null,riskAcceptedRevision=-1;"+method,context);
  await context.prepare();
  assert.equal(sent.gremote_enabled,enabled);
  assert.equal(Object.hasOwn(sent,'companion_identity'),false);assert.equal(Object.hasOwn(sent,'preserve_existing'),false);
 }
});
