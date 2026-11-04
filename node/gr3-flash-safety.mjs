// Host-only evidence. No result from this module authorizes a camera write.
import {createHash} from 'node:crypto';
import {inspectOfficial,inspectFirmwareImport} from './firmware.mjs';
import {requireReleaseBaseline} from './firmware-release-policy.mjs';
import {prepareNative,generateNative} from './gr3-native-library.mjs';

const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const need=(ok,message)=>{if(!ok)throw Error(message);};
const remaining=[
 'Current model/version/provenance are user declarations; camera Flash and component versions were not read.',
 'Existing camera settings, third-party menu/state migrations, SD health and power have not been verified.',
 'Full camera update, boot, shooting and hardware recovery have not been verified for these exact bytes.',
];

export async function auditFlashInputs({source,candidate,receipt,expectedSha256,camera={}}={}){
 const report={schema:'m10v-flash-safety/v1',status:'rejected',installation_allowed:false,
  camera_tested:false,camera_information:'user_declared_unverified',checks:{},reasons:[],
  remaining_device_checks:[...remaining]};
 try{
  need(Buffer.isBuffer(source),'source: official source bytes are required');
  try{requireReleaseBaseline(source);}catch{throw Error('source: only exact official GR III 2.10 / IIIx 1.60 are admitted; anniversary, modified and unknown sources are blocked');}
  const official=inspectOfficial(source),model=official.model==='GR III'?'gr3':'gr3x';
  report.source={model,version:official.public_version,sha256:official.sha256};
  report.checks.pinned_source=true;
  need(camera.model===model,'camera model: missing or different from the official source');
  need(camera.version===official.public_version,'camera version: anniversary, unknown and different versions are blocked; do not downgrade');
  need(['official','m10v-verified'].includes(camera.origin),'camera provenance: unknown or third-party firmware is blocked even if its public version matches');
  if(camera.origin==='m10v-verified'){
   // A matching public version cannot identify the already installed runtime.
   need(/^[a-f0-9]{64}$/.test(camera.installedSha256||''),'camera provenance: a previously recorded installed M10V BIN SHA-256 is required');
  }
  report.camera={...camera};
  need(Buffer.isBuffer(candidate)&&candidate.length>0,'candidate: candidate BIN bytes are required');
  need(!candidate.equals(source),'candidate: unchanged official input is not a custom M10V candidate');
  const digest=sha(candidate);report.candidate_sha256=digest;
  need(/^[a-f0-9]{64}$/.test(expectedSha256||''),'candidate: independently recorded download SHA-256 is required; a receipt is not an authenticated signature');
  need(digest===expectedSha256,'candidate: download SHA-256 mismatch');report.checks.download_digest=true;
  need(receipt&&receipt.schema==='m10v-gr3-native-library-candidate/v2','candidate receipt: missing or unsupported native build receipt');
  need(receipt.source_sha256===official.sha256&&receipt.model===official.model&&receipt.public_version===official.public_version,'candidate receipt: source/model/version differs');
  need(receipt.candidate_sha256===digest&&receipt.candidate_bytes===candidate.length,'candidate receipt: candidate digest or length differs');
  need(!receipt.native_target&&!receipt.version_unlock?.enabled,'candidate: relocated targets and raised package versions are blocked');
  const decoded=inspectFirmwareImport(candidate);
  need(decoded.model===official.model&&decoded.internal_version===official.internal_version,'candidate: component versions differ from the pinned source; version spoofing is blocked');
  report.checks.strict_candidate_decode=true;
  need(receipt.configuration&&typeof receipt.configuration==='object','candidate receipt: configuration missing');
  need(!!receipt.features?.includes('companion')===!!receipt.companion_identity,'candidate receipt: companion identity missing or inconsistent');
  need(receipt.preserve_existing===undefined||typeof receipt.preserve_existing==='boolean','candidate receipt: preserve_existing must be boolean');
  const options={companion_identity:receipt.companion_identity,preserve_existing:receipt.preserve_existing??false,extensions:receipt.extensions,version_unlock:{enabled:false},
   film_library:receipt.film_library_enabled!==false,hdf_enabled:!!receipt.digital_hdf,
   live_color:receipt.live_color,appended_slots:!!receipt.appended_slots,
   halation_enabled:receipt.halation_enabled,border_enabled:receipt.border_enabled,
   ab_enabled:receipt.ab_enabled,debug_mode:receipt.debug_mode,adj_exit_trace:receipt.debug_log?.adj_exit_trace??false,pure_isp_effects:receipt.pure_isp_effects===true};
  const plan=prepareNative(source,receipt.configuration,options);
  need(plan.configuration_sha256===receipt.configuration_sha256&&
   plan.runtime_source_sha256===receipt.runtime_source_sha256&&
   plan.integration_source_sha256===receipt.integration_source_sha256,
  'candidate receipt: stale or altered source/configuration fingerprint; use its exact reviewed source checkout');
  report.checks.configuration_and_current_sources=true;
  // Existing generators validate preimages, full MMU extent, runtime, unchanged
  // partitions, hooks and final readback. Temporary compilation is intentional;
  // no supplied input, SD or camera is written; no final BIN is exported.
  const rebuilt=await generateNative(source,receipt.configuration,plan.configuration_sha256,options);
  need(rebuilt.candidate.equals(candidate),'candidate: exact rebuild mismatch; repaired checksums and a matching public version are insufficient');
  need(rebuilt.receipt.runtime_sha256===receipt.runtime_sha256,'candidate receipt: runtime hash differs from exact rebuild');
  report.checks.exact_rebuild=true;
  report.status='offline_verified_camera_unverified';
 }catch(error){report.reasons.push(error.message);}
 return report;
}
