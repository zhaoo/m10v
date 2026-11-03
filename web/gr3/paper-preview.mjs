import {createFilmPreview} from './preview-controller.mjs';

/** Native IDs 34..65 retain the original catalog table order; no icon IDs are changed. */
export function paperPreviewLook(film,legacyLooks,effects={}) {
 if(!film||!Number.isInteger(film.id))return null;
 if(film.id>=34&&film.id<=65){const look=legacyLooks[film.id-34];return look?{...look,film:film.id,effects}:null;}
 if(film.id>=67)return {film:film.id,effects};
 return null;
}
export function mountPaperPreview(workspace) {
 const section=document.createElement('section');section.className='paper-preview';section.setAttribute('aria-label','胶卷色彩示意');
 section.innerHTML='<div class="paper-preview-head"><span>影像预览</span><div class="paper-preview-modes" role="group" aria-label="预览模式"><button type="button" data-mode="original" aria-pressed="true">原图</button><button type="button" data-mode="film" aria-pressed="false" disabled>胶卷</button></div></div><div class="paper-preview-frame"><img src="/gr3/film-street-source.png" width="620" height="413" alt="用于胶卷色彩示意的街头照片"><canvas width="620" height="413" aria-label="浏览器胶卷色彩近似预览" hidden></canvas></div><p class="paper-preview-caption"><strong>ORIGINAL / 原图参考</strong><span>色彩示意 · 以相机成片为准</span></p>';
 workspace.prepend(section);
 const canvas=section.querySelector('canvas'),caption=section.querySelector('strong'),buttons=[...section.querySelectorAll('[data-mode]')];
 let renderer=createFilmPreview(),film=null,effects={},mode='film',generation=0,destroyed=false;
 const legacy=fetch('/gr3/film-catalog.json').then(response=>{if(!response.ok)throw Error('预览色表读取失败');return response.json();}).then(data=>data.looks).catch(()=>[]);
 async function render(){
  const ticket=++generation,look=paperPreviewLook(film,await legacy,effects);
  if(ticket!==generation||destroyed)return;
  buttons[1].disabled=!look;
  const show=mode==='film'&&!!look;canvas.hidden=!show;
  for(const button of buttons)button.setAttribute('aria-pressed',String(button.dataset.mode===(show?'film':'original')));
  caption.textContent=show?film.name.toUpperCase()+' / 色彩示意':'ORIGINAL / 原图参考';
  if(show)renderer.request(canvas,look,()=>{if(ticket===generation){canvas.hidden=true;caption.textContent='ORIGINAL / 原图参考';}});
 }
 for(const button of buttons)button.addEventListener('click',()=>{mode=button.dataset.mode;void render();});
 const dispose=()=>{destroyed=true;generation++;renderer.destroy();};
 window.addEventListener('pagehide',dispose);
 window.addEventListener('pageshow',event=>{if(event.persisted){destroyed=false;renderer=createFilmPreview();void render();}});
 return {inspect(next,configuration){film=next;effects=configuration?.effects||{};mode='film';void render();}};
}
