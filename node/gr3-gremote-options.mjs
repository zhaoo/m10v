import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {prepareNative} from './gr3-native-library.mjs';
import {companionSourceFingerprint} from './gr3-companion-owner.mjs';
import {sha256} from './gr3-fit-binding.mjs';

const officialHash='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
let cameraMetadata;
function readCameraMetadata(){
 if(cameraMetadata)return cameraMetadata;
 // Isolate SD catalog initialization. Ordinary builds never load it and the
 // long-lived parent only retains the two hashes.
 const output=execFileSync(process.execPath,[
  fileURLToPath(new URL('../scripts/read_gr3_gremote_camera_metadata.mjs',import.meta.url)),
 ],{encoding:'utf8',timeout:30000,maxBuffer:4096});
 const {catalogHash,rendererHash}=JSON.parse(output);
 if(![catalogHash,rendererHash].every(value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value)))
  throw Error('Invalid GRemote camera catalog identity');
 return cameraMetadata=Object.freeze({catalogHash,rendererHash});
}

export function resolveGRemoteOptions(source,input={},sourceModel){
 for(const field of ['companion_identity','preserve_existing'])if(Object.hasOwn(input,field))throw Error('公开 GRemote 构建不接受私有身份或升级存档策略。');
 if(input.gremote_enabled!==undefined&&typeof input.gremote_enabled!=='boolean')throw Error('GRemote 连接开关必须为布尔值');
 if(input.gremote_preserve_settings!==undefined&&typeof input.gremote_preserve_settings!=='boolean')throw Error('GRemote 保留机内设置开关必须为布尔值');
 if(input.gremote_enabled!==true)return {};
 if(sourceModel!=='GR III'||sha256(source)!==officialHash)throw Error('GRemote 连接仅支持精确官方 GR III 2.10；GR IIIx 暂不支持。');
 if((input.film_library??true)!==true||(input.appended_slots??true)!==true||(input.live_color??true)!==true)throw Error('GRemote 连接需要 GR III 十槽胶卷库与原生色调预览管线。');
 const names=['debug_mode','extensions','version_unlock','film_library','hdf_enabled','live_color','appended_slots','halation_enabled','border_enabled','ab_enabled','pure_isp_effects'];
 const ordinaryOptions=Object.fromEntries(names.filter(name=>input[name]!==undefined).map(name=>[name,input[name]]));
 const base=prepareNative(source,input.configuration,ordinaryOptions);
 const preserve_existing=input.gremote_preserve_settings??true;
 const gremoteCameraMetadata=readCameraMetadata();
 const buildId=sha256({schema:'m10v-public-companion-build/v2',configurationSha256:base.configuration_sha256,
  preserveExisting:preserve_existing,companionSourceSha256:companionSourceFingerprint(),...gremoteCameraMetadata,powerImages:input.power_images??{}});
 return {companion_identity:{buildId,...gremoteCameraMetadata},...(preserve_existing?{preserve_existing:true}:{})};
}
