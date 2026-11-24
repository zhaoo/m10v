import test from 'node:test';
import assert from 'node:assert/strict';
import {installReleaseBufferCollection} from './release-buffer-budget.mjs';

test('collection preserves firmware buffer bytes, slices, concat and allocation errors',()=>{
 const methods={alloc:Buffer.alloc,allocUnsafe:Buffer.allocUnsafe,from:Buffer.from};
 let collections=0;
 const restore=installReleaseBufferCollection(()=>collections++,4);
 try{
  assert.deepEqual([...Buffer.alloc(4,0x7b)],[123,123,123,123]);
  const raw=new Uint8Array([1,2,3,4,5,6]).buffer;
  assert.deepEqual([...Buffer.from(raw,2,3)],[3,4,5]);
  const source=Buffer.from([7,8,9,10]),copy=Buffer.from(source);
  source.fill(0);assert.deepEqual([...copy],[7,8,9,10]);
  assert.deepEqual([...Buffer.concat([copy,Buffer.from([11])])],[7,8,9,10,11]);
  assert.equal(Buffer.allocUnsafe(8).length,8);
  assert.throws(()=>Buffer.alloc(-1),RangeError);
  assert.ok(collections>=5);
 }finally{restore();restore();}
 for(const [name,method] of Object.entries(methods))assert.equal(Buffer[name],method);
});

test('collection is guarded against reentrant allocations',()=>{
 let calls=0;
 const restore=installReleaseBufferCollection(()=>{calls++;Buffer.alloc(4);},4);
 try{Buffer.alloc(4);assert.equal(calls,1);}finally{restore();}
});
