import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import vm from 'node:vm';
import {resolveIspEffectOptions} from './gr3-isp-effect-options.mjs';
import {readNativeOfficial,prepareNative} from './gr3-native-library.mjs';
import {configurationForEffects,defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {normalizeWorkbenchDraft,updateWorkbenchFeature} from '../web/gr3/workbench-state.mjs';
import {modelCapabilities} from '../web/gr3/model-capabilities.mjs';

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
 assert.equal(identity.catalogHash,'dec78e808816dd21e7e6225a7a3c539699bd0572bb018b719e7fcc5c328be696');
 assert.equal(identity.rendererHash,'db7fdff7b13e23447f4a58c561b92813319acf249b8922f75b4ffdad3bb74f30');
 assert.match(identity.buildId,/^[a-f0-9]{64}$/);
 assert.deepEqual(resolveIspEffectOptions(source,structuredClone(input),'GR III'),options);
 assert.deepEqual(input,before);
 const plan=prepareNative(source,input.configuration,options);
 assert.deepEqual(plan.companion_identity,identity);
 assert.equal(plan.preserve_existing,true);
 for(const change of [
  {configuration:{...input.configuration,stamp:1}},
  {ab_enabled:true},
  {power_images:{startup:{jpeg_base64:'different-build-image'}}},
 ])assert.notEqual(resolveIspEffectOptions(source,{...input,...change},'GR III').companion_identity.buildId,identity.buildId);
 assert.notEqual(plan.configuration_sha256,prepareNative(source,input.configuration,resolveIspEffectOptions(source,{...input,gremote_enabled:false},'GR III')).configuration_sha256);
});

test('public preservation defaults on only with GRemote and explicit opt-out changes the bound identity',async()=>{
 const source=await readNativeOfficial(),input={gremote_enabled:true,configuration:defaultConfiguration()};
 const normal=resolveIspEffectOptions(source,input,'GR III');
 const on=resolveIspEffectOptions(source,{...input,gremote_preserve_settings:true},'GR III');
 const off=resolveIspEffectOptions(source,{...input,gremote_preserve_settings:false},'GR III');
 assert.equal(normal.preserve_existing,true);assert.deepEqual(normal,on);
 assert.equal(Object.hasOwn(off,'preserve_existing'),false);
 assert.notEqual(on.companion_identity.buildId,off.companion_identity.buildId);
 assert.notEqual(prepareNative(source,input.configuration,on).configuration_sha256,prepareNative(source,input.configuration,off).configuration_sha256);
 for(const gremote_preserve_settings of [true,false]){
  const ordinary=resolveIspEffectOptions(source,{...input,gremote_enabled:false,gremote_preserve_settings},'GR III');
  assert.equal(Object.hasOwn(ordinary,'preserve_existing'),false);
  assert.equal(Object.hasOwn(ordinary,'companion_identity'),false);
  assert.deepEqual(ordinary,resolveIspEffectOptions(source,{configuration:input.configuration},'GR III'));
 }
 for(const gremote_preserve_settings of [null,0,'false',[],{}])for(const gremote_enabled of [true,false])assert.throws(()=>resolveIspEffectOptions(source,{...input,gremote_enabled,gremote_preserve_settings},'GR III'),/GRemote.*布尔/);
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

test('preservation choice survives GR III draft and undo normalization while legacy and other models use safe defaults',()=>{
 const draft={profile:'native',features:['film','gremote'],gremotePreserveSettings:false};
 assert.equal(normalizeWorkbenchDraft(draft).gremotePreserveSettings,false);
 assert.equal(normalizeWorkbenchDraft(normalizeWorkbenchDraft(draft)).gremotePreserveSettings,false);
 assert.equal(normalizeWorkbenchDraft({profile:'native',features:['film','gremote']}).gremotePreserveSettings,true);
 for(const gremotePreserveSettings of [undefined,null,1,'false',{}])assert.equal(normalizeWorkbenchDraft({...draft,gremotePreserveSettings}).gremotePreserveSettings,true);
 for(const model of ['gr3x','gr4','gr2']){
  const restored=normalizeWorkbenchDraft(draft,[],defaultConfiguration(),model);
  assert.equal(restored.gremotePreserveSettings,true);assert.ok(!restored.features.includes('gremote'));
 }
});

test('studio preflight sends the explicit GRemote choice and never sends private identity or upgrade policy',async()=>{
 const app=readFileSync(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 const method=app.slice(app.indexOf('async function prepare()'),app.indexOf('async function build('));
 for(const [enabled,preserve] of [[false,true],[true,true],[true,false]]){
  const state={projectId:'a'.repeat(64),profile:'native',features:new Set(['film',...(enabled?['gremote']:[])]),gremotePreserveSettings:preserve,nativeConfig:defaultConfiguration(),revision:1};
  let sent;
  const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);};
  const context=vm.createContext({state,$:node,configurationForEffects,structuredClone,AbortController,validateZoomControls(){},prepareZoomConfigurationForBuild:c=>c,
   nativeExtensions:()=>({}),debugEnabled:()=>false,versionUnlockSnapshot:()=>({enabled:false}),selectedPowerImages:()=>({}),renderLedger(){},
   api:async(path,options)=>{sent=JSON.parse(options.body);return {json:async()=>({ready:true})};}});
  vm.runInContext("let chosenModel='gr3',activeBuildController=null,riskAcceptedRevision=-1;"+method,context);
  await context.prepare();
  assert.equal(sent.gremote_enabled,enabled);
  assert.equal(sent.gremote_preserve_settings,enabled?preserve:undefined);
  assert.equal(Object.hasOwn(sent,'companion_identity'),false);assert.equal(Object.hasOwn(sent,'preserve_existing'),false);
 }
});

test('studio saves preservation choice in drafts and restores it through undo',()=>{
 const app=readFileSync(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 const state={profile:'native',features:new Set(['film','gremote']),gremotePreserveSettings:false,nativeConfig:defaultConfiguration(),nativeCatalog:[],unresolvedSlots:[],toolFeaturesDraft:[],recipes:new Map(),filmIds:[],filmLibrary:[],filmTexture:{},stockPresets:[],rawNr:{mode:'stock'},films:[]};
 let saved;
 const context=vm.createContext({state,normalizeWorkbenchDraft,powerImages:undefined,$:()=>({}),selection:()=>({}),
  localStorage:{setItem:(key,value)=>{saved=JSON.parse(value);}},notice:message=>assert.fail(message),nativeEditor:{setConfiguration(){},setUnresolved(){}},
  editHistory:{undo(){},snapshot:()=>({config:{...saved,filmIds:[]}})},invalidate(){},renderFeatures(){}});
 const history=app.slice(app.indexOf('function historyConfiguration()'),app.indexOf('const editHistory='));
 const save=app.slice(app.indexOf('function saveDraft()'),app.indexOf('function restoreDraft()'));
 const undo=app.slice(app.indexOf('function restoreHistory('),app.indexOf('function notice('));
 vm.runInContext("let draftPersistenceAllowed=true,draftKey='test',chosenModel='gr3',restoringHistory=false;"+history+save+undo,context);
 assert.equal(context.historyConfiguration().gremotePreserveSettings,false);
 context.saveDraft();assert.equal(saved.gremotePreserveSettings,false);
 state.gremotePreserveSettings=true;
 context.restoreHistory('undo');assert.equal(state.gremotePreserveSettings,false);
});

test('GR III can configure GRemote before source import without enabling other firmware',()=>{
 const studio=readFileSync(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 const availability=studio.slice(studio.indexOf('const gremoteAvailable='),studio.indexOf('\n',studio.indexOf('const gremoteAvailable=')));
 const check=vm.runInNewContext('(chosenModel,state)=>{'+availability+'return gremoteAvailable();}',{modelCapabilities});
 assert.equal(check('gr3',{source:null}),true);
 assert.equal(check('gr3',{source:{sha256:'d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'}}),true);
 assert.equal(check('gr3',{source:{sha256:'0'.repeat(64)}}),false);
 for(const model of ['gr3x','gr4','gr2'])assert.equal(check(model,{source:null}),false);
});

test('active GRemote card exposes preservation checked by default and applies an explicit checkbox choice',()=>{
 const app=readFileSync(new URL('../web/gr3/studio.js',import.meta.url),'utf8'),elements=[];
 const node=tag=>{const value={tag,dataset:{},children:[],listeners:{},append(...children){this.children.push(...children);},setAttribute(){},addEventListener(name,fn){this.listeners[name]=fn;},querySelector:()=>null};elements.push(value);return value;};
 const nodes=new Map(),lookup=id=>{if(!nodes.has(id))nodes.set(id,node('div'));return nodes.get(id);};
 const state={profile:'native',features:new Set(['film','gremote']),nativeConfig:defaultConfiguration(),source:{sha256:'d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'}};
 const context=vm.createContext({state,modelCapabilities,nativeEditor:{},$:lookup,document:{createElement:node},gr4Workbench:false,
  definitions:[['gremote','GRemote 连接','连接说明','GR III 2.10']],textNode:(tag,text)=>Object.assign(node(tag),{textContent:text}),renderZoomControls(){},renderFeatureCount(){},renderLedger(){},invalidate(){}});
 const availability=app.slice(app.indexOf('const gremoteAvailable='),app.indexOf('\n',app.indexOf('const gremoteAvailable=')));
 const render=app.slice(app.indexOf('function renderFeatures()'),app.indexOf('function renderFeatureCount()'));
 vm.runInContext("let chosenModel='gr3';"+availability+render,context);
 context.renderFeatures();
 const control=elements.find(element=>element.dataset.imagingField==='gremote-preserve-settings');
 assert.ok(control);assert.equal(control.checked,true);assert.equal(control.disabled,false);
 assert.ok(elements.some(element=>element.tag==='label'&&element.children.includes(' 保留机内设置')));
 control.checked=false;control.listeners.change();assert.equal(state.gremotePreserveSettings,false);
});
