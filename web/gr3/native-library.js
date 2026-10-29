import {unwrapFirmwareDownload} from './firmware-download.mjs';
import {isGr3Family,modelCapabilities} from './model-capabilities.mjs';
import {renderZoomControls,validateZoomControls} from './zoom-controls.mjs';
import {normalizeVersionUnlock,assertVersionUnlockReceipt} from './version-unlock-state.mjs';
import {createFilmPreview} from './preview-controller.mjs';
import {enhanceFilmSelect} from './film-picker.mjs';
import {defaultConfiguration,normalizeConfiguration,configurationForModel,prepareZoomConfigurationForBuild,selectNativeFilm,toggleNativeFilm,resetNativeTexture,retainCatalogFilms,migrateRetiredFilms} from './native-library-state.mjs';
export function mountNativeLibrary(root=document,{model='gr3',showZoom=true,defaultZoomWrite=false,onInspect=()=>{},onChange=()=>{},onEditStart=()=>{},onEditCommit=()=>{}}={}) {
const selectionLimit=()=>modelCapabilities(sourceModel).filmSlots;
const catalogApi=model==='gr4'?'/api/gr4/native-library/catalog':'/api/gr3/native-library/catalog';
let halationWrite=false;
let pixelPreview=null,pixelFigure=null;
window.addEventListener('pagehide',()=>{pixelPreview?.destroy();pixelPreview=null;});
window.addEventListener('pageshow',event=>{if(event.persisted)render();});
const storageKey=model==='gr4'?'m10v-gr4-native-library-v1':'m10v-native-library-v1';
const $=s=>root.querySelector(s),levels=['关闭','弱','中','强'];
let configuration=defaultConfiguration(model),active=0,films=[],project=null,token='',busy=false,abort=null,urls=[],unresolved=[],sourceModel=model;
configuration.zoom.write=defaultZoomWrite&&isGr3Family(model);
try{const saved=localStorage.getItem(storageKey);if(saved)configuration=migrateRetiredFilms(JSON.parse(saved));}catch{}
configuration=configurationForModel(configuration,sourceModel);
// Retired M10V sketches migrate by slot; their numeric IDs remain firmware-compatible.

const message=(text,error=false)=>{$('#progress').textContent=text;$('#progress').dataset.error=String(error);};
function invalidate(meta={}){onChange(normalizeConfiguration(configuration),meta);for(const u of urls)URL.revokeObjectURL(u);urls=[];$('#downloads').hidden=true;message('');try{localStorage.setItem(storageKey,JSON.stringify(configuration));}catch{}}
function versionUnlockSnapshot(){
 if(sourceModel!=='gr3x')return normalizeVersionUnlock({enabled:false},sourceModel);
 const enabled=$('#native-version-unlock').checked;
 const option=$('#native-version-known').checked?{enabled,dsp:$('#native-version-dsp').value,cpu:$('#native-version-cpu').value}:{enabled,mode:'dsp-package-only'};
 return normalizeVersionUnlock(option,sourceModel);
}
function renderVersionUnlock(){
 if($('#native-bridge-guide'))$('#native-bridge-guide').hidden=sourceModel!=='gr3';
 const supported=sourceModel==='gr3x',toggle=$('#native-version-unlock'),known=$('#native-version-known');
 $('#native-version-unlock-option').hidden=!supported;if(!supported){toggle.checked=false;known.checked=false;}
 toggle.disabled=busy||!supported;$('#native-version-unlock-fields').hidden=!toggle.checked;
 known.disabled=busy||!supported||!toggle.checked;
 const advanced=supported&&toggle.checked&&known.checked;$('#native-version-known-fields').hidden=!advanced;
 for(const key of ['dsp','cpu']){$('#native-version-'+key).disabled=busy||!advanced;$('#native-version-'+key).required=advanced;$('#native-version-'+key).placeholder=(sourceModel==='gr3x'?'1.60':'2.10')+'.x.x';}
 let error='';try{versionUnlockSnapshot();}catch(e){error=e.message;}
 $('#native-version-error').textContent=error;return !error;
}
function segment(selector,labels,value,change){const node=$(selector);node.replaceChildren(...labels.map((text,i)=>{const b=document.createElement('button');b.type='button';b.dataset.focus=selector.slice(1)+'-'+i;b.textContent=text;b.setAttribute('aria-pressed',String(i===value));b.disabled=busy;b.onclick=()=>{change(i);invalidate();render();};return b;}));}
function render(){
 const focused=document.activeElement?.dataset?.focus;
 if(showZoom)renderZoomControls($('#native-zoom-controls'),configuration,sourceModel,value=>{configuration=value;invalidate();render();},busy);
 else if($('#native-zoom-controls'))$('#native-zoom-controls').hidden=true;
 active=Math.max(0,Math.min(active,configuration.slots.length-1));
 const current=configuration.slots[active];
 const countNode=$("#selected-film-count");if(countNode)countNode.textContent=`已选 ${configuration.slots.length}/${selectionLimit()}`;
 const params=$(".film-parameters-panel");if(params)params.hidden=!current;
 const slotNode=$('#slots');slotNode.replaceChildren(...configuration.slots.map((s,i)=>{const item=document.createElement('div');item.className='slot-item';const b=document.createElement('button');b.type='button';b.dataset.focus='slot-'+i;b.className='slot';b.disabled=busy;b.setAttribute('aria-pressed',String(i===active));const n=document.createElement('small');n.textContent=`已选 ${i+1}`;const t=document.createElement('strong');t.textContent=unresolved.find(v=>v.slot===i)?'需重选 · '+unresolved.find(v=>v.slot===i).id:films.find(f=>f.id===s.film)?.name||'载入中';const e=document.createElement('em');e.textContent=`颗粒 ${levels[s.grain]}`;const art=filmIcon(films.find(f=>f.id===s.film));b.append(n,art,t,e);b.onclick=()=>{active=i;const status=$('#film-selection-status');if(status)status.textContent='';render();};const remove=document.createElement('button');remove.type='button';remove.className='slot-remove';remove.textContent='×';remove.disabled=busy;remove.setAttribute('aria-label',`移除 ${t.textContent}`);remove.onclick=()=>toggleFilm(s.film);item.append(b,remove);return item;}));
 if(current){
 segment('#grain',levels,current.grain,v=>configuration.slots[active].grain=v);

 const film=configuration.slots[active].film;
 for(const button of $('#grain').querySelectorAll('button'))button.disabled=busy||((!modelCapabilities(sourceModel).nativeGrain||[289,290].includes(film))&&button.dataset.focus!=='grain-0');
 if(film===290&&!pixelFigure){
  pixelFigure=document.createElement('figure');pixelFigure.style.margin='16px 0';
  const canvas=document.createElement('canvas');canvas.width=620;canvas.height=413;
  canvas.style.cssText='display:block;width:100%;max-width:620px;height:auto;image-rendering:pixelated;border-radius:8px';
  canvas.setAttribute('role','img');canvas.setAttribute('aria-label','Pixel Worlds像素效果参考样张');
  const caption=document.createElement('figcaption');caption.className='hint';
  caption.textContent='Pixel Worlds · 效果参考（不含颗粒）。仅静态 JPEG；需更新固件，实际成片以相机为准。';
  pixelFigure.append(canvas,caption);$('#active-slot-label').closest('.section-head').after(pixelFigure);
 }
 if(pixelFigure){pixelFigure.hidden=film!==290;if(film===290){pixelPreview??=createFilmPreview();pixelPreview.request(pixelFigure.querySelector('canvas'),{film:290},error=>{pixelFigure.querySelector('figcaption').textContent=error;});}}
 onInspect(films.find(f=>f.id===film),true);
 const label=$('#active-slot-label');if(label)label.textContent=`已选 ${active+1} · ${films.find(f=>f.id===film)?.name||'载入中'}`;
 if($('#charmera-controls')){$('#charmera-controls').hidden=film!==289;$('#effect-charmeraColor').value=String(configuration.slots[active].effects.charmeraColor??0);$('#effect-charmeraColor').disabled=busy;}
 $('#halo-controls').hidden=halationWrite||![33,67].includes(film);
 $('#red-controls').hidden=![67,68].includes(film);
 $('#red-controls .label').textContent=(film===67?'Harman Phoenix II':'Harman Red')+' · 模拟曝光EI';
 const eiOptions=film===67?[[0,'EI 200 · 标准'],[1,'EI 120 · 增加曝光']]:[[0,'EI 125 · 标准'],[1,'EI 64 · 明亮橙黄'],[2,'EI 250 · 浓郁暗红']];
 $('#effect-filmExposure').replaceChildren(...eiOptions.map(([value,text])=>{const option=document.createElement('option');option.value=String(value);option.textContent=text;return option;}));
 $('#halo-controls .label').textContent=(film===67?'Harman Phoenix II':'800T')+' 光晕 · 当前胶卷';
 const effects=configuration.slots[active].effects;
 for(const k of ['filmExposure']){$('#effect-'+k).value=String(effects[k]);$('#effect-'+k).disabled=busy||(k==='filmExposure'&&![67,68].includes(film));}
 $('#reset-texture').disabled=busy;
 const halo=configuration.slots[active].halo;
 for(const k of ['gain','spread','threshold']){$('#halo-'+k).value=String(halo[k]);$('#halo-'+k+'-value').textContent=halo[k]+'/8';$('#halo-'+k).disabled=busy;}
 }else{for(const selector of ['#grain','#reset-texture','#halo-controls','#red-controls','#charmera-controls']){const node=$(selector);if(node){if(selector==='#grain')node.replaceChildren();else if(selector==='#reset-texture')node.disabled=true;else node.hidden=true;}}if(pixelFigure)pixelFigure.hidden=true;}
 $('#native-debug-mode').disabled=busy;
 const unlockValid=renderVersionUnlock();
 renderFilms();$('#build').disabled=busy||!project||!unlockValid;$('#local-source').disabled=busy||!$('#local-source').dataset.available;$('#official-file').disabled=busy;$('#search').disabled=busy;
 if(focused)root.querySelector(`[data-focus="${focused}"]`)?.focus({preventScroll:true});
}
function filmIcon(f){const img=document.createElement('img');img.className='film-icon';img.width=40;img.height=40;img.alt='';img.decoding='async';if(f?.icon_url)img.src=f.icon_url;else img.hidden=true;return img;}
function renderFilms(){const q=$('#search').value.toLowerCase().trim(),selected=new Set(configuration.slots.map(s=>s.film));let count=0,lastGroup=null;
 $('#catalog').replaceChildren(...films.filter(f=>f.name.toLowerCase().includes(q)&&(!$('#film-group').value||f.group===$('#film-group').value)).flatMap(f=>{
  const prefix=[];if(f.group!==lastGroup){const title=document.createElement('h3');title.className='film-directory-group';title.style.cssText='grid-column:1/-1;margin:20px 0 0';title.textContent=f.group;prefix.push(title);lastGroup=f.group;}
  count++;const label=document.createElement('label');label.className='film';label.dataset.selected=String(selected.has(f.id));
  const check=document.createElement('input');check.type='checkbox';check.value=String(f.id);check.checked=selected.has(f.id);check.disabled=busy;check.dataset.focus='film-'+f.id;check.setAttribute('aria-label',`选择 ${f.name}`);
  const strong=document.createElement('strong');strong.textContent=`${f.number??films.indexOf(f)+1}. ${f.name}`;const preview=document.createElement('button');preview.type='button';preview.className='film-peek';preview.setAttribute('aria-label',`查看 ${f.name}，不改变已选胶卷`);preview.append(filmIcon(f),strong);preview.onclick=event=>{event.preventDefault();event.stopPropagation();const selectedIndex=configuration.slots.findIndex(s=>s.film===f.id);if(selectedIndex>=0){active=selectedIndex;render();}else onInspect(f,false);};label.append(check,preview);if(f.id>=299&&f.id<=305){const badge=document.createElement('small');badge.textContent=f.infrared_style?'\u7ea2\u5916\u6ee4\u955c\u98ce\u683c\u8fd1\u4f3c':'\u98ce\u683c\u8fd1\u4f3c';badge.style.cssText='display:block;font-size:12px;font-weight:400;opacity:.7;margin-top:4px';strong.append(badge);}
  check.onchange=()=>toggleFilm(f.id);
  return [...prefix,label];
 }));$('#empty').hidden=count!==0;
}
function toggleFilm(id){
 try{
  if(!films.some(f=>f.id===id))throw Error('胶卷已停用，请从当前目录选择');
  const wasSelected=configuration.slots.some(s=>s.film===id),activeFilm=configuration.slots[active]?.film;
  if(!wasSelected&&configuration.slots.length>=selectionLimit())throw Error(`最多选择 ${selectionLimit()} 款胶卷，请先取消一款`);
  configuration=toggleNativeFilm(configuration,id);active=wasSelected?Math.max(0,configuration.slots.findIndex(s=>s.film===activeFilm)):configuration.slots.length-1;
  invalidate({filmSelection:true});render();const status=$('#film-selection-status');if(status)status.textContent=`${wasSelected?'已移除':'已加入'} ${films.find(f=>f.id===id)?.name} · 已选 ${configuration.slots.length}/${selectionLimit()}`;
 }catch(error){const status=$('#film-selection-status');if(status)status.textContent=error.message;renderFilms();}
}
async function jsonResponse(r){const data=await r.json();if(!r.ok)throw Error(data.error||`请求失败 ${r.status}`);return data;}
async function post(url,value,signal){const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-M10V-Token':token,...(url.endsWith('/build')?{Accept:'multipart/form-data'}:{})},body:JSON.stringify(value),signal});return unwrapFirmwareDownload(response);}
function setBusy(value){busy=value;$('#cancel').hidden=!value||!abort;render();}
async function importSource(file){setBusy(true);message('正在核对官方固件…');try{const result=file?await jsonResponse(await fetch('/api/import',{method:'POST',headers:{'X-M10V-Token':token},body:file})):await jsonResponse(await post('/api/gr3/native-library/import-official',{}));project=result.project_id;sourceModel=result.model==='GR IIIx'?'gr3x':'gr3';configuration=configurationForModel(configuration,sourceModel);$('#source-status').textContent=`✓ 官方包已核验 · ${sourceModel==='gr3x'?'GR IIIx 1.60':'GR III 2.10'}`;message('官方包已就绪，可生成实机测试候选。');}catch(e){project=null;$('#source-status').textContent='官方包未通过核验';message(e.message,true);}finally{setBusy(false);}}
for(const k of ['gain','spread','threshold']){$('#halo-'+k).onpointerdown=onEditStart;$('#halo-'+k).onkeydown=onEditStart;$('#halo-'+k).onpointerup=onEditCommit;$('#halo-'+k).onkeyup=onEditCommit;$('#halo-'+k).onchange=onEditCommit;}
for(const k of ['gain','spread','threshold'])$('#halo-'+k).oninput=()=>{configuration.slots[active].halo[k]=Number($('#halo-'+k).value);$('#halo-'+k+'-value').textContent=$('#halo-'+k).value+'/8';invalidate();};
for(const k of ['filmExposure'])$('#effect-'+k).onchange=()=>{configuration.slots[active].effects[k]=Number($('#effect-'+k).value);invalidate();render();};
if($('#effect-charmeraColor'))$('#effect-charmeraColor').onchange=()=>{configuration.slots[active].effects.charmeraColor=Number($('#effect-charmeraColor').value);invalidate();render();};
$('#reset-texture').onclick=()=>{configuration=resetNativeTexture(configuration,active);invalidate();render();};
$('#film-group').onchange=renderFilms;
$('#search').oninput=renderFilms;$('#local-source').onclick=()=>importSource();$('#official-file').onchange=e=>{const f=e.target.files[0];if(f)importSource(f);e.target.value='';};
$('#cancel').onclick=()=>abort?.abort();
$('#native-debug-mode').onchange=()=>invalidate();
$('#native-version-unlock').onchange=()=>{invalidate();render();};
$('#native-version-known').onchange=()=>{invalidate();render();};
for(const key of ['dsp','cpu'])$('#native-version-'+key).oninput=()=>{invalidate();render();};
$('#build').onclick=async()=>{
 if(busy||!project)return;if(configuration.slots.length>selectionLimit()){message('此机型暂不支持导出超过 5 款胶卷',true);return;}let version_unlock;try{validateZoomControls($('#native-zoom-controls'));configuration=prepareZoomConfigurationForBuild(configuration,sourceModel);version_unlock=versionUnlockSnapshot();}catch(e){message(e.message,true);return;}invalidate();abort=new AbortController();setBusy(true);const snapshot=normalizeConfiguration(configuration),debug_mode=$('#native-debug-mode').checked;
 try{message('1 / 3 · 校验所选胶卷配置与官方基线…');const plan=await jsonResponse(await post(`/api/projects/${project}/native-library/prepare`,{configuration:snapshot,debug_mode,version_unlock},abort.signal));
 message('2 / 3 · 编译 ARM 模块、接入机内菜单和 JPEG 路径…');
 const response=await post(`/api/projects/${project}/native-library/build`,{configuration:snapshot,debug_mode,version_unlock,accepted_configuration_sha256:plan.configuration_sha256},abort.signal);
 if(!response.ok){await jsonResponse(response);throw Error('构建失败');}
 message('3 / 3 · 核对下载摘要…');const blob=await response.blob();const encoded=response.headers.get('X-M10V-Native-Receipt');if(!encoded)throw Error('缺少构建校验记录');
 const receipt=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))));
 assertVersionUnlockReceipt(receipt.version_unlock,version_unlock,sourceModel);
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer())),v=>v.toString(16).padStart(2,'0')).join('');
 if(receipt.debug_mode!==debug_mode||digest!==receipt.candidate_sha256||JSON.stringify(receipt.configuration)!==JSON.stringify(snapshot))throw Error('固件摘要或配置回读不一致');
 const binUrl=URL.createObjectURL(blob),recordUrl=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)+'\n'],{type:'application/json'}));urls=[binUrl,recordUrl];
 $('#bin-link').href=binUrl;$('#bin-link').download=sourceModel==='gr3x'?'fwdc243b.bin':'fwdc239b.bin';$('#receipt-link').href=recordUrl;$('#receipt-link').download='M10V-build-receipt.json';$('#downloads').hidden=false;
 message(`候选已生成 · ${(blob.size/1024/1024).toFixed(1)} MB · ${receipt.verified_hooks} 处挂钩、${receipt.icon_count} 个图标回读通过。${debug_mode?'调试已开启，复现后请复制 SD 卡根目录的 M10VMN0/1.BIN、M10VCP0/1.BIN。':''}相机结果待验证。`);$('#bin-link').click();
 }catch(e){message(e.name==='AbortError'?'已取消构建；没有导出固件。':e.message,true);}finally{abort=null;setBusy(false);}
};
(async()=>{try{const [status,catalog]=await Promise.all([fetch('/api/status').then(jsonResponse),fetch(catalogApi).then(jsonResponse)]);token=status.session_token;films=catalog.films;const retained=retainCatalogFilms(configuration,films),removed=configuration.slots.length-retained.slots.length;if(removed){configuration=retained;invalidate({filmSelection:true});const status=$('#film-selection-status');if(status)status.textContent=`已清理 ${removed} 款已停用胶卷，请按当前目录选择。`;}$('#search').placeholder=`搜索 ${films.length} 套胶卷…`;for(const node of root.querySelectorAll('[data-film-count-copy]'))for(const child of node.childNodes)if(child.nodeType===3)child.textContent=child.textContent.replace(/[0-9]+(?=\s*[套款])/g,String(films.length));for(const group of [...new Set(films.map(f=>f.group))]){const option=document.createElement('option');option.value=group;option.textContent=group;option.dataset.icon=films.find(f=>f.group===group)?.icon_url;$('#film-group').append(option);}enhanceFilmSelect($('#film-group'),{caption:'胶卷分类',searchable:false});$('#local-source').dataset.available=catalog.local_source_available?'1':'';$('#source-status').textContent=catalog.local_source_available?'已找到目录中的官方包，请选择使用。':'请选择对应的官方固件包。';render();}catch(e){message(e.message,true);$('#source-status').textContent='服务暂不可用，请刷新页面。';}})();render();

return {toggleFilm,setHalationWrite:value=>{if(halationWrite!==value){halationWrite=value;render();}},setModel:value=>{if(!['gr3','gr3x','gr4'].includes(value))throw Error('不支持的相机机型');sourceModel=value;const previous=JSON.stringify(configuration.zoom);configuration=configurationForModel(configuration,value);if(previous!==JSON.stringify(configuration.zoom))invalidate({globalZoom:true});render();},getConfiguration:()=>normalizeConfiguration(configuration),setFilm:(id,slot=active)=>{if(films.length&&!films.some(f=>f.id===id))throw Error('胶卷已停用，请从当前目录选择');active=slot;if(slot===configuration.slots.length){configuration=toggleNativeFilm(configuration,id);}else configuration=selectNativeFilm(configuration,slot,id);invalidate({filmSlot:slot});render();},setConfiguration:value=>{configuration=configurationForModel(films.length?retainCatalogFilms(value,films):normalizeConfiguration(value),sourceModel);invalidate();render();},setHdf:value=>{configuration=normalizeConfiguration({...configuration,hdf:value});invalidate({globalHdf:true});render();},setUnresolved:value=>{if(JSON.stringify(unresolved)!==JSON.stringify(value)){unresolved=value;render();}}};
}
if(location.pathname.endsWith('/native-library.html'))mountNativeLibrary();
