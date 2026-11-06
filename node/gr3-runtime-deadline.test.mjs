import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {runGr3Runtime} from './gr3-runtime.mjs';

test('GR III runtime separates build deadlines, keeps timeout and cancellation bounded',async()=>{
 const folder=await mkdtemp(join(tmpdir(),'m10v-gr3-deadline-'));
 const previous=process.env.M10V_PYTHON,previousRuntime=process.env.M10V_RUNTIME_PYTHON;
 try{
  const python=join(folder,'fake-python'),runtime=join(folder,'runtime');
  const {mkdir}=await import('node:fs/promises');
  await mkdir(join(runtime,'reconstruction/firmware_store'),{recursive:true});
  await writeFile(join(runtime,'reconstruction/firmware_store/browser_engine.py'),'# isolated test runtime\n');
  await writeFile(python,'#!/usr/bin/env python3\nimport sys,time,json\nfrom pathlib import Path\ntime.sleep(.15)\nPath(sys.argv[5]).write_bytes(b"candidate")\nprint(json.dumps({"ready":True}))\n',{mode:0o700});
  process.env.M10V_PYTHON=join(folder,'missing-build-python');
  process.env.M10V_RUNTIME_PYTHON=python;
  const source=await readFile(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url));
  for(const buildTimeoutMs of [0,Infinity,300_001])
   await assert.rejects(runGr3Runtime(source,{},'build',runtime,{buildTimeoutMs}),/invalid runtime timeout/);
  await assert.rejects(runGr3Runtime(source,{},'prepare',runtime,{timeoutMs:40,buildTimeoutMs:1500}),/timed out/);
  const result=await runGr3Runtime(source,{},'build',runtime,{timeoutMs:40,buildTimeoutMs:1500});
  assert.equal(result.candidate.toString(),'candidate');
  await assert.rejects(runGr3Runtime(source,{},'build',runtime,{buildTimeoutMs:40}),/timed out/);
  const cancel=new AbortController();const timer=setTimeout(()=>cancel.abort(),40);
  try{await assert.rejects(runGr3Runtime(source,{},'build',runtime,{signal:cancel.signal}),/操作已取消/);}finally{clearTimeout(timer);}
 }finally{
  if(previous===undefined)delete process.env.M10V_PYTHON;else process.env.M10V_PYTHON=previous;
  if(previousRuntime===undefined)delete process.env.M10V_RUNTIME_PYTHON;else process.env.M10V_RUNTIME_PYTHON=previousRuntime;
  await rm(folder,{recursive:true,force:true});
 }
});
