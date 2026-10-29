// Package an already audited prepareNative/generateNative build, binding it to
// the exact current source/configuration. No camera, network or publishing.
import {readFile,mkdir,writeFile,stat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import path from 'node:path';
import {readNativeOfficial,prepareNative} from '../node/gr3-native-library.mjs';
import {decodeFrameMap} from '../node/gr3-frames.mjs';
import {auditGr3Candidate} from '../node/gr3-candidate-audit.mjs';
import {MAX_NATIVE_RTOS_GROWTH} from '../node/gr3-native-budget.mjs';
import {buildSdFilmPack,auditSdFilmPack} from '../node/gr3-sd-film-pack.mjs';
import {encodeZip} from '../node/gr3-sd-film-export.mjs';

const run=promisify(execFile),sha=b=>createHash('sha256').update(b).digest('hex');
const json=x=>Buffer.from(JSON.stringify(x,null,2)+'\n');
const input=path.resolve(process.argv[2]||'builds/gr3-half-frame-r2-20261029');
const read=async n=>JSON.parse(await readFile(path.join(input,n),'utf8'));
const [receipt,manifest,configuration,options,bin,runtime]=await Promise.all([
 read('receipt.json'),read('manifest.json'),read('configuration.json'),read('options.json'),
 readFile(path.join(input,'fwdc239b.bin')),readFile(path.join(input,'runtime.bin'))]);
const debug=options.debug_mode===true;
const name=debug?'M10V-GR3-HalfFrame-TEST-20261029-r3-debug':'M10V-GR3-HalfFrame-TEST-20261029-r2';
const output=path.resolve(process.argv[3]||'builds/'+name);
try{await stat(output);throw Error('Output directory exists; choose a new directory');}catch(e){if(e.code!=='ENOENT')throw e;}
const source=await readNativeOfficial('gr3'),plan=prepareNative(source,configuration,options);
if(receipt.debug_mode!==debug||receipt.model!=='GR III'||receipt.public_version!=='2.10'||receipt.candidate_sha256!==sha(bin)||
 receipt.configuration_sha256!==plan.configuration_sha256||receipt.runtime_source_sha256!==plan.runtime_source_sha256||
 receipt.integration_source_sha256!==plan.integration_source_sha256||!receipt.composition?.verified||
 receipt.composition.half_frame?.enabled!==true||receipt.composition.half_frame.raw_id!==6||
 manifest.camera_model!=='gr3'||manifest.code_sha256!==sha(runtime)||manifest.debug_mode!==debug||!manifest.hdf_adj||
 !manifest.appended_slots||!manifest.universal_halation||!manifest.border?.pixel_pipeline_enabled)throw Error('Candidate provenance/features differ');
if(debug&&(!manifest.debug_log||manifest.debug_log.build_id!==plan.debug_log?.build_id||
 JSON.stringify(manifest.debug_log.files)!==JSON.stringify(plan.debug_log.files)||manifest.debug_log.adj_exit_trace))throw Error('Diagnostic logger/readback differs');
const sources={};
for(const [file,hash]of Object.entries(manifest.sources)){
 const bytes=await readFile(file);if(sha(bytes)!==hash)throw Error('Source changed since build: '+file);sources[file]=bytes;
}
for(const file of ['native/gr3/m10v_aspect.c','native/gr3/m10v_aspect_hooks.S','native/gr3/m10v_aspect_dng.c',
 'native/gr3/m10v_aspect_config.h','scripts/gr3_aspect_overlay.py','node/gr3-integrated-components.mjs',
 'node/gr3-native-library.mjs','node/gr3-runtime-worker.py','node/gr3-runtime.mjs','node/gr3-m10v-native-build.mjs',
 'node/gr3-native-budget.mjs','scripts/build_gr3_half_frame_candidate.mjs','scripts/package_gr3_half_frame_candidate.mjs','tests/test_gr3_half_frame.py',
 'tests/test_gr3_aspect.py','tests/test_gr3_aspect_dng.py','tests/test_gr3_aspect_indicator_final.py',
 'docs/superpowers/specs/2026-10-29-gr3-half-frame-design.md','docs/testing/gr3-half-frame-20261029.md',
 ...(debug?['docs/testing/gr3-half-frame-debug-20261029.md','scripts/read_gr3_debug_log.py']:[])])sources[file]=await readFile(file);
const structure=auditGr3Candidate(source,bin,{minRtosGrowth:0,maxRtosGrowth:MAX_NATIVE_RTOS_GROWTH});
const decoded=decodeFrameMap(bin,bin.readUInt32LE(bin.length-8)).decoded;
const rtos=decoded.subarray(0x10870,0x10870+decoded.readUInt32LE(0x1086c));
if(!rtos.subarray(manifest.base-0x53000000,manifest.base-0x53000000+runtime.length).equals(runtime))throw Error('Final runtime readback differs');
const halfRecord=manifest.base; // The overlay precedes this native module.
const marker=Buffer.from('41374648','hex'),at=rtos.indexOf(marker,0x10bc000);
if(at<0||at+12>halfRecord-0x53000000||rtos.indexOf(marker,at+1)!==-1||
 rtos.readUInt32LE(at+4)!==receipt.composition.half_frame.resource_id||rtos.readUInt32LE(at+8)!==875)throw Error('Half-frame final binding differs');
const pack=buildSdFilmPack();auditSdFilmPack(pack);
const provenance={candidate:name,status:'WAITING_FOR_USER_VALIDATION',model:'GR III',firmware:'2.10',camera_tested:false,
 created_at:new Date().toISOString(),base_commit:'38a847b5871e2441a7934fafd38dcee50d4faef4',
 git_revision:(await run('git',['rev-parse','HEAD'])).stdout.trim(),
 git_status:(await run('git',['status','--short'])).stdout.trim().split('\n').filter(Boolean),
 official_sha256:sha(source),bin_sha256:sha(bin),runtime_sha256:sha(runtime),sd_sha256:sha(pack),
 configuration_sha256:plan.configuration_sha256,runtime_source_sha256:plan.runtime_source_sha256,
 integration_source_sha256:plan.integration_source_sha256,source_files:Object.fromEntries(Object.entries(sources).map(([p,b])=>[p,sha(b)])),
 debug_mode:debug,debug_log:manifest.debug_log,offline_checks:structure,
 actual_models:debug?['gr3 diagnostic candidate']:['gr3','gr3x compile-gate regression only'],
 skipped_models:debug?['gr3x/gr4: GR III diagnostic configuration only']:['gr4: no consumers changed']};
const files={'README.md':await readFile(debug?'docs/testing/gr3-half-frame-debug-20261029.md':'docs/testing/gr3-half-frame-20261029.md'),
 'gr3/fwdc239b.bin':bin,'gr3/receipt.json':json(receipt),'gr3/manifest.json':json(manifest),
 'gr3/configuration.json':json(configuration),'gr3/options.json':json(options),
 'SD/M10V/FILMS.M10':pack,'evidence/provenance.json':json(provenance),'evidence/source-snapshot.zip':encodeZip(sources)};
for(const p of ['LICENSE','THIRD_PARTY_NOTICES.md','third_party/curated-film-luts/LICENSE','third_party/spectral-film-lut/LICENSE'])files[p]=await readFile(p);
for(const name of (debug?['half-frame-final-artifact-r3-debug.log','half-frame-pipeline-r3-debug.log',
 'half-frame-logger-r3-debug.log','half-frame-installed-logger-r3-debug.log','half-frame-debug-plan-r3.log','half-frame-debug-overflow-r3.log','half-frame-node-r3-debug.log',
 'half-frame-final-node-failures-r3-debug.txt']:['half-frame-final-artifact-r2.log','half-frame-pipeline-r2.log','half-frame-source-r2.log',
 'half-frame-node-r2.log','half-frame-baseline-node-failures.txt','half-frame-final-node-failures-r2.txt','half-frame-gr3x-gate-r2.log','half-frame-review.md','half-frame-border-regression-r2.log','half-frame-border-node-r2.log','half-frame-border-geometry-r2.log'])){
 files['evidence/'+name]=await readFile('builds/'+name);
}
if(debug){
 files['tools/read_gr3_debug_log.py']=await readFile('scripts/read_gr3_debug_log.py');
 files['evidence/r2-feature-validation.md']=await readFile('docs/testing/gr3-half-frame-20261029.md');
}
files.SHA256SUMS=Buffer.from(Object.entries(files).map(([p,b])=>sha(b)+'  '+p).join('\n')+'\n');
await mkdir(output,{recursive:false});
for(const[p,b]of Object.entries(files)){const dest=path.join(output,p);await mkdir(path.dirname(dest),{recursive:true});await writeFile(dest,b);}
const zip=encodeZip(files);await writeFile(path.join(output,name+'.zip'),zip);
await writeFile(path.join(output,'SHA256SUMS'),files.SHA256SUMS.toString()+sha(zip)+'  '+name+'.zip\n');
console.log(JSON.stringify({output,zip:path.join(output,name+'.zip'),zip_sha256:sha(zip),bin_sha256:sha(bin),camera_tested:false,status:provenance.status},null,2));
