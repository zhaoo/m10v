// Emergency website restriction. Offline research/builders remain available.
import {createHash} from 'node:crypto';
export const RELEASE_BASELINES=Object.freeze({
 gr3:'d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4',
 gr3x:'708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7',
});
export const firmwareReleasePolicy=Object.freeze({
 uploads_allowed:false,locked_models:['gr4','gr2'],baselines:{gr3:'2.10',gr3x:'1.60'},
 blocked_firmware:{gr3:['2.20'],gr3x:['1.70']},
 message:'GR III 2.20 的 M10V 改包已永久停用。普通工作台仅支持内置 GR III 2.10 / GR IIIx 1.60，GR IV / GR II 固件导出已暂停。官方 2.20 / 1.70 可通过「更多 → 二阶降级」回到对应官方基线。普通入口不接受自定义 BIN 或修改版本号绕过。',
});
export function releaseRequestLocked(url){
 if(/^\/api\/gr[24](?:\/|$)/.test(url))return true;
 if(['/api/import','/api/backup/restore'].includes(url))return true;
 if(/^\/api\/projects\/[^/]+\/bridge(?:\/|$)/.test(url))return true;
 const project=/^\/api\/projects\/([^/]+)/.exec(url);
 return !!project&&!Object.values(RELEASE_BASELINES).includes(project[1]);
}
export function requireReleaseBaseline(bytes,model){
 const digest=createHash('sha256').update(bytes).digest('hex');
 if(model?RELEASE_BASELINES[model]!==digest:!Object.values(RELEASE_BASELINES).includes(digest))
  throw Error(firmwareReleasePolicy.message);
 return bytes;
}
