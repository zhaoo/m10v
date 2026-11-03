import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {nativeSelection} from '../web/gr3/native-library-state.mjs';
const app=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
const method=app.slice(app.indexOf('async function importSource('),app.indexOf('async function download('));
function harness(model='gr3'){
 const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{value:'gr3',hidden:true,disabled:true,textContent:'',append(){},replaceChildren(){}});return nodes.get(id);};
 const state={profile:'native',features:new Set(['film']),nativeConfig:{slots:[{film:33}]},projectId:'',source:null};
 let imported;const calls=[],messages=[],texts=[];
 const context=vm.createContext({gr4Workbench:model==='gr4',nativeApi:'/api/'+model+'/native-library',nativeSelection,nativeEditor:{setModel(){},setConfiguration(c){state.nativeConfig=c;}},state,$:node,document:{title:'',createElement:()=>({append(){}}),querySelector:()=>node('hero')},notice:(...v)=>messages.push(v),invalidate(){},renderFeatures(){},showStep(){},showSettingsTab(){},textNode:(tag,text)=>{texts.push(text);return node('text');},
 api:async(path,options={})=>{calls.push({path,options});return {json:async()=>path.endsWith('import-official')?(model==='gr4'?{...imported,project_id:imported.sha256}:{project_id:imported.sha256}):path.endsWith('stock-presets')?[]:imported};}});
 vm.runInContext("let chosenModel='gr3';let modelLabel='GR III';"+app.slice(app.indexOf('function enterNativeSelection()'),app.indexOf('function renderFeatures()'))+method,context);
 const report=(model,sha)=>({model,sha256:sha.repeat(64),public_version:model==='GR IIIx'?'1.60':'2.10',internal_version:'test',size:100,sections:[{}]});
 return {state,nodes,node,calls,messages,texts,report,context,run:async(r,local=true)=>{imported=r;await context.importSource(local?null:{},local);}};
}
test('the same import handler accepts both models and updates target labels from official identity',async()=>{
 const h=harness();await h.run(h.report('GR IIIx','a'));
 assert.equal(h.state.source.model,'GR IIIx');assert.equal(vm.runInContext('chosenModel',h.context),'gr3x');assert.equal(h.node('build-model').textContent,'GR IIIx · 输出基线 1.60');
 const config=h.state.nativeConfig;await h.run(h.report('GR III','b'));
 assert.equal(h.state.source.model,'GR III');assert.equal(vm.runInContext('chosenModel',h.context),'gr3');assert.equal(h.node('build-model').textContent,'GR III · 输出基线 2.10');assert.equal(h.state.nativeConfig,config);
});
test('2.20 upload stays closed and cannot replace a verified ordinary baseline',async()=>{
 const h=harness();await h.run(h.report('GR III','b'),true);const previous=h.state.source;
 await h.run({...h.report('GR III','a'),public_version:'2.20'},false);
 assert.equal(h.state.source,previous);assert.equal(h.state.projectId,'b'.repeat(64));
 assert.match(h.messages.at(-1)[0],/上传已关闭/);
 assert.equal(h.calls.filter(call=>call.path==='/api/import').length,0);
});
test('local sample selection does not override the loaded target until import completes',async()=>{
 const h=harness();await h.run(h.report('GR IIIx','a'));h.node('local-source-model').value='gr3';
 assert.equal(vm.runInContext('chosenModel',h.context),'gr3x');await h.run(h.report('GR III','b'),true);
 const call=h.calls.find(c=>c.path.endsWith('import-official'));assert.equal(JSON.parse(call.options.body).model,'gr3');assert.equal(h.state.source.model,'GR III');
});
test('unsupported identity leaves the previous verified source and configuration intact',async()=>{
 const h=harness();await h.run(h.report('GR III','a'));const previous=h.state.source;await h.run(h.report('GR IV','b'));
 assert.equal(h.state.source,previous);assert.equal(vm.runInContext('chosenModel',h.context),'gr3');assert.match(h.messages.at(-1)[0],/仅支持/);
});


test('GR IIIx import preserves all selected native extensions',async()=>{
 const h=harness();h.state.features=new Set(['film','timestamp','aspect','level','negativeGrain','rawNr']);
 await h.run(h.report('GR IIIx','a'));
 assert.deepEqual([...h.state.features],['film','timestamp','aspect','level','negativeGrain','rawNr']);
});

test('switching to IIIx clears GR III-only GRemote without removing other choices',async()=>{
 const h=harness();h.state.features=new Set(['film','gremote','aspect','border']);
 await h.run(h.report('GR IIIx','a'));
 assert.deepEqual([...h.state.features],['film','aspect','border']);
});

test('GR IIIx native workflow does not fetch retired stock customization resources',async()=>{
 const h=harness();await h.run(h.report('GR IIIx','a'));
 assert.ok(!h.calls.some(c=>c.path.endsWith('/stock-presets')));
});
test('GR IIIx extension tab retains the native workflow',()=>{
 const node=()=>({setAttribute(){}}),context=vm.createContext({document:{querySelector:()=>({querySelector:()=>({})})},cinematicEditor:undefined,gr4Workbench:false,state:{profile:'native',features:new Set(['recipes'])},$:node,renderFeatures(){},invalidate(){},notice(){},enterNativeSelection(){}});
 vm.runInContext("let chosenModel='gr3x',settingsTab='library';"+app.slice(app.indexOf('function showSettingsTab('),app.indexOf("$('tab-imaging').onclick")),context);
 context.showSettingsTab('imaging');assert.equal(vm.runInContext('state.profile',context),'native');
});


test('GR IV import uses the shared workflow and isolated native endpoints',async()=>{
 const h=harness('gr4');await h.run(h.report('GR IV','c'),true);
 assert.equal(h.state.source.model,'GR IV');assert.equal(vm.runInContext('chosenModel',h.context),'gr4');
 assert.ok(h.calls.some(c=>c.path==='/api/gr4/native-library/import-official'));
 assert.ok(!h.calls.some(c=>c.path.endsWith('/stock-presets')));
});

test('paused GR IV backup cannot bypass the firmware download gate after confirmation',async()=>{
 let options,filename,message,calls=0;const state={revision:1,projectId:'a'.repeat(64)},node={addEventListener(){}};
 const ctx=vm.createContext({gr4Workbench:true,state,$:()=>node,createFirmwareSaveGate:value=>(options=value,{open(){}}),renderLedger(){},api:async()=>{calls++;return {};},download:async(response,name)=>{filename=name;},notice:value=>{message=value;}});
 const block=app.slice(app.indexOf('const firmwareSaveGate='),app.indexOf("$('cancel-build').addEventListener"));
 vm.runInContext('let saving=false,riskAcceptedRevision=-1,firmwareDownloadAction="backup";'+block,ctx);
 assert.equal(filename,undefined);
 await options.save({revision:1,project:state.projectId,action:'backup'});assert.equal(filename,undefined);assert.equal(calls,0);assert.match(message,/暂停/);
});

test('opening imaging settings preserves an HDF-only selection',()=>{
 const node=()=>({setAttribute(){}}),state={profile:'native',features:new Set(['digitalHdf'])};
 const context=vm.createContext({document:{querySelector:()=>({querySelector:()=>({})})},cinematicEditor:undefined,state,$:node,renderFeatures(){}});
 vm.runInContext("let settingsTab='library';"+app.slice(app.indexOf('function enterNativeSelection()'),app.indexOf('function renderFeatures()'))+app.slice(app.indexOf('function showSettingsTab('),app.indexOf("$('tab-imaging').onclick")),context);
 context.showSettingsTab('imaging');assert.equal(state.profile,'native');assert.deepEqual([...state.features],['digitalHdf']);
});
test('IIIx import retains shared HDF and halation selections',async()=>{
 const h=harness();h.state.features=new Set(['film','digitalHdf','halation']);
 await h.run(h.report('GR IIIx','d'));
 assert.deepEqual([...h.state.features],['film','digitalHdf','halation']);
});
