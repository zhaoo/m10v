import {encodeZip} from './gr3-sd-film-export.mjs';
import {buildSdFilmPack} from '../compat/gr2-v1/node/gr3-sd-film-pack.mjs';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {nativeCatalog} from '../compat/gr2-v1/node/gr3-native-library.mjs';
import {readFileSync} from 'node:fs';
import {readModelOfficial} from './model-firmware.mjs';
import {readUnityModelComponent} from './unity-firmware.mjs';
import {prepareGr2Native,generateGr2Native} from './gr2-native-library.mjs';
const identity='3643850f2ae74ae967eb336794048f554caa1b11d05b8569824d5719f1838331';
export async function handleGr2NativeRequest({request,response,runtime,token,readBody,send,origin}){
 const prefix='/api/gr2/native-library/';if(!request.url?.startsWith(prefix))return false;
 const route=request.url.slice(prefix.length),file=path.join(runtime.root,'..','gr2','inputs',identity+'.frm');
 try{
  if(request.method==='GET'&&route==='catalog'){
   const catalog=await nativeCatalog();
   const art=new Map(JSON.parse(readFileSync(new URL('../web/gr3/film-icons/catalog.json',import.meta.url),'utf8')).map(icon=>[icon.id,icon]));
   catalog.films=catalog.films.map(f=>{const icon=art.get(f.id);return icon?{...f,icon_url:icon.icon_url,icon_compact_url:icon.icon_compact_url,icon_color:icon.color}:f;});
   send(response,200,{...catalog,local_sources:['gr2'],local_source_available:await readModelOfficial('gr2').then(()=>true,()=>false),hardware_verified:false});return true;
  }
  if(request.headers['x-m10v-token']!==token||(request.headers.origin&&request.headers.origin!==origin)){send(response,403,{error:'authorization failed'});return true;}
  if(request.method!=='POST'){send(response,405,{error:'POST required'});return true;}
  const body=await readBody(request,route==='import'?64*1024*1024:16384);
  if(['import','import-official'].includes(route)){
   const source=route==='import'?body:await readModelOfficial('gr2');readUnityModelComponent(source,'gr2','b01firm8');
   await mkdir(path.dirname(file),{recursive:true});try{await writeFile(file,source,{flag:'wx',mode:0o400});}catch(e){if(e.code!=='EEXIST')throw e;readUnityModelComponent(await readFile(file),'gr2','b01firm8');}
   send(response,200,{project_id:identity,model:'GR II',source_sha256:identity});return true;
  }
  const input=JSON.parse(body.toString()||'{}');if(input.project_id!==identity)throw Error('请先导入 GR II 官方固件');
  if(route==='sd-export'){send(response,200,encodeZip({'SD/M10V/FILMS.M10':buildSdFilmPack(input.ids),'README.txt':Buffer.from('GR II 实验胶卷资源包。将 SD/M10V 复制到卡根目录；保留其他存档。需配套 M10V GR II 实验固件，真机使用尚待验证。此 ZIP 不是刷机固件。')}),'application/zip','M10V-GR2-SD-films.zip');return true;}
  const source=await readFile(file);readUnityModelComponent(source,'gr2','b01firm8');
  const controller=new AbortController();response.on('close',()=>{if(!response.writableEnded)controller.abort();});
  if(route==='prepare'){send(response,200,await prepareGr2Native(source,input.configuration));return true;}
  if(route==='build'){
   const result=await generateGr2Native(source,input.configuration,input.configuration_sha256,{signal:controller.signal});
   response.setHeader('X-M10V-Native-Receipt',Buffer.from(JSON.stringify(result.receipt)).toString('base64'));
   send(response,200,result.candidate,'application/octet-stream','rg2_v003.frm');return true;
  }
  send(response,404,{error:'接口不存在'});return true;
 }catch(error){if(!response.destroyed)send(response,400,{error:error.message});return true;}
}
