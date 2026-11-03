const $=id=>document.getElementById(id);
function sync(){const model=$('sd-model').value;for(const link of document.querySelectorAll('header .wordmark,.primary-nav>a:first-child'))link.href='/gr3/#model='+model;$('device-name').textContent=model==='gr3x'?'GR IIIx':model==='gr4'?'GR IV':'GR III';$('device-version').textContent=model==='gr3x'?'1.60':model==='gr4'?'1.11':'2.10';}
$('camera-button').onclick=()=>{const open=$('camera-menu').hidden;$('camera-menu').hidden=!open;$('camera-button').setAttribute('aria-expanded',String(open));};
for(const button of document.querySelectorAll('[data-model]'))button.onclick=()=>{$('sd-model').value=button.dataset.model;$('sd-model').dispatchEvent(new Event('change'));$('camera-menu').hidden=true;$('camera-button').setAttribute('aria-expanded','false');sync();};
$('sd-model').addEventListener('change',sync);
for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>{location.href='/gr3/#model='+$('sd-model').value+(button.dataset.view==='tools'?'&view=tools':button.dataset.view==='build'?'&view=build':'');};
$('visual-open-lut').onclick=event=>{event.preventDefault();$('visual-lut-dialog').showModal();};document.querySelector('[data-close-lut]').onclick=()=>$('visual-lut-dialog').close();
document.addEventListener('click',event=>{if(!event.target.closest('.camera-picker')){$('camera-menu').hidden=true;$('camera-button').setAttribute('aria-expanded','false');}});
sync();window.addEventListener('load',sync);
