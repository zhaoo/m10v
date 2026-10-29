import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {defaultConfiguration,normalizeExtensions} from '../web/gr3/native-library-state.mjs';
import {prepareNative,generateNative} from './gr3-native-library.mjs';
const source=readFileSync(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url));

test('native extensions have a strict complete configuration without accepting unrelated controls',()=>{
 assert.deepEqual(normalizeExtensions(),{aspect:false,level:false,negativeGrain:false,rawNr:{mode:'stock'}});
 assert.deepEqual(normalizeExtensions({aspect:true,level:true,negativeGrain:true}),{aspect:true,level:true,negativeGrain:true,rawNr:{mode:'stock'}});
 for(const value of [null,{aspect:true},{aspect:1,level:false,negativeGrain:false},{aspect:false,level:false,negativeGrain:false,timestamp:true}])assert.throws(()=>normalizeExtensions(value));
});
test('one accepted plan binds native slots, timestamp, aspect, level and native negative grain',async()=>{
 const c=defaultConfiguration();c.stamp=2;c.slots[4].grain=2;
 const plain=prepareNative(source,c),extensions={aspect:true,level:true,negativeGrain:true};
 const joined=prepareNative(source,c,{extensions});
 assert.deepEqual(joined.extensions,{...extensions,rawNr:{mode:'stock'}});
 assert.deepEqual(joined.configuration,c);
 assert.notEqual(joined.configuration_sha256,plain.configuration_sha256);
 assert.ok(joined.features.includes('aspect')&&joined.features.includes('level')&&joined.features.includes('negativeGrain'));
 await assert.rejects(()=>generateNative(source,c,plain.configuration_sha256,{extensions}),/变化/);
 const x=readFileSync(new URL('../bin/fwdc243b-gr3x-official.bin',import.meta.url));
 assert.deepEqual(prepareNative(x,c,{extensions}).extensions,joined.extensions);
 assert.throws(()=>prepareNative(source,c,{extensions,live_color:false}),/颗粒.*GR III/);
 const supported=structuredClone(c);supported.slots[4].grain=0;
 assert.deepEqual(prepareNative(x,supported,{extensions}).extensions,prepareNative(source,supported,{extensions}).extensions);
});

test('final joined firmware contains all selected components and rejects repaired-checksum tampering',async()=>{
 const {decodeFrameMap,sum32}=await import('./gr3-frames.mjs');
 const {auditIntegratedNative}=await import('./gr3-integrated-components.mjs');
 const config=defaultConfiguration();config.slots[4].grain=2;config.stamp=2;
 const extensions={aspect:true,level:true,negativeGrain:true};
 const plan=prepareNative(source,config,{extensions});
 const result=await generateNative(source,config,plan.configuration_sha256,{extensions});
 assert.deepEqual(result.receipt.extensions,{...extensions,rawNr:{mode:'stock'}});
 assert.equal(result.manifest.base,0x540be000);
 assert.ok(result.receipt.composition.verified);
 const resourceLast=result.manifest.resources.last_id;
 assert.equal(result.receipt.composition.aspect_resource_id,resourceLast+1);
 assert.equal(result.receipt.composition.native_resource_range[0],786);
 assert.equal(result.receipt.composition.native_resource_range[1],resourceLast);
 assert.equal(sum32(result.candidate),0);
 const d=decodeFrameMap(result.candidate,result.candidate.readUInt32LE(result.candidate.length-8)).decoded;
 let at=0;while(d.toString('ascii',at,at+4)!=='RTOS')at+=16+d.readUInt32LE(at+12);
 // Independent opcode expectations follow the current native resource table.
 for(const address of [0x540b8a4c,0x540b8a6c,0x540b8c14])assert.equal(d.readUInt32LE(at+16+address-0x53000000),(0xe3003000|resourceLast)>>>0);
 assert.equal(d.readUInt32LE(at+16+0x540b9448-0x53000000),(0xe3000000|(resourceLast+1))>>>0);
 for(const address of [0x540b8a18,0x540b8be4])assert.equal(d.readUInt32LE(at+16+address-0x53000000),(0xe300c000|(resourceLast+1))>>>0);
 assert.equal(d.readUInt32LE(at+16+0xb348c0),10);
 assert.equal(d.subarray(at+16+0xb3501e,at+16+0xb35020).toString('hex'),'020f');
 assert.deepEqual(auditIntegratedNative(source,result.candidate,result.nativeCandidate,result.runtime,result.manifest,result.component,extensions),result.receipt.composition);
 const damaged=Buffer.from(result.candidate);damaged[200]^=1;
 damaged.writeUInt32LE(0,damaged.length-4);damaged.writeUInt32LE(-sum32(damaged)>>>0,damaged.length-4);
 assert.throws(()=>auditIntegratedNative(source,damaged,result.nativeCandidate,result.runtime,result.manifest,result.component,extensions));
});

test('library selection retains composable tools and refuses unsupported combinations without dropping options',async()=>{
 const {withNativeLibrary}=await import('../web/gr3/native-library-state.mjs');
 assert.deepEqual(withNativeLibrary(['aspect','level','negativeGrain','timestamp']),['film','timestamp','aspect','level','negativeGrain']);
 assert.deepEqual(withNativeLibrary(['film','aspect','level']),['film','aspect','level']);
 assert.throws(()=>withNativeLibrary(['recipes','aspect']),/配方|组合/);
});

test('native transition synchronizes timestamp and clears GR III-only tools on model switch',async()=>{
 const {nativeSelection}=await import('../web/gr3/native-library-state.mjs');
 const c=defaultConfiguration();
 assert.equal(nativeSelection(['timestamp','aspect'],c,'gr3').configuration.stamp,1);
 assert.equal(nativeSelection(['aspect'],{...c,stamp:2},'gr3').configuration.stamp,0);
 const x=nativeSelection(['film','timestamp','aspect','level','negativeGrain'],{...c,stamp:2},'gr3x');
 assert.deepEqual(x.features,['film','timestamp','aspect','level','negativeGrain']);
 assert.equal(x.configuration.stamp,2);
});


test('RAW NR plans bind all modes and reject unknown model addresses',()=>{
 const flags={aspect:false,level:false,negativeGrain:false},c=defaultConfiguration();
 const plans=['stock','off','threshold'].map(mode=>prepareNative(source,c,{extensions:{...flags,rawNr:mode==='threshold'?{mode,iso:6400}:{mode}}}));
 assert.equal(new Set(plans.map(p=>p.configuration_sha256)).size,3);
 assert.ok(plans[1].features.includes('rawNr'));assert.ok(!plans[0].features.includes('rawNr'));
 const x=readFileSync(new URL('../bin/fwdc243b-gr3x-official.bin',import.meta.url));
 assert.equal(prepareNative(x,c).filename,'fwdc243b.bin');
 assert.equal(prepareNative(x,c,{extensions:{...flags,rawNr:{mode:'off'}}}).extensions.rawNr.mode,'off');
 for(const rawNr of [null,{mode:'threshold',iso:6300},{mode:'off',iso:6400},{mode:'stock',extra:1}])assert.throws(()=>normalizeExtensions({...flags,rawNr}));
});

test('native RAW NR export independently reads back off and threshold together with old extensions',async()=>{
 const {decodeFrameMap,sum32}=await import('./gr3-frames.mjs');
 const {auditIntegratedNative,composeNative}=await import('./gr3-integrated-components.mjs');
 const {planRawNr}=await import('./gr3-raw-nr.mjs');
 const config=defaultConfiguration(),flags={aspect:true,level:true,negativeGrain:true};
 // Build the ARM/native image once; composition tests reuse it for each isolated RAW mode.
 const plan=prepareNative(source,config,{extensions:flags});
 const base=await generateNative(source,config,plan.configuration_sha256,{extensions:flags});
 for(const rawNr of [{mode:'stock'},{mode:'off'},{mode:'threshold',iso:6400}]){
  const extensions={...flags,rawNr};
  const result=composeNative(source,base.nativeCandidate,base.runtime,base.manifest,base.component,extensions);
  const d=decodeFrameMap(result.candidate,result.candidate.readUInt32LE(result.candidate.length-8)).decoded;
  let at=0;while(d.toString('ascii',at,at+4)!=='RTOS')at+=16+d.readUInt32LE(at+12);
  for(const e of planRawNr(source,rawNr))assert.equal(d.subarray(at+16+e.offset,at+16+e.offset+e.replacementHex.length/2).toString('hex'),e.replacementHex);
  assert.deepEqual(result.composition.raw_nr.configuration,rawNr);
  assert.equal(result.composition.raw_nr.patch_count,planRawNr(source,rawNr).length);
  assert.equal(result.composition.raw_nr.jpeg_nr,'stock');
  assert.equal(sum32(result.candidate),0);
  assert.deepEqual(auditIntegratedNative(source,result.candidate,base.nativeCandidate,base.runtime,base.manifest,base.component,extensions),result.composition);
  if(rawNr.mode!=='stock')assert.throws(()=>auditIntegratedNative(source,result.candidate,base.nativeCandidate,base.runtime,base.manifest,base.component,flags),/bytes differ/);
 }
});
