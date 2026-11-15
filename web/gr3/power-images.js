export function mountPowerImages(root,{api,onChange,model}){
 let configuration={};
 let enabled=true;
 const cards={};
 const tabs=document.createElement('div');tabs.className='power-mode-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','开关机画面');root.prepend(tabs);
 let activeKind='startup';
 const entries=[['startup','开机图片'],['shutdown','关机图片']];
 for(const [kind,label] of entries){
  const card=document.createElement('section');card.className='power-image-card';
  card.innerHTML=`<h3>${label}</h3><p>${kind==='startup'?'替换原生 StartUp.jpg；显示时机仍待真机验证。原生槽较小，细节可能被压缩。':'替换所有五种原厂关机请求（含 Street）；相机显示仍待真机验证。'}</p><canvas width="720" height="480" aria-label="${label}裁切预览"></canvas><label class="outline power-upload" tabindex="0" role="button">上传图片<input type="file" accept="image/jpeg,image/png,image/webp" hidden></label><div class="power-crop" hidden><label>缩放<input data-field="zoom" type="range" min="1" max="3" step="0.01" value="1"></label><label>左右<input data-field="x" type="range" min="0" max="1" step="0.01" value="0.5"></label><label>上下<input data-field="y" type="range" min="0" max="1" step="0.01" value="0.5"></label><button type="button" class="outline" data-apply>应用裁切</button></div><button type="button" class="outline" data-reset>恢复默认</button><p role="status" aria-live="polite" class="power-status">使用原厂图片</p>`;
  const visual=document.createElement('div');visual.className='power-visual';visual.append(card.querySelector('canvas'));
  const controls=document.createElement('div');controls.className='power-editor-controls';for(const node of [...card.querySelectorAll('.power-upload,.power-crop,[data-reset],.power-status')])controls.append(node);
  card.append(visual,controls);card.id='power-'+kind+'-panel';card.setAttribute('role','tabpanel');card.setAttribute('aria-labelledby','power-'+kind+'-tab');card.hidden=kind!==activeKind;
  const tab=document.createElement('button');tab.type='button';tab.id='power-'+kind+'-tab';tab.setAttribute('role','tab');tab.setAttribute('aria-controls',card.id);tab.setAttribute('aria-selected',String(kind===activeKind));tab.tabIndex=kind===activeKind?0:-1;tab.innerHTML=`${label}<small>原厂默认</small>`;
  tab.onclick=()=>{activeKind=kind;for(const item of Object.values(cards)){const selected=item.card===card;item.card.hidden=!selected;item.tab.setAttribute('aria-selected',String(selected));item.tab.tabIndex=selected?0:-1;}};
  tab.onkeydown=event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const target=event.key==='Home'?tabs.firstElementChild:event.key==='End'?tabs.lastElementChild:kind==='startup'?tabs.lastElementChild:tabs.firstElementChild;target.click();target.focus();}};tabs.append(tab);root.append(card);
  card.querySelector('.power-upload').addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();card.querySelector('input[type=file]').click();}});
  const canvas=card.querySelector('canvas'),context=canvas.getContext('2d'),status=card.querySelector('.power-status'),crop=card.querySelector('.power-crop');
  let bitmap=null,localSequence=0,previewFailed=false;
  const draw=()=>{context.fillStyle='#171717';context.fillRect(0,0,720,480);if(!bitmap){context.fillStyle='#ddd';context.textAlign='center';context.font='24px sans-serif';context.fillText('原厂图片',360,245);return;}const value=k=>Number(card.querySelector(`[data-field="${k}"]`).value),scale=Math.max(720/bitmap.width,480/bitmap.height)*value('zoom'),w=bitmap.width*scale,h=bitmap.height*scale;context.drawImage(bitmap,-(w-720)*value('x'),-(h-480)*value('y'),w,h);};
  async function showSaved(){previewFailed=false;tab.querySelector('small').textContent=configuration[kind]?'已自定义':'原厂默认';const mySequence=++localSequence;bitmap?.close?.();bitmap=null;crop.hidden=true;draw();if(!configuration[kind]){status.textContent='使用原厂图片';return true;}status.textContent='正在核验压缩预览…';try{const result=await(await api('/api/gr3/power-images/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[kind]:configuration[kind]})})).json();if(mySequence!==localSequence)return;const response=await fetch(result[kind].preview_data_url),image=await createImageBitmap(await response.blob());if(mySequence!==localSequence){image.close();return;}context.drawImage(image,0,0,720,480);image.close();status.textContent=`已加入同一固件 · 720 × 480 · 压缩质量 ${result[kind].quality}`;return true;}catch(error){previewFailed=true;status.textContent=error.message;return false;}}
  card.querySelector('input[type=file]').addEventListener('change',async event=>{const file=event.target.files[0];event.target.value='';if(!file)return;const mySequence=++localSequence;try{if(file.size>20*1024*1024)throw Error('图片最大 20 MB');const image=await createImageBitmap(file);if(image.width*image.height>40000000){image.close();throw Error('图片最大 4000 万像素');}if(mySequence!==localSequence){image.close();return;}bitmap?.close?.();bitmap=image;for(const [key,value] of [['zoom',1],['x',0.5],['y',0.5]])card.querySelector(`[data-field="${key}"]`).value=value;crop.hidden=false;draw();status.textContent='调整裁切后点“应用裁切”加入固件';}catch(error){status.textContent=error.message;}});
  for(const input of card.querySelectorAll('input[type=range]'))input.addEventListener('input',draw);
  const apply=async()=>{if(!bitmap)return previewFailed?await showSaved():true;if(kind==='shutdown'){albumSequence++;albumPending=null;delete configuration.shutdownAlbum;showAlbum();}configuration[kind]={jpeg_base64:canvas.toDataURL('image/jpeg',0.95).split(',')[1]};onChange();return await showSaved();};
  card.querySelector('[data-apply]').addEventListener('click',apply);
  card.querySelector('[data-reset]').addEventListener('click',()=>{delete configuration[kind];onChange();showSaved();});
  cards[kind]={showSaved,card,tab,apply,hasPending:()=>!!bitmap||previewFailed};draw();
 }
 const album=document.createElement('section');album.className='power-image-card';
 album.innerHTML='<h3>机内关机图相册</h3><p>选择 1 至 3 张已裁切的 720 × 480 JPEG。刷入后在「设置 → 关机图」选择图片。</p><label class="outline power-upload">选择图片<input type="file" accept="image/jpeg,.jpg,.jpeg" multiple hidden></label><button type="button" class="outline" data-clear-album>清空相册</button><p role="status" aria-live="polite"></p>';
 root.append(album);
 const albumStatus=album.querySelector('[role=status]');
 let albumSequence=0,albumPending=null;
 function showAlbum(){
  const count=configuration.shutdownAlbum?.length??0;
  albumStatus.textContent=count?`已加入 ${count} 张图片`:'相册尚未添加图片';
  album.querySelector('[data-clear-album]').disabled=!count;
 }
 album.querySelector('input').onchange=event=>{
  const files=[...event.target.files];event.target.value='';if(!files.length)return;
  if(files.length>3||files.some(file=>file.size>512*1024)){albumStatus.textContent='请选择最多 3 张、每张不超过 512 KB 的 JPEG';return;}
  const sequence=++albumSequence;
  albumStatus.textContent='正在检查相册图片…';
  albumPending=(async()=>{
   try{
    const images=await Promise.all(files.map(file=>new Promise((resolve,reject)=>{
     const reader=new FileReader();reader.onload=()=>resolve({jpeg_base64:String(reader.result).split(',')[1]});
     reader.onerror=()=>reject(Error('无法读取图片'));reader.readAsDataURL(file);
    })));
    const result=await api('/api/gr3/power-images/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shutdownAlbum:images})});
    const preview=await result.json();
    if(!result.ok||preview.shutdownAlbum?.length!==images.length)throw Error('需要 720 × 480 JPEG 图片');
    if(sequence!==albumSequence)return true;
    delete configuration.shutdown;configuration.shutdownAlbum=images;cards.shutdown.showSaved();showAlbum();onChange();return true;
   }catch(error){if(sequence===albumSequence)albumStatus.textContent=error.message;return false;}
   finally{if(sequence===albumSequence)albumPending=null;}
  })();
 };
 album.querySelector('[data-clear-album]').onclick=()=>{albumSequence++;albumPending=null;delete configuration.shutdownAlbum;showAlbum();onChange();};
 showAlbum();
 const setModel=()=>{root.hidden=!enabled||!['gr3','gr3x'].includes(model());album.hidden=model()!=='gr3';};
 return {setEnabled:value=>{enabled=value;setModel();},hasPending:()=>enabled&&(!!albumPending||Object.values(cards).some(item=>item.hasPending())),applyPending:async()=>{if(!enabled)return true;if(albumPending&&!await albumPending)return false;for(const item of Object.values(cards))if(item.hasPending()&&!await item.apply())return false;return true;},getConfiguration:()=>structuredClone(model()==='gr3'?configuration:Object.fromEntries(Object.entries(configuration).filter(([key])=>key!=='shutdownAlbum'))),setConfiguration:value=>{albumSequence++;albumPending=null;configuration=structuredClone(value||{});for(const item of Object.values(cards))item.showSaved();showAlbum();},setModel};
}
