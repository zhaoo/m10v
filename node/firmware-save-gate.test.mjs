import test from 'node:test';import assert from 'node:assert/strict';
import {createFirmwareSaveGate} from '../web/gr3/firmware-save-gate.mjs';
function fixture(save,canSave=()=>true){
 const node=()=>({handlers:{},disabled:false,focused:false,addEventListener(k,fn){this.handlers[k]=fn;},focus(){this.focused=true;}});
 const dialog={...node(),open:false,showModal(){this.open=true;},close(){this.open=false;this.handlers.close?.();}};
 const trigger=node(),cancel=node(),confirm=node();let snapshot={revision:1,project:'gr3'};
 const gate=createFirmwareSaveGate({dialog,trigger,cancel,confirm,readSnapshot:()=>snapshot,save,canSave});
 return {gate,dialog,trigger,cancel,confirm,change:()=>snapshot={revision:2,project:'gr3x'}};
}
test('cancel and Escape never invoke save; risk confirmation is required for every attempt',async()=>{
 const calls=[],f=fixture(async s=>calls.push(s));f.gate.open();assert.ok(f.cancel.focused);f.cancel.handlers.click();assert.equal(calls.length,0);assert.equal(f.dialog.open,false);
 f.gate.open();f.dialog.handlers.cancel();f.dialog.close();assert.equal(calls.length,0);
 f.gate.open();await f.confirm.handlers.click();assert.deepEqual(calls,[{revision:1,project:'gr3'}]);assert.ok(f.trigger.focused);
 f.gate.open();assert.ok(f.dialog.open);assert.equal(calls.length,1);
});
test('changed source or settings invalidate the open confirmation',async()=>{
 let calls=0;const f=fixture(async()=>calls++);f.gate.open();f.change();await f.confirm.handlers.click();assert.equal(calls,0);assert.equal(f.dialog.open,false);
});
test('repeated confirmation cannot start concurrent firmware builds',async()=>{
 let calls=0,finish;const f=fixture(()=>{calls++;return new Promise(r=>finish=r);});f.gate.open();const pending=f.confirm.handlers.click();
 f.gate.open();await f.confirm.handlers.click();assert.equal(calls,1);assert.equal(f.dialog.open,false);assert.ok(f.confirm.disabled);finish();await pending;assert.equal(f.confirm.disabled,false);
});
test('a failed save requires fresh confirmation on the next attempt',async()=>{
 let calls=0;const f=fixture(async()=>{calls++;throw Error('failed build');});f.gate.open();await assert.rejects(f.confirm.handlers.click(),/failed build/);f.gate.open();assert.ok(f.dialog.open);assert.equal(calls,1);
});
test('camera mismatch blocks download even if confirmation is triggered programmatically',async()=>{
 let ready=false,calls=0;const f=fixture(async()=>calls++,()=>ready);
 f.gate.open();assert.equal(f.confirm.disabled,true);
 await f.confirm.handlers.click();assert.equal(calls,0);
 ready=true;f.gate.refresh();assert.equal(f.confirm.disabled,false);
 ready=false;await f.confirm.handlers.click();assert.equal(calls,0);
 ready=true;f.gate.refresh();await f.confirm.handlers.click();assert.equal(calls,1);
});
test('a second download trigger uses the same confirmation and receives focus back',async()=>{
 let calls=0;const f=fixture(async()=>calls++),backup={disabled:false,focused:false,focus(){this.focused=true;}};
 f.trigger.disabled=true;f.gate.open(backup);assert.equal(f.dialog.open,true);
 f.cancel.handlers.click();assert.equal(calls,0);assert.equal(backup.focused,true);
});
test('the real official-backup button requests confirmation before making any download',async()=>{
 const {readFile}=await import('node:fs/promises'),{default:vm}=await import('node:vm');
 const source=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 const block=source.slice(source.indexOf("$('download-backup').addEventListener"),source.indexOf("$('prepare-build').addEventListener"));
 const node={addEventListener(type,handler){this[type]=handler;}},events=[];
 vm.runInNewContext(block,{$:()=>node,state:{projectId:'official'},gr4Workbench:false,notice(){},api:async()=>{events.push('api');throw Error('unexpected direct download');},download:async()=>events.push('download'),requestFirmwareDownload:(kind,trigger)=>events.push({kind,correctTrigger:trigger===node})});
 await node.click();assert.deepEqual(events,[{kind:'backup',correctTrigger:true}]);
});

test('the real studio save callback authorizes after preflight and revokes acceptance afterward',async()=>{
 const {readFile}=await import('node:fs/promises'),{default:vm}=await import('node:vm');
 const source=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 const block=source.slice(source.indexOf('const firmwareSaveGate='),source.indexOf("$('cancel-build').addEventListener"));
 async function run(mode){
  const state={revision:1,projectId:'official',source:{model:'GR IIIx',public_version:'1.60'},preparation:null},events=[];let options;
  const node={textContent:'',addEventListener(){}};
  const ctx=vm.createContext({gr4Workbench:false,state,$:()=>node,renderLedger(){},createFirmwareSaveGate:value=>(options=value,{open(){}}),prepare:async()=>{events.push('prepare');state.preparation=mode==='not-ready'?null:{};if(mode==='seed')state.revision++;const revision=state.revision;if(mode==='changed')state.revision++;return state.preparation?revision:undefined;},build:async()=>{assert.equal(vm.runInContext('riskAcceptedRevision',ctx),state.revision);events.push('build');}});
  vm.runInContext('let saving=false,riskAcceptedRevision=-1;'+block,ctx);
  await options.save({revision:1,project:'official'});
  assert.equal(vm.runInContext('riskAcceptedRevision',ctx),-1);assert.equal(vm.runInContext('saving',ctx),false);
  return events;
 }
 assert.deepEqual(await run('ready'),['prepare','build']);assert.deepEqual(await run('seed'),['prepare','build']);assert.deepEqual(await run('not-ready'),['prepare']);assert.deepEqual(await run('changed'),['prepare']);
});
