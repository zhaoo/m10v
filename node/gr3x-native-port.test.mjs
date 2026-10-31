import test from 'node:test';
import assert from 'node:assert/strict';
import {nativePortTestSupport as t,portNativeToGr3x,verifyGr3xNativePort} from './gr3x-native-port.mjs';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
const layout=[{name:'RTOS',size:80},{name:'CPU',size:48},{name:'ICONBIN',size:48},{name:'RES',size:48}];
function image({x=false,growth=0,patch=false}={}){
 const blocks=layout.map(({name,size})=>{const n=size+(name==='RTOS'?growth:0),b=Buffer.alloc(n);b.write(name);b.writeUInt32LE(7,8);b.writeUInt32LE(n-16,12);
  if(name==='RTOS'){b.writeUInt32LE(x?609:588,24);if(patch)b.writeUInt32LE(0xea000001,40);if(growth)b.fill(0xab,size);}
  if(name==='CPU')b.fill(x?0x61:0x4c,16);return b;});
 const decoded=Buffer.concat([...blocks,Buffer.alloc(4)]);t.repair(decoded);
 const header=Buffer.alloc(128);header.writeUInt32LE(x?609:588,48);header.writeUInt32LE(x?0x02610261:0x024c024c,120);
 const h=Buffer.alloc(2);h.writeUInt16BE(0x8000|decoded.length);const payload=Buffer.concat([h,decoded,Buffer.alloc(2)]),footer=Buffer.alloc(24);footer.writeUInt32LE(x?609:588);footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(decoded.length,16);
 const bytes=Buffer.concat([header,payload,Buffer.alloc(-(128+payload.length)&3),footer]);t.repair(bytes);return bytes;
}
function setup(){const g=image(),x=image({x:true}),c=image({growth:32,patch:true});return {g,x,c,a:t.read(g,layout),b:t.read(x,layout),p:t.read(c,layout)};}
test('generated native growth fixture ports patches/tail and preserves full X CPU, model word and identity',()=>{
 const {g,x,c,a,b,p}=setup(),intent=t.expected(a,b,p),{candidate}=t.pack(c,p,intent.target,x),r=t.read(candidate,layout);
 assert.equal(intent.growth,32);assert.equal(intent.words.length,1);assert.equal(r.sections.RTOS.payload.readUInt32LE(8),609);
 assert.equal(r.sections.RTOS.payload.readUInt32LE(24),0xea000001);assert.ok(r.sections.RTOS.payload.subarray(64).every(v=>v===0xab));
 assert.ok(r.sections.CPU.block.equals(b.sections.CPU.block));assert.ok(r.sections.ICONBIN.block.equals(p.sections.ICONBIN.block));
 assert.ok(candidate.subarray(0,128).equals(x.subarray(0,128)));assert.ok(candidate.subarray(-24,-12).equals(x.subarray(-24,-12)));
 assert.ok(r.decoded.equals(intent.target));assert.equal(sum32(candidate),0);assert.equal(sum32(r.decoded),0);assert.ok(!g.equals(x));
});
test('model-word overlap and unrelated CPU/RES edits fail closed',()=>{
 for(const name of ['RTOS','CPU','RES']){const {a,b,p}=setup();p.sections[name].block[name==='RTOS'?24:20]^=1;assert.throws(()=>t.expected(a,b,p),name==='RTOS'?/overlaps model/:/unrelated section/);}
});
test('candidate resource edits carry over without copying stock G CPU',()=>{
 const {x,c,a,b,p}=setup();p.sections.ICONBIN.payload[3]=0x84;const intent=t.expected(a,b,p),r=t.read(t.pack(c,p,intent.target,x).candidate,layout);
 assert.equal(r.sections.ICONBIN.payload[3],0x84);assert.ok(r.sections.CPU.block.equals(b.sections.CPU.block));
});
test('history-dependent compressed frame must be replaced after prior model change',()=>{
 // Two frames: literal 64 bytes then 16-byte backreference to earlier model data.
 const first=Buffer.alloc(64,0x33),h=Buffer.alloc(2);h.writeUInt16BE(0x8040);
 const compressed=Buffer.from([0,7,0xc0,0,7,16,6,0,0]); // flags: copy offset16 len16, terminator
 const payload=Buffer.concat([h,first,compressed,Buffer.alloc(2)]),footer=Buffer.alloc(24);footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(80,16);
 const base=Buffer.concat([Buffer.alloc(128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);t.repair(base);
 const r=decodeFrameMap(base,80),target=Buffer.from(r.decoded);target[48]=0x55;
 const packed=t.pack(base,r,target,base);assert.equal(packed.replaced_frames,2);assert.ok(decodeFrameMap(packed.candidate,80).decoded.equals(target));
});
test('public APIs reject fabricated official identities',()=>{
 const {g,x,c}=setup();assert.throws(()=>portNativeToGr3x(g,x,c),/container: project mismatch/);assert.throws(()=>verifyGr3xNativePort(g,x,c,c),/container: project mismatch/);
});
