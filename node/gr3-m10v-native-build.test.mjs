import test from 'node:test';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { buildNativeLibrary, auditNativeLibrary } from './gr3-m10v-native-build.mjs';
import { decodeFrameMap } from './gr3-frames.mjs';
import {MAX_NATIVE_RTOS_GROWTH} from './gr3-native-budget.mjs';

const source = readFileSync(new URL('../bin/fwdc239b-gr3-official.bin', import.meta.url));

test('M10V native library builds from official bytes without a compatibility runtime and audits every patch', async () => {
  const folder = await mkdtemp(path.join(tmpdir(), 'm10v-native-build-'));
  try {
    const manifest = JSON.parse(execFileSync(process.env.M10V_PYTHON || new URL('../.venv/bin/python', import.meta.url).pathname,
      ['scripts/build_gr3_m10v_library.py', '--out', folder], {cwd:new URL('..', import.meta.url).pathname}));
    const runtime = await readFile(path.join(folder, 'm10v-library-arm.bin'));
    const result = buildNativeLibrary(source, runtime, manifest);
    assert.deepEqual(result.receipt.changed_sections, ['RTOS']);
    assert.equal(result.receipt.camera_tested, false);
    assert.equal(result.receipt.film_count, 103);
    assert.equal(result.receipt.external_film_pack, false);
    assert.deepEqual(auditNativeLibrary(source, result.candidate, runtime, manifest), result.receipt);
    // Data appended to the valid runtime must not hit an arbitrary byte ceiling.
    const largeRuntime=Buffer.concat([runtime,Buffer.alloc(8192)]);
    const largeManifest={...manifest,code_bytes:largeRuntime.length,code_sha256:createHash('sha256').update(largeRuntime).digest('hex')};
    const large=buildNativeLibrary(source,largeRuntime,largeManifest);
    assert.ok(largeRuntime.length>runtime.length);
    assert.deepEqual(auditNativeLibrary(source,large.candidate,largeRuntime,largeManifest),large.receipt);

    // Reproduce the website's observed RTOS extent independently of compiler
    // padding; appended ROM data still receives full mapping and byte audits.
    const serverGrowth=1156188,ceiling=MAX_NATIVE_RTOS_GROWTH;
    const withGrowth=growth=>{
      const bytes=Buffer.concat([runtime,Buffer.alloc(growth-result.receipt.rtos_growth)]);
      return [bytes,{...manifest,code_bytes:bytes.length,code_sha256:createHash('sha256').update(bytes).digest('hex')}];
    };
    const [serverRuntime,serverManifest]=withGrowth(serverGrowth);
    const serverResult=buildNativeLibrary(source,serverRuntime,serverManifest);
    assert.equal(serverResult.receipt.rtos_growth,serverGrowth);
    assert.deepEqual(auditNativeLibrary(source,serverResult.candidate,serverRuntime,serverManifest),serverResult.receipt);
    const [overflowRuntime,overflowManifest]=withGrowth(ceiling+16);
    assert.throws(()=>buildNativeLibrary(source,overflowRuntime,overflowManifest),/RTOS growth invalid/);

    const decoded = decodeFrameMap(result.candidate, result.candidate.readUInt32LE(result.candidate.length - 8)).decoded;
    assert.ok(decoded.includes(Buffer.from('M10V3A.bin')));
    assert.ok(!runtime.includes(Buffer.from('GRLIFE')));
    assert.deepEqual(manifest.detail.ids,[18,19,20,28,29]);
    assert.equal(manifest.detail.backend,'m10v_camera_library_detail');
    // Updating an untrusted manifest hash cannot authorize arbitrary shim code.
    assert.deepEqual(manifest.isp_base.carriers,[12,18,19,20,21]);
    for(const name of Object.keys(manifest.isp_base.entries)) {
      const modified=Buffer.from(runtime);modified[manifest.isp_base.entries[name]-manifest.base+32]^=1;
      assert.throws(()=>buildNativeLibrary(source,modified,{...manifest,code_sha256:createHash('sha256').update(modified).digest('hex')}),/ISP instruction differs/);
    }
    const changedRow=Buffer.from(runtime);changedRow[manifest.detail.entries.row_dispatch-manifest.base+32]^=1;
    assert.throws(()=>buildNativeLibrary(source,changedRow,{...manifest,code_sha256:createHash('sha256').update(changedRow).digest('hex')}),/detail instruction differs/);
    const changedDetail=Buffer.from(runtime);
    changedDetail[manifest.detail.entries.callback-manifest.base]^=1;
    const changedManifest={...manifest,code_sha256:createHash('sha256').update(changedDetail).digest('hex')};
    assert.throws(()=>buildNativeLibrary(source,changedDetail,changedManifest),/detail instruction differs/);
    const changedCaption=Buffer.from(runtime);
    changedCaption.writeUInt16LE(866,manifest.detail.captions-manifest.base+72);
    assert.throws(()=>buildNativeLibrary(source,changedCaption,{...manifest,code_sha256:createHash('sha256').update(changedCaption).digest('hex')}),/detail caption differs/);
    for(const [address,pattern] of [[manifest.detail.slider_dispatch,/slider selector differs/],
      [manifest.detail.variant_tables.red+4,/detail count differs/]]){
      const modified=Buffer.from(runtime);modified[address-manifest.base]^=1;
      assert.throws(()=>buildNativeLibrary(source,modified,{...manifest,code_sha256:createHash('sha256').update(modified).digest('hex')}),pattern);
    }
    const damaged = Buffer.from(result.candidate); damaged[200] ^= 1;
    assert.throws(() => auditNativeLibrary(source, damaged, runtime, manifest));
    const wrongRuntime = Buffer.from(runtime); wrongRuntime[0] ^= 1;
    assert.throws(() => buildNativeLibrary(source, wrongRuntime, manifest), /hash|摘要/);
    const changedSource = Buffer.from(source); changedSource[200] ^= 1;
    assert.throws(() => buildNativeLibrary(changedSource, runtime, manifest));
  } finally { await rm(folder, {recursive:true, force:true}); }
});
