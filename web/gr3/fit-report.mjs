// DOM-only rendering. Never trusts report metadata to authorize firmware parameters.
export function saveJson(value,filename){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function renderFitChoices(host,result,onSelect){
 host.replaceChildren();for(const [id,choice] of Object.entries(result.choices||{})){
 const card=document.createElement('section'),title=document.createElement('h3'),summary=document.createElement('p'),details=document.createElement('details'),pre=document.createElement('pre'),download=document.createElement('button'),select=document.createElement('button');
 title.textContent=id==='tone'?'灰阶 / 肤色优先':'全色域优先';const q=choice.quality;
 summary.textContent=q?`256节点独立验证 ΔE00 平均 ${q.validation.mean.toFixed(2)} · P95 ${q.validation.p95.toFixed(2)} · 最大 ${q.validation.max.toFixed(2)}；33节点平均 ${q.knot_validation.mean.toFixed(2)} / P95 ${q.knot_validation.p95.toFixed(2)}。${q.style}。软件近似，尚未实拍验证。`:'旧拟合，未评估';
 const label=document.createElement('summary');label.textContent='误差、范围及来源详情';pre.textContent=JSON.stringify(q,null,2);details.append(label,pre);download.type=select.type='button';download.textContent='下载 JSON 报告';download.onclick=()=>saveJson(q,`m10v-${id}-quality.json`);select.textContent=q?.envelope.encodable?'选择此方案':'超出表达范围，请生成独立近似方案';select.disabled=!q?.envelope.encodable;select.onclick=()=>onSelect(id,choice);card.append(title,summary,details,download,select);host.append(card);
 }
}
export function createFitSession(){let generation=0,controller;return {cancel(){generation++;controller?.abort();},async run(operation,apply){controller?.abort();controller=new AbortController();const current=++generation;try{const value=await operation(controller.signal);if(current===generation)apply(value);return current===generation;}catch(error){if(current!==generation||error.name==='AbortError')return false;throw error;}}};}
