import {FILM_DIRECTORY,directoryFilm} from './gr3-film-directory.mjs';
import {createHash} from 'node:crypto';
import {readFile,mkdtemp,rm,access} from 'node:fs/promises';
import {promisify} from 'node:util';
import {execFile} from 'node:child_process';
import path from 'node:path';
import {readFileSync,existsSync} from 'node:fs';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {normalizeConfiguration,normalizeExtensions,activeExtensions} from '../web/gr3/native-library-state.mjs';
import {inspectOfficial} from './firmware.mjs';
import {buildNativeLibrary,nativeSourceFingerprint} from './gr3-m10v-native-build.mjs';
import {buildCameraComponents,composeNative,integrationFingerprint,cameraComponentBase} from './gr3-integrated-components.mjs';
import {normalizeVersionUnlock,applyVersionUnlock} from './gr3-version-unlock.mjs';
import {modelCapabilities} from '../web/gr3/model-capabilities.mjs';
import {portNativeToGr3x} from './gr3x-native-port.mjs';
const root=fileURLToPath(new URL('..',import.meta.url));
const hash=b=>createHash('sha256').update(b).digest('hex');
const officialHash='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
const run=promisify(execFile);
export async function nativeCatalog(){
 const source=await readFile(path.join(root,'native/gr3/m10v_library.c'),'utf8');
 const films=[...source.matchAll(/\{"([^"\n]+)",(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+)\}/g)].map((m,i)=>({id:i+1,name:m[1]}));
 if(films.length!==33)throw Error('M10V 原生目录不完整');
 const legacy=JSON.parse(await readFile(path.join(root,'web/gr3/film-catalog.json'),'utf8')).looks;
 films.forEach(f=>f.group='M10V精选');
 films.push(...legacy.map((f,i)=>({id:34+i,name:f.name,group:f.group||'胶片模拟',legacy_id:f.id,color_path:'saved-jpeg-rgb-tables'})));
 films.push({id:66,key:'m10v-5207',name:'5207',group:'M10V精选',camera_calibrated:false,film_calibrated:false});
 films.push({id:67,key:'harman-phoenix-ii-200',name:'蓝凤凰',stock:'PhoenixII200',group:'M10V精选',camera_calibrated:false,film_calibrated:false},{id:68,key:'harman-red-125',name:'哈曼 RED',stock:'RED125',group:'M10V精选',camera_calibrated:false,film_calibrated:false});
 films.push(...[{id:69,key:'portra-160',name:'Portra 160'},{id:70,key:'fuji-industrial-100',name:'富士业务用 100'},{id:71,key:'lucky-c200-new',name:'乐凯 C200'},{id:72,key:'ccd-classic',name:'CCD Classic'}].map(f=>({...f,group:'M10V精选',camera_calibrated:false,film_calibrated:false})));
 films.push(...JSON.parse(readFileSync(path.join(root,'web/gr3/newstocks-luts.json'),'utf8')).stocks.map(({values,...f})=>({...f,group:'M10V精选',camera_calibrated:false,film_calibrated:false})));
 films.push({id:289,key:'kodak-charmera',name:'Kodak Charmera',group:'M10V精选',camera_calibrated:false,approximation:true,colors:['红','黄','蓝','灰']});
 films.push({id:290,key:'pixel-world',name:'方块世界',ascii_name:'Pixel World',group:'M10V精选',camera_calibrated:false,approximation:true,description:'方块像素与有限色阶，适合草地、天空与建筑；仅静态 JPEG，需更新固件。'});
 films.push(...JSON.parse(readFileSync(path.join(root,'web/gr3/style-filters-luts.json'),'utf8')).stocks.map(({values,...f})=>({...f,group:'M10V精选'})));
 films.push({id:298,key:'vision3-200t-5213',name:'5213',group:'ECN2',camera_calibrated:false,film_calibrated:false});
 films.push(...JSON.parse(readFileSync(path.join(root,'web/gr3/d76-luts.json'),'utf8')).stocks.map(({values,...f})=>({...f,group:'D76'})));
 films.push(...JSON.parse(readFileSync(path.join(root,'web/gr3/anime-e6-luts.json'),'utf8')).stocks.filter(s=>s.id>=309).map(({values,...f})=>f));
 films.push(...JSON.parse(readFileSync(path.join(root,'web/gr3/c41-luts.json'),'utf8')).stocks.map(({values,...f})=>f));
 films.push(...JSON.parse(readFileSync(path.join(root,'web/gr3/extra-films-luts.json'),'utf8')).stocks.map(({values,...f})=>f));
 films.forEach(f=>{const d=directoryFilm(f.id);if(d)Object.assign(f,d);});
 const icons=JSON.parse(await readFile(path.join(root,'web/gr3/film-icons/catalog.json'),'utf8'));
 if(icons.length!==films.length||icons.some((v,i)=>v.id!==films[i].id||v.name!==films[i].name))throw Error('M10V 图标目录与胶卷不同步');
 films.forEach((f,i)=>Object.assign(f,{icon_url:icons[i].icon_url,icon_color:icons[i].color}));
 let available=false;try{available=hash(await readFile(path.join(root,'fwdc239b-offical.bin')))===officialHash;}catch{}
 const byId=new Map(films.map(f=>[f.id,f]));
 const visibleFilms=FILM_DIRECTORY.map(d=>({...byId.get(d.id),...d}));
 return {film_count:visibleFilms.length,local_sources:['gr3','gr3x'],films:visibleFilms,external_film_pack:true,camera_tested:false,local_source_available:available,
  scope:'GR III 新增最多十个独立胶卷位置，原厂预设保留；JPEG 与已接入的原生色调预览，RAW 再开发未接入。GR III / IIIx 使用相同十位置与原生 ISP 管线。',slot_tone_ids:Array.from({length:10},(_,i)=>25+i)};
}
export async function readNativeOfficial(model='gr3'){
 const profiles={gr3:['bin/fwdc239b-gr3-official.bin',officialHash],gr3x:['bin/fwdc243b-gr3x-official.bin','708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7']};
 if(!profiles[model])throw Error('首批仅开放 GR III 和 GR IIIx');
 const [file,expected]=profiles[model];const b=await readFile(path.join(root,file));if(hash(b)!==expected)throw Error('本地官方固件摘要不匹配');return b;
}
export function initialState(configuration){
 const c=normalizeConfiguration(configuration),b=Buffer.alloc(184);b.writeUInt32LE(0x5630314d);b.writeUInt16LE(5,4);b.writeUInt16LE(184,6);
 c.slots.forEach((s,i)=>{b.writeUInt16LE(s.film,12+i*8);b[14+i*8]=s.grain;b[15+i*8]=s.soft;b[16+i*8]=s.halo.gain;b[17+i*8]=s.halo.spread;b[18+i*8]=s.halo.threshold;b[19+i*8]=s.halo.profile;const e=s.effects;b[96+i*8]=e.grainSize;b[97+i*8]=e.leakGain;b[98+i*8]=e.leakPosition;b[99+i*8]=e.leakSpread;b[100+i*8]=e.leakVariation;b[101+i*8]=e.filmExposure;b[103+i*8]=e.charmeraColor??0;});
 b[92]=c.stamp;b[93]=c.format;b[94]=c.corner;b[95]=c.color;
 b.writeUInt32LE(c.filmNameStamp?1:0,176);
 let crc=0xffffffff;for(const byte of b.subarray(0,180)){crc^=byte;for(let k=0;k<8;k++)crc=(crc>>>1)^(0xedb88320&-(crc&1));}
 b.writeUInt32LE(~crc>>>0,180);return b;
}
export function prepareNative(source,value,{debug_mode=false,extensions:requestedExtensions,version_unlock:requestedUnlock,film_library=true,hdf_enabled,live_color,appended_slots,halation_enabled=false,border_enabled=false}={}){
 const report=inspectOfficial(source),extensions=normalizeExtensions(requestedExtensions),version_unlock=normalizeVersionUnlock(requestedUnlock,report.model==='GR IIIx'?'gr3x':'gr3');
 const camera_model=report.model==='GR IIIx'?'gr3x':'gr3',capabilities=modelCapabilities(camera_model);
 if(typeof film_library!=='boolean')throw Error('胶卷库开关必须为布尔值');
 if(typeof border_enabled!=='boolean'||(border_enabled&&!film_library))throw Error('边框需要原生胶卷库和布尔开关');
 if(appended_slots===undefined)appended_slots=capabilities.filmSlots===10&&film_library;
 if(typeof appended_slots!=='boolean')throw Error('追加胶卷槽开关必须为布尔值');
 if(appended_slots&&!film_library)throw Error('追加胶卷槽需要启用胶卷库');
 if(!film_library&&(value?.stamp||value?.filmNameStamp))throw Error('独立 HDF 暂不可组合胶卷时间戳，请关闭时间戳后构建');
 if(typeof debug_mode!=='boolean')throw Error('调试模式必须为布尔值');
 const integration_source_sha256=integrationFingerprint();
 const reference=JSON.parse(readFileSync(path.join(root,'native/gr3/5207-reference.json'),'utf8'));
 const configuration=normalizeConfiguration(value);
 if(configuration.zoom.write&&!film_library)throw Error('裁切焦距写入仅支持 GR III 胶卷库');
 if(configuration.zoom.write&&configuration.zoom.slots.some(mm=>mm<capabilities.zoom.min||mm>capabilities.zoom.max))throw Error(`裁切焦距需要 ${capabilities.zoom.min}–${capabilities.zoom.max} mm 整数`);
 if(film_library&&configuration.slots.some(s=>!directoryFilm(s.film)))throw Error('包含已停用的胶卷，请从当前目录重新选择');
 if(!appended_slots&&configuration.slots.length>5)throw Error('此机型仍使用五个胶卷位置，暂不支持导出超过 5 款胶卷');
 if(hdf_enabled===undefined)hdf_enabled=!film_library||configuration.hdf>0;
 if(typeof hdf_enabled!=='boolean'||(!hdf_enabled&&(configuration.hdf>0||!film_library)))throw Error('HDF 功能开关与配置不一致');

 if(live_color===undefined)live_color=capabilities.liveColor&&film_library;
 if(typeof live_color!=='boolean'||(live_color&&!film_library))throw Error('原生色调预览仅支持 GR III 胶卷方案');
 if(border_enabled&&!live_color)throw Error('边框需要原生 ISP 成片与预览管线');
 if(typeof halation_enabled!=='boolean'||(halation_enabled&&(!film_library||!live_color)))throw Error('通用光晕仅支持 GR III 原生胶卷库，写入开关必须为布尔值');
 if(halation_enabled)configuration.slots.forEach(s=>{s.halo.gain=0;s.halo.profile=2;});
 const capture_pipeline=live_color?'gr3-native-v8':hdf_enabled?'gr3-native-hdf':debug_mode?'gr3-native-v7':'software';
 const native_grain=capabilities.nativeGrain&&film_library&&['gr3-native-v7','gr3-native-v8'].includes(capture_pipeline);
 if(configuration.slots.some(s=>s.grain>0)&&!native_grain)throw Error('颗粒仅支持 GR III 原厂原生成像管线，请关闭颗粒后导出此方案');
 if(configuration.slots.some(s=>s.grain>0&&[289,290].includes(s.film)))throw Error('Charmera / 方块世界暂不支持原厂颗粒，请关闭该槽位颗粒');
 if(configuration.slots.some(s=>s.film===294||(s.film>=306&&s.film<=316))&&!['gr3-native-v7','gr3-native-v8'].includes(capture_pipeline))throw Error('新滤镜需要 GR III 已接入的 ISP 成片管线');
 const runtime_source_sha256=nativeSourceFingerprint(),configuration_sha256=hash(JSON.stringify({source:report.sha256,configuration,film_library,appended_slots,hdf_enabled,halation_enabled,border_enabled,extensions,debug_mode,version_unlock,runtime_source_sha256,integration_source_sha256,capture_pipeline}));
 const zoom_seed=configuration.zoom.write?{id:hash(JSON.stringify({source:report.sha256,zoom:configuration.zoom,runtime_source_sha256})).slice(0,16),slots:configuration.zoom.slots}:null;
 return {camera_model,capabilities,zoom_seed,schema:'m10v-native-library-plan/v1',ready:true,extensions,version_unlock,integration_source_sha256,film_library,appended_slots,slot_tone_ids:appended_slots?Array.from({length:10},(_,i)=>25+i):[12,18,19,20,21],hdf_enabled,halation_enabled,border_enabled,features:[...(halation_enabled?['halation']:[]),...(film_library?['film','800t','5207','phoenix-ii-200','harman-red-125',...(native_grain?['grain']:[]),'timestamp']:[]),...(hdf_enabled?['digitalHdf']:[]),...(border_enabled?['border']:[]),...activeExtensions(extensions)],source_sha256:report.sha256,configuration,configuration_sha256,runtime_source_sha256,model:report.model,public_version:report.public_version,filename:report.model==='GR IIIx'?'fwdc243b.bin':'fwdc239b.bin',
  capture_pipeline,live_color,debug_mode,debug_log:debug_mode?{schema:'m10v-gr3-sd-debug/v1',build_id:configuration_sha256.slice(0,8),files:['M10VMN0.BIN','M10VMN1.BIN','M10VCP0.BIN','M10VCP1.BIN','M10VIO0.BIN','M10VIO1.BIN','M10VAK0.BIN','M10VAK1.BIN'],page_bytes:4096,records_per_channel:63}:null,
  stock_detail:{ids:[18,19,20,...(native_grain?[21]:[]),...(halation_enabled?[22]:[]),28,29],fields:['gain','spread','threshold',...(native_grain?['grain']:[]),...(halation_enabled?['halationMode']:[]),'filmExposure','charmeraColor'],films:'all',halation_films:halation_enabled?'all':[33,67],halation_modes:halation_enabled?['off','spill','streak']:null,charmera_color:{film:289,colors:['红','黄','蓝','灰']},film_exposure:{films:{67:[200,120],68:[125,64,250]}},slots:appended_slots?10:5,lifecycle:'stock immediate callback'},
  initial_state_hex:initialState(configuration).toString('hex'),film_5207_reference:{table_sha256:reference.table_sha256,table_size:reference.table_size,table_bits:reference.table_bits,input:reference.input,camera_calibrated:false,film_calibrated:false,halation:false},visible_film_count:film_library?FILM_DIRECTORY.length:0,film_count:film_library?103:0,active_slots:film_library?configuration.slots.length:0,camera_tested:false,external_film_pack:film_library,
  scope:film_library&&live_color?'原厂 ISP 胶卷色彩、取景色调预览、颗粒与静态照片效果；光晕与 HDF 不提供实时取景。':film_library?(hdf_enabled?'静态 JPEG 胶卷与时间戳；HDF 使用独立机内菜单。取景与 RAW 再开发未接入。':'静态 JPEG 胶卷与时间戳；取景与 RAW 再开发未接入。'):'独立数字 HDF 菜单与静态 JPEG 柔焦；原厂影像控制、名称、图标及 RAW 像素保持原样。',
  initial_settings_policy:'首次无有效 M10V 记录时使用网页默认值；已有机内 M10V 记录优先。'};
}
let building=false;
export async function generateNative(source,value,accepted,{signal,debug_mode=false,extensions,version_unlock,film_library=true,hdf_enabled,live_color,appended_slots,halation_enabled=false,border_enabled=false}={}){
 const plan=prepareNative(source,value,{debug_mode,extensions,version_unlock,film_library,hdf_enabled,live_color,appended_slots,halation_enabled,border_enabled});if(accepted!==plan.configuration_sha256)throw Error('配置已变化，请重新预检');
 if(building)throw Error('另一个 M10V 原生固件正在构建，请稍后重试');
 building=true;let folder;
 try{
  folder=await mkdtemp(path.join(os.tmpdir(),'m10v-native-export-'));
  let python=path.join(root,'.venv/bin/python');try{await access(python);}catch{python='python3';}
  // Child hooks invoke LLVM tools too; systemd may have only Node's absolute path.
  const compiler=process.env.M10V_LLVM_CLANG||['/opt/homebrew/opt/llvm/bin/clang','/usr/local/opt/llvm/bin/clang','/usr/bin/clang'].find(existsSync);
  const linker=[process.env.M10V_LLVM_LD,compiler&&path.join(path.dirname(compiler),'ld.lld'),'/opt/homebrew/opt/lld/bin/ld.lld','/usr/local/opt/lld/bin/ld.lld','/usr/bin/ld.lld'].find(p=>p&&existsSync(p));
  const toolPaths=[compiler&&path.dirname(compiler),linker&&path.dirname(linker),process.env.PATH].filter(Boolean);
  const buildEnv={...process.env,M10V_NODE:process.execPath,PATH:toolPaths.join(path.delimiter),...(compiler?{M10V_LLVM_CLANG:compiler}:{})};
  const commonSource=plan.model==='GR IIIx'?await readNativeOfficial('gr3'):source;
  const component=await buildCameraComponents(commonSource,plan.extensions,{signal,halfFrame:plan.camera_model==='gr3'});
  await run(python,['scripts/build_gr3_m10v_library.py','--base','0x'+cameraComponentBase(commonSource,component).toString(16),'--out',folder,'--initial-state-hex',plan.initial_state_hex,'--sd-library',...(plan.halation_enabled?['--universal-halation']:[]),...(plan.zoom_seed?['--zoom-seed',JSON.stringify(plan.zoom_seed)]:[]),'--camera-model',plan.camera_model,...(plan.appended_slots?['--appended-slots']:[]),'--hdf-default',String(plan.configuration.hdf),...(film_library?[]:['--hdf-only']),...(plan.hdf_enabled?['--with-hdf']:['--no-hdf']),...(debug_mode?['--debug','--debug-build-id','0x'+plan.debug_log.build_id]:[]),...(process.env.M10V_ADJ_EXIT_TRACE==='1'?['--adj-exit-trace']:[]),...(plan.live_color?['--live-color']:[]),...(plan.border_enabled?['--border-enabled','--border-hardware']:[]),...(['gr3-native-v7','gr3-native-v8'].includes(plan.capture_pipeline)?[...(debug_mode?['--profile']:[]),'--candidate-color','--spatial-neon','--texture-neon','--lifecycle-trace','--save-chain-trace','--recipe-snapshot','--native-color','--native-grain','--view-deferred']:[])],{cwd:root,signal,env:buildEnv,timeout:120000,maxBuffer:2*1024*1024});
  const manifest=JSON.parse(await readFile(path.join(folder,'m10v-library-arm.json'),'utf8'));
  if(manifest.border?.enabled!==plan.border_enabled||manifest.border?.pixel_pipeline_enabled!==plan.border_enabled)throw Error('ARM 边框硬件组件回读不同');
  if(manifest.universal_halation!==plan.halation_enabled)throw Error('ARM 光晕写入开关回读不同');
  if(JSON.stringify(manifest.zoom?.seed)!==JSON.stringify(plan.zoom_seed))throw Error('ARM 焦距写入配置回读不同');
  if(manifest.zoom?.enabled!==film_library)throw Error('ARM 自定义焦距机型隔离回读不同');
  if(manifest.camera_model!==plan.camera_model)throw Error('ARM 目标机型回读不同');
  if(!!manifest.appended_slots!==plan.appended_slots)throw Error('ARM 胶卷槽布局回读不同');
  if(manifest.initial_state_hex!==plan.initial_state_hex||manifest.hdf_default!==plan.configuration.hdf||manifest.hdf_enabled!==plan.hdf_enabled)throw Error('ARM 初始配置回读不同');
  if(!!manifest.capture_lifecycle?.snapshot?.live_color!==plan.live_color)throw Error('ARM 取景色彩接入回读不同');
  if(manifest.debug_mode!==debug_mode||(debug_mode&&manifest.debug_log?.build_id!==plan.debug_log.build_id))throw Error('ARM 调试模式回读不同');
  const runtime=await readFile(path.join(folder,'m10v-library-arm.bin'));
  const result=buildNativeLibrary(commonSource,runtime,manifest);
  const joined=composeNative(commonSource,result.candidate,runtime,manifest,component,plan.extensions);
  const ported=plan.model==='GR IIIx'?portNativeToGr3x(commonSource,source,joined.candidate):null;
  const unlocked=applyVersionUnlock(ported?ported.candidate:joined.candidate,plan.version_unlock);
  return {...result,candidate:unlocked.candidate,nativeCandidate:result.candidate,component,manifest,runtime,receipt:{...result.receipt,capture_pipeline:plan.capture_pipeline,live_color:plan.live_color,experimental_capture:manifest.experimental_capture??null,extensions:plan.extensions,version_unlock:unlocked.receipt,features:plan.features,halation_enabled:plan.halation_enabled,border_enabled:plan.border_enabled,border:manifest.border,film_5207_reference:plan.film_5207_reference,integration_source_sha256:plan.integration_source_sha256,composition:joined.composition,candidate_sha256:hash(unlocked.candidate),candidate_bytes:unlocked.candidate.length,rtos_growth:joined.structure.rtosGrowth,configuration:plan.configuration,configuration_sha256:plan.configuration_sha256,runtime_source_sha256:plan.runtime_source_sha256,
   camera_model:plan.camera_model,capabilities:plan.capabilities,source_sha256:plan.source_sha256,reference_source_sha256:hash(commonSource),gr3x_port:ported?.receipt??null,model:plan.model,public_version:plan.public_version,filename:plan.filename,initial_state_hex:plan.initial_state_hex,initial_settings_policy:plan.initial_settings_policy,zoom_seed:plan.zoom_seed}};
 }finally{if(folder)await rm(folder,{recursive:true,force:true});building=false;}
}
