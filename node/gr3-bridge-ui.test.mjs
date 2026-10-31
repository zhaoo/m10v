import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {normalizeVersionUnlock} from '../web/gr3/version-unlock-state.mjs';
const studio=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
const independent=await readFile(new URL('../web/gr3/native-library.js',import.meta.url),'utf8');
function controls(source,model,standalone=false){
 const map=new Map(),$=id=>{if(!map.has(id))map.set(id,{checked:true,value:model==='gr3x'?'1.60.11.18':'2.10.21.40',disabled:false,hidden:false,textContent:''});return map.get(id);};
 $(standalone?'#native-version-known':'version-known').checked=false;
 const context=vm.createContext({$,state:{profile:'native'},normalizeVersionUnlock});
 const declarations=standalone?`let sourceModel='${model}',busy=false;`:`let chosenModel='${model}',saving=false,activeBuildController=null;`;
 const end=standalone?'function segment(':'function renderLedger()';
 vm.runInContext(declarations+source.slice(source.indexOf('function versionUnlockSnapshot()'),source.indexOf(end)),context);
 return {context,$};
}
test('GR III ignores retired adaptation in both workbench entries',()=>{
 for(const [source,standalone] of [[studio,false],[independent,true]]){
  const h=controls(source,'gr3',standalone);assert.equal(h.context.renderVersionUnlock(),true);
  assert.deepEqual(JSON.parse(JSON.stringify(h.context.versionUnlockSnapshot())),{enabled:false});
  assert.equal(h.$(standalone?'#native-version-unlock-option':'version-unlock-option').hidden,true);
 }
});
test('GR IIIx retains its separate opt-in version adaptation',()=>{
 const h=controls(studio,'gr3x');assert.equal(h.context.renderVersionUnlock(),true);
 assert.equal(h.$('version-unlock-option').hidden,false);assert.equal(h.context.versionUnlockSnapshot().mode,'dsp-package-only');
});
test('bridge entry and instructions are removed while backend capability remains',async()=>{
 for(const file of ['gr3/index.html','gr3/native-library.html','gr3/native-library-controls.html','gr2/native-library-controls.html','guide.html']){
  const html=await readFile(new URL('../web/'+file,import.meta.url),'utf8');
  assert.doesNotMatch(html,/bridge-open|bridge-dialog|native-bridge-guide|href="[^"]*#bridge"|固件桥接/);
 }
 const server=await readFile(new URL('./server.mjs',import.meta.url),'utf8');
 assert.match(server,/prepareGr3Bridge/);assert.match(server,/exportGr3Bridge/);
});
