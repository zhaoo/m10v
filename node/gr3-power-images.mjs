// Fixed-size GR III family power-screen resource replacement.
import {createHash} from 'node:crypto';
import {readFileSync,existsSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {inspectNativeSource as inspectOfficial} from './gr3-native-source.mjs';
import {inspectFirmwareImport} from './firmware.mjs';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const need=(v,m)=>{if(!v)throw Error(m);};
const root=fileURLToPath(new URL('../',import.meta.url));
const python=existsSync(root+'.venv/bin/python')?root+'.venv/bin/python':'python3';
const slots={shutdown:{filename:'GB_Diary.jpg',capacity:112509,pathOffset:0xb2298c,descriptor:0x53b5f508,requests:[2,3,10,11,12]},startup:{filename:'StartUp.jpg',capacity:16687,pathOffset:0xb22adc,descriptor:0x53b5f520,requests:[1]}};
const shutdownMenuRoute=0x0200f109;
const albumSlots=[
 {filename:'GB_ING.jpg',capacity:91119,pathOffset:0xb229cc,descriptor:0x53b5f510},
 {filename:'GB_Urban.jpg',capacity:107902,pathOffset:0xb229ac,descriptor:0x53b5f558},
 {filename:'GB_Diary.jpg',capacity:112509,pathOffset:0xb2298c,descriptor:0x53b5f508},
];
const imageCache=new Map();
const imageEngine=sha(readFileSync(root+'scripts/gr3_power_image.py'));
const table=[0x53b5f520,0x53b5f540,0x53b5f550,0x53b5f530,0x53b5f518,0x53b5f528,0x53b5f568,0x53b5f538,0x53b5f560,0x53b5f510,0x53b5f558,0x53b5f508];
function sections(decoded){let p=0;const result={};for(const name of ['BOOTPARA','DRAMPARA','PARTPARA','M0','BOOT','RTOS','LINUX','INITFS','SRIC','CPU','SHELLCMD','ICONBIN','FDRVPARA','RES']){need(decoded.toString('ascii',p,p+8).split('\0')[0]===name,'图片构建分区布局不符');const n=decoded.readUInt32LE(p+12);result[name]={offset:p+16,size:n};p+=16;if(name==='RES'){let q=p;for(let i=0;i<n;i++){need(q+36<=decoded.length-4,'RES越界');q+=36+decoded.readUInt32LE(q+32);}result.RES.size=q-p;p=q;}else p+=n;}need(p===decoded.length-4,'图片构建分区尾部不符');return result;}
function record(decoded,map,filename){let p=map.RES.offset;for(let i=0;i<35;i++){const path=decoded.toString('ascii',p,p+32).split('\0')[0],size=decoded.readUInt32LE(p+32);if(path===`B:\\Resource\\Jpeg\\${filename}`)return {header:p,start:p+36,size};p+=36+size;}throw Error('图片资源缺失');}
function decodeImage(value,capacity){
 need(value&&Object.keys(value).length===1&&typeof value.jpeg_base64==='string'&&value.jpeg_base64.length<3*1024*1024&&/^[A-Za-z0-9+/]*={0,2}$/.test(value.jpeg_base64),'图片 JPEG 数据无效');
 const cacheKey=sha(value.jpeg_base64)+':'+capacity+':'+imageEngine;
 if(imageCache.has(cacheKey))return imageCache.get(cacheKey);
 const process=spawnSync(python,[root+'scripts/gr3_power_image.py'],{
  input:JSON.stringify({...value,capacity}),encoding:'utf8',maxBuffer:3*1024*1024,timeout:15000,
 });
 need(process.status===0,'图片 JPEG 解码或压缩失败：'+(process.stderr||process.error?.message||'unknown'));
 const result=JSON.parse(process.stdout);
 const image={jpeg:Buffer.from(result.jpeg_base64,'base64'),quality:result.quality};
 if(imageCache.size>=8)imageCache.delete(imageCache.keys().next().value);
 imageCache.set(cacheKey,image);
 return image;
}
function normalize(input={}){
 need(input&&typeof input==='object'&&!Array.isArray(input)&&
  Object.keys(input).every(k=>Object.hasOwn(slots,k)||k==='shutdownAlbum'),'图片配置无效');
 const album=input.shutdownAlbum;
 if(album!=null){
  need(input.shutdown==null,'关机单图与相册不能同时使用');
  need(Array.isArray(album)&&album.length>=1&&album.length<=albumSlots.length,'关机相册可选 1 至 3 张图片');
 }
 const out={};
 for(const [kind,slot] of Object.entries(slots)){
  if(input[kind]!=null)out[kind]=decodeImage(input[kind],slot.capacity);
 }
 if(album!=null)out.shutdownAlbum=Array.from(album,(value,index)=>decodeImage(value,albumSlots[index].capacity));
 return out;
}
function imageReceipt(image){
 return {jpeg_sha256:sha(image.jpeg),bytes:image.jpeg.length,quality:image.quality};
}
export function preparePowerImages(source,input={}){
 const selected=normalize(input);
 const report=Object.keys(selected).length?inspectOfficial(source):inspectFirmwareImport(source);
 const supported=['GR III','GR IIIx'].includes(report.model);
 need(!Object.values(input).some(Boolean)||supported,'图片替换仅支持已核验的 GR III / IIIx');
 need(!selected.shutdownAlbum||report.model==='GR III','关机相册仅支持 GR III 2.10');
 const result={schema:'m10v-gr3-power-images/v1',camera_tested:false};
 for(const kind of Object.keys(slots)){
  const image=selected[kind];
  result[kind]={enabled:!!image,supported,display_verified:false,
   status:kind==='startup'?'native_resource_only_display_entry_unverified':'offline_verified_camera_unverified',
   ...(image?imageReceipt(image):{}),width:720,height:480};
 }
 if(selected.shutdownAlbum)result.shutdownAlbum=selected.shutdownAlbum.map((image,index)=>({
  request:13+index,...imageReceipt(image),display_verified:false,
 }));
 return result;
}
export function bindPowerPreparation(base,source,input={}){
 const power_images=preparePowerImages(source,input);
 if(!power_images.shutdown.enabled&&!power_images.startup.enabled&&!power_images.shutdownAlbum)return base;
 const engine=sha(Buffer.concat([readFileSync(new URL(import.meta.url)),readFileSync(root+'scripts/gr3_power_image.py')]));
 return {...base,power_images,base_configuration_sha256:base.configuration_sha256,
  configuration_sha256:sha(JSON.stringify({base:base.configuration_sha256,power_images,engine}))};
}
function pack(base,target,frames,decoded){const chunks=[];for(const f of frames){const data=target.subarray(f.decoded_start,f.decoded_end);if(target.subarray(Math.max(0,f.decoded_start-8191),f.decoded_end).equals(decoded.subarray(Math.max(0,f.decoded_start-8191),f.decoded_end)))chunks.push(base.subarray(128+f.encoded_start,128+f.encoded_end));else for(let p=0;p<data.length;p+=0x6000){const part=data.subarray(p,p+0x6000),prefix=Buffer.alloc(2);prefix.writeUInt16BE(0x8000|part.length);chunks.push(prefix,part);}}chunks.push(Buffer.alloc(2));const payload=Buffer.concat(chunks),footer=Buffer.from(base.subarray(-24));footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(0,20);const candidate=Buffer.concat([base.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);candidate.writeUInt32LE(-sum32(candidate)>>>0,candidate.length-4);return candidate;}
export function applyPowerImages(source,base,input={},native){const receipt=preparePowerImages(source,input),selected=normalize(input);if(!Object.keys(selected).length)return {candidate:base,receipt};const sourceDecoded=decodeFrameMap(source).decoded,originalMap=sections(sourceDecoded);const size=base.readUInt32LE(base.length-8),{decoded,frames}=decodeFrameMap(base,size),map=sections(decoded),target=Buffer.from(decoded),ranges=[];
 const write=(section,offset,before,after,stock=true)=>{const p=map[section].offset+offset,s=originalMap[section].offset+offset;need((!stock||before.equals(sourceDecoded.subarray(s,s+before.length)))&&before.equals(decoded.subarray(p,p+before.length)),'图片补丁前像与已有功能冲突');need(before.length===after.length,'图片容量不符');after.copy(target,p);ranges.push([p,p+after.length]);};
 if(selected.shutdownAlbum&&native){
  const installedRows=native.hdf_menu?.rows??native.settings_menu?.rows;
  const row=native.settings_menu?.exports?.m10v_shutdown_album_row;
  const lookup=native.settings_menu?.exports?.m10v_shutdown_album_lookup;
  const config=native.symbols?.m10v_settings_controller_shutdown_config;
  const render=native.symbols?.m10v_settings_controller_shutdown_render;
  function instruction(at,before,after,stock=true){
   const word=value=>{const b=Buffer.alloc(4);b.writeUInt32LE(value);return b;};
   write('RTOS',at-0x53000000,word(before),word(after),stock);
  }
  need(native.camera_model==='gr3'&&Array.isArray(installedRows)&&installedRows.length>=2&&installedRows.length<=4,
   '关机图相册需要 GR III 原生设置菜单');
  const runtimeEntry=at=>Number.isInteger(at)&&!(at&3)&&at>=native.base&&at+8<=native.base+native.code_bytes;
  need(runtimeEntry(row)&&runtimeEntry(config)&&runtimeEntry(render)&&runtimeEntry(lookup),'关机图相册运行时不完整');
  const count=installedRows.length;
  instruction(0x53b36adc,((30+count)<<24)|0x1d1b19,((31+count)<<24)|0x1d1b19,false);
  instruction(0x53b36bd0+count*8,0,row);
  instruction(0x53b36c88+count*4,0x10000000,shutdownMenuRoute);
  const site=0x5319f234,delta=render-site-8;
  need(delta%4===0&&delta>=-(2**25)&&delta<2**25,'关机图相册分支超出范围');
  instruction(site,0xeb023c9b,(0xeb000000|((delta>>2)&0xffffff))>>>0);
  const load=0x5322e4c8,lookupDelta=lookup-load-8;
  need(lookupDelta%4===0&&lookupDelta>=-(2**25)&&lookupDelta<2**25,'关机图相册查表分支超出范围');
  instruction(load,0xe79c1101,(0xea000000|((lookupDelta>>2)&0xffffff))>>>0);
  const marker=map.RTOS.offset+config-0x53000000;
  need(decoded.readUInt32LE(marker)===0x3141534d,'关机图相册配置标识不符');
  instruction(config+4,0,selected.shutdownAlbum.length,false);
  receipt.shutdown_album_menu={route:shutdownMenuRoute,entries:selected.shutdownAlbum.length,camera_tested:false};
 }
 const entries=Object.keys(slots).filter(kind=>selected[kind]).map(kind=>[kind,slots[kind],selected[kind]]);
 for(const [index,image] of (selected.shutdownAlbum??[]).entries())entries.push(['album',albumSlots[index],image]);
 for(const [kind,slot,image] of entries){const r=record(sourceDecoded,originalMap,slot.filename);need(r.size===slot.capacity,'图片槽容量不符');const descriptor=originalMap.RTOS.offset+slot.descriptor-0x53000000;need(decoded.subarray(map.RTOS.offset+slot.descriptor-0x53000000,map.RTOS.offset+slot.descriptor-0x53000000+8).equals(sourceDecoded.subarray(descriptor,descriptor+8)),'图片描述符与已有功能冲突');need(sourceDecoded.readUInt16LE(descriptor)===720&&sourceDecoded.readUInt16LE(descriptor+2)===480&&sourceDecoded.readUInt32LE(descriptor+4)===0x53000000+slot.pathOffset,'图片原生描述符不符');const oldPath=Buffer.from(`B:\\Resource\\Jpeg\\${slot.filename}\0`);need(sourceDecoded.subarray(originalMap.RTOS.offset+slot.pathOffset,originalMap.RTOS.offset+slot.pathOffset+oldPath.length).equals(oldPath),'RTOS图片路径不符');if(kind!=='album')write('RTOS',slot.pathOffset,Buffer.from('B'),Buffer.from('A'));write('RES',r.header-originalMap.RES.offset,Buffer.from('B'),Buffer.from('A'));write('RES',r.start-originalMap.RES.offset,sourceDecoded.subarray(r.start,r.start+r.size),image.jpeg);
 if(kind==='shutdown')for(const request of slot.requests){const offset=0x107e0bc+(request-1)*4,before=Buffer.alloc(4),after=Buffer.alloc(4);before.writeUInt32LE(table[request-1]);after.writeUInt32LE(slot.descriptor);write('RTOS',offset,before,after);}
 }
 target.writeUInt32LE(0,target.length-4);target.writeUInt32LE(-sum32(target)>>>0,target.length-4);const candidate=pack(base,target,frames,decoded),fresh=decodeFrameMap(candidate,size).decoded;need(fresh.equals(target)&&sum32(candidate)===0&&sum32(fresh)===0,'图片固件独立回读失败');let p=0;for(const [a,b] of [...ranges.sort((a,b)=>a[0]-b[0]),[fresh.length-4,fresh.length]]){need(fresh.subarray(p,a).equals(decoded.subarray(p,a)),'非图片补丁范围变化');p=b;}
 const runtimeSha=native&&receipt.shutdown_album_menu?sha(fresh.subarray(map.RTOS.offset+native.base-0x53000000,map.RTOS.offset+native.base-0x53000000+native.code_bytes)):undefined;
 return {candidate,receipt:{...receipt,...(runtimeSha?{runtime_sha256:runtimeSha}:{}),candidate_sha256:sha(candidate),base_candidate_sha256:sha(base),non_target_bytes_unchanged:true,resource_count_unchanged:true,decoded_size_unchanged:true}};
}

function imagePreview(image){
 return {preview_data_url:'data:image/jpeg;base64,'+image.jpeg.toString('base64'),
  quality:image.quality,bytes:image.jpeg.length};
}
export function previewPowerImages(input){
 return Object.fromEntries(Object.entries(normalize(input)).map(([kind,image])=>
  [kind,Array.isArray(image)?image.map(imagePreview):imagePreview(image)]));
}
