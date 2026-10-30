/** The same navigation contract is used by every public page and model desk. */
export function navigationItems(pathname = '/') {
  const path = pathname.replace(/\/index\.html$/, '/');
  const model = path.startsWith('/gr4') ? 'gr4' : 'gr3';
  const sd = /\/sd-library(?:\.html)?\/?$/.test(path);
  return [
    ['gr3', '/gr3/', 'GR III / IIIx'], ['gr4', '/gr4/', 'GR IV'],
    ['gr2', '/gr2/', 'GR II'], ['sd', path.startsWith('/gr2') ? '/gr2/#sd' : `/${model}/sd-library.html`, 'SD 胶卷'],
    ['test-packages', '/test-packages/', '测试包'], ['guide', '/guide/', '说明'], ['changelog', '/changelog/', '更新日志'], ['support', '/support/', '打赏'],
  ].map(([id, href, label]) => ({id, href, label, active: id === 'sd' ? sd : !sd && (id === 'gr3' ? path.startsWith('/gr3') : id === 'gr4' ? path.startsWith('/gr4') : id === 'gr2' ? path.startsWith('/gr2') : path.startsWith(`/${id}`))}));
}
export function renderNavigation(pathname = '/') {
  const items=navigationItems(pathname),models=items.slice(0,3);
  const current=models.find(item=>pathname.startsWith(`/${item.id}`))||models[0];
  const link=item=>`<a href="${item.href}"${item.active ? ' class="current" aria-current="page"' : ''}>${item.label}${item.id==='gr4'||item.id==='gr2'?'<small class="model-progress">进行中</small>':''}</a>`;
  return `<nav class="site-navigation" aria-label="主导航"><details class="model-menu"><summary aria-label="切换机型">${current.label}<span aria-hidden="true">⌄</span></summary><div class="model-menu-options">${models.map(link).join('')}</div></details><div class="navigation-links">${items.slice(3).map(link).join('')}<a class="navigation-github" href="https://github.com/zhaoo/m10v" target="_blank" rel="noopener noreferrer" aria-label="GitHub 项目，新窗口打开">GitHub ↗</a></div></nav>`;
}
export function mountNavigation() {
  if(!document.querySelector('link[data-workbench-theme]')){
    const theme=document.createElement('link');theme.rel='stylesheet';theme.href='/shared/workbench.css';theme.dataset.workbenchTheme='';document.head.insertBefore(theme,document.querySelector('link[href="/gr3/cinematic.css"]'));
  }
  const header = document.querySelector('body > header');
  if (!header) return;
  const brand = header.querySelector('.m10v-brand');
  const status = header.querySelector('#studio-model-status');
  const menu = header.querySelector('#more-menu');
  if (!brand) return;
  brand.setAttribute('href', '/');
  const brandName = brand.querySelector('.m10v-brand-name');
  if (brandName) brandName.innerHTML = '<b>m10v</b><span class="brand-dot">·</span>GR固件工作台';
  header.classList.add('site-header');
  header.replaceChildren(brand);
  header.insertAdjacentHTML('beforeend', renderNavigation(location.pathname));
  mountSupport(header.querySelector('a[href="/support/"]'));
  if (status) {status.className = 'navigation-source-status'; status.removeAttribute('aria-current'); header.append(status);}
  if (menu) header.append(menu);
  const modelMenu=header.querySelector('.model-menu');
  document.addEventListener('click',event=>{if(!modelMenu.contains(event.target))modelMenu.open=false;});
  modelMenu.addEventListener('keydown',event=>{if(event.key==='Escape'){modelMenu.open=false;modelMenu.querySelector('summary').focus();}});
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
