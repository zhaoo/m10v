/** The same navigation contract is used by every public page and model desk. */
export function navigationItems(pathname = '/') {
  const path = pathname.replace(/\/index\.html$/, '/');
  const model = path.startsWith('/gr4') ? 'gr4' : 'gr3';
  const sd = /\/sd-library(?:\.html)?\/?$/.test(path);
  const downgrade = /\/downgrade(?:\.html)?\/?$/.test(path);
  return [
    ['gr3', '/gr3/', 'GR III / IIIx'], ['gr4', '/gr4/', 'GR IV'],
    ['gr2', '/gr2/', 'GR II'], ['sd', path.startsWith('/gr2') ? '/gr2/#sd' : `/${model}/sd-library.html`, '胶卷库'],
    ['downgrade', '/gr3/downgrade.html', '二阶降级'], ['guide', '/guide/', '说明'], ['skills', '/skills/', '技能'], ['changelog', '/changelog/', '更新日志'], ['support', '/support/', '打赏'],
  ].map(([id, href, label]) => ({id, href, label, active: id === 'sd' ? sd : id === 'downgrade' ? downgrade : !sd && !downgrade && (id === 'gr3' ? path==='/'||path.startsWith('/gr3') : id === 'gr4' ? path.startsWith('/gr4') : id === 'gr2' ? path.startsWith('/gr2') : path.startsWith(`/${id}`))}));
}
export function renderNavigation(pathname = '/') {
  const items=navigationItems(pathname),models=items.slice(0,3);
  const current=models.find(item=>pathname.startsWith(`/${item.id}`));
  const link=item=>`<a href="${item.href}"${item.active ? ' class="current" aria-current="page"' : ''}>${item.label}</a>`;
  const descriptions={gr3:'胶卷与影像方案',gr4:'独立工作台 · 待实机验证',gr2:'固件检查与适配'};
  const codes={gr3:'III',gr4:'IV',gr2:'II'};
  const modelLink=item=>`<a class="model-choice${item.active?' current':''}" href="${item.href}"><span class="model-choice-icon" aria-hidden="true">${codes[item.id]}<i></i></span><span class="model-choice-copy"><b>${item.label}</b><small>${descriptions[item.id]}</small></span><span class="model-choice-state">${item.active?'<span class="model-check" aria-hidden="true">✓</span>':item.id==='gr3'?'<span aria-hidden="true">↗</span>':'<small class="model-progress">进行中</small>'}</span></a>`;
  const workbench={href:current?.href||'/gr3/',label:'工作台',active:models.some(item=>item.active)};
  return `<nav class="site-navigation" aria-label="主导航"><div class="navigation-primary">${link(workbench)}${link(items.find(item=>item.id==='sd'))}</div><details class="navigation-more"><summary aria-label="更多" title="更多"><span aria-hidden="true">•••</span><span class="navigation-more-label">更多</span></summary><div class="navigation-more-options">${items.slice(4).map(link).join('')}${gremoteLink}<a class="navigation-github" href="https://github.com/zhaoo/m10v" target="_blank" rel="noopener noreferrer" aria-label="GitHub 项目，新窗口打开">GitHub ↗</a><details class="model-menu"><summary aria-label="切换机型"><span class="model-summary-label">${current?.label||'选择机型'}</span><span class="model-chevron" aria-hidden="true"></span></summary><div class="model-menu-options"><div class="model-menu-heading"><span>相机工作台</span><span>RICOH GR</span></div>${models.map(modelLink).join('')}</div></details></div></details></nav>`;
}
const gremoteLink='<a href="https://gremote.izhaoo.com" target="_blank" rel="noopener noreferrer" aria-label="GRemote 网站，新窗口打开">GRemote ↗</a>';
export function mountGRemoteLink(menu){
 if(!menu.querySelector('a[href="https://gremote.izhaoo.com"]'))menu.insertAdjacentHTML('beforeend',gremoteLink);
}
export function mountNavigation() {
  if(document.body.classList.contains('visual-v5')){mountVisualNavigation();return;}

  if(!document.querySelector('link[data-workbench-theme]')){
    const theme=document.createElement('link');theme.rel='stylesheet';theme.href='/shared/workbench.css';theme.dataset.workbenchTheme='';document.head.insertBefore(theme,document.querySelector('link[href="/gr3/cinematic.css"]'));
  }
  document.body.classList.add('paper-theme');
  const colorScheme=document.querySelector('meta[name="color-scheme"]');
  if(colorScheme)colorScheme.content='light';
  if(!document.querySelector('link[data-paper-theme]')){
    const paper=document.createElement('link');paper.rel='stylesheet';paper.href='/shared/paper-theme.css';paper.dataset.paperTheme='';document.head.append(paper);
  }
  const header = document.querySelector('body > header');
  if (!header) return;
  const brand = header.querySelector('.m10v-brand');
  const status = header.querySelector('#studio-model-status');
  const menu = header.querySelector('#more-menu');
  if (!brand) return;
  brand.setAttribute('href', '/');
  const brandName = brand.querySelector('.m10v-brand-name');
  if (brandName) brandName.innerHTML = '<b>m10v<span class="brand-dot">.</span></b><span class="brand-description">GR固件工作台</span>';
  header.classList.add('site-header');
  header.replaceChildren(brand);
  header.insertAdjacentHTML('beforeend', renderNavigation(location.pathname));
  document.body.classList.add('site-navigation-mounted');
  const updateHeaderHeight=()=>document.documentElement.style.setProperty('--site-header-height',`${Math.ceil(header.getBoundingClientRect().height)}px`);
  updateHeaderHeight();
  if(typeof ResizeObserver!=='undefined')new ResizeObserver(updateHeaderHeight).observe(header);
  else window.addEventListener('resize',updateHeaderHeight);
  mountSupport(header.querySelector('a[href="/support/"]'));
  if (status) {status.className = 'navigation-source-status'; status.removeAttribute('aria-current'); header.append(status);}
  // The shared More menu replaces legacy page navigation.
  if (menu) menu.remove();
  const modelMenu=header.querySelector('.model-menu');
  const moreMenu=header.querySelector('.navigation-more');
  document.addEventListener('click',event=>{if(!moreMenu.contains(event.target)){moreMenu.open=false;modelMenu.open=false;}});
  moreMenu.addEventListener('keydown',event=>{if(event.key==='Escape'&&!modelMenu.open){event.preventDefault();moreMenu.open=false;moreMenu.querySelector('summary').focus();}});
  modelMenu.addEventListener('keydown',event=>{
    const summary=modelMenu.querySelector('summary'),choices=[...modelMenu.querySelectorAll('.model-choice')];
    if(event.key==='Escape'){event.preventDefault();modelMenu.open=false;summary.focus();return;}
    if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;
    event.preventDefault();const index=choices.indexOf(document.activeElement),wasOpen=modelMenu.open;modelMenu.open=true;
    const next=event.key==='Home'?0:event.key==='End'?choices.length-1:!wasOpen||index<0?(event.key==='ArrowUp'?choices.length-1:0):(index+(event.key==='ArrowDown'?1:-1)+choices.length)%choices.length;
    choices[next].focus();
  });
}
function mountSupport(trigger) {
  trigger.setAttribute('aria-haspopup','dialog');
  const style=document.createElement('link');style.rel='stylesheet';style.href='/shared/support.css';document.head.append(style);
  const dialog=document.createElement('dialog');dialog.className='support-dialog';dialog.setAttribute('aria-labelledby','support-title');
  dialog.innerHTML=`<div class="support-heading"><h2 id="support-title">请我喝杯咖啡</h2><button type="button" class="support-close" aria-label="关闭打赏">×</button></div>
    <p class="support-thanks">感谢支持 M10V 持续开发，金额随意。</p>
    <div class="support-switch" role="group" aria-label="支付方式"><button type="button" data-method="alipay" aria-pressed="true">支付宝</button><button type="button" data-method="wechat" aria-pressed="false">微信支付</button></div>
    <a class="support-image" target="_blank" rel="noopener noreferrer" aria-label="查看收款码原图，新窗口打开"><img alt=""></a>
    <a class="support-download">保存收款码 ↓</a>
    <p class="support-note">扫一扫或保存图片后从相册识别<br>自愿打赏，不影响功能使用。</p>`;
  document.body.append(dialog);
  const methods={alipay:{name:'支付宝',file:'alipay.jpg'},wechat:{name:'微信支付',file:'wechat.png'}};
  const select=method=>{
    const {name,file}=methods[method],url=`/shared/support/${file}`;
    for(const button of dialog.querySelectorAll('[data-method]'))button.setAttribute('aria-pressed',String(button.dataset.method===method));
    const image=dialog.querySelector('img');image.src=url;image.alt=`M10V 作者${name}收款码，收款人兆兆（**杰）`;
    const preview=dialog.querySelector('.support-image');preview.href=url;preview.dataset.method=method;
    const save=dialog.querySelector('.support-download');save.href=url;save.download=`m10v-${file}`;
  };
  let previousOverflow='';
  const open=()=>{if(dialog.open)return;select('alipay');previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';dialog.showModal();};
  trigger.addEventListener('click',event=>{event.preventDefault();open();});
  dialog.querySelector('.support-close').addEventListener('click',()=>dialog.close());
  dialog.querySelectorAll('[data-method]').forEach(button=>button.addEventListener('click',()=>select(button.dataset.method)));
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  dialog.addEventListener('close',()=>{document.body.style.overflow=previousOverflow;trigger.focus();});
  if(/^\/support\/?$/.test(location.pathname))open();
}
if (typeof document !== 'undefined') mountNavigation();

function mountVisualNavigation(){
 const toggle=document.getElementById('compact-toggle'),menu=document.getElementById('compact-menu');
 if(!toggle||!menu)return;
 mountGRemoteLink(menu);
 const close=()=>{menu.hidden=true;toggle.setAttribute('aria-expanded','false');};
 toggle.onclick=()=>{const open=menu.hidden;menu.hidden=!open;toggle.setAttribute('aria-expanded',String(open));};
 document.addEventListener('click',event=>{if(!event.target.closest('.nav-more'))close();});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!menu.hidden){close();toggle.focus();}});
 void import('/shared/visual-resources.mjs').then(module=>module.mountVisualResources()).catch(()=>{});
}
