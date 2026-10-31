import {mountNavigation} from './navigation.js';
// Shared GR III desk interaction for the model-specific editors.
export function deskState(model, loaded, requested) {
  const page = ['source', 'features', 'build'].includes(requested) && (loaded || requested === 'source') ? requested : 'source';
  return {page, canSave: model === 'gr4' && loaded};
}
function mountDesk() {
  const model = document.body.dataset.studioModel;
  if (!['gr2', 'gr4'].includes(model)) return;
  const gr4 = model === 'gr4', name = gr4 ? 'GR IV' : 'GR II', $ = id => document.getElementById(id);
  const oldMain = gr4 ? $('editor-workspace') : document.querySelector('main');
  const source = gr4 ? $('source-summary') : document.querySelector('.actions');
  const settings = gr4 ? [document.querySelector('.sidebar'), document.querySelector('.editor')] : [$('report')];
  const build = gr4 ? $('build-panel') : null;
  const oldHeader = document.querySelector('header');
  oldHeader.className = 'topbar';
  const menu = gr4 ? $('more-menu') : null;
  oldHeader.innerHTML = `<a class="brand m10v-brand" href="/" aria-label="m10v · GR固件工作台 首页"><img class="m10v-mark" src="/shared/m10v-logo.png" width="48" height="48" alt=""><span class="m10v-brand-name"><b>m10v</b><span class="brand-dot">·</span>GR固件工作台</span></a><nav class="model-nav" aria-label="主导航"><a href="/">选择机型</a><a href="/gr3/">GR III / IIIx</a><a href="/gr4/" ${gr4 ? 'class="current" aria-current="page"' : ''}>GR IV</a><a href="/gr2/" ${!gr4 ? 'class="current" aria-current="page"' : ''}>GR II</a><a href="/guide/">说明</a></nav>`;
  if (menu) oldHeader.append(menu);
  mountNavigation();
  const hero = document.createElement('section');hero.className = 'hero';
  hero.innerHTML = `<div class="hero-inner"><p class="kicker">RICOH ${name} · 固件工作台</p><h1>固件工作台</h1><p>导入官方固件，调整参数并保存。</p><div class="hero-rule"><span>${gr4 ? '影像控制 / 裁切 / 关机画面' : '组件 / 内置资源 / 只读检查'}</span><span>${name}</span></div></div>`;
  oldHeader.after(hero);
  const desk = document.createElement('main');desk.className = 'studio model-studio';
  const descriptions = ['官方文件 · 身份核验', gr4 ? '影像 · 裁切 · 关机画面' : '组件 · 资源 · 能力状态', '构建 · 回读 · 下载'];
  const labels = ['导入固件', '设置方案', '保存固件'];
  desk.innerHTML = `<aside class="steps" aria-label="工作台导航"><p class="section-kicker">工作流程</p>${['source','features','build'].map((step,i)=>`<button class="step" data-step="${step}"><b>0${i+1}</b><span>${labels[i]}<small>${descriptions[i]}</small></span></button>`).join('')}<div class="steps-foot"><strong>你的影像方案</strong><p>随时切换区域，右侧方案清单持续显示当前状态。</p></div></aside><div class="stage"></div><aside class="plan-rail" aria-label="当前方案清单"><p class="section-kicker">方案摘要</p><h2>当前工作台</h2><div class="plan-ledger"><div><span>机型</span><strong>${name}</strong></div><div><span>固件来源</span><strong id="desk-source-status">等待导入固件</strong></div><div><span>当前方案</span><strong id="desk-plan-status">${gr4 ? '原厂影像控制编辑' : '只读固件检查'}</strong></div></div><button class="primary rail-action" id="open-build-desk">继续保存固件 ↗</button><p class="rail-note">${gr4 ? '原厂参数参考工具。胶卷方案请使用 GR IV 主工作台，生成结果仍需实机验证。' : '更新校验已验证；加载链与原生功能继续逆向，当前不提供修改固件导出。'}</p></aside>`;
  hero.after(desk);
  const stage = desk.querySelector('.stage'), pages = {};
  const heads = [ ['固件来源','导入官方固件',`导入对应机型的官方 ${gr4 ? 'BIN' : 'FRM'}，系统核验机型和版本。`], ['设置','设置功能',gr4 ? '影像控制、裁切与关机画面共享官方来源和保存出口。' : '已验证的组件与资源在此查看；影像编辑尚未开放。'], ['保存','核对并保存固件',gr4 ? '保存前自动核验来源与方案，完成后下载对应机型的 BIN。' : '当前支持读取官方固件；修改与保存功能尚未开放。'] ];
  ['source','features','build'].forEach((key,i)=>{
    const page=document.createElement('section');page.className='page';page.dataset.page=key;
    page.innerHTML=`<div class="page-head"><p>${heads[i][0]}</p><h2>${heads[i][1]}</h2><span>${heads[i][2]}</span></div>`;
    pages[key]=page;stage.append(page);
  });
  const notice=$('notice');stage.prepend(notice);
  const sourceReport=document.createElement('div');sourceReport.className='source-report';sourceReport.hidden=true;
  if(!gr4)pages.source.append(sourceReport);
  const file=gr4 ? $('firmware-file') : $('firmware');
  const drop=document.createElement('label');drop.className='dropzone';drop.id='dropzone';drop.htmlFor=file.id;
  drop.innerHTML=`<span class="drop-icon">＋</span><strong>选择官方 ${gr4 ? 'BIN' : 'FRM'}，或拖到这里</strong><small>支持 ${name} · 导入后核验固件身份</small>`;
  pages.source.append(drop,file,source);file.hidden=true;
  if (gr4) drop.addEventListener('click',event=>{event.preventDefault();$('import-firmware').click();});
  drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('dragging');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));
  drop.addEventListener('drop',event=>{
    event.preventDefault();drop.classList.remove('dragging');
    if(file.disabled || (gr4 && !$('busy-overlay').hidden) || !event.dataTransfer.files.length)return;
    file.files=event.dataTransfer.files;file.dispatchEvent(new Event('change',{bubbles:true}));
  });
  const grid=document.createElement('div');grid.className='model-settings';grid.append(...settings);pages.features.append(grid);
  if(build)pages.build.append(build);
  else {
    const pending=document.createElement('div');pending.className='feature-row';
    pending.innerHTML='<h3>固件保存尚未开放</h3><p>GR II 的更新载荷校验已验证；加载链与原生胶卷功能继续逆向。当前方案为只读检查。</p><button class="primary wide" id="build-firmware" disabled>保存固件 · 尚未开放</button>';
    pages.build.append(pending);
  }
  const history=gr4 ? document.querySelector('.history-summary') : null;
  if(history)desk.querySelector('.plan-rail').append(history);
  for(const key of ['source','features','build']){
    const actions=document.createElement('div');actions.className='stage-actions';
    actions.innerHTML=key==='source' ? '<a class="outline" href="/">返回机型选择</a><button class="primary" data-next="features">继续设置方案 →</button>' : key==='features' ? '<button class="outline" data-next="source">返回导入固件</button><button class="primary" data-next="build">继续保存固件 →</button>' : '<button class="outline" data-next="features">返回设置方案</button>';
    pages[key].append(actions);
  }
  document.querySelector('.gr4-hero')?.remove();
  if(!gr4)oldMain.querySelector('.hero')?.remove();
  // All original controls remain live in the desk; remove only the emptied legacy layout.
  if(gr4){oldMain.style.display='none';desk.append(oldMain);}else oldMain.remove();
  let current='source';
  const loaded=()=>gr4 ? !$('filter-search').disabled : !$('report').hidden;
  function show(requested){
    current=deskState(model,loaded(),requested).page;
    for(const [key,page] of Object.entries(pages))page.hidden=key!==current;
    desk.querySelectorAll('[data-step]').forEach(button=>{
      button.classList.toggle('active',button.dataset.step===current);
      button.setAttribute('aria-current',button.dataset.step===current?'step':'false');
    });
  }
  desk.querySelectorAll('[data-step],[data-next]').forEach(button=>button.addEventListener('click',()=>show(button.dataset.step||button.dataset.next)));
  $('open-build-desk').onclick=()=>show('build');
  function sync(){
    const ready=loaded();
    desk.querySelectorAll('[data-step="features"],[data-step="build"],[data-next="features"],[data-next="build"]').forEach(button=>button.disabled=!ready);
    $('open-build-desk').disabled=!ready;
    $('desk-source-status').textContent=ready ? (gr4 ? `GR IV · ${$('source-meta').textContent}` : $('identity').textContent) : '等待导入固件';
    if(!gr4){sourceReport.hidden=!ready;sourceReport.textContent=ready ? `${$('identity').textContent} · ${$('proof').textContent}` : ''; }
    if(gr4)$('desk-plan-status').textContent=`影像控制 ${$('filter-count').textContent} · 原厂编辑方案`;
    if(!ready&&current!=='source')show('source');
  }
  const observer=new MutationObserver(sync);
  observer.observe(gr4 ? $('filter-search') : $('report'),{attributes:true,attributeFilter:[gr4?'disabled':'hidden']});
  if(gr4)observer.observe($('filter-count'),{childList:true,subtree:true,characterData:true});
  sync();show('source');
}
if (typeof document !== 'undefined') {
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mountDesk,{once:true});
  else mountDesk();
}
