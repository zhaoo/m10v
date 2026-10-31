import {defaultConfiguration,prepareZoomConfigurationForBuild} from '../web/gr3/native-library-state.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {normalizeVersionUnlock,assertVersionUnlockReceipt} from '../web/gr3/version-unlock-state.mjs';

test('unlock defaults off without inventing device versions and requires exact GR III 2.10 four-part input',()=>{
 assert.deepEqual(normalizeVersionUnlock(),{enabled:false});
 assert.deepEqual(normalizeVersionUnlock({enabled:false,dsp:'',cpu:''},'gr3x'),{enabled:false});
 const valid={enabled:true,dsp:'2.10.21.40',cpu:'2.10.21.27'};
 assert.deepEqual(normalizeVersionUnlock(valid),valid);
 assert.deepEqual(normalizeVersionUnlock({...valid,dsp:'002.010.021.040'}),valid);
 for(const version of ['', '2.10','2.10.21','2.10.21.256','2.10.-1.40','2.10.21.4.0','2.10.21.4x','3.10.21.40','2.11.21.40']){
  assert.throws(()=>normalizeVersionUnlock({...valid,dsp:version}));
  assert.throws(()=>normalizeVersionUnlock({...valid,cpu:version}));
 }
 assert.throws(()=>normalizeVersionUnlock(valid,'gr3x'),/1.60/);
});

test('receipt must attest the same explicit current DSP and CPU versions as the immutable request',()=>{
 const input=normalizeVersionUnlock({enabled:true,dsp:'2.10.21.40',cpu:'2.10.21.27'});
 assert.ok(Object.isFrozen(input));
 assert.doesNotThrow(()=>assertVersionUnlockReceipt({enabled:true,mode:'observed-versions',current_versions:{dsp:input.dsp,cpu:input.cpu}},input));
 for(const receipt of [undefined,{enabled:false},{enabled:true,current_versions:{dsp:input.dsp,cpu:'2.10.21.28'}},{enabled:true,target_versions:{dsp:input.dsp,cpu:input.cpu}}])assert.throws(()=>assertVersionUnlockReceipt(receipt,input),/回读/);
 assert.doesNotThrow(()=>assertVersionUnlockReceipt({enabled:false},{enabled:false}));
 assert.throws(()=>assertVersionUnlockReceipt({enabled:true},{enabled:false}),/回读/);
});

test('the independent export and actual shared studio both expose the opt-in with blank full-version fields',async()=>{
 for(const [file,prefix] of [['native-library.html','native-'],['native-library-controls.html','native-'],['index.html','']]){
  const html=await readFile(new URL('../web/gr3/'+file,import.meta.url),'utf8');
  assert.match(html,new RegExp(`id="${prefix}version-unlock"`));
  assert.doesNotMatch(html,new RegExp(`id="${prefix}version-unlock"[^>]*checked`));
  for(const key of ['dsp','cpu'])assert.match(html,new RegExp(`id="${prefix}version-${key}"[^>]*type="text"`));
  assert.match(html,/DSP Version:/);assert.match(html,/CPU Version:/);
 }
});

import vm from 'node:vm';
const studio=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
const independent=await readFile(new URL('../web/gr3/native-library.js',import.meta.url),'utf8');
function nodes(){const map=new Map();return id=>{if(!map.has(id))map.set(id,{checked:false,value:'',hidden:false,disabled:false,textContent:'',className:''});return map.get(id);};}
function studioHarness({mismatch=false,simple=false,model='gr3',powerConfiguration={},powerEnabled=true,duringBody=()=>{}}={}){
 const $=nodes(),calls=[],downloads=[],completed=[],state={projectId:'official',profile:'native',revision:3,features:new Set(['film']),nativeConfig:{...defaultConfiguration(),slots:defaultConfiguration().slots.map((s,i)=>i===0?{...s,film:33}:s)}};
 if(powerEnabled)state.features.add('powerImages');
 const input=simple?{enabled:true,mode:'dsp-package-only'}:model==='gr3x'?{enabled:true,dsp:'1.60.11.18',cpu:'1.60.11.17'}:{enabled:true,dsp:'2.10.21.40',cpu:'2.10.21.27'};
 const audit=simple?{enabled:true,mode:mismatch?'observed-versions':'dsp-package-only',checks:{cpu_payload_unchanged:true}}:{enabled:true,mode:'observed-versions',current_versions:{dsp:input.dsp,cpu:mismatch?'2.10.21.28':input.cpu}};
 const context=vm.createContext({$,state,Response,completion:{show:value=>completed.push(value)},prepareZoomConfigurationForBuild,validateZoomControls(){},nativeEditor:{setConfiguration(c){state.nativeConfig=c;state.revision++;}},AbortController,structuredClone,atob,Uint8Array,TextDecoder,JSON,normalizeVersionUnlock,assertVersionUnlockReceipt,powerImages:{getConfiguration:()=>structuredClone(powerConfiguration),setModel(){}},
  versionUnlockSnapshot:()=>normalizeVersionUnlock(input,model),nativeExtensions:()=>({aspect:false}),debugEnabled:()=>false,renderLedger(){},notice(){},
  api:async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});return {blob:async()=>{duringBody(state);return new Blob(['candidate']);},json:async()=>({ready:true,configuration_sha256:'hash',filename:'candidate.bin'}),headers:{get:()=>Buffer.from(JSON.stringify({version_unlock:audit})).toString('base64')}};},
  download:async(...args)=>downloads.push(args)});
 vm.runInContext(`let activeBuildController=null,riskAcceptedRevision=3,chosenModel='${model}';`+studio.slice(studio.indexOf('const selectedPowerImages='),studio.indexOf('\n\nconst $'))+studio.slice(studio.indexOf('async function prepare()'),studio.indexOf('function showSettingsTab(')),context);
 return {context,state,$,calls,downloads,completed,input};
}
test('actual studio prepare/build reuse one captured snapshot and validate version receipt before download',async()=>{
 const h=studioHarness();await h.context.prepare();
 h.state.nativeConfig.slots[0].film=68;h.input.cpu='2.10.21.29';
 await h.context.build();
 assert.equal(h.calls.length,2);assert.deepEqual(h.calls[0].body.version_unlock,h.calls[1].body.version_unlock);
 assert.deepEqual(h.calls[0].body.configuration,h.calls[1].body.configuration);
 assert.equal(h.calls[1].body.configuration.slots[0].film,33);assert.equal(h.downloads.length,1);
 assert.equal(h.completed.length,1);assert.equal(await h.completed[0].firmwareBlob.text(),'candidate');assert.equal(h.completed[0].filename,'candidate.bin');assert.deepEqual(h.completed[0].record.configuration.version_unlock,h.calls[1].body.version_unlock);
 const bad=studioHarness({mismatch:true});await bad.context.prepare();await bad.context.build();
 assert.equal(bad.downloads.length,0);assert.match(bad.$('build-result').textContent,/版本回读/);
});
test('actual studio retires GR III controls and validates the remaining GR IIIx input while busy',()=>{
 const $=nodes();$('version-unlock').checked=true;$('version-known').checked=true;
 const context=vm.createContext({$,state:{profile:'native'},normalizeVersionUnlock});
 vm.runInContext("let chosenModel='gr3',saving=true,activeBuildController=null;"+studio.slice(studio.indexOf('function versionUnlockSnapshot()'),studio.indexOf('function renderLedger()')),context);
 assert.equal(context.renderVersionUnlock(),true);assert.equal($('version-unlock-option').hidden,true);assert.equal(context.versionUnlockSnapshot().enabled,false);
 vm.runInContext("chosenModel='gr3x'",context);$('version-unlock').checked=true;$('version-known').checked=true;$('version-dsp').value='1.60.11.18';$('version-cpu').value='1.60.11.17';
 assert.equal(context.renderVersionUnlock(),true);for(const id of ['version-unlock','version-dsp','version-cpu'])assert.equal($(id).disabled,true);
 vm.runInContext('saving=false',context);$('version-cpu').value='1.60';assert.equal(context.renderVersionUnlock(),false);assert.match($('version-error').textContent,/四段/);
 $('version-cpu').value='1.60.11.17';assert.equal(context.renderVersionUnlock(),true);assert.equal($('version-unlock-option').hidden,false);assert.equal($('version-unlock').checked,true);
});
test('both entries invalidate previous output when toggle or version inputs change',()=>{
 assert.match(independent,/native-version-known'\)\.onchange=\(\)=>\{invalidate\(\);render\(\);\}/);
 assert.match(independent,/native-version-unlock'\)\.onchange=\(\)=>\{invalidate\(\);render\(\);\}/);
 assert.match(independent,/native-version-'\+key\)\.oninput=\(\)=>\{invalidate\(\);render\(\);\}/);
 assert.match(studio,/version-known'\)\.addEventListener\('change',\(\)=>invalidate\(false\)\)/);
 assert.match(studio,/version-unlock'\)\.addEventListener\('change',\(\)=>invalidate\(false\)\)/);
 assert.match(studio,/version-'\+key\)\.addEventListener\('input',\(\)=>invalidate\(false\)\)/);
});

test('actual independent exporter posts identical version snapshot and refuses mismatched audit before exposing URLs',async()=>{
 async function run(mismatch=false,simple=false){
  const $=nodes(),calls=[],created=[],busyChanges=[],messages=[];
  const configuration=defaultConfiguration(),option=simple?{enabled:true,mode:'dsp-package-only'}:{enabled:true,dsp:'2.10.21.40',cpu:'2.10.21.27'};
  const receipt={debug_mode:false,candidate_sha256:'aa',configuration,version_unlock:simple?{enabled:true,mode:mismatch?'observed-versions':'dsp-package-only',checks:{cpu_payload_unchanged:true}}:{enabled:true,mode:'observed-versions',current_versions:{dsp:option.dsp,cpu:mismatch?'2.10.21.28':option.cpu}}};
  const context=vm.createContext({$,configuration,AbortController,Blob,TextDecoder,Uint8Array,atob,JSON,Array,
   selectionLimit:()=>10,normalizeConfiguration:structuredClone,prepareZoomConfigurationForBuild,validateZoomControls(){},versionUnlockSnapshot:()=>normalizeVersionUnlock(option),assertVersionUnlockReceipt,
   invalidate(){},setBusy:v=>busyChanges.push(v),message:(...args)=>messages.push(args),jsonResponse:async r=>r.json(),
   crypto:{subtle:{digest:async()=>new Uint8Array([170]).buffer}},
   URL:{createObjectURL:()=>{created.push('url');return 'blob:test';}},
   post:async(path,body)=>{calls.push({path,body:structuredClone(body)});if(path.endsWith('/prepare')){option.cpu='2.10.21.29';return {json:async()=>({configuration_sha256:'hash'})};}return {ok:true,blob:async()=>new Blob(['candidate']),headers:{get:()=>Buffer.from(JSON.stringify(receipt)).toString('base64')}};}
  });
  $('#bin-link').click=()=>{};
  vm.runInContext("let busy=false,project='official',sourceModel='gr3',abort=null,urls=[];"+independent.slice(independent.indexOf("$('#build').onclick=async()=>"),independent.indexOf('(async()=>{try{const [status,catalog]')),context);
  await $('#build').onclick();return {calls,created,busyChanges,messages};
 }
 const h=await run();assert.equal(h.calls.length,2);assert.deepEqual(h.calls[0].body.version_unlock,h.calls[1].body.version_unlock);
 assert.equal(h.calls[1].body.version_unlock.cpu,'2.10.21.27');assert.equal(h.created.length,2);assert.deepEqual(h.busyChanges,[true,false]);
 const bad=await run(true);assert.equal(bad.created.length,0);assert.match(bad.messages.at(-1)[0],/版本回读/);
 const simple=await run(false,true);assert.deepEqual(simple.calls[0].body.version_unlock,{enabled:true,mode:'dsp-package-only'});assert.deepEqual(simple.calls[0].body.version_unlock,simple.calls[1].body.version_unlock);assert.equal(simple.created.length,2);
 const badSimple=await run(true,true);assert.equal(badSimple.created.length,0);assert.match(badSimple.messages.at(-1)[0],/模式回读/);
});

test('DSP-package-only mode needs no unknown version numbers and requires matching receipt mode',()=>{
 const input={enabled:true,mode:'dsp-package-only'};
 assert.deepEqual(normalizeVersionUnlock(input),input);
 assert.doesNotThrow(()=>assertVersionUnlockReceipt({enabled:true,mode:'dsp-package-only',checks:{cpu_payload_unchanged:true}},input));
 for(const receipt of [{enabled:true},{enabled:false},{enabled:true,current_versions:{dsp:'2.10.21.40',cpu:'2.10.21.27'}}])assert.throws(()=>assertVersionUnlockReceipt(receipt,input),/回读/);
 assert.deepEqual(normalizeVersionUnlock(input,'gr3x'),input);
});
test('GR IIIx control handlers default to DSP package mode and only require known versions after explicit advanced opt-in',()=>{
 for(const [source,prefix,declarations,end] of [[studio,'',"let chosenModel='gr3x',saving=false,activeBuildController=null;",'function renderLedger()'],[independent,'#native-',"let sourceModel='gr3x',busy=false;",'function segment(']]){
  const $=nodes(),context=vm.createContext({$,state:{profile:'native'},normalizeVersionUnlock});
  const key=s=>prefix+s;
  $(key('version-unlock')).checked=true;
  vm.runInContext(declarations+source.slice(source.indexOf('function versionUnlockSnapshot()'),source.indexOf(end)),context);
  assert.equal(context.renderVersionUnlock(),true);
  assert.deepEqual(JSON.parse(JSON.stringify(context.versionUnlockSnapshot())),{enabled:true,mode:'dsp-package-only'});
  assert.equal($(key('version-known-fields')).hidden,true);
  for(const k of ['dsp','cpu']){assert.equal($(key('version-'+k)).disabled,true);assert.equal($(key('version-'+k)).required,false);}
  $(key('version-known')).checked=true;assert.equal(context.renderVersionUnlock(),false);assert.match($(key('version-error')).textContent,/四段/);
  $(key('version-dsp')).value='1.60.11.18';$(key('version-cpu')).value='1.60.11.17';
  assert.equal(context.renderVersionUnlock(),true);assert.deepEqual(JSON.parse(JSON.stringify(context.versionUnlockSnapshot())),{enabled:true,dsp:'1.60.11.18',cpu:'1.60.11.17'});
  for(const k of ['dsp','cpu'])assert.equal($(key('version-'+k)).required,true);
  $(key('version-known')).checked=false;assert.equal(context.renderVersionUnlock(),true);assert.equal(context.versionUnlockSnapshot().mode,'dsp-package-only');
 }
});

test('actual studio default-mode requests contain no guessed CPU or DSP and reject a receipt from another mode',async()=>{
 const h=studioHarness({simple:true});await h.context.prepare();await h.context.build();
 assert.deepEqual(h.calls[0].body.version_unlock,{enabled:true,mode:'dsp-package-only'});assert.deepEqual(h.calls[0].body.version_unlock,h.calls[1].body.version_unlock);assert.equal(h.downloads.length,1);
 const bad=studioHarness({simple:true,mismatch:true});await bad.context.prepare();await bad.context.build();assert.equal(bad.downloads.length,0);assert.match(bad.$('build-result').textContent,/模式回读/);
});

test('advanced receipt rejects a DSP-only or missing mode even with matching forged current_versions',()=>{
 const input={enabled:true,dsp:'2.10.21.40',cpu:'2.10.21.27'},current_versions={dsp:input.dsp,cpu:input.cpu};
 for(const mode of [undefined,'dsp-package-only'])assert.throws(()=>assertVersionUnlockReceipt({enabled:true,mode,current_versions,checks:{cpu_payload_unchanged:true}},input),/模式回读/);
});
test('DSP-only receipt must explicitly attest unchanged CPU payload',()=>{
 const input={enabled:true,mode:'dsp-package-only'};
 for(const checks of [undefined,{}, {cpu_payload_unchanged:false},{cpu_payload_unchanged:'true'}])assert.throws(()=>assertVersionUnlockReceipt({enabled:true,mode:'dsp-package-only',checks},input),/CPU.*回读/);
});


test('GR IIIx advanced controls validate its line and receipt against an explicit model',()=>{
 const option={enabled:true,dsp:'1.60.11.18',cpu:'1.60.11.17'};
 assert.deepEqual(normalizeVersionUnlock(option,'gr3x'),option);
 assert.doesNotThrow(()=>assertVersionUnlockReceipt({enabled:true,mode:'observed-versions',current_versions:{dsp:option.dsp,cpu:option.cpu}},option,'gr3x'));
 assert.throws(()=>normalizeVersionUnlock(option,'gr3'));
});

test('GR IIIx ledger exposes debug mode and forwards its enabled state in native mode',()=>{
 const $=nodes();$('plan-ledger').replaceChildren=()=>{};$('plan-ledger').append=()=>{};
 const context=vm.createContext({$,state:{profile:'native',features:new Set(['film']),nativeConfig:{slots:[]},nativeCatalog:[],unresolvedSlots:[],projectId:'x'},document:{createElement:()=>({append(){}})},textNode:()=>({}),renderVersionUnlock:()=>true,renderFeatureCount(){},powerImages:{setEnabled(){},setModel(){},getConfiguration:()=>({})}});
 vm.runInContext("let chosenModel='gr3x',modelLabel='GR IIIx',activeBuildController=null,saving=false,debugMode=true;"+studio.slice(studio.indexOf('const debugEnabled='),studio.indexOf('\n\nconst $'))+studio.slice(studio.indexOf('function renderLedger()'),studio.indexOf('function textNode(')),context);
 context.renderLedger();assert.equal($('debug-option').hidden,false);assert.equal(vm.runInContext('debugEnabled()',context),true);
});


test('GR IIIx actual prepare and build preserve the 1.60 advanced snapshot and verify its receipt',async()=>{
 const h=studioHarness({model:'gr3x'});await h.context.prepare();await h.context.build();
 assert.equal(h.calls.length,2);assert.deepEqual(h.calls[0].body.version_unlock,{enabled:true,dsp:'1.60.11.18',cpu:'1.60.11.17'});
 assert.deepEqual(h.calls[1].body.version_unlock,h.calls[0].body.version_unlock);assert.equal(h.downloads.length,1);
});

test('studio freezes power images with the same preparation snapshot and preserves them for GR IIIx',async()=>{
 const powerConfiguration={startup:{jpeg_base64:'initial-cropped-jpeg'}};const h=studioHarness({powerConfiguration});
 await h.context.prepare();powerConfiguration.startup.jpeg_base64='later-cropped-jpeg';await h.context.build();
 assert.deepEqual(h.calls[0].body.power_images,h.calls[1].body.power_images);assert.equal(h.calls[1].body.power_images.startup.jpeg_base64,'initial-cropped-jpeg');
 const x=studioHarness({model:'gr3x',powerConfiguration});await x.context.prepare();assert.deepEqual(x.calls[0].body.power_images,powerConfiguration);
});

test('disabled power-image switch omits retained images from the actual prepared request',async()=>{
 const h=studioHarness({powerEnabled:false,powerConfiguration:{startup:{jpeg_base64:'retained-draft'}}});
 await h.context.prepare();assert.deepEqual(h.calls[0].body.power_images,{});
 assert.equal(h.calls[0].body.ab_enabled,false);
});

test('changing configuration while response bytes arrive suppresses stale binary and completion',async()=>{const h=studioHarness({duringBody:state=>{state.revision++;}});await h.context.prepare();await h.context.build();assert.equal(h.downloads.length,0);assert.equal(h.completed.length,0);});
