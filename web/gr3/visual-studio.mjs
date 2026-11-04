import {createFilmPreview} from './preview-controller.mjs';
import {paperPreviewLook} from './paper-preview.mjs';
import {supportsNativeFilm} from './model-capabilities.mjs';
import {defaultFilmEffects,resetNativeTexture} from './native-library-state.mjs';
const FEATURED=[37,35,56,66,299,34,33,67];
const details={
 37:{brand:'KODAK',category:'color',meta:'C41 · ISO 400',note:'温暖肤色，柔和日光。',tags:['人像','日常','暖调']},
 35:{brand:'KODAK',category:'color',meta:'C41 · ISO 200',note:'像午后阳光一样，明亮温暖。',tags:['街拍','暖黄','复古']},
 56:{brand:'FUJICOLOR',category:'color',meta:'C41 · ISO 200',note:'清透绿调，留住日常的呼吸感。',tags:['街头','自然','清透']},
 66:{brand:'KODAK',category:'cinema',meta:'ECN2 · DAYLIGHT',note:'舒展的层次，电影里的日光。',tags:['电影感','日光','柔和']},
 299:{brand:'KODAK',category:'bw',meta:'B&W · ISO 400',note:'纯粹黑白，细节与情绪并存。',tags:['黑白','纪实','颗粒']},
 34:{brand:'KODAK',category:'color',meta:'C41 · ISO 100',note:'鲜明色彩，利落细腻。',tags:['浓郁','风景','清晰']},
 33:{brand:'CINESTILL',category:'cinema',meta:'ECN2 · TUNGSTEN',note:'蓝色夜晚，柔和霓虹。',tags:['夜景','冷调','电影感']},
 67:{brand:'HARMAN',category:'color',meta:'C41 · ISO 200',note:'一点意外，让画面更有性格。',tags:['实验','橙红','个性']},
};
const metadata=film=>details[film.id]||{brand:film.name.split(' ')[0].toUpperCase(),category:film.group==='D76'?'bw':film.group==='ECN2'?'cinema':'color',meta:film.group,note:film.description||'本卷参数独立保存。',tags:[film.group]};
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
export function mountVisualStudio({state,editor,getModel,importModel,generate,showSettings,refreshFeatures,isBusy}){
 const $=id=>document.getElementById(id),engine=$('native-editor');
 let active=37,view='films',category='all',query='',all=false,previewMode='film',renderer=createFilmPreview({width:1536,height:1024}),previewSequence=0;
 let renderQueued=false,toastTimer,importing=false,legacyLooks=[];
 const config=()=>editor.getConfiguration();
 const catalog=()=>state.nativeCatalog.filter(f=>supportsNativeFilm(getModel(),f.id));
 const byId=id=>catalog().find(f=>f.id===id);
 const canvas=document.createElement('canvas');canvas.width=1536;canvas.height=1024;canvas.setAttribute('aria-label','浏览器胶卷色彩示意');canvas.className='visual-preview-canvas';$('preview-frame').querySelector('img').after(canvas);
 const toast=message=>{$('toast').textContent=message;$('toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),2400);};
 // Live controls are moved, retaining every original ID, handler and configuration path.
 $('tools-view').querySelector('[data-live-tools]').append($('imaging-settings'));
 const advanced=document.querySelector('.advanced-options');if(advanced){const section=node('section',undefined,'advanced-options');section.append(node('h3','调试选项'));for(const child of [...advanced.children])if(child.tagName!=='SUMMARY')section.append(child);advanced.replaceWith(section);}

 $('visual-stock-controls').append(engine);
 for(const id of ['preflight-result','build-result','cancel-build','build-completion'])$('visual-build-host').append($(id));
 const undo=$('undo-edit'),redo=$('redo-edit');undo.className='visual-history';redo.className='visual-history';
 document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='z'&&!/^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)){event.preventDefault();(event.shiftKey?redo:undo).click();refresh();}});
 function activeSlot(){return config().slots.find(slot=>slot.film===active);}
 const effectLevels=['关','轻','中','强'];
 const haloToggle=$('halo-toggle');
 const effectControls=node('div',undefined,'film-effect-controls');
 const haloControls=node('div',undefined,'film-effect-controls');
 haloToggle.closest('.toggle-row').before(effectControls);
 haloToggle.closest('.toggle-row').after(haloControls);
 function updateSlot(update){
  const next=config(),index=next.slots.findIndex(slot=>slot.film===active);
  if(index<0||isBusy())return;
  update(next.slots[index]);
  editor.setConfiguration(next,{filmSlot:index});
  refresh();
 }
 function control(parent,label,choices,change){
  const row=node('label',undefined,'control-label'),input=node('select');
  input.setAttribute('aria-label',label);
  row.append(node('span',label),input);
  input.append(...choices.map(([value,name])=>{const option=node('option',name);option.value=value;return option;}));
  input.onchange=()=>updateSlot(slot=>change(slot,Number(input.value)));
  parent.append(row);
  return {row,input};
 }
 const filmEffects=[
  ['leakGain','漏光',effectLevels],['leakPosition','漏光位置',['左','上','右','下','随机']],
  ['leakSpread','漏光范围',['低','中','高']],['blur','模糊',effectLevels],
 ].map(([key,label,labels])=>[key,control(effectControls,label,labels.map((label,value)=>[value,label]),
  (slot,value)=>{slot.filmEffects={...defaultFilmEffects(),...slot.filmEffects,[key]:value};})]);
 const haloMode=control(haloControls,'光晕模式',[[4,'高光溢出'],[5,'横向拉丝']],(slot,value)=>{slot.halo.profile=value;});
 const haloParameters=[['gain','光晕强度'],['spread','光晕范围'],['threshold','光晕阈值']].map(([key,label])=>[key,
  control(haloControls,label,Array.from({length:9},(_,i)=>[i,String(i)]),(slot,value)=>{slot.halo[key]=value;})]);
 function renderEffects(slot){
  const perFilm=state.features.has('ispEffects');
  const special=[33,67].includes(active),halo=slot?.halo;
  const haloOn=!!halo?.gain&&(special||halo.profile===4||halo.profile===5);
  const canEdit=!!slot&&!isBusy(),haloAvailable=getModel()!=='gr4'&&state.features.has('halation');
  const grainLevels=perFilm?['关','细','中','粗']:['关闭','弱','中','强'];
  for(const button of document.querySelectorAll('[data-grain]')){
   const value=Number(button.dataset.grain);
   button.textContent=grainLevels[value];
   button.classList.toggle('active',value===(slot?.grain||0));
   button.disabled=!canEdit||(!perFilm&&[289,290].includes(active)&&value!==0);
  }
  $('grain-value').textContent=grainLevels[slot?.grain||0];
  effectControls.hidden=!perFilm;
  for(const [key,{row,input}] of filmEffects){
   row.hidden=(key==='leakPosition'||key==='leakSpread')&&!slot?.filmEffects?.leakGain;
   input.disabled=!canEdit;input.value=slot?.filmEffects?.[key]??0;
  }
  haloToggle.disabled=!canEdit||!haloAvailable;
  haloToggle.setAttribute('aria-pressed',String(haloOn));
  haloControls.hidden=!haloAvailable||!haloOn;
  haloMode.row.hidden=special;haloMode.input.value=halo?.profile===5?5:4;
  haloMode.input.disabled=!canEdit;
  for(const [key,{input}] of haloParameters){input.value=halo?.[key]??0;input.disabled=!canEdit;}
 }
 function select(id){
  active=id;const index=config().slots.findIndex(slot=>slot.film===id);
  if(index>=0)engine.querySelectorAll('#slots .slot')[index]?.click();
  render();renderPreview();
 }
 function renderFilms(){
  const films=catalog(),rows=(all||query||category!=='all'?films:FEATURED.map(id=>films.find(f=>f.id===id)).filter(Boolean)).filter(f=>(category==='all'||metadata(f).category===category)&&f.name.toLowerCase().includes(query));
  const grid=$('film-grid');grid.replaceChildren();
  for(const film of rows){const button=node('button',undefined,'film-card'+(active===film.id?' active':''));button.type='button';button.dataset.film=String(film.id);button.setAttribute('aria-label',`预览 ${film.name}`);button.setAttribute('aria-pressed',String(active===film.id));
   const art=node('span',undefined,'film-art'),dot=node('span',active===film.id?'✓':'','select-dot'),icon=document.createElement('img');icon.src=film.icon_url;icon.alt='';icon.width=80;icon.height=80;art.append(dot,icon);
   button.append(art,node('span',film.name,'film-name'),node('span',metadata(film).meta,'film-meta'));button.onclick=()=>select(film.id);grid.append(button);
  }
  $('no-results').hidden=rows.length>0;document.querySelector('.library-count').textContent='/ '+String(rows.length).padStart(2,'0');
 }
 function renderSelected(){
  const c=config(),host=$('selected-films');host.replaceChildren();
  for(const [index,slot]of c.slots.entries()){const film=byId(slot.film);if(!film)continue;const button=node('button',undefined,'selected-item'+(slot.film===active?' active':''));button.type='button';button.dataset.selected=String(film.id);const icon=document.createElement('img');icon.className='selected-film-icon';icon.src=film.icon_compact_url||film.icon_url;icon.alt='';const remove=node('span','×','remove-film');remove.dataset.remove=String(film.id);remove.setAttribute('aria-label',`移除 ${film.name}`);button.append(node('span',String(index+1).padStart(2,'0'),'index'),icon,node('span',film.name,'selected-name'),remove);button.onclick=event=>{if(event.target.closest('[data-remove]')){editor.toggleFilm(film.id);render();}else select(film.id);};host.append(button);}
  $('selected-count').textContent=String(c.slots.length).padStart(2,'0');$('summary-count').textContent=c.slots.length+' 款胶卷';$('selected-mini').replaceChildren(...c.slots.slice(0,5).map(slot=>{const img=document.createElement('img'),film=byId(slot.film);img.src=film?.icon_compact_url||film?.icon_url||'';img.alt='';return img;}));
 }
 function render(){
  const film=byId(active)||catalog()[0];if(!film)return;active=film.id;const d=metadata(film),slot=activeSlot(),included=!!slot,c=config();
  $('look-title').textContent=film.name;$('photo-look').textContent=film.name.toUpperCase();$('look-type').textContent=d.brand+' / '+(d.category==='bw'?'BLACK & WHITE':d.category==='cinema'?'MOTION PICTURE':'COLOR NEGATIVE');$('look-note').textContent=d.note;$('look-tags').replaceChildren(...d.tags.map(tag=>node('span',tag,'tag')));
  const add=$('add-film');add.classList.toggle('selected',included);add.replaceChildren();if(included){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#i-check');svg.append(use);add.append(svg,document.createTextNode('已在方案中'));}else add.textContent='+ 加入方案';
  renderEffects(slot);$('look-reset').disabled=!included||isBusy();
  $('film-name-toggle').setAttribute('aria-pressed',String(c.filmNameStamp));$('date-toggle').setAttribute('aria-pressed',String(c.stamp>0));
  for(const link of document.querySelectorAll('a[href^="/gr3/sd-library.html"]'))link.href='/gr3/sd-library.html#model='+getModel();
  for(const link of document.querySelectorAll('header .wordmark,.primary-nav>a:first-child'))link.href='/gr3/#model='+getModel();
  $('device-name').textContent=getModel()==='gr3x'?'GR IIIx':getModel()==='gr4'?'GR IV':'GR III';$('device-version').textContent=getModel()==='gr3x'?'1.60':getModel()==='gr4'?'1.11':'2.10';
  $('generate-button').disabled=importing||isBusy()||getModel()==='gr4';$('visual-source-state').textContent=importing?'正在核对来源':state.projectId?'准备就绪':'选择机型后生成';
  const icons={halation:'i-sun',digitalHdf:'i-sun',border:'i-frame',ispEffects:'i-sliders',timestamp:'i-type',aspect:'i-frame',negativeGrain:'i-grid',rawNr:'i-sliders',level:'i-grid',abCompare:'i-arrow',powerImages:'i-camera'};
  for(const row of document.querySelectorAll('#feature-list .feature-row')){row.classList.add('tool-card');if(!row.querySelector('.visual-tool-icon')){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS('http://www.w3.org/2000/svg','use');svg.setAttribute('class','tool-icon visual-tool-icon');svg.setAttribute('aria-hidden','true');use.setAttribute('href','#'+(icons[row.dataset.feature]||'i-camera'));svg.append(use);row.prepend(svg);}}
  renderFilms();renderSelected();
 }
 async function renderPreview(){
  const ticket=++previewSequence,film=byId(active),look=paperPreviewLook(film,legacyLooks,activeSlot()?.effects||{});const show=previewMode==='film'&&!!look;canvas.hidden=!show;$('preview-frame').classList.toggle('original',!show);
  for(const button of document.querySelectorAll('[data-preview]'))button.classList.toggle('active',button.dataset.preview===(show?'film':'original'));
  if(show)renderer.request(canvas,look,()=>{if(ticket===previewSequence){canvas.hidden=true;$('preview-frame').classList.add('original');}});
 }
 function refresh(){if(renderQueued)return;renderQueued=true;queueMicrotask(()=>{renderQueued=false;render();renderPreview();});}
 function reflectView(){
  $('films-view').hidden=view!=='films';$('tools-view').hidden=view!=='tools';$('page-title').replaceChildren(document.createTextNode(view==='films'?'胶卷工作台':'影像工具'));const dot=node('span','.');dot.style.color='var(--accent)';$('page-title').append(dot);
  document.querySelectorAll('[data-view]').forEach(button=>button.classList.toggle('active',button.dataset.view===view));
 }
 function setView(next){
  if(next==='build'){void requestGenerate();return;}
  view=next==='tools'?'tools':'films';reflectView();showSettings(view==='films'?'library':'imaging');refresh();
 }
 async function requestGenerate(){
  if(importing||isBusy())return;
  if(!state.projectId){await changeModel(getModel());if(!state.projectId)return;}
  generate();
 }
 async function changeModel(model){if(importing||isBusy())return;const desiredView=view;importing=true;render();try{await importModel(model);setView(desiredView);}catch(error){toast(error.message);}finally{importing=false;if(state.projectId)history.replaceState(null,'','#model='+getModel()+(view==='tools'?'&view=tools':''));render();renderPreview();}}
 for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>setView(button.dataset.view);
 for(const button of document.querySelectorAll('[data-category]'))button.onclick=()=>{all=button.dataset.category==='all'?!all:true;category=button.dataset.category;document.querySelectorAll('[data-category]').forEach(other=>other.classList.toggle('active',other===button));renderFilms();};
 for(const button of document.querySelectorAll('[data-preview]'))button.onclick=()=>{previewMode=button.dataset.preview;void renderPreview();};
 $('film-search').oninput=event=>{query=event.target.value.toLowerCase().trim();renderFilms();};
 $('add-film').onclick=()=>{if(activeSlot()){toast('这款胶卷已在方案中');return;}editor.toggleFilm(active);refresh();};
 for(const button of document.querySelectorAll('[data-grain]'))button.onclick=()=>updateSlot(slot=>{
  slot.grain=Number(button.dataset.grain);
  if(state.features.has('ispEffects'))slot.filmEffects??=defaultFilmEffects();
 });
 $('look-reset').onclick=()=>{
  const next=config(),index=next.slots.findIndex(slot=>slot.film===active);
  if(index<0||isBusy())return;
  const reset=resetNativeTexture(next,index);
  if(state.features.has('ispEffects'))reset.slots[index].filmEffects=defaultFilmEffects();
  if(state.features.has('halation'))reset.slots[index].halo.profile=6;
  editor.setConfiguration(reset,{filmSlot:index});refresh();
 };
 haloToggle.onclick=()=>updateSlot(slot=>{
  const special=[33,67].includes(slot.film),enabled=haloToggle.getAttribute('aria-pressed')==='true';
  slot.halo.gain=enabled?0:3;slot.halo.profile=enabled?6:special?2:4;
 });
 const setMark=(key,value)=>{const next={...config(),[key]:value};if(next.stamp||next.filmNameStamp)state.features.add('timestamp');else state.features.delete('timestamp');editor.setConfiguration(next);refreshFeatures();refresh();};
 $('film-name-toggle').onclick=()=>setMark('filmNameStamp',!config().filmNameStamp);$('date-toggle').onclick=()=>setMark('stamp',config().stamp?0:1);
 $('generate-button').onclick=()=>void requestGenerate();
 $('camera-button').onclick=()=>{const open=$('camera-menu').hidden;$('camera-menu').hidden=!open;$('camera-button').setAttribute('aria-expanded',String(open));};
 for(const button of document.querySelectorAll('[data-model]'))button.onclick=()=>{$('camera-menu').hidden=true;$('camera-button').setAttribute('aria-expanded','false');void changeModel(button.dataset.model);};
 document.addEventListener('click',event=>{if(!event.target.closest('.camera-picker')){$('camera-menu').hidden=true;$('camera-button').setAttribute('aria-expanded','false');}});
 $('visual-progress-close').onclick=()=>{if(isBusy())$('cancel-build').click();$('visual-progress').close();};
 new MutationObserver(()=>{const message=$('build-result').textContent||$('preflight-result').textContent;$('visual-action-status').textContent=message;}).observe($('visual-build-host'),{subtree:true,childList:true,characterData:true});
 new MutationObserver(()=>{const message=engine.querySelector('#film-selection-status')?.textContent?.trim();if(message)toast(message);}).observe(engine.querySelector('#film-selection-status'),{childList:true,characterData:true,subtree:true});
 new MutationObserver(()=>{const text=$('draft-indicator').textContent;document.querySelector('.saved').lastChild.textContent=text.includes('失败')?'草稿未保存':'草稿已保存';}).observe($('draft-indicator'),{childList:true,characterData:true,subtree:true});
 window.addEventListener('pagehide',()=>renderer.destroy());
 fetch('/gr3/film-catalog.json').then(r=>r.json()).then(data=>{legacyLooks=data.looks;renderPreview();}).catch(()=>{});
 const pageParams=new URLSearchParams(location.hash.slice(1));const initialView=pageParams.get('view')||(location.hash==='#tools'?'tools':location.hash==='#build'?'build':'films');
 render();select(active);if(initialView==='tools')setView('tools');
 void changeModel(getModel()).then(()=>{if(initialView==='build')void requestGenerate();});
 return {refresh,showView:next=>{view=next==='imaging'?'tools':'films';reflectView();refresh();},startBuild(){if(!$('visual-progress').open)$('visual-progress').showModal();},endBuild(){render();},toast};
}
