import {customFilmArtwork} from '/gr3/film-artwork.mjs';
const model=location.pathname.startsWith('/gr4')?'gr4':'gr3';
const $=id=>document.getElementById(id);
if(model==='gr4')document.querySelector('.sd-custom')?.setAttribute('hidden','');
const selected=new Set(),custom=[];let films=[],token='',busy=false;
function status(text,error=false){$('sd-status').textContent=text;$('sd-status').dataset.error=String(error);}
function update(){
 $('sd-count').textContent=`已选 ${selected.size+custom.length} / ${films.length+custom.length} 款 · ${(4096+(selected.size+custom.length)*12288)/1024} KiB`;
 $('sd-download').disabled=busy||!(selected.size+custom.length);
 for(const input of document.querySelectorAll('#sd-films input')){input.checked=selected.has(Number(input.value));input.disabled=busy;}
 $('sd-all').disabled=busy||!films.length;$('sd-none').disabled=busy||!films.length;
 $('custom-add').disabled=busy;
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
 const name=$('custom-name').value.trim(),file=$('custom-file').files?.[0];
 if(!/^[\x20-\x7e]{1,23}$/.test(name)){customStatus('胶卷名称需为 1–23 个英文字符。',true);return;}
 if(!file||!file.name.toLowerCase().endsWith('.cube')||!file.size||file.size>8*1024*1024){customStatus('请选择不超过 8 MiB 的 .cube 文件。',true);return;}
 if(custom.some(v=>v.name.toLowerCase()===name.toLowerCase())){customStatus('胶卷名称重复。',true);return;}
 try{busy=true;update();const base64=await fileBase64(file);custom.push({name,filename:file.name,base64});$('custom-name').value='';$('custom-file').value='';customStatus(`已添加 ${name}；下载时会校验 LUT 内容。`);renderCustom();}
 catch(e){customStatus(e.message,true);}finally{busy=false;update();}
};
$('sd-all').onclick=()=>{films.forEach(f=>selected.add(f.id));update();};
$('sd-none').onclick=()=>{selected.clear();update();};
$('sd-download').onclick=async()=>{
 busy=true;update();status(custom.length?'正在拟合自定义 LUT 并生成误差报告，请稍候…':'正在打包并校验胶卷…');
 try{
  const response=await fetch(model==='gr4'?'/api/gr4/native-library/sd-export':'/api/gr3/sd-library/export',{method:'POST',headers:{'Content-Type':'application/json','X-M10V-Token':token},body:JSON.stringify({model,ids:films.filter(f=>selected.has(f.id)).map(f=>f.id),...(model==='gr3'?{customFilms:custom}: {})})});
  if(!response.ok)throw Error((await response.json()).error||'下载失败');
  const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='M10V-SD-films.zip';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  status('已生成下载文件。请按下方说明复制到 SD 卡。');
 }catch(e){status(e.message,true);}finally{busy=false;update();}
};
try{
 const responses=await Promise.all([fetch('/api/status'),fetch('/api/'+model+'/native-library/catalog')]);
 if(responses.some(r=>!r.ok))throw Error('胶卷目录读取失败，请刷新重试');
 const [session,catalog]=await Promise.all(responses.map(r=>r.json()));token=session.session_token;films=catalog.films;
 if(!token||!Array.isArray(films)||!films.length)throw Error('胶卷目录不可用');
 for(const node of document.querySelectorAll('[data-film-count-copy]'))for(const child of node.childNodes)if(child.nodeType===3)child.textContent=child.textContent.replace(/[0-9]+(?=\s*[套款])/g,String(films.length));
 const groups=new Map();for(const film of films){selected.add(film.id);const group=film.group||'胶卷';if(!groups.has(group))groups.set(group,[]);groups.get(group).push(film);}
 for(const [name,rows] of groups){
  const section=document.createElement('fieldset'),legend=document.createElement('legend'),grid=document.createElement('div');legend.textContent=`${name} · ${rows.length} 款`;grid.className='sd-grid';section.append(legend,grid);
  for(const f of rows){const label=document.createElement('label'),check=document.createElement('input'),icon=document.createElement('img'),text=document.createElement('span');
   label.className='sd-film';check.type='checkbox';check.value=f.id;check.checked=true;check.onchange=()=>{check.checked?selected.add(f.id):selected.delete(f.id);update();};icon.src=f.icon_url;icon.alt='';icon.width=40;icon.height=40;text.textContent=`${f.number??films.indexOf(f)+1}. ${f.name}`;label.append(check,icon,text);if(f.id>=299&&f.id<=305){const badge=document.createElement('small');badge.textContent=f.infrared_style?'\u7ea2\u5916\u6ee4\u955c\u98ce\u683c\u8fd1\u4f3c':'\u98ce\u683c\u8fd1\u4f3c';badge.style.cssText='display:block;font-size:12px;font-weight:400;opacity:.7;margin-top:4px';text.append(badge);}grid.append(label);}
  $('sd-films').append(section);
 }
 $('sd-films').setAttribute('aria-busy','false');update();status('可全选或多选，不改变固件工作台的已选胶卷。');
}catch(e){$('sd-films').setAttribute('aria-busy','false');$('sd-count').textContent='目录暂不可用';status(e.message,true);}
