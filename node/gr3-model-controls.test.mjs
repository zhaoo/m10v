import test from 'node:test';
import assert from 'node:assert/strict';
import {renderZoomControls} from '../web/gr3/zoom-controls.mjs';
import {defaultConfiguration,prepareZoomConfigurationForBuild} from '../web/gr3/native-library-state.mjs';
class Element{
 constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.children=[];this.attributes={};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];}
 setAttribute(k,v){this.attributes[k]=v;}
 all(tag){return this.children.filter(n=>n instanceof Element).flatMap(n=>[...(n.tag===tag?[n]:[]),...n.all(tag)]);}
}
test('both models expose the same two editable crop controls with correct lens units',()=>{
 for(const [model,min,max,defaults] of [['gr3',28,50,[35,50]],['gr3x',40,71,[50,71]]]){
  const doc={createElement:tag=>new Element(tag,doc)},root=new Element('section',doc),c=defaultConfiguration(model);c.zoom.write=true;
  let updated;renderZoomControls(root,c,model,value=>updated=value);
  assert.equal(root.hidden,false);const fields=root.all('input').filter(e=>e.type==='number');
  assert.equal(fields.length,2);assert.deepEqual(fields.map(e=>Number(e.value)),defaults);
  for(const field of fields){assert.equal(Number(field.min),min);assert.equal(Number(field.max),max);assert.equal(field.disabled,false);}
  fields[0].value=String(min+1);fields[0].setCustomValidity=()=>{};fields[0].onchange();assert.equal(updated.zoom.slots[0],min+1);
  const prepared=prepareZoomConfigurationForBuild(c,model,{getRandomValues(a){a[0]=7;return a;}});assert.equal(prepared.zoom.revision,7);
 }
});
test('restoring a GR III draft on IIIx uses the normalized editor state for the build',async()=>{
 const {readFileSync}=await import('node:fs');const vm=await import('node:vm');
 const {configurationForModel}=await import('../web/gr3/native-library-state.mjs');
 const {normalizeWorkbenchDraft}=await import('../web/gr3/workbench-state.mjs');
 const source=readFileSync(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 const original=defaultConfiguration();original.zoom.write=true;
 const state={nativeConfig:defaultConfiguration('gr3x'),nativeCatalog:[],unresolvedSlots:[]},restoreErrors=[];let editor=state.nativeConfig;
 const ctx=vm.createContext({state,chosenModel:'gr3x',localStorage:{getItem:()=>JSON.stringify({profile:'native',features:['film'],nativeConfiguration:original})},draftKey:'draft',preserveLegacyDraft(){},normalizeWorkbenchDraft,powerImages:null,
 nativeEditor:{setConfiguration(c){editor=configurationForModel(c,'gr3x');state.nativeConfig=editor;},getConfiguration:()=>editor,setUnresolved(){}},notice(message,error){if(error)restoreErrors.push(message);},editHistory:{restore(){}},historyConfiguration(){return {};},updateHistoryButtons(){}});
 vm.runInContext('let restoringHistory=false,draftPersistenceAllowed=true;'+source.slice(source.indexOf('function restoreDraft()'),source.indexOf('function invalidate(')),ctx);
 ctx.restoreDraft();assert.deepEqual(restoreErrors,[]);assert.deepEqual(state.nativeConfig.zoom.slots,[50,71]);assert.equal(state.nativeConfig.zoom.write,true);
});
