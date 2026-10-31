import {modelCapabilities} from './model-capabilities.mjs';
import {normalizeConfiguration,zoomSummary} from './native-library-state.mjs';

// Shared by the imaging plan and the standalone library editor.
export function renderZoomControls(root,configuration,model,onChange,busy=false,{feature=false,number='01'}={}){
 if(!root)return;
 const lens=modelCapabilities(model).zoom;
 root.hidden=!lens;root.replaceChildren();if(root.hidden)return;
 const doc=root.ownerDocument,make=(tag,text)=>{const n=doc.createElement(tag);if(text)n.textContent=text;return n;};
 const heading=make('h3','裁切焦距 · 两档');
 const label=make('label'),toggle=make('input');toggle.type='checkbox';toggle.checked=configuration.zoom.write;toggle.disabled=busy;
 toggle.setAttribute('aria-label','下次固件更新写入裁切焦距');
 label.append(toggle,' 下次固件更新写入这两档焦距');
 toggle.onchange=()=>onChange(normalizeConfiguration({...configuration,zoom:{...configuration.zoom,write:toggle.checked}}));
 const fields=make('div');fields.className='stamp-fields';
 configuration.zoom.slots.forEach((mm,index)=>{
  const field=make('label',`第 ${index+1} 档（mm）`),input=make('input');input.type='number';input.dataset.imagingField='zoom-'+index;input.min=String(lens.min);input.max=String(lens.max);input.step='1';input.value=String(mm);input.required=true;input.disabled=busy||!configuration.zoom.write;
  input.setAttribute('aria-label',`裁切焦距第 ${index+1} 档（mm）`);
  input.oninput=()=>input.setCustomValidity('');
  input.onchange=()=>{
   const value=Number(input.value);
   if(input.value.trim()===''||!Number.isInteger(value)||value<lens.min||value>lens.max){input.setCustomValidity(`请输入 ${lens.min}–${lens.max} 的整数焦距`);input.reportValidity();return;}
   input.setCustomValidity('');const slots=[...configuration.zoom.slots];slots[index]=value;
   onChange(normalizeConfiguration({...configuration,zoom:{...configuration.zoom,slots}}));
  };
  field.append(input);fields.append(field);
 });
 const hint=make('p',`开启后，下次安装此固件时写入一次；之后在机内的修改会保留。关闭则保留机内设置。两档支持 ${lens.min}–${lens.max} mm，按 1 mm 调整。`);hint.className='hint';
 const summary=make('p',zoomSummary(configuration));summary.className='hint';summary.setAttribute('aria-live','polite');
 if(feature){
  const copy=make('div'),title=make('div'),num=make('span',number),tag=make('span','GR III / IIIx · 两档焦距 · 更新时写入一次');
  title.className='feature-title';num.className='feature-num';tag.className='feature-tag';
  title.append(num,heading);copy.append(title,hint,tag);
  const button=make('button',configuration.zoom.write?'关闭':'开启');button.type='button';button.disabled=busy;
  button.dataset.imagingField='zoom-toggle';button.className='feature-toggle'+(configuration.zoom.write?' selected':'');button.setAttribute('aria-pressed',String(configuration.zoom.write));button.onclick=toggle.onchange=()=>onChange(normalizeConfiguration({...configuration,zoom:{...configuration.zoom,write:!configuration.zoom.write}}));
  root.append(copy,button);
  if(configuration.zoom.write){const detail=make('div');detail.className='feature-detail zoom-detail';detail.append(fields,summary);root.append(detail);}
 }else root.append(heading,label,fields,hint,summary);
}

export function validateZoomControls(root){
 const invalid=root?.querySelector('input:invalid');
 if(invalid){invalid.reportValidity();throw Error('请输入当前机型范围内的整数裁切焦距');}
}
