import {createHash} from 'node:crypto';

const exactSources=new Map([
 ['d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4','GR III'],
 ['708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7','GR IIIx'],
]);

// Use the source model already inspected by the upload route. A matching public
// version alone never enables native effects or substitutes uploaded bytes.
export function resolveIspEffectOptions(source,input={},sourceModel){
 if(input.pure_isp_effects!==undefined&&typeof input.pure_isp_effects!=='boolean')throw Error('纯 ISP 效果开关必须为布尔值');
 for(const name of ['hdf_enabled','border_enabled'])if(input[name]!==undefined&&typeof input[name]!=='boolean')throw Error('HDF 和边框开关必须为布尔值');
 const film_library=input.film_library??true;
 const eligible=film_library!==false&&exactSources.get(createHash('sha256').update(source).digest('hex'))===sourceModel&&['GR III','GR IIIx'].includes(sourceModel);
 const pure_isp_effects=input.pure_isp_effects??false;
 if(pure_isp_effects&&!eligible)throw Error('胶片效果菜单仅支持启用胶卷库的 GR III 2.10 / GR IIIx 1.60 官方固件');
 if(pure_isp_effects&&(input.hdf_enabled!==true||input.border_enabled!==true))throw Error('胶片效果菜单需要明确同时开启 HDF 模拟和边框功能');
 // This opt-in includes the HDF and border menus and their saved camera state.
 // Preserve every component choice; inclusion must be explicit for all three.
 return {
  debug_mode:input.debug_mode??false,extensions:input.extensions,version_unlock:input.version_unlock,
  film_library,hdf_enabled:input.hdf_enabled,
  halation_enabled:input.halation_enabled??false,border_enabled:input.border_enabled??false,
  ab_enabled:input.ab_enabled??false,appended_slots:input.appended_slots,
  live_color:input.live_color,pure_isp_effects,
 };
}
