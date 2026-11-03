import {readFileSync} from 'node:fs';
import {nativeCatalog,prepareNative} from './gr3-native-library.mjs';
import {companionSourceFingerprint} from './gr3-companion-owner.mjs';
import {sdFilmRecord} from './gr3-sd-film-pack.mjs';
import {sha256} from './gr3-fit-binding.mjs';

const officialHash='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
const contract=JSON.parse(readFileSync(new URL('../contracts/companion-v1.json',import.meta.url)));
const catalog=await nativeCatalog();
// Match GRemote's sync_m10v_contract + sync_camera_contract metadata, without
// importing the phone renderer or any private pairing material.
const cameraCatalog={schemaVersion:1,rendererHash:sdFilmRecord(33).subarray(8448,8480).toString('hex'),entries:catalog.films.map(f=>({
 id:f.id,name:f.name,group:f.group,icon:`assets/films/camera-icons/${f.id}.png`,
 parameters:Object.fromEntries(Object.entries(contract.parameters).filter(([,p])=>(!p.filmIds||p.filmIds.includes(f.id))&&!p.excludeFilmIds?.includes(f.id)).map(([key,p])=>[key,{min:p.min,max:p.overrides?.[f.id]??p.max,default:p.default,label:p.label}])),
 approximation:f.approximation??false,
}))};
export const gremoteCameraMetadata=Object.freeze({catalogHash:sha256(cameraCatalog),rendererHash:cameraCatalog.rendererHash});

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
 const buildId=sha256({schema:'m10v-public-companion-build/v2',configurationSha256:base.configuration_sha256,
  preserveExisting:preserve_existing,companionSourceSha256:companionSourceFingerprint(),...gremoteCameraMetadata,powerImages:input.power_images??{}});
 return {companion_identity:{buildId,...gremoteCameraMetadata},...(preserve_existing?{preserve_existing:true}:{})};
}
