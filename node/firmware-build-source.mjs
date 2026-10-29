// Uploaded originals remain immutable. Patches only target a verified per-model
// build baseline, never an unported firmware's addresses.
import {inspectFirmwareImport} from './firmware.mjs';
import {updateCompatibilityPlan} from './gr3-version-unlock.mjs';
import {readModelOfficial} from './model-firmware.mjs';

export async function resolveBuildSource(uploaded) {
 const imported=inspectFirmwareImport(uploaded);
 const model=imported.model==='GR III'?'gr3':'gr3x';
 const source=await readModelOfficial(model),baseline=inspectFirmwareImport(source);
 if(baseline.model!==imported.model)throw Error('构建基线与上传包机型不一致');
 const build_source={
  model:baseline.model,public_version:baseline.public_version,internal_version:baseline.internal_version,
  sha256:baseline.sha256,imported_sha256:imported.sha256,
  imported_public_version:imported.public_version,imported_internal_version:imported.internal_version,
  normalized:baseline.sha256!==imported.sha256,
 };
 const compatibility=updateCompatibilityPlan(build_source);
 if(compatibility)build_source.update_compatibility=compatibility;
 return {source,report:{...imported,build_source}};
}
