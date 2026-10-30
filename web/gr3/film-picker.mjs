import {pickerArtwork} from './film-artwork.mjs';
// Keep the underlying select as the form/change contract; render its visual picker in the top layer.
let sequence=0;
// Keep stable order within each category, even when new films are appended to
// the catalogue to preserve firmware IDs.
export function groupedFilmOptions(options){
 const groups=new Map();
 for(const option of options){const key=option.dataset.group||'';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(option);}
 return [...groups.values()].flat();
}
export function enhanceFilmSelect(select,{placeholder='搜索胶卷…',caption='胶卷目录',searchable=true}={}){
 if(select.dataset.enhanced)return;
 select.dataset.enhanced='true';select.classList.add('film-picker-native');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
 const wrap=document.createElement('div');wrap.className='film-picker';select.before(wrap);wrap.append(select);
 const trigger=document.createElement('button');trigger.type='button';trigger.className='film-picker-trigger';
 trigger.setAttribute('aria-label',select.getAttribute('aria-label')||'选择胶卷');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');
 if(select.dataset.sharedSlot!==undefined){trigger.dataset.sharedSlot=select.dataset.sharedSlot;delete select.dataset.sharedSlot;}
 const panel=document.createElement('div');panel.className='film-picker-panel';panel.id=`film-picker-${++sequence}`;panel.setAttribute('popover','auto');trigger.setAttribute('aria-controls',panel.id);
 const head=document.createElement('div');head.className='film-picker-head';head.textContent=caption;
 const search=document.createElement('input');search.type='search';search.placeholder=placeholder;search.setAttribute('aria-label',placeholder);search.autocomplete='off';search.hidden=!searchable;
 const list=document.createElement('div');list.className='film-picker-list';list.setAttribute('role','listbox');list.setAttribute('aria-label',trigger.getAttribute('aria-label'));
 panel.append(head,search,list);wrap.append(trigger,panel);
 const art=option=>{const img=document.createElement('img');img.width=40;img.height=40;img.alt='';img.loading='lazy';const url=pickerArtwork(option);if(url)img.src=url;else{const span=document.createElement('span');span.className='film-picker-reel';span.textContent='▤';span.setAttribute('aria-hidden','true');return span;}return img;};
 function sync(){const option=select.selectedOptions[0];trigger.replaceChildren();if(option){trigger.append(art(option));const text=document.createElement('span');text.textContent=option.textContent;trigger.append(text);}const arrow=document.createElement('i');arrow.textContent='⌄';trigger.append(arrow);trigger.disabled=select.disabled;}
 function close(focus=false){if(panel.matches(':popover-open'))panel.hidePopover();trigger.setAttribute('aria-expanded','false');if(focus&&trigger.isConnected)trigger.focus({preventScroll:true});}
 function render(){list.replaceChildren();let group=null,count=0;for(const option of groupedFilmOptions(select.options)){if(option.disabled||!`${option.textContent} ${option.dataset.group||''}`.toLowerCase().includes(search.value.toLowerCase().trim()))continue;
  if(option.dataset.group&&group!==option.dataset.group){group=option.dataset.group;const title=document.createElement('div');title.className='film-picker-group';title.textContent=group;list.append(title);}
  const row=document.createElement('button');row.type='button';row.className='film-picker-option';row.setAttribute('role','option');row.setAttribute('aria-selected',String(option.selected));row.append(art(option));const copy=document.createElement('span');copy.textContent=option.textContent;row.append(copy);if(option.selected){const check=document.createElement('b');check.textContent='✓';row.append(check);}
  row.onclick=()=>{select.value=option.value;sync();close(true);select.dispatchEvent(new Event('change',{bubbles:true}));};list.append(row);count++;
 }if(!count){const empty=document.createElement('p');empty.className='film-picker-empty';empty.textContent='没有找到胶卷，试试其他名称';list.append(empty);}}
 function open(){
  if(select.disabled)return;
  trigger.scrollIntoView({block:'nearest',inline:'nearest'});
  search.value='';render();panel.showPopover();
  const r=trigger.getBoundingClientRect(),width=Math.min(Math.max(r.width,320),innerWidth-24);
  const below=Math.max(0,innerHeight-r.bottom-20),above=Math.max(0,r.top-20),down=below>=Math.min(420,above);
  panel.style.width=`${width}px`;panel.style.maxHeight=`${Math.max(0,Math.min(420,down?below:above))}px`;
  panel.style.left=`${Math.max(12,Math.min(r.left,innerWidth-width-12))}px`;
  const height=panel.getBoundingClientRect().height;
  panel.style.top=`${Math.max(12,Math.min(down?r.bottom+8:r.top-height-8,innerHeight-height-12))}px`;
  trigger.setAttribute('aria-expanded','true');
  if(searchable)search.focus({preventScroll:true});else list.querySelector('[aria-selected="true"]')?.focus({preventScroll:true});
 }
 trigger.onclick=()=>panel.matches(':popover-open')?close():open();
 trigger.onkeydown=e=>{if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();open();list.querySelector('[aria-selected="true"]')?.focus();}};
 panel.addEventListener('keydown',e=>{const options=[...list.querySelectorAll('[role="option"]')],current=options.indexOf(document.activeElement);if(e.key==='Escape'){e.preventDefault();close(true);}else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const index=e.key==='Home'?0:e.key==='End'?options.length-1:e.key==='ArrowDown'?Math.min(current+1,options.length-1):Math.max(current-1,0);options[index]?.focus();}else if(e.key==='Enter'&&document.activeElement===search){e.preventDefault();options[0]?.click();}else if(e.key==='Tab'){close();}});
 search.oninput=render;panel.addEventListener('toggle',()=>trigger.setAttribute('aria-expanded',String(panel.matches(':popover-open'))));select.addEventListener('change',sync);sync();return {sync,close};
}
