/** The same navigation contract is used by every public page and model desk. */
export function navigationItems(pathname = '/') {
  const path = pathname.replace(/\/index\.html$/, '/');
  const model = path.startsWith('/gr4') ? 'gr4' : 'gr3';
  const sd = /\/sd-library(?:\.html)?\/?$/.test(path);
  return [
    ['gr3', '/gr3/', 'GR III / IIIx'], ['gr4', '/gr4/', 'GR IV'],
    ['gr2', '/gr2/', 'GR II'], ['sd', path.startsWith('/gr2') ? '/gr2/#sd' : `/${model}/sd-library.html`, 'SD 胶卷'],
    ['test-packages', '/test-packages/', '测试包'], ['guide', '/guide/', '说明'], ['changelog', '/changelog/', '更新日志'], ['support', '/support/', '支持 M10V'],
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
  if (status) {status.className = 'navigation-source-status'; status.removeAttribute('aria-current'); header.append(status);}
  if (menu) header.append(menu);
  const modelMenu=header.querySelector('.model-menu');
  document.addEventListener('click',event=>{if(!modelMenu.contains(event.target))modelMenu.open=false;});
  modelMenu.addEventListener('keydown',event=>{if(event.key==='Escape'){modelMenu.open=false;modelMenu.querySelector('summary').focus();}});
}
if (typeof document !== 'undefined') mountNavigation();
