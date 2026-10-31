import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {exportSdFilms,encodeZip} from './gr3-sd-film-export.mjs';
import {nativeCatalog} from './gr3-native-library.mjs';
import {readModelOfficial,inspectModelFirmware} from './model-firmware.mjs';
import {GR4_OFFICIAL_SHA256,validateGr4Source,prepareGr4Native,generateGr4Native} from './gr4-m10v-native-build.mjs';
export async function handleGr4NativeRequest({request,response,runtime,token,readBody,send,origin}){
 const prefix='/api/gr4/native-library/';if(!request.url?.startsWith(prefix))return false;
 const route=request.url.slice(prefix.length),sourcePath=path.join(runtime.root,'inputs',GR4_OFFICIAL_SHA256+'.bin');
 try{
  if(request.method==='GET'&&route==='catalog'){const catalog=await nativeCatalog();catalog.films=catalog.films.filter(f=>f.id<289).map((f,i)=>({...f,number:i+1}));catalog.film_count=catalog.films.length;return send(response,200,{...catalog,local_sources:['gr4'],local_source_available:await readModelOfficial('gr4').then(()=>true,()=>false),slot_tone_ids:undefined}),true;}
  if(request.headers['x-m10v-token']!==token||(request.headers.origin&&request.headers.origin!==origin))return send(response,403,{error:'authorization failed'}),true;
  if(request.method!=='POST')return send(response,405,{error:'POST required'}),true;
  const body=await readBody(request,route==='import'?64*1024*1024:16384);
  if(['import','import-official'].includes(route)){
   const source=route==='import'?body:await readModelOfficial('gr4');validateGr4Source(source);
   const report=await inspectModelFirmware(source);await mkdir(path.dirname(sourcePath),{recursive:true});try{await writeFile(sourcePath,source,{mode:0o400,flag:'wx'});}catch(error){if(error.code!=='EEXIST')throw error;validateGr4Source(await readFile(sourcePath));}
   return send(response,200,{...report,project_id:GR4_OFFICIAL_SHA256}),true;
  }
  const input=JSON.parse(body.toString('utf8')||'{}');
  if(route==='sd-export'){
   if(!Array.isArray(input.ids)||input.ids.some(id=>id>78))throw Error('GR IV 尚未适配此胶卷');
   const {receipt}=await exportSdFilms({model:'gr3',ids:input.ids});
   const {buildSdFilmPack}=await import('./gr3-sd-film-pack.mjs');
   const pack=buildSdFilmPack(input.ids),record={...receipt,model:'gr4',camera_tested:false};
   return send(response,200,encodeZip({'SD/M10V/FILMS.M10':pack,'manifest.json':Buffer.from(JSON.stringify(record,null,2)),'README.txt':Buffer.from(gr4SdInstructions())}),'application/zip','M10V-GR4-SD-films.zip'),true;
  }
  if(input.project_id!==GR4_OFFICIAL_SHA256)throw Error('GR IV 项目标识无效');
  const source=await readFile(sourcePath);validateGr4Source(source);
  const controller=new AbortController();response.on('close',()=>{if(!response.writableEnded)controller.abort();});
  if(route==='prepare')return send(response,200,await prepareGr4Native(source,input,{signal:controller.signal})),true;
  if(route==='build'){
   const {candidate,receipt}=await generateGr4Native(source,input,{signal:controller.signal});
   response.setHeader('X-M10V-Native-Receipt',Buffer.from(JSON.stringify(receipt)).toString('base64'));
   return send(response,200,candidate,'application/octet-stream','fwdc248b.bin'),true;
  }
  if(route==='backup')return send(response,200,source,'application/octet-stream','fwdc248b-original.bin'),true;
  return send(response,404,{error:'接口不存在'}),true;
 }catch(error){send(response,400,{error:error.message});return true;}
}
export function gr4SdInstructions(){return `M10V SD 胶卷库 / GR IV 1.11
需要配套的 GR IV 原生 M10V 固件；此 ZIP 是胶卷资源，不是刷机固件。
解压，将 SD/M10V 目录复制到 SD 卡根目录，与 DCIM 并列。更新时只替换 FILMS.M10，保留其他文件。
机内：MENU > 设置 > 胶卷库，选择要替换的槽位并按 OK，直接进入卡上的胶卷列表。
左右选卷、上下翻页，按 OK 装入；成功后返回五槽列表。MENU 返回上一级，五槽页按 MENU 退出。
最多五个活动槽，卡上可存全部可用胶卷。装入成功后重启或换卡仍保留。无卡、损坏或不兼容文件不替换原槽。
时间水印：MENU > 设置 > 时间水印，设置模式、日期格式、位置、颜色，OK 保存，MENU 取消当前编辑。
文件包含配方身份快照和图标；5207、Phoenix II、HARMAN RED 通过 SHA-256 绑定固件内完整 LUT（含 RED 三档曝光），不在文件中存放 LUT。
仅接受匹配版本的胶卷，未来新配方需匹配固件。固件与资源包使用同一份渲染合同。
胶卷效果作用于保存的静态 JPEG，实时取景和机内 RAW 再开发沿用原厂流程。异常时间只跳过日期水印。
离线验证通过，GR IV 刷入、菜单、拍摄和 SD 换卷仍需真机验收。\n`;}
export function gr4WorkbenchHtml(shared){return shared.replaceAll('GR III／GR IIIx','GR IV').replace('GR III / GR IIIx','GR IV').replaceAll('GR III / GR IIIx','GR IV').replace('支持 GR III 与 GR IIIx · 导入后自动识别机型','支持 GR IV · 官方固件身份核验').replace('<option value="gr3">GR III · Street 2.10</option><option value="gr3x">GR IIIx · 1.60</option>','<option value="gr4">GR IV · 1.11</option>').replaceAll('/gr3/sd-library.html','/gr4/sd-library.html').replace('<a href="/gr4/">GR IV</a>','<a href="/gr4/reference/">GR IV 参考工具</a>');}

export function gr4SdLibraryHtml(shared){
 return shared.replaceAll('/gr3/','/gr4/').replace('/gr4/styles.css','/gr3/styles.css')
  .replace('GR III / GR IIIx · 胶卷库','GR IV · 胶卷库')
  .replace('选择胶卷并下载资源包，在机内管理最多十款已选胶卷。','选择胶卷并下载资源包，在机内管理五个胶卷位置。')
  .replace(/<p data-sd-model-scope>[\s\S]*?<\/p>/,'<p data-sd-model-scope>配套 GR IV 1.11 的 M10V 固件使用。更新固件后重新下载匹配资源。</p>')
  .replace(/<p data-sd-color-scope>[\s\S]*?<\/p>/,'<p data-sd-color-scope>胶卷效果仅作用于静态 JPEG，实时取景与机内 RAW 再开发保留原厂流程。当前未开放自定义 LUT，菜单与成像仍待实机验证。</p>')
  .replace('<section class="sd-custom"','<section hidden class="sd-custom"')
  .replace(/<a href="\/gr4\/fit.html">[\s\S]*?<\/a>/,'')
  .replace(/<section class="sd-guide"[\s\S]*?<\/section>/,"<section class=\"sd-guide\" aria-labelledby=\"guide-heading\"><h2 id=\"guide-heading\">安装方法</h2><ol><li>解压胶卷包，将 <code>SD/M10V</code> 文件夹复制到 SD 卡根目录，与 <code>DCIM</code> 并列。更新时只替换 <code>FILMS.M10</code>，保留其他设置文件。</li><li>机内进入 <strong>MENU → 设置 → 胶卷库</strong>，选择五个位置中的一个，再从卡上选择胶卷，按 OK 装入。</li><li>MENU 返回上一级。装入成功后设置会保存；文件损坏或不兼容时保持原槽。</li></ol><p>GR IV 最多五个活动胶卷位置。胶卷效果作用于静态 JPEG，取景与机内 RAW 再开发沿用原厂流程。</p><p>时间水印：MENU → 设置 → 时间水印，调整日期、时间、格式、位置和颜色，OK 保存、MENU 取消。当前不提供胶卷名称印字。</p><p>GR IV 的刷入、菜单、拍摄与换卷仍待实机验证。</p></section>");
}
