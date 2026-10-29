import {unwrapFirmwareDownload} from './firmware-download.mjs';
import {mountCinematicStudio} from './cinematic-studio.mjs';
import {mountBuildCompletion} from './full-library.mjs';
import {focusWorkbenchHeading} from '/shared/workbench-focus.mjs';
import {mountPowerImages} from './power-images.js';
import {normalizeVersionUnlock,assertVersionUnlockReceipt} from './version-unlock-state.mjs';
import {createFirmwareSaveGate} from './firmware-save-gate.mjs';
import { createEditorState, createImportGate } from './editor-state.mjs';
import { createFilmPreview } from './preview-controller.mjs';
import { previewFilmPixels } from './film-preview.mjs';
import {enhanceFilmSelect} from './film-picker.mjs';
import {mountNativeLibrary} from './native-library.js';
import {defaultConfiguration,prepareZoomConfigurationForBuild,zoomSummary} from './native-library-state.mjs';
import {renderZoomControls,validateZoomControls} from './zoom-controls.mjs';
import {normalizeWorkbenchDraft,preserveLegacyDraft,extensionFeatures} from './workbench-state.mjs';
const gr4Workbench=location.pathname.startsWith('/gr4');
const nativeApi=gr4Workbench?'/api/gr4/native-library':'/api/gr3/native-library';
let chosenModel=gr4Workbench?'gr4':location.pathname.startsWith('/gr3x')?'gr3x':'gr3';
let modelLabel=chosenModel==='gr4'?'GR IV':chosenModel==='gr3x'?'GR IIIx':'GR III';
let nativeEditor;
let cinematicEditor;
let completion;
let powerImages;
let powerTransitioning=false;
let settingsTab='library';
let debugMode=false;
const nativeExtensions=()=>({aspect:state.features.has('aspect'),level:state.features.has('level'),negativeGrain:state.features.has('negativeGrain'),rawNr:state.features.has('rawNr')?state.rawNr:{mode:'stock'}});
const debugEnabled=()=>debugMode&&state.profile==='native';

const $ = (id) => document.getElementById(id);
const fields = [
  ['saturation', '饱和度'], ['hue', '色相'], ['high_low_key', '影调'],
  ['contrast', '对比度'], ['highlight_contrast', '高光对比'],
  ['shadow_contrast', '阴影对比'], ['sharpness', '锐度'],
  ['shading', '暗角'], ['clarity', '清晰度'],
];
const slots = [
  ['builtin-0b', 'Standard', 'Standard'],
  ['builtin-16', 'Negative Film', 'Negative Film'],
  ['builtin-11', 'Positive Film', 'Positive Film'],
  ['builtin-15', 'Cross Processing', 'Cross Processing'],
  ['custom1', 'Custom1', 'Standard'],
  ['custom2', 'Custom2', 'Standard'],
];
const definitions = [
  ['halation', '光晕', '写入高光溢出与横向拉丝。写入后默认关闭，需在机内针对胶卷开启；800T 与蓝凤凰保留专属溢出。开启后可能增加保存与回放等待。', 'GR III / IIIx · 所有胶卷 · 机内设置'],
  ['digitalHdf', 'HDF 模拟', 'GR III / IIIx 的独立数字柔焦。机内入口：MENU → 设置 → HDF 模拟；可单独使用。', 'GR III / IIIx · 独立机内菜单'],
  ['timestamp', '时间戳', '在 JPEG 中写入拍摄日期、时间和胶卷名称，机内也可调整。', '拍摄时间'],
  ['aspect', '画幅比例', '增加 4:3、6x7、XPan 画幅与取景蒙版。', '4:3 / 6x7 / XPan'],
  ['negativeGrain', '原厂负片颗粒', '开放原厂负片颗粒菜单，档位在机内调整。', '机内调整'],
  ['rawNr', 'RAW 降噪', '设置写入 DNG 前的降噪策略。', '独立设置'],
  ['level', '滑轨水平仪', '使用横竖滑轨显示机身倾斜。', '取景辅助'],
];
const initial = { features: new Set(), recipes: new Map(), projectId: '', source: null,
  token: '', preparation: null, activeStep: 'source', filmMode: 'ektar100', films: [],
  filmIds: ['ektar100', 'gold200', 'pro400h', 'portra400', 'vision3-250d'], filmLibrary: [],
  openFilmGroups: new Set(['内置胶片']), pendingLut: null, community: [],
  modalSlot: null, runtime: false, experiment: null };
const state = initial;
state.profile='native';state.features=new Set(['film']);state.nativeConfig=defaultConfiguration();state.nativeCatalog=[];state.unresolvedSlots=[];state.toolFeaturesDraft=[];
state.filmTexture = {}; state.stockPresets = []; state.stockCapabilities = []; state.rawNr = {mode:'stock'}; state.revision = 0;
let filmPreview = createFilmPreview();
window.addEventListener('pageshow',event=>{if(event.persisted)filmPreview=createFilmPreview();});
let restoringHistory=false;
function historyConfiguration(){return {powerImages:powerImages?.getConfiguration()||{},...selection(),features:[...state.features],profile:state.profile,nativeConfiguration:state.nativeConfig,unresolvedSlots:state.unresolvedSlots,toolFeaturesDraft:state.toolFeaturesDraft};}
const editHistory=createEditorState(historyConfiguration());
powerImages=mountPowerImages($('power-images'),{api,onChange:()=>invalidate(),model:()=>chosenModel});powerImages.setModel();
const iconImports=createImportGate();
let saving=false,riskAcceptedRevision=-1;
let bridgeBusy=false,bridgePlan=null,bridgeProject=null;
let draftPersistenceAllowed=true;
let draftTimer, activeBuildController, fitController, fitSequence=0;
window.addEventListener('pagehide', () => { clearTimeout(draftTimer); saveDraft(); filmPreview.destroy(); });
const draftKey = gr4Workbench?'m10v-gr4-draft-v1':'m10v-gr3-street-draft-v2';
const slotById = new Map(slots.map((slot) => [slot[0], slot]));
const featureName = Object.fromEntries(definitions.map(([id, name]) => [id, name]));
const zeroParams = () => Object.fromEntries(fields.map(([key]) => [key, 0]));

function updateHistoryButtons(){const snapshot=editHistory.snapshot();$('undo-edit').disabled=!snapshot.canUndo;$('redo-edit').disabled=!snapshot.canRedo;}
function restoreHistory(direction){
  editHistory[direction]();const saved=normalizeWorkbenchDraft(editHistory.snapshot().config,state.nativeCatalog,state.nativeConfig);
  powerImages?.setConfiguration(saved.powerImages);
  state.profile='native';state.unresolvedSlots=saved.unresolvedSlots||[];state.toolFeaturesDraft=saved.toolFeaturesDraft||[];
  restoringHistory=true;if(saved.nativeConfiguration)nativeEditor?.setConfiguration(saved.nativeConfiguration);restoringHistory=false;nativeEditor?.setUnresolved(state.unresolvedSlots);
  state.features=new Set(saved.features);state.recipes=new Map((saved.recipes||[]).map(r=>[r.slotId,r]));
  state.filmIds=[...saved.filmIds];state.filmLibrary=saved.filmLibrary||[];
  state.films=[...state.films.filter(f=>!f.id.startsWith('lut-')),...state.filmLibrary];
  state.filmTexture=saved.filmTexture||{};state.stockPresets=saved.stockPresets||[];state.rawNr=saved.rawNr||{mode:'stock'};
  invalidate(false);renderFeatures();
}
function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
  $('notice').hidden = !message;
}
async function api(path, options = {}) {
  if(gr4Workbench){
    const custom=/^\/api\/projects\/([0-9a-f]{64})\/(stock-presets|edit\/(prepare|build))$/.exec(path);
    if(custom)path='/api/gr4/customization/'+custom[1]+'/'+(custom[3]||'stock-presets');
    const match=/^\/api\/projects\/([0-9a-f]{64})\/(native-library\/(prepare|build)|backup)$/.exec(path);
    if(match){path=nativeApi+'/'+(match[3]||'backup');options={...options,body:JSON.stringify({...JSON.parse(options.body||'{}'),project_id:match[1]})};}
  }
  const response = await fetch(path, { ...options,
    headers: { 'X-M10V-Token': state.token, ...(/\/(native-library|edit)\/build$/.test(path)&&!gr4Workbench?{Accept:'multipart/form-data'}:{}), ...(options.headers || {}) } });
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`;
    try { message = (await response.json()).error || message; } catch {
      if(response.status===502)message+='：下载网关未能接收构建结果，请重试；若持续失败，请反馈此错误码。';
      if(response.status===504)message+='：构建等待超时，请稍后重试。';
    }
    throw new Error(message);
  }
  return unwrapFirmwareDownload(response);
}
function selection() {
  return { variant: 'street', features: definitions.map(([id]) => id).filter((id) => state.features.has(id)),
    recipes: [...state.recipes.values()], filmIds: [...state.filmIds], filmLibrary: state.filmLibrary,
    filmTexture: state.features.has('film') ? Object.fromEntries(Object.entries(state.filmTexture).filter(([id])=>state.filmIds.includes(id))) : {},
    stockPresets: state.features.has('presets') ? state.stockPresets : [],
    negativeGrainMenu: state.features.has('negativeGrain'), rawNr: state.features.has('rawNr') ? state.rawNr : {mode:'stock'} };
}
function saveDraft() {
  if(!draftPersistenceAllowed)return;
  try {
    localStorage.setItem(draftKey, JSON.stringify({
      powerImages:powerImages?.getConfiguration()||{},profile:state.profile,toolFeaturesDraft:state.toolFeaturesDraft,unresolvedSlots:state.unresolvedSlots, features: [...state.features], recipes: [...state.recipes.values()],
      filmIds: state.filmIds, filmLibrary: state.filmLibrary,
      filmTexture: state.filmTexture, nativeConfiguration:state.nativeConfig, stockPresets:state.stockPresets, rawNr:state.rawNr,
    }));
    $('draft-indicator').textContent='草稿已保存到本机';
  } catch { $('draft-indicator').textContent='草稿保存失败';notice('草稿未能保存到本机，请检查浏览器存储空间。',true); }
}
function restoreDraft() {
  try {
    const raw=localStorage.getItem(draftKey);
    if(raw&&raw.length>4*1024*1024)throw Error('草稿过大');
    if(raw){
      const previous=JSON.parse(raw);
      preserveLegacyDraft(localStorage,draftKey,raw,previous);
      const draft=normalizeWorkbenchDraft(previous,state.nativeCatalog,state.nativeConfig);
      state.profile='native';state.features=new Set(draft.features);state.recipes=new Map();state.stockPresets=[];
      powerImages?.setConfiguration(draft.powerImages);
      state.rawNr=draft.rawNr;state.unresolvedSlots=draft.unresolvedSlots;state.toolFeaturesDraft=[];
      restoringHistory=true;
      try{nativeEditor.setConfiguration(draft.nativeConfiguration);}finally{restoringHistory=false;}
      state.nativeConfig=nativeEditor.getConfiguration();
    }
  }catch{draftPersistenceAllowed=false;notice('草稿未能恢复，已保留原始记录；本次修改暂不覆盖本机草稿。',true);}
  nativeEditor?.setUnresolved(state.unresolvedSlots);
  if(state.unresolvedSlots.length)notice('旧草稿已备份。部分胶卷不受支持，请为标记的槽位重新选择胶卷。',true);
  editHistory.restore(historyConfiguration());updateHistoryButtons();
}
function invalidate(recordHistory=true) {
  completion?.reset();
  fitController?.abort();fitSequence++;
  iconImports.invalidate();
  if(recordHistory)editHistory.update(historyConfiguration());
  updateHistoryButtons();
  activeBuildController?.abort();
  state.revision++;
  state.preparation = null;state.preparationRequest=null;
  riskAcceptedRevision=-1;
  $('build-firmware').disabled = true;
  $('preflight-result').className = 'preflight-result';
  $('preflight-result').textContent = '方案已更新，请重新预检。';
  $('build-result').textContent = '';
  clearTimeout(draftTimer); draftTimer=setTimeout(saveDraft,300);
  renderLedger();
}
async function showStep(step) {
  if(powerTransitioning)return;
  if(state.activeStep==='power'&&step!=='power'&&powerImages?.hasPending()){powerTransitioning=true;$('power-next').disabled=true;try{if(!await powerImages.applyPending())return;}finally{powerTransitioning=false;$('power-next').disabled=false;}}
  cinematicEditor?.close();
  document.body.dataset.view=step;
  state.activeStep = step;
  document.querySelectorAll('.page').forEach((page) => { page.hidden = page.dataset.page !== step; });
  document.querySelectorAll('.step').forEach((button) => (button.classList.toggle('active', button.dataset.step === step),button.setAttribute('aria-current',button.dataset.step===step?'step':'false')));
  if (step === 'build') renderBuildSummary();
  renderLedger();
  notice('');
  const heading=document.querySelector(`.page[data-page="${step}"] h2`);
  focusWorkbenchHeading(heading);
}
function versionUnlockSnapshot(){
 if(chosenModel!=='gr3x')return normalizeVersionUnlock({enabled:false},chosenModel);
 const enabled=state.profile==='native'&&$('version-unlock').checked;
 const option=$('version-known').checked?{enabled,dsp:$('version-dsp').value,cpu:$('version-cpu').value}:{enabled,mode:'dsp-package-only'};
 return normalizeVersionUnlock(option,chosenModel);
}
function renderVersionUnlock(){
 if($('bridge-option'))$('bridge-option').hidden=chosenModel!=='gr3'||Boolean(state.source?.build_source?.update_compatibility);
 if($('bridge-open'))$('bridge-open').disabled=!state.projectId||saving||Boolean(activeBuildController)||bridgeBusy;
 const bridgeResult=$('bridge-result'),sourceHint='请先在“导入固件”中选择 GR III 官方包，再下载桥接测试套件。';
 if(bridgeResult){if(!state.projectId)bridgeResult.textContent=sourceHint;else if(bridgeResult.textContent===sourceHint)bridgeResult.textContent='官方来源已核验，可下载桥接测试套件。';}
 const supported=state.profile==='native'&&chosenModel==='gr3x',toggle=$('version-unlock'),known=$('version-known');
 $('version-unlock-option').hidden=!supported;if(!supported){toggle.checked=false;known.checked=false;}
 toggle.disabled=saving||Boolean(activeBuildController)||!supported;$('version-unlock-fields').hidden=!toggle.checked;
 known.disabled=saving||Boolean(activeBuildController)||!supported||!toggle.checked;
 const advanced=supported&&toggle.checked&&known.checked;$('version-known-fields').hidden=!advanced;
 for(const key of ['dsp','cpu']){$('version-'+key).disabled=saving||Boolean(activeBuildController)||!advanced;$('version-'+key).required=advanced;$('version-'+key).placeholder=(chosenModel==='gr3x'?'1.60':'2.10')+'.x.x';}
 let error='';try{versionUnlockSnapshot();}catch(e){error=e.message;}
 $('version-error').textContent=error;return !error;
}
function renderLedger() {
  powerImages?.setModel();
  $('power-unavailable').hidden=chosenModel!=='gr4';
  const ledger = $('plan-ledger');
  ledger.replaceChildren();
  const native=state.profile==='native';
  const rows = [
    ['机型',state.source?`${state.source.model} · 上传 ${state.source.public_version}`:modelLabel],
    ['输出基线',state.source?`${state.source.model} · ${state.source.build_source?.public_version||state.source.public_version}`:'等待导入'],
    ['胶卷',native&&state.features.has('film')?state.nativeConfig.slots.map(s=>state.nativeCatalog.find(f=>f.id===s.film)?.name||`#${s.film}`).join(' / '):state.features.has('film')?`${state.filmIds.length} / 5 款`:'未启用'],
    ['固件来源',state.projectId?'官方文件已核验':'等待导入'],
    ['开关机图片',chosenModel!=='gr4'?Object.keys(powerImages?.getConfiguration()||{}).map(k=>k==='startup'?'开机':'关机').join(' / ')||'原厂默认':'该机型未启用'],
    ['保存状态',activeBuildController?'正在处理':state.preparation?'方案已核验':'保存时自动核验'],
  ];
  $('open-build-desk').hidden=false;
  $('open-build-desk').textContent=state.projectId?'继续保存固件':'导入官方固件';
  $('open-build-desk').disabled=saving||Boolean(activeBuildController);
  $('open-build-desk').title=state.projectId?'查看配置并保存固件':'先导入官方固件以核验机型与版本';
  for (const [label, value] of rows) {
    const row = document.createElement('div');
    row.append(textNode('span', label), textNode('strong', value));
    ledger.append(row);
  }
  const unlockValid=renderVersionUnlock();
  const canConfigure=unlockValid&&(state.profile==='native'?((state.features.has('film')||state.features.has('digitalHdf'))&&(!state.features.has('film')||!state.unresolvedSlots.length)&&(!state.features.has('digitalHdf')||chosenModel!=='gr4')&&(!state.features.has('halation')||(chosenModel!=='gr4'&&state.features.has('film')))):(state.features.size&&(!state.features.has('recipes')||state.recipes.size)));
  $('prepare-build').disabled = Boolean(activeBuildController)||!state.projectId||!canConfigure;
  $('build-firmware').disabled = saving||Boolean(activeBuildController)||!state.projectId||!canConfigure;
  $('features-next').disabled=!canConfigure;
  $('debug-option').hidden=state.profile!=='native';
  $('debug-mode').checked=debugMode;
  $('debug-mode').disabled=saving||Boolean(activeBuildController);

}
function textNode(tag, value, className = '') {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}
function enterNativeSelection(){
 state.profile='native';
}
function renderFeatures() {
  nativeEditor?.setHalationWrite?.(state.features.has('halation'));
  const target = $('feature-list');
  let zoomControls=$('studio-zoom-controls');
  if(!zoomControls){zoomControls=document.createElement('section');zoomControls.id='studio-zoom-controls';zoomControls.className='feature-row';target.prepend(zoomControls);}
  renderZoomControls(zoomControls,state.nativeConfig,chosenModel,value=>nativeEditor.setConfiguration(value),false,{feature:true,number:'01'});
  for (const [index, [id, name, description, tag]] of definitions.entries()) {
    const active = state.features.has(id);
    const signature=JSON.stringify([chosenModel,active,state.features.has('film'),id==='film'?[state.nativeConfig,state.nativeCatalog.length,state.unresolvedSlots]:id==='recipes'?[...state.recipes]:id==='presets'?[state.stockPresets,state.stockCapabilities.length]:id==='rawNr'?state.rawNr:id==='digitalHdf'?state.nativeConfig.hdf:null]);
    const existing=target.querySelector(`[data-feature="${id}"]`);
    if(existing?.dataset.signature===signature)continue;
    const row = document.createElement('article');row.dataset.feature=id;row.dataset.signature=signature;
    row.className = 'feature-row';
    const copy = document.createElement('div');
    const heading = document.createElement('div');
    heading.className = 'feature-title';
    heading.append(textNode('span', String(index + (chosenModel==='gr4'?1:2)).padStart(2, '0'), 'feature-num'), textNode('h3', name));
    copy.append(heading, textNode('p',gr4Workbench&&id==='timestamp'?'在 JPEG 中写入拍摄日期与时间，样式可在机内调整。':gr4Workbench&&id==='aspect'?'增加 65:24 画幅与宽幅取景蒙版。':chosenModel==='gr3'&&id==='aspect'?'增加 4:3、6x7、XPan 与竖向半格画幅，取景显示对应蒙版。':description), textNode('span', gr4Workbench&&id==='aspect'?'65:24':chosenModel==='gr3'&&id==='aspect'?'4:3 / 6x7 / XPan / 半格':tag, 'feature-tag'));
    const button = textNode('button', active ? '关闭' : '开启', 'feature-toggle' + (active ? ' selected' : ''));
    button.type = 'button';
    button.setAttribute('aria-pressed',String(active));
    if(gr4Workbench&&id==='timestamp'&&state.profile!=='native'&&!active){button.disabled=true;button.textContent='在胶卷库设置';}
    if((id==='timestamp'||(id==='halation'&&!active))&&!state.features.has('film')){button.disabled=true;button.textContent='需启用胶卷库';}
    if((id==='digitalHdf'||(id==='halation'&&!active))&&chosenModel==='gr4'){button.disabled=true;button.textContent='仅支持 GR III';}
    button.addEventListener('click', () => {
      if(id==='digitalHdf'&&active&&!state.features.has('film')){notice('可将档位设为关闭以保留独立菜单；或先启用胶卷库。');return;}
      active?state.features.delete(id):state.features.add(id);
      if(id==='digitalHdf')nativeEditor.setHdf(active?0:(state.nativeConfig.hdf||1));
      if(id==='timestamp')nativeEditor.setConfiguration({...state.nativeConfig,stamp:active?0:(state.nativeConfig.stamp||1),filmNameStamp:active?false:state.nativeConfig.filmNameStamp});

      invalidate();
      renderFeatures();
    });
    row.append(copy, button);
    if (active) {
      const detail = document.createElement('div');
      detail.className = 'feature-detail';
      if (id === 'halation') {
        detail.append(textNode('p','机内在图像控制中选中胶卷，按 FN 进入详细设置：光晕模式 0关闭 / 1高光溢出 / 2横向拉丝。强度、范围和阈值按胶卷保存；取景不显示光晕。'));
      } else if (id === 'digitalHdf') {
        const levels=document.createElement('div');levels.className='hdf-levels';levels.setAttribute('role','group');levels.setAttribute('aria-label','HDF 模拟默认档位');
        ['关闭','弱','中','强'].forEach((label,value)=>{const b=textNode('button',label);b.type='button';b.setAttribute('aria-pressed',String(state.nativeConfig.hdf===value));b.onclick=()=>nativeEditor.setHdf(value);levels.append(b);});
        const filmToggle=textNode('button',state.features.has('film')?'关闭胶卷库，仅使用 HDF':'同时启用胶卷库','outline');filmToggle.type='button';filmToggle.onclick=()=>{if(state.features.has('film')){state.features.delete('film');state.features.delete('halation');state.features.delete('timestamp');state.nativeConfig.stamp=0;state.nativeConfig.zoom.write=false;}else state.features.add('film');invalidate();renderFeatures();};
        detail.append(levels,filmToggle,textNode('p','这是固件初始档位。机内 HDF 菜单独立保存设置，换卷与重置胶卷不会改变它。'));
      } else if (id === 'recipes') renderRecipeDetail(detail);
      else if (id === 'film') renderFilmDetail(detail);
      else if (id === 'presets') renderStockDetail(detail);
      else if (id === 'negativeGrain') detail.append(textNode('p','档位由原厂菜单保存。'));
      else if (id === 'rawNr') renderRawNrDetail(detail);
      else if (id === 'timestamp') {
        if(state.profile==='native'){
          const c=state.nativeConfig;
          const fields=document.createElement('div');fields.className='native-stamp-fields';
          const select=(label,key,items)=>{const wrap=document.createElement('label');wrap.textContent=label;const input=document.createElement('select');input.setAttribute('aria-label',label);items.forEach((name,value)=>{const option=textNode('option',name);option.value=String(value);input.append(option);});input.value=String(c[key]);input.onchange=()=>nativeEditor.setConfiguration({...state.nativeConfig,[key]:Number(input.value)});wrap.append(input);return wrap;};
          fields.append(select('日期时间','stamp',['关闭','日期','日期 + 时间']),select('日期格式','format',['YYYY.MM.DD','DD.MM.YYYY','YYYY-MM-DD','YY.MM.DD']),select('位置','corner',['左上','右上','左下','右下']),select('颜色','color',['白色','橙色','红色','黄色']));
          if(!gr4Workbench){const name=document.createElement('label');const check=document.createElement('input');check.type='checkbox';check.checked=c.filmNameStamp;check.onchange=()=>nativeEditor.setConfiguration({...state.nativeConfig,filmNameStamp:check.checked});name.append(check,' 胶卷名称');fields.append(name);}
          detail.append(fields,textNode('p',gr4Workbench?'机内菜单 → 设置 → 时间水印也可调整。':'机内菜单 → 设置 → 时间水印也可调整。胶卷名称可单独开启。'));
        }
        else detail.append(textNode('p', '默认 ON · YYYY.MM.DD · 右下 · 中 · 橙。日期格式、位置、字号和颜色可在相机菜单中调整，关机后保留。'));
        const points = document.createElement('div'); points.className = 'feature-points';
        for (const value of (state.profile==='native'?(gr4Workbench?['开 / 关','四种颜色','四种日期格式','四角位置']:['开 / 关','胶卷名称','四种颜色','四种日期格式','四角位置']):['ON / OFF', '五色字体', '四种日期格式', '四角位置', '3:2 / 4:3 / 1:1 / 6x7 / XPan'])) points.append(textNode('span', value));
        detail.append(points);
      } else if (id === 'aspect') {
        const points = document.createElement('div'); points.className = 'feature-points';
        for (const value of (gr4Workbench?['＋ 全宽 65:24 画幅','＋ 实时半透明取景蒙版']:['＋ 4:3 画幅','＋ 6x7 画幅','＋ 全宽 XPan 画幅',...(chosenModel==='gr3'?['＋ 半格 3:4 · 单次快门独立成片']:[]),'＋ 实时半透明取景蒙版'])) points.append(textNode('span', value));
        detail.append(points);
      } else {
        detail.append(textNode('p', '底部横轨显示左右倾斜；右侧竖轨显示前后俯仰。圆点移入中间圆环并变绿时表示水平。'));
        const graphic = document.createElement('div'); graphic.className = 'level-graphic';
        graphic.append(document.createElement('i')); detail.append(graphic);
      }
      row.append(detail);
    }
    if(existing)existing.replaceWith(row);else target.append(row);
  }
  $('selection-count').textContent = settingsTab==='library'?`已选 ${state.nativeConfig.slots.length}/${chosenModel==='gr4'?5:10} 款胶卷`:`已开启 ${extensionFeatures.filter(id=>state.features.has(id)).length+(chosenModel!=='gr4'&&state.nativeConfig.zoom.write?1:0)} 项扩展功能`;
  $('features-next').disabled = state.profile!=='native' && !state.features.size || (state.features.has('recipes') && !state.recipes.size);
  renderLedger();
}
function renderRawNrDetail(target) {
  const mode=document.createElement('select'); mode.setAttribute('aria-label','RAW 降噪策略');
  for(const [value,label] of [['stock','原厂策略'],['off','关闭 RAW 降噪'],['threshold','达到指定 ISO 时启用']]){
    const option=textNode('option',label);option.value=value;mode.append(option);
  } mode.value=state.rawNr.mode;
  const iso=document.createElement('select');iso.setAttribute('aria-label','RAW 降噪起始 ISO');
  for(const value of [400,800,1600,3200,5000,6400,8000,10000,12800]){const option=textNode('option',`ISO ${value}`);option.value=value;iso.append(option);}
  iso.value=String(state.rawNr.iso||6400);iso.hidden=mode.value!=='threshold';
  const change=()=>{state.rawNr=mode.value==='threshold'?{mode:mode.value,iso:Number(iso.value)}:{mode:mode.value};iso.hidden=mode.value!=='threshold';invalidate();};
  mode.addEventListener('change',change);iso.addEventListener('change',change);
  target.append(mode,iso,textNode('p','仅调整 DNG 降噪，不改变 JPEG 降噪与胶卷颗粒。'));
}
function updateStock(slot,patch){
  const previous=state.stockPresets.find(p=>p.slot===slot)||{slot};const next={...previous,...patch};
  for(const key of ['name','iconPixelsBase64'])if(next[key]===undefined)delete next[key];
  state.stockPresets=state.stockPresets.filter(p=>p.slot!==slot);
  if(Object.keys(next).length>1)state.stockPresets.push(next);invalidate();
}
function renderStockDetail(target){
  if(!state.stockCapabilities.length){target.append(textNode('p','请先在固件来源页面导入官方 BIN，核对实际名称空间与图标。'));return;}
  target.append(textNode('p',gr4Workbench?'名称支持英文、数字和可打印符号；每个预设使用独立名称和图标资源，名称同步到全部菜单语言。':'名称支持英文、数字和可打印符号。加长名称可能共享另一种菜单语言存储，构建预检会列出受影响的语言编号。'));
  for(const preset of state.stockCapabilities){
    const row=document.createElement('div');row.className='stock-preset-row';
    const current=state.stockPresets.find(p=>p.slot===preset.slot)||{};
    row.append(iconCanvas(current.iconPixelsBase64||preset.iconPixelsBase64),textNode('strong',preset.name));
    const input=document.createElement('input');input.value=current.name||preset.factoryName;input.maxLength=preset.nameMax;input.disabled=!preset.canRename;
    input.setAttribute('aria-label',`${preset.name}机内名称`);
    input.addEventListener('change',()=>{if(!/^[\x20-\x7e]+$/.test(input.value)||input.value.trim()!==input.value||input.value.includes('  ')){
      input.setCustomValidity('请输入无多余空格的英文名称');input.reportValidity();return;}
      input.setCustomValidity('');updateStock(preset.slot,{name:input.value===preset.factoryName?undefined:input.value});});
    const upload=document.createElement('input');upload.type='file';upload.accept='image/png,image/jpeg';upload.setAttribute('aria-label',`${preset.name}图标图片`);
    upload.addEventListener('change',async()=>{
      const file=upload.files[0];if(!file)return;let bitmap;const request=iconImports.start(preset.slot);
      try{bitmap=await createImageBitmap(file);if(!iconImports.current(request))return;const canvas=document.createElement('canvas');canvas.width=40;canvas.height=40;
        const c=canvas.getContext('2d');c.clearRect(0,0,40,40);const edge=Math.min(bitmap.width,bitmap.height);
        c.drawImage(bitmap,(bitmap.width-edge)/2,(bitmap.height-edge)/2,edge,edge,1,2,38,36);
        const pixels=c.getImageData(0,0,40,40).data;for(let y=0;y<40;y++)for(let x=0;x<40;x++)pixels[(y*40+x)*4+3]=(x>=1&&x<39&&y>=2&&y<38)?255:0;
        updateStock(preset.slot,{iconPixelsBase64:btoa(String.fromCharCode(...pixels))});renderFeatures();
      }catch(error){if(iconImports.current(request))notice(`图标载入失败：${error.message}`,true);}finally{bitmap?.close();}
    });
    const reset=textNode('button','还原','text-action');reset.type='button';reset.addEventListener('click',()=>{state.stockPresets=state.stockPresets.filter(p=>p.slot!==preset.slot);invalidate();renderFeatures();});
    row.append(input,upload,reset);target.append(row);
  }
}
function renderRecipeDetail(target) {
  const heading = document.createElement('div'); heading.className = 'slot-heading';
  heading.append(textNode('strong', '机内配方位置'), textNode('span', `已配置 ${state.recipes.size} / 6`));
  target.append(heading);
  for (const [id, label, base] of slots) {
    if (id === 'builtin-15' && state.features.has('film')) continue;
    const recipe = state.recipes.get(id);
    const row = document.createElement('div'); row.className = 'slot-row';
    row.append(textNode('span', '原厂', 'slot-icon'));
    const copy = document.createElement('div');
    copy.append(textNode('strong', label),
      textNode('small', recipe ? `基底 ${base} · ${recipe.cameraName} · ${recipe.source === 'community_reference' ? '社区配方' : '手动配方'}` : `基底 ${base} · 保持原厂`));
    if (recipe) copy.append(textNode('span', fields.map(([key, title]) =>
      `${title} ${recipe.parameters[key] > 0 ? '+' : ''}${recipe.parameters[key]}`).join(' · '), 'slot-param'));
    row.append(copy);
    const actions = document.createElement('div');
    const edit = textNode('button', recipe ? '编辑' : '配置'); edit.type = 'button';
    edit.addEventListener('click', () => openRecipe(id)); actions.append(edit);
    if (recipe) {
      const restore = textNode('button', '还原'); restore.type = 'button';
      restore.addEventListener('click', () => { state.recipes.delete(id); invalidate(); renderFeatures(); });
      actions.append(restore);
    }
    row.append(actions); target.append(row);
  }
  target.append(textNode('p', '其余机内位置保持原厂。Custom1 / Custom2 默认值可能需要在相机中执行 Still Settings Reset。', 'slot-foot'));
}
function iconCanvas(base64) {
  const canvas = document.createElement('canvas'); canvas.width = 40; canvas.height = 40;
  const context = canvas.getContext('2d');
  const image = context.createImageData(40, 40);
  const bytes = atob(base64);
  for (let i = 0; i < 6400; i++) image.data[i] = bytes.charCodeAt(i);
  context.putImageData(image, 0, 0);
  return canvas;
}
function lutIcon(name) {
  const canvas = document.createElement('canvas'); canvas.width = 40; canvas.height = 40;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  context.fillStyle = '#353536'; context.fillRect(2, 1, 36, 38);
  context.fillStyle = '#d6d6d2';
  for (let x = 5; x < 36; x += 6) {
    context.fillRect(x, 5, 3, 3); context.fillRect(x, 32, 3, 3);
  }
  context.fillStyle = '#f4f4f0'; context.font = '700 13px Arial';
  context.textAlign = 'center'; context.textBaseline = 'middle';
  context.fillText(name.replace(/[^A-Za-z0-9]/g, '').slice(0, 4).toUpperCase() || 'LUT', 20, 20.5, 32);
  return btoa(String.fromCharCode(...context.getImageData(0, 0, 40, 40).data));
}
async function fitLutFile(file) {
  if (!file) return;
  fitController?.abort();fitController=new AbortController();const sequence=++fitSequence;
  notice('正在读取并拟合色彩文件…');
  try {
    const response = await api('/api/gr3/film/fit', { method: 'POST', signal:fitController.signal, body: file,
      headers: { 'Content-Type': 'application/octet-stream',
        'X-M10V-Filename': encodeURIComponent(file.name) } });
    const result=await response.json();if(sequence!==fitSequence)return;
    state.pendingLut = { filename: file.name, ...result };
    renderFeatures(); notice('LUT 已拟合。请选择拟合取向并保存。');
  } catch (error) { if(sequence===fitSequence&&error.name!=='AbortError')notice(`色彩文件导入失败：${error.message}`, true); }
}
function renderFilmControls(panel) {
  if (!panel) return;
  const look = state.films.find((item) => item.id === state.filmMode);
  const selected = look && state.filmIds.includes(look.id);
  panel.replaceChildren();
  if (!selected) {
    panel.append(textNode('p', '选择一款胶片，查看预览并设置颗粒。', 'film-selection-empty'));
    return;
  }
  const heading = document.createElement('div'); heading.className = 'film-selection-heading';
  heading.append(textNode('span', '当前胶卷', 'film-selection-kicker'), textNode('strong', look.name));
  const grain = document.createElement('div'); grain.className = 'film-texture-field';
  grain.append(textNode('span', '颗粒', 'film-texture-label'));
  const levels = document.createElement('div'); levels.className = 'film-levels';
  for (const [value, label] of ['关闭', '弱', '中', '强'].entries()) {
    const button = textNode('button', label); button.type = 'button';
    button.setAttribute('aria-label', `${look.name}颗粒${label}`);
    const active = (state.filmTexture[look.id]?.grain || 0) === value;
    button.classList.toggle('selected', active); button.setAttribute('aria-pressed', String(active));
    button.addEventListener('click', () => {
      if (active) return;
      state.filmTexture[look.id] = {grain:0,hdf:0,...state.filmTexture[look.id],grain:value};
      invalidate(); renderFilmControls(panel);
    });
    levels.append(button);
  }
  grain.append(levels);
  const hdf = document.createElement('div'); hdf.className = 'film-hdf-status';
  hdf.append(textNode('span', '柔光', 'film-texture-label'), textNode('span', '暂未开放', 'film-hdf-badge'));
  const controls = document.createElement('div'); controls.className = 'film-selection-controls';
  controls.append(grain, hdf); panel.append(heading, controls);
}
function renderFilmDetail(target) {
  target.append(textNode('p',`已选 ${state.nativeConfig.slots.length}/${chosenModel==='gr4'?5:10} 款胶卷，按选择顺序显示；每款胶卷参数独立保存。`));
  const rows=document.createElement('div');rows.className='shared-slots';
  state.nativeConfig.slots.forEach((slot,index)=>{
    const film=state.nativeCatalog.find(f=>f.id===slot.film),label=textNode('div',`${index+1}. ${film?.name||slot.film}`);
    if(film?.icon_url){const icon=document.createElement('img');icon.className='film-icon';icon.src=film.icon_url;icon.alt='';icon.width=40;icon.height=40;label.prepend(icon);}rows.append(label);
  });
  target.append(rows);const button=textNode('button','多选胶卷 · 调整胶卷参数 →','outline');button.type='button';button.onclick=()=>showSettingsTab('library');target.append(button);
}

function openRecipe(slotId) {
  state.modalSlot = slotId;
  const [, label, base] = slotById.get(slotId);
  const existing = state.recipes.get(slotId);
  $('dialog-slot-label').textContent = `机内位置：${label} · 基底：${base}`;
  const options = state.community.filter((item) => item.baseEffect === base);
  $('community-select').replaceChildren(...options.map((preset) => {
    const option = document.createElement('option'); option.value = preset.id;
    option.textContent = `${preset.name} · ${preset.author?.name || '社区'}`; return option;
  }));
  const source = existing?.source || (options.length ? 'community_reference' : 'manual');
  document.querySelector(`input[name="recipe-source"][value="${source}"]`).checked = true;
  $('community-select').value = existing?.id || options[0]?.id || '';
  $('recipe-name').value = existing?.cameraName || (source === 'manual' ? label.replace(' ', '') : '');
  for (const [key] of fields) document.querySelector(`[data-param="${key}"]`).value =
    existing?.parameters[key] ?? 0;
  $('recipe-icon-mode').value = existing?.iconMode || 'original';
  syncRecipeSource(false);
  $('recipe-dialog').showModal();
}
function syncRecipeSource(usePreset = true) {
  const source = document.querySelector('input[name="recipe-source"]:checked').value;
  $('community-field').hidden = source !== 'community_reference';
  $('json-field').hidden = source !== 'json';
  $('recipe-icon-mode').querySelector('option[value="preset"]').disabled = source !== 'community_reference';
  if (source !== 'community_reference') $('recipe-icon-mode').value = 'original';
  if (source === 'community_reference' && usePreset) {
    const preset = state.community.find((item) => item.id === $('community-select').value);
    if (preset) {
      $('recipe-name').value = preset.name.slice(0, 11).trim();
      for (const [key] of fields) document.querySelector(`[data-param="${key}"]`).value = preset.parameters[key];
    }
  }
}
function renderBuildSummary() {
  if(state.profile==='native'&&!state.features.has('film')){
    $('build-feature-count').textContent='HDF 模拟 · 独立机内菜单';$('runtime-state').textContent='独立影像功能';
    $('build-details').replaceChildren(textNode('p',`HDF 模拟默认档位 · ${['关闭','弱','中','强'][state.nativeConfig.hdf]}`),textNode('p','机内入口：MENU → 设置 → HDF 模拟。未启用胶卷库。'));return;
  }
  if(state.profile==='native'){
    $('build-feature-count').textContent=`${state.nativeCatalog.length} 套胶卷 / 已选 ${state.nativeConfig.slots.length}/${chosenModel==='gr4'?5:10} / 专属参数 / 质感 / 时间戳`+(state.features.has('aspect')?' / 画幅':'')+(state.features.has('level')?' / 水平仪':'')+(state.features.has('negativeGrain')?' / 负片颗粒':'');
    $('runtime-state').textContent='胶卷库 · 全部内置';
    $('build-details').replaceChildren(...state.nativeConfig.slots.map((v,i)=>textNode('p',`槽位 ${i+1} · ${state.nativeCatalog.find(f=>f.id===v.film)?.name||v.film} · 颗粒 ${['关','弱','中','强'][v.grain]}`)),textNode('p',state.features.has('halation')?'光晕：已写入；机内默认关闭，按胶卷选择高光溢出或横向拉丝。':`专属光晕 · ${state.nativeConfig.slots.filter(v=>[33,67].includes(v.film)).map(v=>`${v.film===67?'Harman Phoenix II':'800T'} 强度${v.halo.gain}/8 · 范围${v.halo.spread}/8 · 阈值${v.halo.threshold}/8 · 档位${['关','弱','自然','强'][v.halo.profile]}`).join(' / ')||'未装入'}`),textNode('p',`Harman Red · ${state.nativeConfig.slots.filter(v=>v.film===68).map(v=>`模拟曝光EI ${[125,64,250][v.effects.filmExposure]}`).join(' / ')||'未装入'}`),...(chosenModel!=='gr4'?[textNode('p',zoomSummary(state.nativeConfig))]:[]),textNode('p',`HDF 模拟（全局） · ${['关闭','弱','中','强'][state.nativeConfig.hdf||0]}`),textNode('p',`时间戳 · ${['关闭','日期','日期 + 时间'][state.nativeConfig.stamp]}`),textNode('p',`同一固件包含：${[...state.features].map(id=>id==='film'?'胶卷库':featureName[id]).join('、')}。机内入口：菜单 → 设置 → 胶卷库；快捷菜单保留原厂列表。`));
    return;
  }
  $('build-feature-count').textContent = `${state.features.size} 项 / ${state.recipes.size} 个配方位置`;
  $('runtime-state').textContent = state.runtime ? '本地构建可用' : '构建组件未就绪';
  const target = $('build-details'); target.replaceChildren();
  for (const [id, name] of definitions) {
    if (!state.features.has(id)) continue;
    const row = document.createElement('p');
    row.append(textNode('strong', name), textNode('span', id === 'recipes' ?
      [...state.recipes.values()].map((r) => `${slotById.get(r.slotId)[1]}: ${r.cameraName}`).join(' / ') :
      id === 'film' ? state.filmIds.map((filmId) => state.films.find((film) => film.id === filmId)?.name).join(' / ') : '固定功能包'));
    target.append(row);
  }
}
async function importSource(file,local=false) {
  if (!file&&!local) return;
  notice('正在核验官方固件，请稍候…');
  try {
    let report;
    if(local){
      const imported=await (await api(nativeApi+'/import-official',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:$('local-source-model').value})})).json();
      report=gr4Workbench?imported:await (await api(`/api/projects/${imported.project_id}`)).json();
    }else report=await (await api(gr4Workbench?nativeApi+'/import':'/api/import',{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}})).json();
    if(!(gr4Workbench?['GR IV']:['GR III','GR IIIx']).includes(report.model))throw Error('当前工作台仅支持 GR III 和 GR IIIx 官方包。');
    chosenModel=gr4Workbench?'gr4':report.model==='GR IIIx'?'gr3x':'gr3';if(chosenModel==='gr4')state.features.delete('halation');modelLabel=report.model;nativeEditor?.setModel(chosenModel);
    $('local-source-model').value=chosenModel;
    $('studio-model-status').textContent=`${report.model} · ${report.public_version}`;
    $('build-model').textContent=`${report.model} · 输出基线 ${report.build_source?.public_version||report.public_version}`;
    document.title=`m10v · GR固件工作台 · ${report.model}`;
    document.querySelector('.hero .kicker').textContent=`${report.model} · ${report.public_version}`;
    state.projectId = report.sha256; state.source = report; invalidate();
    // Legacy recipe resources are not needed by the film-library workbench.
    renderFeatures();

    const node = $('source-report'); node.hidden = false; node.replaceChildren();
    node.append(textNode('h3', `${report.model} · ${report.public_version} · ${report.proof?.identity===false?'固件结构核验通过':'来源核验通过'}`));
    const dl = document.createElement('dl');
    for (const [key, value] of [['内部版本', report.internal_version], ['文件字节', report.size.toLocaleString('zh-CN')],
      ['SHA-256', report.sha256], ['分区数量', String(report.sections.length)]]) {
      dl.append(textNode('dt', key), textNode('dd', value));
    }
    node.append(dl);
    node.append(textNode('p',`输出基线：${report.model} · ${report.build_source?.public_version||report.public_version}（${report.build_source?.internal_version||report.internal_version}）。`));
    if(report.build_source?.normalized)node.append(textNode('p',`上传的 ${report.public_version} 固件原包用于机型与版本核验，并保留在备份中。M10V 将基于已适配的 ${report.build_source.public_version} 官方包生成，不包含上传版本的新功能；实际相机能否接受更新仍取决于机内版本。`));
    if(report.build_source?.update_compatibility)node.append(textNode('p',`机身更新兼容：导出包版本 ${report.build_source.update_compatibility.package_version}，保留 ${report.build_source.public_version} 功能基线并附带官方固件恢复准入；刷入与恢复待实机验证。`));
    $('download-backup').disabled = false; $('source-next').disabled = false;
    showStep(globalThis.location?.hash==='#bridge'&&chosenModel==='gr3'?'build':'features');showSettingsTab(state.profile==='native'?'library':'imaging');notice(report.proof?.identity===false?'固件结构核验通过，继续设置方案。':'官方固件核验通过，继续设置方案。');
  } catch (error) { notice(error.message, true); }
}
async function download(response, filename) {
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
async function prepare() {
  if (!state.projectId) return;
  let request;try{validateZoomControls($('studio-zoom-controls'));validateZoomControls($('native-editor'));if(state.profile==='native'){if(state.nativeConfig.zoom?.write&&!state.features.has('film'))throw Error('写入裁切焦距需要启用胶卷库');const configuration=prepareZoomConfigurationForBuild(state.nativeConfig,chosenModel);if(configuration.zoom.write){state.nativeConfig=configuration;nativeEditor?.setConfiguration(configuration);}}request=state.profile==='native'?{configuration:structuredClone(state.nativeConfig),film_library:state.features.has('film'),hdf_enabled:state.features.has('digitalHdf'),halation_enabled:state.features.has('halation'),extensions:nativeExtensions(),debug_mode:debugEnabled(),version_unlock:versionUnlockSnapshot(),...(chosenModel!=='gr4'?{power_images:powerImages?.getConfiguration()||{}}:{})}:{selection:selection()};}catch(e){$('preflight-result').textContent=e.message;return;}
  activeBuildController?.abort();const controller=new AbortController();activeBuildController=controller;
  const revision=state.revision;state.preparation=null;renderLedger();
  $('prepare-build').disabled = true;
  $('preflight-result').textContent = '正在核验固件、胶卷配置与扩展功能…';
  try {
    const report = await (await api(`/api/projects/${state.projectId}/${state.profile==='native'?'native-library':'edit'}/prepare`, {
      method: 'POST', signal:controller.signal, body: JSON.stringify(request),
      headers: { 'Content-Type': 'application/json' },
    })).json();
    if(revision!==state.revision||activeBuildController!==controller)return;
    state.preparation = report.ready ? report : null;state.preparationRequest=report.ready?request:null;
    $('preflight-result').className = 'preflight-result ' + (report.ready ? 'ok' : 'error');
    $('preflight-result').textContent = report.ready ? '方案核验通过，保存时继续构建与独立回读。'+(report.build_source?`输出基线：${report.build_source.model} · ${report.build_source.public_version}。`:'')+(report.reset_required?'配方默认值在相机对应影像控制的详细设置内执行重置后生效；请仅重置该影像控制的参数。':'') :
      `预检未通过：${(report.blockers||[]).join('；')}`;
    $('build-firmware').disabled = !(report.ready && (riskAcceptedRevision===state.revision));
    renderLedger();return report.ready?revision:undefined;
  } catch (error) {
    if(revision!==state.revision||activeBuildController!==controller)return;
    $('preflight-result').className = 'preflight-result error';
    $('preflight-result').textContent = error.name==='AbortError'?'已取消预检。':error.message;
  } finally { if(activeBuildController===controller){activeBuildController=null;renderLedger();} }
}
async function build() {
  if (!state.preparation || !state.preparationRequest || !(riskAcceptedRevision===state.revision)) return;
  activeBuildController?.abort();const controller=new AbortController();activeBuildController=controller;
  const revision=state.revision;
  const exported={model:chosenModel,catalog:structuredClone(state.nativeCatalog),filmLibrary:state.profile==='native'&&state.features.has('film'),request:structuredClone(state.preparationRequest)};
  $('build-firmware').disabled = true;
  $('cancel-build').hidden=false;
  renderLedger();
  $('build-result').className = 'build-result';
  $('build-result').textContent = '正在构建、重编码并独立回读，约需半分钟…';
  try {
    const response = await api(`/api/projects/${state.projectId}/${state.profile==='native'?'native-library':'edit'}/build`, {
      method: 'POST', signal:controller.signal, body: JSON.stringify({ ...state.preparationRequest,
        accepted_configuration_sha256: state.preparation.configuration_sha256 }),
      headers: { 'Content-Type': 'application/json' },
    });
    if(revision!==state.revision||activeBuildController!==controller){notice('构建期间方案已变化，已放弃旧方案下载。请重新预检。',true);return;}
    let completedReceipt=null;
    if(state.profile==='native'){
      const encoded=response.headers.get('X-M10V-Native-Receipt');if(!encoded)throw Error('缺少构建校验记录');
      const receipt=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))));
      completedReceipt=receipt;
      assertVersionUnlockReceipt(receipt.version_unlock,exported.request.version_unlock,exported.model);
    }
    const filename=state.preparation.filename||(chosenModel==='gr4'?'fwdc248b.bin':chosenModel==='gr3x'?'fwdc243b.bin':'fwdc239b.bin');
    const firmwareBlob=await response.blob();
    if(revision!==state.revision||activeBuildController!==controller){notice('方案已变化，已放弃旧方案下载，请重新保存。',true);return;}
    await download(new Response(firmwareBlob),filename);
    completion?.show({firmwareBlob,filename,model:exported.model,catalog:exported.catalog,filmLibrary:exported.filmLibrary,record:{receipt:completedReceipt,configuration:exported.request}});
    $('build-result').textContent = '固件已生成并下载；服务端独立回读通过。'+(state.preparation.build_source?`输出基线：${state.preparation.build_source.model} · ${state.preparation.build_source.public_version}。`:'')+(state.preparation.debug_mode?'调试已开启：SD 卡根目录保存 M10VMN0/1.BIN、M10VCP0/1.BIN；复现后请复制日志。':'')+(state.source?.build_source?.update_compatibility?`本包更新版本 ${state.source.build_source.update_compatibility.package_version}。`:'')+'相机接受与成像仍需真机验证。'+(state.preparation.reset_required?'配方默认值需在对应影像控制详细设置内重置参数后生效。':'');
  } catch (error) {
    if(revision!==state.revision||activeBuildController!==controller)return;
    $('build-result').className = 'build-result error';
    $('build-result').textContent = error.name==='AbortError'?'已取消构建。':error.message;
  } finally { if(activeBuildController===controller){activeBuildController=null;$('cancel-build').hidden=true;$('build-firmware').disabled=!(state.preparation&&(riskAcceptedRevision===state.revision));renderLedger();} }
}
function showSettingsTab(tab){
 cinematicEditor?.close();
 enterNativeSelection();
 settingsTab=tab;renderFeatures();const library=tab==='library';$('imaging-settings').hidden=library;$('native-editor').hidden=!library;
 for(const name of ['imaging','library']){const b=$('tab-'+name);b.setAttribute('aria-selected',String(name===tab));b.tabIndex=name===tab?0:-1;}
}
$('tab-imaging').onclick=()=>showSettingsTab('imaging');$('tab-library').onclick=()=>showSettingsTab('library');
document.querySelector('[data-close-imaging]')?.addEventListener('click',()=>showSettingsTab('library'));

for(const name of ['imaging','library'])$('tab-'+name).onkeydown=e=>{
 if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
 e.preventDefault();const next=e.key==='Home'?'library':e.key==='End'?'imaging':settingsTab==='imaging'?'library':'imaging';
 showSettingsTab(next);$('tab-'+next).focus();
};
$('use-local-source').onclick=()=>importSource(null,true);
nativeEditor?.setModel?.(chosenModel);
    $('local-source-model').value=chosenModel;
for (const [key, label] of fields) {
  const field = document.createElement('label'); field.textContent = label;
  const input = document.createElement('input'); input.type = 'number'; input.min = '-4'; input.max = '4';
  input.step = '1'; input.value = '0'; input.dataset.param = key; field.append(input);
  $('recipe-parameters').append(field);
}
document.querySelectorAll('.step').forEach((button) =>
  button.addEventListener('click', () => showStep(button.dataset.step)));
document.querySelectorAll('[data-back]').forEach((button) =>
  button.addEventListener('click', () => showStep(button.dataset.back)));
$('camera-next').addEventListener('click', () => showStep('features'));
$('power-next').addEventListener('click',()=>showStep(state.projectId?'build':'source'));
$('features-next').addEventListener('click', () => showStep('power'));
$('source-next').addEventListener('click', () => showStep('features'));
$('open-build-desk').addEventListener('click', () => showStep(state.projectId?'build':'source'));
document.querySelectorAll('input[name="recipe-source"]').forEach((input) =>
  input.addEventListener('change', () => syncRecipeSource()));
$('community-select').addEventListener('change', () => syncRecipeSource());
$('recipe-json').addEventListener('change', async (event) => {
  try {
    const file = event.target.files[0]; if (!file || file.size > 64 * 1024) throw new Error('JSON 文件须小于 64 KiB。');
    const data = JSON.parse(await file.text());
    $('recipe-name').value = data.cameraName || data.name || '';
    for (const [key] of fields) document.querySelector(`[data-param="${key}"]`).value =
      data.parameters?.[key] ?? data.params?.[key] ?? 0;
    notice('配方 JSON 已读取，请核对九项参数后应用。');
  } catch (error) { notice(`JSON 导入失败：${error.message}`, true); }
});
$('recipe-form').addEventListener('submit', (event) => {
  if (event.submitter?.value !== 'apply') return;
  event.preventDefault();
  const source = document.querySelector('input[name="recipe-source"]:checked').value;
  const cameraName = $('recipe-name').value;
  if (!/^(?=.{1,11}$)(?=.*[A-Za-z])[A-Za-z0-9 -]+$/.test(cameraName) || cameraName.trim() !== cameraName)
    return notice('机内名称需为 1–11 个字符，含英文字母且首尾无空格。', true);
  const parameters = {};
  for (const [key] of fields) {
    const value = Number(document.querySelector(`[data-param="${key}"]`).value);
    if (!Number.isInteger(value) || value < -4 || value > 4)
      return notice('九项参数必须是 −4 至 +4 的整数。', true);
    parameters[key] = value;
  }
  const preset = state.community.find((item) => item.id === $('community-select').value);
  const isCommunity = source === 'community_reference';
  if (isCommunity && !preset) return notice('当前槽位没有可用的社区配方。', true);
  state.recipes.set(state.modalSlot, { slotId: state.modalSlot, cameraName,
    baseEffect: slotById.get(state.modalSlot)[2], parameters,
    iconMode: isCommunity ? $('recipe-icon-mode').value : 'original',
    source: isCommunity ? 'community_reference' : 'manual',
    ...(isCommunity ? { id: preset.id } : {}) });
  $('recipe-dialog').close();
  invalidate(); renderFeatures(); notice(`${slotById.get(state.modalSlot)[1]} 已配置。`);
});
$('firmware-file').addEventListener('change', (event) => {const file=event.target.files[0];event.target.value='';importSource(file);});
const dropzone = $('dropzone');
dropzone.addEventListener('dragover', (event) => { event.preventDefault(); dropzone.classList.add('dragging'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragging'));
dropzone.addEventListener('drop', (event) => {
  event.preventDefault(); dropzone.classList.remove('dragging'); importSource(event.dataTransfer.files[0]);
});
$('download-backup').addEventListener('click', async () => {
  try { await download(await api(`/api/projects/${state.projectId}/backup`, { method: 'POST', body: '' }),
    gr4Workbench?'fwdc248b-original.bin':'m10v-gr3-official-backup.zip'); notice('官方固件备份已下载。'); }
  catch (error) { notice(error.message, true); }
});
$('prepare-build').addEventListener('click', prepare);
$('undo-edit').addEventListener('click',()=>restoreHistory('undo'));
$('redo-edit').addEventListener('click',()=>restoreHistory('redo'));
const firmwareSaveGate=createFirmwareSaveGate({
 dialog:$('firmware-disclaimer'),trigger:$('build-firmware'),cancel:$('disclaimer-cancel'),confirm:$('disclaimer-confirm'),
 readSnapshot:()=>({revision:state.revision,project:state.projectId}),
 save:async accepted=>{
  if(saving||accepted.revision!==state.revision||accepted.project!==state.projectId)return;
  saving=true;renderLedger();
  try{const preparedRevision=await prepare();if(state.preparation&&preparedRevision===state.revision&&accepted.project===state.projectId){riskAcceptedRevision=preparedRevision;await build();}}
  finally{riskAcceptedRevision=-1;saving=false;renderLedger();}
 }
});
$('build-firmware').addEventListener('click',()=>{
 $('disclaimer-target').textContent=state.source?`本次保存：${state.source.model} · 输出基线 ${state.source.build_source?.public_version||state.source.public_version}（上传 ${state.source.public_version}）`:'';
 firmwareSaveGate.open();
});
$('cancel-build').addEventListener('click',()=>{activeBuildController?.abort();$('build-result').textContent='已取消构建，后台处理与临时文件会随请求清理。';});
try {
  const [status, film, community, nativeCatalog, nativeMarkup] = await Promise.all([
    fetch('/api/status').then((r) => r.json()),
    fetch('/gr3/film-catalog.json').then((r) => r.json()),
    fetch('/gr3/community-data.json').then((r) => r.json()),
    fetch(nativeApi+'/catalog').then(r=>r.json()),
    fetch('/gr3/native-library-controls.html').then(r=>{if(!r.ok)throw Error('胶卷库控件加载失败');return r.text();}),
  ]);
  state.token = status.session_token; state.runtime = gr4Workbench || status.gr3_custom_runtime === true;
  state.nativeCatalog=nativeCatalog.films;
  $('native-editor').innerHTML=gr4Workbench?nativeMarkup.replaceAll('GR III STREET · 2.10','GR IV · 1.11').replaceAll('/gr3/sd-library.html','/gr4/sd-library.html').replaceAll('fwdc239b.bin','fwdc248b.bin'):nativeMarkup;
  cinematicEditor=mountCinematicStudio($('native-editor'),{showImaging:()=>showSettingsTab('imaging'),addFilm:id=>nativeEditor.toggleFilm(id)});
  nativeEditor=mountNativeLibrary($('native-editor'),{model:chosenModel,onInspect:(film,selected)=>cinematicEditor?.inspect(film,selected),showZoom:false,defaultZoomWrite:true,onEditStart:()=>editHistory.begin(),onEditCommit:()=>{editHistory.commit();updateHistoryButtons();},onChange:(configuration,meta={})=>{state.nativeConfig=configuration;if(!restoringHistory){state.profile='native';if(!meta.globalHdf&&!meta.globalZoom)state.features.add('film');if(configuration.hdf)state.features.add('digitalHdf');if(configuration.stamp||configuration.filmNameStamp)state.features.add('timestamp');if(meta.filmSelection)state.unresolvedSlots=[];if(meta.filmSlot!==undefined)state.unresolvedSlots=state.unresolvedSlots.filter(v=>v.slot!==meta.filmSlot);invalidate();}else invalidate(false);nativeEditor?.setUnresolved(state.unresolvedSlots);if(settingsTab==='imaging'){const focused=document.activeElement?.dataset?.sharedSlot;renderFeatures();if(focused!==undefined)document.querySelector(`[data-shared-slot="${focused}"]`)?.focus({preventScroll:true});}renderBuildSummary();}});
  state.nativeConfig=nativeEditor.getConfiguration();
  if(state.nativeConfig.stamp||state.nativeConfig.filmNameStamp)state.features.add('timestamp');
  if(state.nativeConfig.hdf)state.features.add('digitalHdf');
  state.films = film.looks; state.community = community;
  restoreDraft();showSettingsTab('library');
  renderFeatures();
  if (!state.runtime&&state.profile==='custom') notice('构建组件尚未就绪，固件导出会被阻止。', true);
} catch (error) { notice(`工作区载入失败：${error.message}`, true); }

completion=mountBuildCompletion($('build-completion'),{api});
$('debug-mode').addEventListener('change',()=>{debugMode=$('debug-mode').checked;invalidate(false);});

$('version-unlock').addEventListener('change',()=>invalidate(false));
for(const key of ['dsp','cpu'])$('version-'+key).addEventListener('input',()=>invalidate(false));

$('version-known').addEventListener('change',()=>invalidate(false));

$('bridge-open')?.addEventListener('click',async()=>{
 if(chosenModel!=='gr3'||!state.projectId||bridgeBusy)return;
 bridgeBusy=true;renderVersionUnlock();$('bridge-result').textContent='正在核验桥接来源…';
 try{
  bridgeProject=state.projectId;
  bridgePlan=await(await api(`/api/projects/${bridgeProject}/bridge/prepare`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
  if(state.projectId!==bridgeProject||chosenModel!=='gr3')throw Error('来源已变化，请重新打开桥接预检');
  if(!bridgePlan.download_available)throw Error(bridgePlan.suspension_reason);
  $('bridge-ack').checked=false;$('bridge-export').disabled=true;$('bridge-dialog').showModal();$('bridge-result').textContent='预检通过：2.10.33.27 · 待实机验证。';
 }catch(e){$('bridge-result').textContent=e.message;}
 finally{bridgeBusy=false;renderVersionUnlock();}
});
$('bridge-ack')?.addEventListener('change',()=>{$('bridge-export').disabled=!$('bridge-ack').checked||bridgeBusy;});
$('bridge-cancel')?.addEventListener('click',()=>{$('bridge-dialog').close();});
$('bridge-export')?.addEventListener('click',async()=>{
 if(bridgeBusy||!$('bridge-ack').checked||!bridgePlan)return;
 if(state.projectId!==bridgeProject||chosenModel!=='gr3'){$('bridge-dialog').close();$('bridge-result').textContent='来源已变化，请重新预检';return;}
 bridgeBusy=true;$('bridge-export').disabled=true;$('bridge-dialog').close();renderVersionUnlock();$('bridge-result').textContent='正在生成并独立校验桥接套件…';
 try{
  const response=await api(`/api/projects/${bridgeProject}/bridge/export`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({accepted_plan_id:bridgePlan.plan_id,acknowledge_instructions:true})});
  await download(response,'M10V-GRIII-bridge-2.10.33.27.zip');
  $('bridge-result').textContent='两阶段桥接套件已生成并发起下载。请按 README.txt 先刷桥接包，再刷官方 2.10。';
 }catch(e){$('bridge-result').textContent=e.message;}
 finally{bridgeBusy=false;bridgePlan=null;renderVersionUnlock();}
});
