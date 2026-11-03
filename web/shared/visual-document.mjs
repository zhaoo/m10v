for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>{location.href='/gr3/'+(button.dataset.view==='tools'?'#tools':button.dataset.view==='build'?'#build':'');};
function revealHash(){if(!location.hash)return;const target=document.getElementById(location.hash.slice(1));for(let parent=target?.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;requestAnimationFrame(()=>target?.scrollIntoView({block:'start'}));}
window.addEventListener('hashchange',revealHash);revealHash();
