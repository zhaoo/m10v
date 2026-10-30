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
import {CANDIDATE_NAME,BASE_COMMIT,LOG_FILES,auditHalfPair,validateChecks,packageReadme} from './gr3_half_frame_package_contract.mjs';

const run=promisify(execFile),sha=b=>createHash('sha256').update(b).digest('hex');
const json=x=>Buffer.from(JSON.stringify(x,null,2)+'\n');
const input=path.resolve(process.argv[2]||'builds/gr3-half-frame-r4-debug-20261030');
const read=async n=>JSON.parse(await readFile(path.join(input,n),'utf8'));
const [receipt,manifest,configuration,options,bin,runtime]=await Promise.all([
 read('receipt.json'),read('manifest.json'),read('configuration.json'),read('options.json'),
 readFile(path.join(input,'fwdc239b.bin')),readFile(path.join(input,'runtime.bin'))]);
const debug=options.debug_mode===true;
if(!debug)throw Error('r4 candidate requires diagnostic logging');
const name=CANDIDATE_NAME;
auditHalfPair(manifest,receipt,runtime);
const validation=await read('validation.json'),checks=validateChecks(validation);
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
 JSON.stringify(manifest.debug_log.files)!==JSON.stringify(plan.debug_log.files)||
 JSON.stringify(manifest.debug_log.files)!==JSON.stringify(LOG_FILES)||manifest.debug_log.adj_exit_trace))throw Error('Diagnostic logger/readback differs');
const sources={};
for(const [file,hash]of Object.entries(manifest.sources)){
 const bytes=await readFile(file);if(sha(bytes)!==hash)throw Error('Source changed since build: '+file);sources[file]=bytes;
}
for(const file of ['native/gr3/m10v_aspect.c','native/gr3/m10v_aspect_hooks.S','native/gr3/m10v_aspect_dng.c',
 'native/gr3/m10v_aspect_config.h','native/gr3/m10v_half_pair.c','native/gr3/m10v_half_pair.h',
 'native/gr3/m10v_half_pair_camera.c','native/gr3/m10v_half_pair_camera.h','scripts/gr3_aspect_overlay.py','node/gr3-integrated-components.mjs',
 'node/gr3-native-library.mjs','node/gr3-runtime-worker.py','node/gr3-runtime.mjs','node/gr3-m10v-native-build.mjs',
 'node/gr3-native-budget.mjs','scripts/build_gr3_half_frame_candidate.mjs','scripts/package_gr3_half_frame_candidate.mjs','scripts/gr3_half_frame_package_contract.mjs','scripts/gr3_half_frame_package_contract.test.mjs',
 'tests/test_gr3_half_pair_final.py','tests/test_gr3_half_encoded_policy.py','tests/test_gr3_half_live_callers.py','docs/testing/gr3-half-pair-r4-20261030.md',
 'tests/test_gr3_half_pair.py','tests/test_gr3_half_pair_camera.py','tests/test_gr3_aspect_full_callers.py','tests/test_gr3_half_frame.py',
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
 rtos.readUInt32LE(at+4)!==receipt.composition.half_frame.resource_id||rtos.readUInt32LE(at+8)!==876)throw Error('Half-frame final binding differs');
const pack=buildSdFilmPack();auditSdFilmPack(pack);
const provenance={candidate:name,status:'WAITING_FOR_USER_VALIDATION',model:'GR III',firmware:'2.10',camera_tested:false,
 created_at:new Date().toISOString(),base_commit:BASE_COMMIT,
 git_revision:(await run('git',['rev-parse','HEAD'])).stdout.trim(),
 git_status:(await run('git',['status','--short'])).stdout.trim().split('\n').filter(Boolean),
 official_sha256:sha(source),bin_sha256:sha(bin),runtime_sha256:sha(runtime),sd_sha256:sha(pack),
 configuration_sha256:plan.configuration_sha256,runtime_source_sha256:plan.runtime_source_sha256,
 integration_source_sha256:plan.integration_source_sha256,source_files:Object.fromEntries(Object.entries(sources).map(([p,b])=>[p,sha(b)])),
 debug_mode:debug,debug_log:manifest.debug_log,half_pair:manifest.half_pair,offline_checks:structure,validation,
 actual_models:debug?['gr3 diagnostic candidate']:['gr3','gr3x compile-gate regression only'],
 skipped_models:debug?['gr3x/gr4: GR III diagnostic configuration only']:['gr4: no consumers changed']};
const files={'README.md':Buffer.from(packageReadme({buildId:manifest.debug_log.build_id,binSha:sha(bin),officialSha:sha(source),checks})),
 'gr3/fwdc239b.bin':bin,'gr3/receipt.json':json(receipt),'gr3/manifest.json':json(manifest),
 'gr3/configuration.json':json(configuration),'gr3/options.json':json(options),
 'SD/M10V/FILMS.M10':pack,'evidence/provenance.json':json(provenance),'evidence/source-snapshot.zip':encodeZip(sources)};
for(const p of ['LICENSE','THIRD_PARTY_NOTICES.md','third_party/curated-film-luts/LICENSE','third_party/spectral-film-lut/LICENSE'])files[p]=await readFile(p);
for(const [i,check]of checks.entries()){
 const logPath=path.isAbsolute(check.log)?check.log:path.resolve(input,check.log);
 const content=await readFile(logPath);
 if(!content.length)throw Error('Empty validation log: '+check.name);
 const safe=String(i+1).padStart(2,'0')+'-'+path.basename(logPath);
 files['evidence/checks/'+safe]=content;
 check.packaged_log='evidence/checks/'+safe;check.log_sha256=sha(content);
}
files['evidence/validation.json']=json(validation);
files['evidence/provenance.json']=json(provenance);
files['tools/read_gr3_debug_log.py']=await readFile('scripts/read_gr3_debug_log.py');
files.SHA256SUMS=Buffer.from(Object.entries(files).map(([p,b])=>sha(b)+'  '+p).join('\n')+'\n');
await mkdir(output,{recursive:false});
for(const[p,b]of Object.entries(files)){const dest=path.join(output,p);await mkdir(path.dirname(dest),{recursive:true});await writeFile(dest,b);}
const zip=encodeZip(files);await writeFile(path.join(output,name+'.zip'),zip);
await writeFile(path.join(output,'SHA256SUMS'),files.SHA256SUMS.toString()+sha(zip)+'  '+name+'.zip\n');
console.log(JSON.stringify({output,zip:path.join(output,name+'.zip'),zip_sha256:sha(zip),bin_sha256:sha(bin),camera_tested:false,status:provenance.status},null,2));
