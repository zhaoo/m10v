// Resource dialogs retain the approved visual's static markup and CSS classes.
// Only the current site's resource URLs and actual changelog data are used.
const dialogs = {
  skills: `<dialog id="skills-dialog" class="resource-dialog" aria-labelledby="skills-title"><button class="dialog-close" data-close aria-label="关闭技能">×</button><p class="dialog-kicker">A SECOND PAIR OF EYES</p><h2 id="skills-title">让 AI 帮你核验。</h2><p class="resource-copy">核对来源、配置和校验记录，保留每一步的检查结果。</p><div class="skill-card"><span class="skill-symbol">✳</span><div><strong>M10V 固件安全技能</strong><p>只读检测 · 操作指引 · 校验清单</p></div></div><p class="resource-copy">下载并解压后，将目录交给 AI 阅读其中的 SKILL.md，或安装到所用工具的技能目录。</p><a class="primary" href="/downloads/m10v-firmware-safety-skill.zip" download>下载技能包 <span class="arrow">↓</span></a><a class="secondary-link" href="/skills/" target="_blank" rel="noopener noreferrer">查看安装说明 ↗</a><p class="demo-note">技能包不含固件，不会自动刷机；AI 检查不能代替真机验证。</p></dialog>`,
  changelog: `<dialog id="changelog-dialog" class="resource-dialog" aria-labelledby="changelog-title"><button class="dialog-close" data-close aria-label="关闭更新日志">×</button><p class="dialog-kicker">MADE BETTER, LITTLE BY LITTLE</p><h2 id="changelog-title">更新日志。</h2><div id="release-list"></div><a class="secondary-link" href="/changelog/" target="_blank" rel="noopener noreferrer">查看全部更新 ↗</a><p class="demo-note">更新记录来自当前站点日志。</p></dialog>`,
  support: `<dialog id="support-dialog" class="resource-dialog" aria-labelledby="support-title"><button class="dialog-close" data-close aria-label="关闭打赏">×</button><p class="dialog-kicker">THANK YOU FOR KEEPING IT GOING</p><h2 id="support-title">请我喝杯咖啡。</h2><p class="resource-copy">感谢支持 M10V 持续开发，金额随意。</p><div class="support-methods" role="group" aria-label="支付方式"><button class="active" data-pay="alipay" aria-pressed="true">支付宝</button><button data-pay="wechat" aria-pressed="false">微信支付</button></div><img class="payment-code" id="payment-code" src="/shared/support/alipay.jpg" alt="M10V 作者支付宝收款码"><a class="payment-save" id="payment-save" href="/shared/support/alipay.jpg" download="m10v-alipay.jpg">保存收款码 ↓</a><p class="demo-note">自愿打赏，不影响功能使用。</p></dialog>`,
};
const paymentMethods = {
  alipay: {file:'alipay.jpg', name:'支付宝'},
  wechat: {file:'wechat.png', name:'微信支付'},
};
let mounted = false;

function selectPayment(dialog, method) {
  if (!Object.hasOwn(paymentMethods, method)) return;
  const {file,name} = paymentMethods[method], url = '/shared/support/'+file;
  for (const button of dialog.querySelectorAll('[data-pay]')) {
    const active=button.dataset.pay===method;
    button.classList.toggle('active',active);
    button.setAttribute('aria-pressed',String(active));
  }
  const image=dialog.querySelector('#payment-code'), save=dialog.querySelector('#payment-save');
  image.src=url;
  image.alt='M10V 作者'+name+'收款码';
  save.href=url;
  save.download='m10v-'+file;
}

async function loadReleases(list) {
  list.textContent='正在读取更新记录…';
  try {
    const response=await fetch('/changelog.json',{cache:'no-cache'});
    if (!response.ok) throw Error('changelog unavailable');
    const data=await response.json();
    if (!Array.isArray(data.releases) || !data.releases.length) throw Error('empty changelog');
    const articles=[];
    for (const release of data.releases.slice(0,3)) {
      if (!release || typeof release.date!=='string' || typeof release.version!=='string' ||
        typeof release.title!=='string' || !Array.isArray(release.changes) || typeof release.changes[0]!=='string')
        throw Error('invalid changelog entry');
      const article=document.createElement('article');article.className='release-item';
      const date=document.createElement('span');date.className='release-date';
      date.textContent=release.date+' / '+release.version;
      const title=document.createElement('h3');title.textContent=release.title;
      const copy=document.createElement('p');copy.textContent=release.changes[0];
      article.append(date,title,copy);articles.push(article);
    }
    list.replaceChildren(...articles);
  } catch {
    list.textContent='暂无法读取更新记录，请查看完整更新日志。';
  }
}

export function mountVisualResources() {
  if (typeof document==='undefined' || !document.body?.classList.contains('visual-v5') || mounted) return;
  mounted=true;
  const resources=new Map();
  for (const [name,markup] of Object.entries(dialogs)) {
    let dialog=document.getElementById(name+'-dialog');
    if (!dialog) {
      const template=document.createElement('template');
      // Fixed, locally authored template only. Remote data is textContent above.
      template.innerHTML=markup;
      dialog=template.content.firstElementChild;
      document.body.append(dialog);
    }
    resources.set('/'+name+'/',dialog);
    dialog.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>dialog.close()));
    dialog.addEventListener('click',event=>{
      if (event.target!==dialog) return;
      const box=dialog.getBoundingClientRect();
      if (event.clientX<box.left || event.clientX>box.right || event.clientY<box.top || event.clientY>box.bottom) dialog.close();
    });
  }
  const support=resources.get('/support/');
  support.querySelectorAll('[data-pay]').forEach(button=>button.addEventListener('click',()=>selectPayment(support,button.dataset.pay)));
  selectPayment(support,'alipay');
  let trigger=null, loading=false, loaded=false;
  for(const dialog of resources.values()) dialog.addEventListener('close',()=>{trigger?.focus();trigger=null;});
  document.addEventListener('click',event=>{
    if (event.defaultPrevented || event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor=event.target?.closest?.('#compact-menu a[href]');
    if (!anchor || (anchor.target && anchor.target!=='_self') || anchor.hasAttribute('download')) return;
    const dialog=resources.get(anchor.getAttribute('href'));
    if (!dialog) return;
    event.preventDefault();
    const menu=document.getElementById('compact-menu'),toggle=document.getElementById('compact-toggle');
    menu.hidden=true;toggle?.setAttribute('aria-expanded','false');
    trigger=toggle||anchor;
    if (!dialog.open) dialog.showModal();
    if (dialog===resources.get('/changelog/') && !loaded && !loading) {
      loading=true;
      loadReleases(dialog.querySelector('#release-list')).then(()=>{loaded=true;}).finally(()=>{loading=false;});
    }
  });
  document.querySelectorAll('#compact-menu a[href]').forEach(anchor=>{
    if(resources.has(anchor.getAttribute('href'))) anchor.setAttribute('aria-haspopup','dialog');
  });
}
