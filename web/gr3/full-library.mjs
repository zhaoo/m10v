import {supportsNativeFilm} from './model-capabilities.mjs';
export function fullLibraryRequest(model,catalog){
 if(!['gr3','gr3x','gr4'].includes(model))throw Error('此机型暂不支持此胶卷库下载');
 if(!Array.isArray(catalog)||!catalog.length||catalog.some(f=>!Number.isInteger(f.id)||f.id<1))throw Error('配套胶卷目录不可用，请重新读取');
 return {url:model==='gr4'?'/api/gr4/native-library/sd-export':'/api/gr3/sd-library/export',body:{model,ids:[...new Set(catalog.filter(f=>supportsNativeFilm(model,f.id)).map(f=>f.id))]}};
}
export function mountBuildCompletion(root,{api}){
 let snapshot=null,libraryBusy=false,urls=[];
 const button=root.querySelector('[data-full-library]'),status=root.querySelector('[data-library-status]');
 function file(blob,name){const url=URL.createObjectURL(blob);urls.push(url);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>{URL.revokeObjectURL(url);urls=urls.filter(v=>v!==url);},60000);}
 button.onclick=async()=>{
  if(!snapshot||libraryBusy)return;
  const job=snapshot;libraryBusy=true;button.disabled=true;status.textContent='正在打包全部配套胶卷…';
  try{const request=fullLibraryRequest(job.model,job.catalog);const response=await api(request.url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request.body)});file(await response.blob(),`M10V-${job.model}-full-library.zip`);if(job===snapshot)status.textContent='下载已发起。解压后，将 SD/M10V 文件夹复制到 SD 卡根目录，与 DCIM 并列。';}
  catch(error){if(job===snapshot)status.textContent=`胶卷库下载失败：${error.message}。请重试，已生成的固件不受影响。`;}
  finally{libraryBusy=false;button.disabled=false;}
 };
 root.querySelector('[data-firmware-download]').onclick=()=>{if(snapshot?.firmwareBlob)file(snapshot.firmwareBlob,snapshot.filename);};
 root.querySelector('[data-record-download]').onclick=()=>{if(snapshot)file(new Blob([JSON.stringify(snapshot.record,null,2)+'\n'],{type:'application/json'}),`M10V-${snapshot.model}-configuration.json`);};
 window.addEventListener('pagehide',()=>{for(const url of urls)URL.revokeObjectURL(url);urls=[];});
 return {show(value){snapshot=structuredClone(value);root.hidden=false;root.querySelector('#completion-title').textContent=value.filmLibrary?'固件已生成，准备装卷。':'固件已生成。';button.hidden=!value.filmLibrary;root.querySelector('[data-library-guide]').hidden=!value.filmLibrary;status.textContent=value.filmLibrary?'固件已生成。接下来下载全量胶卷库，准备机内装卷。':'固件已生成。本方案未启用胶卷库，无需准备胶卷文件。';root.querySelector('[data-completed-model]').textContent=({gr3:'GR III',gr3x:'GR IIIx',gr4:'GR IV'})[value.model];root.querySelector('pre').textContent=`SD 卡根目录\n├─ ${{gr3:'fwdc239b.bin',gr3x:'fwdc243b.bin',gr4:'fwdc248b.bin'}[value.model]}  ← 固件\n├─ M10V/\n│  └─ FILMS.M10\n└─ DCIM/`;},reset(){root.hidden=true;snapshot=null;}};
}
