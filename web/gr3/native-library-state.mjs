import {isGr3Family,modelCapabilities} from './model-capabilities.mjs';
// One catalogue and one selected-film contract for simulation and in-camera library.
export const defaultEffects=()=>({grainSize:0,leakGain:0,leakPosition:0,leakSpread:4,leakVariation:0,filmExposure:0});
export const defaultHalo=()=>({gain:0,spread:3,threshold:5,profile:2});
export const defaultConfiguration=(model='gr3')=>({slots:Array.from({length:5},(_,i)=>({film:i===4?33:34+i,grain:0,soft:0,halo:defaultHalo(),effects:defaultEffects()})),stamp:0,format:0,corner:0,color:0,filmNameStamp:false,hdf:0,zoom:{write:false,slots:[...(modelCapabilities(model).zoom?.defaults??[35,50])],revision:0}});
export function normalizeConfiguration(value=defaultConfiguration()){
 const exact=(obj,keys)=>obj&&typeof obj==='object'&&!Array.isArray(obj)&&Object.keys(obj).sort().join('|')===[...keys].sort().join('|');
 const int=(n,min,max)=>Number.isInteger(n)&&n>=min&&n<=max;
 const required=['slots','stamp','format','corner','color'],allowed=[...required,'hdf','filmNameStamp','zoom'];
 if(!value||typeof value!=='object'||Array.isArray(value)||required.some(k=>!Object.hasOwn(value,k))||Object.keys(value).some(k=>!allowed.includes(k))||!Array.isArray(value.slots)||value.slots.length>10)throw Error('需要完整的胶卷选择配置');
 const z=value.zoom===undefined?{write:false,slots:[35,50],revision:0}:value.zoom;
 if(!exact(z,['write','slots','revision'])||typeof z.write!=='boolean'||!Array.isArray(z.slots)||z.slots.length!==2||z.slots.some(n=>!int(n,28,71))||!int(z.revision,0,0xffffffff))throw Error('裁切焦距需要两档 28–71 mm 整数和有效写入标识');
 const zoom={write:z.write,slots:[...z.slots],revision:z.revision};
 const hdf=value.hdf===undefined?0:value.hdf;if(!int(hdf,0,3))throw Error('HDF 模拟档位无效');
 const slots=value.slots.map(s=>{
  if(!(exact(s,['film','grain','soft','halo'])||exact(s,['film','grain','soft'])||exact(s,['film','grain','soft','halo','effects']))||!(int(s.film,1,78)||(int(s.film,289,305)||int(s.film,309,317)))||!int(s.grain,0,3)||!int(s.soft,0,3))throw Error('胶卷或质感档位无效');
  const h=s.halo??defaultHalo();if(!exact(h,['gain','spread','threshold','profile'])||!int(h.gain,0,8)||!int(h.spread,0,8)||!int(h.threshold,0,8)||!int(h.profile,0,3))throw Error('胶卷光晕参数无效');
  const inputEffects=s.effects??defaultEffects(),oldKeys=['grainSize','leakGain','leakPosition','leakSpread','leakVariation'];
  if(!(exact(inputEffects,oldKeys)||exact(inputEffects,[...oldKeys,'filmExposure'])||(s.film===289&&exact(inputEffects,[...oldKeys,'filmExposure','charmeraColor']))))throw Error('胶卷质感参数无效');
  const e={...inputEffects,filmExposure:exact(inputEffects,oldKeys)?0:inputEffects.filmExposure};if(!int(e.filmExposure,0,2)||(s.film===67?e.filmExposure>1:s.film!==68&&e.filmExposure!==0)||!int(e.grainSize,0,2)||!int(e.leakGain,0,8)||!int(e.leakPosition,0,5)||!int(e.leakSpread,0,8)||!int(e.leakVariation,0,1))throw Error('胶卷质感参数无效');
  if(s.film===289){e.charmeraColor=inputEffects.charmeraColor??0;if(!int(e.charmeraColor,0,3))throw Error('Charmera 颜色无效');}
  return {film:s.film,grain:s.grain,soft:0,halo:{gain:h.profile===0?0:h.gain,spread:h.spread,threshold:h.threshold,profile:h.profile},effects:{...e,grainSize:0,leakGain:0,leakPosition:0,leakSpread:4,leakVariation:0}};
 });
 if(!int(value.stamp,0,2)||!int(value.format,0,3)||!int(value.corner,0,3)||!int(value.color,0,3)||(value.filmNameStamp!==undefined&&typeof value.filmNameStamp!=='boolean'))throw Error('时间戳配置无效');
 return {slots:slots.filter((s,i,list)=>list.findIndex(v=>v.film===s.film)===i),stamp:value.stamp,format:value.format,corner:value.corner,color:value.color,filmNameStamp:value.filmNameStamp??false,hdf,zoom};
}
// Explicit restoration migration; new exports still reject retired identities.
export function migrateRetiredFilms(value){
 if(!value||!Array.isArray(value.slots))return normalizeConfiguration(value);
 return normalizeConfiguration({...value,slots:value.slots.filter(s=>!(s?.film>=306&&s.film<=308))});
}
export function retainCatalogFilms(value,catalog){
 const configuration=migrateRetiredFilms(value),ids=new Set(catalog.map(f=>f.id));
 configuration.slots=configuration.slots.filter(s=>ids.has(s.film));return configuration;
}
export function migrateSimulationSelection(ids,texture,catalog,current=defaultConfiguration()){
 const configuration=normalizeConfiguration(current),unresolved=[];
 configuration.slots=[];
 ids.slice(0,10).forEach((id,index)=>{
  const entry=catalog.find(f=>f.legacy_id===id);
  if(!entry){unresolved.push({slot:index,id});return;}
  if(configuration.slots.some(s=>s.film===entry.id))return;
  configuration.slots.push({film:entry.id,grain:texture?.[id]?.grain??0,soft:0,halo:defaultHalo(),effects:defaultEffects()});
 });
 return {configuration:normalizeConfiguration(configuration),unresolved};
}

// Optional camera features share the native export; no implicit draft conversion.
export const rawNrThresholds=[400,800,1600,3200,5000,6400,8000,10000,12800];
export function normalizeRawNr(value={mode:'stock'}){
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!['mode','iso'].includes(k))||!['stock','off','threshold'].includes(value.mode)||
  (value.mode==='threshold'?!rawNrThresholds.includes(value.iso):value.iso!==undefined))throw Error('RAW 降噪配置或 ISO 阈值无效');
 return value.mode==='threshold'?{mode:value.mode,iso:value.iso}:{mode:value.mode};
}
export const defaultExtensions=()=>({aspect:false,level:false,negativeGrain:false,rawNr:{mode:'stock'}});
export function normalizeExtensions(value=defaultExtensions()){
 const keys=['aspect','level','negativeGrain'];
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>![...keys,'rawNr'].includes(k))||keys.some(k=>typeof value[k]!=='boolean'))throw Error('附加功能配置必须包含画幅、水平仪和负片颗粒开关');
 return {aspect:value.aspect,level:value.level,negativeGrain:value.negativeGrain,rawNr:normalizeRawNr(value.rawNr)};
}
export function activeExtensions(value){
 const e=normalizeExtensions(value);return ['aspect','level','negativeGrain'].filter(k=>e[k]).concat(e.rawNr.mode==='stock'?[]:['rawNr']);
}
export function withNativeLibrary(features){
 const allowed=['film','digitalHdf','timestamp','aspect','border','level','negativeGrain','rawNr'];
 if(!Array.isArray(features)||features.some(id=>!allowed.includes(id)))throw Error('胶卷库可组合边框、时间戳、画幅、水平仪、负片颗粒和 RAW 降噪；请先移除其他配方或工具');
 const selected=new Set(['film',...features]);return allowed.filter(id=>selected.has(id));
}

export function nativeSelection(features,configuration,model){
 const compatible=features;
 return {features:withNativeLibrary(compatible),configuration:{...configuration,stamp:compatible.includes('timestamp')?(configuration.stamp||1):0,filmNameStamp:compatible.includes('timestamp')?(configuration.filmNameStamp??false):false}};
}

export function selectNativeFilm(value,slot,film){
 const c=normalizeConfiguration(value);if(!Number.isInteger(slot)||slot<0||slot>=c.slots.length)throw Error('槽位无效');
 if(c.slots.some((s,i)=>i!==slot&&s.film===film))throw Error('此胶卷已在选择列表中');
 const s=c.slots[slot];
 if(s.film!==film){
  s.grain=0;s.soft=0;s.halo={gain:0,spread:3,threshold:5,profile:film===66?1:2};
  s.effects={...defaultEffects()};
 }
 if(film!==s.film||![67,68].includes(film))s.effects.filmExposure=0;
 if(film===289){s.effects.charmeraColor=s.film===289?(s.effects.charmeraColor??0):0;if(s.film!==289)s.grain=0;}else delete s.effects.charmeraColor;
 s.film=film;return normalizeConfiguration(c);
}

export function resetNativeTexture(value,slot){
 const c=normalizeConfiguration(value);if(!Number.isInteger(slot)||slot<0||slot>=c.slots.length)throw Error("槽位无效");
 const s=c.slots[slot];s.grain=0;s.halo.gain=0;s.soft=0;s.effects={...defaultEffects(),filmExposure:s.effects.filmExposure,...(s.film===289?{charmeraColor:s.effects.charmeraColor}: {})};return c;
}

// Selection order is the camera order; removing a film retains every other recipe.
export function toggleNativeFilm(value,film){
 const c=normalizeConfiguration(value),index=c.slots.findIndex(s=>s.film===film);
 if(index>=0){c.slots.splice(index,1);return c;}
 if(c.slots.length>=10)throw Error('最多选择 10 款胶卷，请先取消一款');
 c.slots.push({film,grain:0,soft:0,halo:{...defaultHalo(),profile:film===66?1:2},effects:defaultEffects()});
 return normalizeConfiguration(c);
}

// Generate once before prepare; the build must reuse the resulting snapshot.
export function prepareZoomConfigurationForBuild(value,model,random=globalThis.crypto){
 const configuration=normalizeConfiguration(value);
 if(configuration.zoom.write){
  if(!isGr3Family(model))throw Error('裁切焦距写入仅支持 GR III / IIIx');
  const lens=modelCapabilities(model).zoom;
  if(configuration.zoom.slots.some(mm=>mm<lens.min||mm>lens.max))throw Error(`裁切焦距需要 ${lens.min}–${lens.max} mm 整数`);
  let revision=0;const word=new Uint32Array(1);
  while(!revision||revision===configuration.zoom.revision){random.getRandomValues(word);revision=word[0];}
  configuration.zoom.revision=revision;
 }
 return configuration;
}
export function zoomSummary(configuration){
 const z=configuration.zoom;
 return z?.write?`裁切焦距 · 更新时写入一次：第一档 ${z.slots[0]} mm / 第二档 ${z.slots[1]} mm`:'裁切焦距 · 保留机内设置';
}

export function configurationForModel(value,model){
 const c=normalizeConfiguration(value),lens=modelCapabilities(model).zoom;
 if(!lens){c.zoom.write=false;return c;}
 if(c.zoom.slots.some(mm=>mm<lens.min||mm>lens.max))c.zoom={...c.zoom,slots:[...lens.defaults],revision:0};
 return c;
}
