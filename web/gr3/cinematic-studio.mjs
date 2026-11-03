import {mountPaperPreview} from './paper-preview.mjs';
export function mountCinematicStudio(root,{showImaging,addFilm,catalogHint='点图片查看 · 勾选加入固件'}){
 if(document.body?.classList?.contains?.('visual-v5'))return {inspect(){},close(){}};
 const workspace=root.querySelector('.workspace'),browser=root.querySelector('.film-browser-panel'),params=root.querySelector('.film-parameters-panel');
 const paper=!!root.closest('.paper-studio');
 const imagePreview=paper?mountPaperPreview(workspace):null;
 if(paper){
  const selected=document.createElement('section');selected.className='paper-selection';selected.setAttribute('aria-label','我的方案');
  const heading=document.createElement('div');heading.className='paper-selection-heading';heading.innerHTML='<h3>我的方案</h3>';
  const count=root.querySelector('#selected-film-count');if(count)heading.append(count);
  selected.append(heading,root.querySelector('#slots'));params.append(selected);
 }
 const controls=document.createElement('div');controls.className='cinema-panel-tabs';controls.setAttribute('aria-label','胶卷编辑面板');
 controls.innerHTML='<button type="button" data-cinema-panel="library" aria-expanded="false">全部胶卷 <span>＋</span></button><button type="button" data-cinema-panel="params" aria-expanded="false">本卷参数 <span>↗</span></button><button type="button" data-cinema-panel="imaging">影像方案 <span>↗</span></button>';
 workspace.prepend(controls);
 const scrim=document.createElement('button');scrim.type='button';scrim.className='cinema-scrim';scrim.setAttribute('aria-label','关闭编辑面板');scrim.tabIndex=-1;root.append(scrim);
 let oldOverflow=null;
 const bar=document.createElement('div');bar.className='catalog-panel-head';bar.innerHTML='<h3>全部胶卷</h3><button type="button" data-close-library>收起胶卷库 ×</button><p>点图片查看 · 勾选加入固件</p>';bar.querySelector('p').textContent=catalogHint;browser.prepend(bar);const selectionStatus=root.querySelector('#film-selection-status');if(selectionStatus)bar.append(selectionStatus);
 const more=document.createElement('div');more.className='parameter-extra';
 for(const node of [...params.children])if(!node.classList.contains('section-head')&&!node.classList.contains('texture')&&!node.classList.contains('paper-selection'))more.append(node);
 if(paper)params.insertBefore(more,params.querySelector('.paper-selection'));else params.append(more);
 const title=document.createElement('div');title.className='current-film-title';title.innerHTML='<span>CURRENT FILM</span><strong>读取胶卷…</strong>';params.prepend(title);
 const close=document.createElement('button');close.type='button';close.className='close-parameters';close.textContent='收起参数 ×';params.prepend(close);
 const preview=document.createElement('div');preview.className='film-preview-note';preview.hidden=true;preview.innerHTML='<strong></strong><span>正在查看 · 尚未加入固件</span><button type="button">加入这卷 ＋</button>';workspace.append(preview);
 let inspected=null,lastSelected=null,opener=null;
 function panel(name,trigger){
  opener=trigger||opener;
  if(root.dataset.panel===name){dismiss();return;}const active=name;root.dataset.panel=active;
  for(const button of controls.querySelectorAll('[aria-expanded]'))button.setAttribute('aria-expanded',String(button.dataset.cinemaPanel===active));
  if(matchMedia('(max-width:760px)').matches&&active){if(oldOverflow===null)oldOverflow=document.documentElement.style.overflow;document.documentElement.style.overflow='hidden';const surface=active==='library'?browser:params;surface.setAttribute('role','dialog');surface.setAttribute('aria-modal','true');surface.setAttribute('aria-label',active==='library'?'全部胶卷':'本卷参数');}
  if(active==='library')browser.querySelector('input[type=search]')?.focus({preventScroll:true});else close.focus({preventScroll:true});
 }
 controls.onclick=event=>{const button=event.target.closest('button');if(!button)return;if(button.dataset.cinemaPanel==='imaging'){dismiss();showImaging();}else panel(button.dataset.cinemaPanel,button);};
 const dismiss=()=>{if(root.dataset.inspect==='unselected')inspect(lastSelected,true);root.dataset.panel='';for(const surface of [browser,params]){surface.removeAttribute('role');surface.removeAttribute('aria-modal');}if(oldOverflow!==null){document.documentElement.style.overflow=oldOverflow;oldOverflow=null;}for(const b of controls.querySelectorAll('[aria-expanded]'))b.setAttribute('aria-expanded','false');opener?.focus({preventScroll:true});};
 bar.querySelector('button').onclick=dismiss;close.onclick=dismiss;scrim.onclick=dismiss;
 root.addEventListener('keydown',event=>{if(event.defaultPrevented)return;if(event.key==='Tab'&&oldOverflow!==null){const surface=root.dataset.panel==='library'?browser:params;const stops=[...surface.querySelectorAll('button,input,select,[tabindex]')].filter(e=>!e.disabled&&e.tabIndex>=0&&e.getClientRects().length);const first=stops[0],last=stops.at(-1);if(!surface.contains(document.activeElement)){event.preventDefault();(event.shiftKey?last:first)?.focus();}else if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}if(event.key==='Escape'&&root.dataset.panel){event.preventDefault();dismiss();}});
 preview.querySelector('button').onclick=()=>{if(inspected)addFilm(inspected.id);};
 function inspect(film,selected=true,configuration){
  imagePreview?.inspect(film,configuration);
  inspected=film;if(selected)lastSelected=film;if(!selected)bar.after(preview);preview.hidden=selected||!film;root.dataset.inspect=selected?'selected':'unselected';
  if(film){if(selected)title.querySelector('strong').textContent=film.name;preview.querySelector('strong').textContent=film.name;}
 }
 window.addEventListener('pagehide',dismiss);
 matchMedia('(max-width:760px)').addEventListener('change',()=>{if(oldOverflow!==null)dismiss();});
 return {inspect,close:dismiss};
}
