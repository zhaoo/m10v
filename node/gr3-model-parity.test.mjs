import test from 'node:test';
import {FILM_DIRECTORY} from './gr3-film-directory.mjs';
import assert from 'node:assert/strict';
import {readNativeOfficial,prepareNative} from './gr3-native-library.mjs';
import {defaultConfiguration,selectNativeFilm} from '../web/gr3/native-library-state.mjs';
import {supportsNativeFilm} from '../web/gr3/model-capabilities.mjs';
const sources=await Promise.all(['gr3','gr3x'].map(readNativeOfficial));
const comparable=p=>Object.fromEntries(['capture_pipeline','live_color','features','appended_slots','slot_tone_ids','stock_detail','hdf_enabled','halation_enabled','initial_state_hex','scope'].map(k=>[k,p[k]]));
for(const [name,configure,options] of [
 ['default',c=>c,{}],
 ['native grain',c=>{c.slots[0].grain=3;return c;},{}],
 ['ten films',c=>{const shared=FILM_DIRECTORY.filter(f=>supportsNativeFilm('gr3x',f.id));c.slots=Array.from({length:10},(_,i)=>({...structuredClone(c.slots[0]),film:shared[i].id}));return c;},{}],
 ['HDF and universal halation',c=>({...c,hdf:2}),{halation_enabled:true}],
 ['standalone HDF',c=>({...c,hdf:1}),{film_library:false}],
 ...[294,306,307,308,309,310,311].map(id=>['ISP film '+id,c=>selectNativeFilm(c,0,id),{}])
])test('III and IIIx share '+name,()=>{
 const c=configure(defaultConfiguration());
 const plans=sources.map(s=>prepareNative(s,c,options));
 assert.deepEqual(comparable(plans[1]),comparable(plans[0]));
 assert.notEqual(plans[0].configuration_sha256,plans[1].configuration_sha256);
 assert.equal(plans[1].filename,'fwdc243b.bin');assert.equal(plans[1].model,'GR IIIx');
});
test('cross-model approvals and invalid shared options stay rejected',()=>{
 for(const source of sources){
  assert.throws(()=>prepareNative(source,defaultConfiguration(),{halation_enabled:true,live_color:false}),/光晕/);
  assert.throws(()=>prepareNative(source,defaultConfiguration(),{appended_slots:true,film_library:false}),/胶卷/);
 }
});
test('IIIx power images preserve its CPU and all unrelated decoded bytes',async()=>{
 const {preparePowerImages,applyPowerImages}=await import('./gr3-power-images.mjs');
 const {decodeFrameMap}=await import('./gr3-frames.mjs');
 const original=decodeFrameMap(sources[1]).decoded;
 const jpeg=original.subarray(59298689,59298689+112509).toString('base64');
 const images={shutdown:{jpeg_base64:jpeg}};
 assert.equal(preparePowerImages(sources[1],images).shutdown.supported,true);
 const {candidate,receipt}=applyPowerImages(sources[1],sources[1],images);
 assert.equal(receipt.non_target_bytes_unchanged,true);
 assert.equal(receipt.camera_tested,false);
 assert.equal(candidate.readUInt32LE(0x30),609);
 assert.equal(decodeFrameMap(candidate).decoded[0x10870+0xb2298c],65);
});
test('IIIx focal writes accept its full native lens range and reject wider-than-lens crops',()=>{
 const c=defaultConfiguration();c.zoom={write:true,slots:[50,71],revision:1};
 const plan=prepareNative(sources[1],c);
 assert.deepEqual(plan.zoom_seed.slots,[50,71]);
 assert.throws(()=>prepareNative(sources[0],c),/裁切焦距/);
 c.zoom.slots=[35,50];assert.throws(()=>prepareNative(sources[1],c),/裁切焦距/);
});
