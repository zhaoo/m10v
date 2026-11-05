import {customFilmArtwork} from '/gr3/film-artwork.mjs';
import {catalogFilms} from '/gr3/film-catalog-view.mjs';
const gr4Page=location.pathname.startsWith('/gr4');
const visualPage=document.body?.classList?.contains('visual-v5')===true;
const requestedModel=new URLSearchParams(location.hash?.startsWith('#model=')?location.hash.slice(1):location.search).get('model');
let model=gr4Page?'gr4':requestedModel===null?'gr3':['gr3','gr3x'].includes(requestedModel)?requestedModel:'';
const $=id=>document.getElementById(id);
if(gr4Page){document.querySelector('.sd-custom')?.setAttribute('hidden','');document.querySelector('.sd-model-picker')?.setAttribute('hidden','');}
const selected=new Set(),custom=[];let films=[],allFilms=[],token='',busy=false;
$('sd-model').value=model;
function status(text,error=false){$('sd-status').textContent=text;$('sd-status').dataset.error=String(error);}
function update(){
 $('sd-count').textContent=`已选 ${selected.size+custom.length} / ${films.length+custom.length} 款`+(visualPage?'':` · ${(4096+(selected.size+custom.length)*12288)/1024} KiB`);
 $('sd-download').disabled=busy||!model||!(selected.size+custom.length);
 for(const input of document.querySelectorAll('#sd-films input')){input.checked=selected.has(Number(input.value));input.disabled=busy;}
 for(const label of document.querySelectorAll('#sd-films .resource-film'))label.classList.toggle('selected',selected.has(Number(label.dataset.film)));
 const total=document.getElementById('library-total');if(total)total.textContent=films.length+' 款胶卷';
 $('sd-export-all').disabled=busy||!model||!films.length;
 $('sd-all').disabled=busy||!films.length;$('sd-none').disabled=busy||!films.length;
 $('custom-add').disabled=busy||!model;
 for(const button of $('custom-films').querySelectorAll('button'))button.disabled=busy;
 $('sd-model').disabled=busy;
}
function customStatus(message,error=false){$('custom-status').textContent=message;$('custom-status').dataset.error=String(error);}
function renderCustom(){
 const host=$('custom-films');host.replaceChildren();
 for(const entry of custom){const card=document.createElement('div'),name=document.createElement('strong'),button=document.createElement('button');
  card.className='sd-film';name.textContent=entry.name;button.type='button';button.textContent='移除';button.disabled=busy;
  const icon=document.createElement('img');icon.src=customFilmArtwork(entry.name);icon.alt='';icon.width=72;icon.height=72;
  button.onclick=()=>{custom.splice(custom.indexOf(entry),1);renderCustom();update();};card.append(icon,name,button);host.append(card);
 }
}
const fileBase64=file=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(Error('读取 LUT 文件失败'));reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.readAsDataURL(file);});
$('custom-add').onclick=async()=>{
 if(busy||!model)return;
 const name=$('custom-name').value.trim(),file=$('custom-file').files?.[0];
 if(!/^[\x20-\x7e]{1,23}$/.test(name)){customStatus('胶卷名称需为 1–23 个英文字符。',true);return;}
 if(!file||!file.name.toLowerCase().endsWith('.cube')||!file.size||file.size>8*1024*1024){customStatus('请选择不超过 8 MiB 的 .cube 文件。',true);return;}
 if(custom.some(v=>v.name.toLowerCase()===name.toLowerCase())){customStatus('胶卷名称重复。',true);return;}
 try{busy=true;update();const base64=await fileBase64(file);custom.push({name,filename:file.name,base64});$('custom-name').value='';$('custom-file').value='';customStatus(`已添加 ${name}；下载时会校验 LUT 内容。`);renderCustom();}
 catch(e){customStatus(e.message,true);}finally{busy=false;update();}
};
$('sd-all').onclick=()=>{films.forEach(f=>selected.add(f.id));update();};
$('sd-none').onclick=()=>{selected.clear();update();};
$('sd-export-all').onclick=()=>{
 if(busy||!model||!films.length)return;
 films.forEach(f=>selected.add(f.id));update();return $('sd-download').onclick();
};
$('sd-download').onclick=async()=>{
 if(busy||!model||!(selected.size+custom.length))return;
 busy=true;update();status(custom.length?'正在拟合自定义 LUT 并生成误差报告，请稍候…':'正在打包并校验胶卷…');
 try{
  const response=await fetch(model==='gr4'?'/api/gr4/native-library/sd-export':'/api/gr3/sd-library/export',{method:'POST',headers:{'Content-Type':'application/json','X-M10V-Token':token},body:JSON.stringify({model,ids:films.filter(f=>selected.has(f.id)).map(f=>f.id),...(!gr4Page?{customFilms:custom}: {})})});
  if(!response.ok)throw Error((await response.json()).error||'下载失败');
  const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='M10V-SD-films.zip';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  status('已生成下载文件。请按安装说明复制到 SD 卡。');
 }catch(e){status(e.message,true);}finally{busy=false;update();}
};
try{
 const responses=await Promise.all([fetch('/api/status'),fetch('/api/'+(gr4Page?'gr4':'gr3')+'/native-library/catalog')]);
 if(responses.some(r=>!r.ok))throw Error('胶卷目录读取失败，请刷新重试');
 const [session,catalog]=await Promise.all(responses.map(r=>r.json()));token=session.session_token;allFilms=catalog.films;
 if(!token||!Array.isArray(allFilms)||!allFilms.length)throw Error('胶卷目录不可用');
 applyModel(model);
 $('sd-films').setAttribute('aria-busy','false');
}catch(e){$('sd-films').setAttribute('aria-busy','false');$('sd-count').textContent='目录暂不可用';status(e.message,true);}

function applyModel(next){
 model=gr4Page?'gr4':['gr3','gr3x'].includes(next)?next:'';
 $('sd-model').value=model;
 films=model?catalogFilms(allFilms,model):[];
 selected.clear();$('sd-films').replaceChildren();
 for(const node of document.querySelectorAll('[data-film-count-copy]'))for(const child of node.childNodes)if(child.nodeType===3)child.textContent=child.textContent.replace(/[0-9]+(?=\s*[套款])/g,String(films.length));
 for(const f of films){
  selected.add(f.id);const label=document.createElement('label'),art=document.createElement('span'),check=document.createElement('input'),icon=document.createElement('img'),name=document.createElement('span'),meta=document.createElement('span'),dot=document.createElement('span');
  label.className='resource-film selected';label.dataset.film=String(f.id);art.className='film-art';check.type='checkbox';check.value=f.id;check.checked=true;check.setAttribute('aria-label','选择 '+f.name);check.onchange=()=>{check.checked?selected.add(f.id):selected.delete(f.id);update();};
  dot.className='select-dot';dot.textContent='✓';icon.src=f.icon_url;icon.alt='';icon.width=95;icon.height=95;name.className='film-name';name.textContent=f.name;meta.className='film-meta';meta.textContent=f.group;
  art.append(check,dot,icon);label.append(art,name,meta);$('sd-films').append(label);
 }
 update();status(visualPage?'':model?`${model==='gr3x'?'GR IIIx':model==='gr4'?'GR IV':'GR III'} 配套资源，可全选或多选，不改变工作台已选胶卷。`:'请先选择 GR III 或 GR IIIx，确认机型后再导出。',!model);
}
$('sd-model').onchange=()=>{
 if(busy){$('sd-model').value=model;return;}
 applyModel($('sd-model').value);
 if(model)history.replaceState(null,'','#model='+model);
};
