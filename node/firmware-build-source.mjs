// The uploaded original is the only build source. Feature-specific ABI checks
// must reject unsupported layouts; selecting an older image is never a fallback.
import {inspectFirmwareImport} from './firmware.mjs';

export async function resolveBuildSource(uploaded) {
 const imported=inspectFirmwareImport(uploaded);
 const build_source={
  model:imported.model,public_version:imported.public_version,internal_version:imported.internal_version,
  sha256:imported.sha256,imported_sha256:imported.sha256,
  imported_public_version:imported.public_version,imported_internal_version:imported.internal_version,
  normalized:false,
 };
 return {source:Buffer.from(uploaded),report:{...imported,build_source}};
}
