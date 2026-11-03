import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {navigationItems} from '../web/shared/navigation.js';
const read=path=>readFile(new URL('../'+path,import.meta.url),'utf8');
test('approved v5 stylesheet is preserved byte for byte without a replacement theme',async()=>{
 const css=await read('web/shared/visual-v5.css');
 assert.equal(createHash('sha256').update(css.trim()).digest('hex'),'07259f97da91efd345837b7c2707d5f3e99ee1225a7d6e9b6d5501f6fb9ffddc');
});
test('the visible workbench uses the original structural components and keeps real engine dialogs at body level',async()=>{
 const html=await read('web/gr3/index.html');
 for(const cls of ['shell','sidebar','workbench','workspace-head','workspace-tabs','studio-grid','visual-column','inspector','look-intro','control-section','selected-films','actionbar'])assert.ok(html.includes(`class="${cls}"`)||html.includes(`class="${cls} `),cls);
 for(const id of ['look-title','look-type','look-note','look-tags','add-film','grain-control','halo-toggle','film-name-toggle','date-toggle','selected-films','generate-button'])assert.ok(html.includes(`id="${id}"`),id);
 assert.match(html,/<div id="legacy-workbench" hidden>/);
 const engineEnd=html.indexOf('<dialog id="recipe-dialog"');
 assert.ok(engineEnd>html.indexOf('id="legacy-workbench"'));
 assert.match(html,/<\/div>\s*<dialog id="recipe-dialog"/);
 assert.match(html,/src="\/gr3\/studio.js"/);
 assert.doesNotMatch(html,/href="\/(?:gr3\/(?:cinematic|imaging|styles)|shared\/paper-theme)\.css"/);
 const tools=html.slice(html.indexOf('<section class="tool-panel"'),html.indexOf('<div class="actionbar">'));
 assert.match(tools,/data-live-tools/);
 assert.doesNotMatch(html,/id="visual-tools-dialog"|id="visual-all-tools"/);
 for(const id of ['i-sun','i-frame','i-camera','i-type'])assert.ok(html.includes(`id="${id}"`));
});
test('resource cards use original library structure and retain a real independent full export action',async()=>{
 const html=await read('web/gr3/sd-library.html');
 for(const cls of ['library-toolbar','library-toolbar-actions','library-grid','library-secondary','library-download-bar'])assert.ok(html.includes(`class="${cls}"`),cls);
 for(const id of ['sd-all','sd-none','sd-export-all','sd-download','sd-model','custom-name','custom-file','custom-add'])assert.ok(html.includes(`id="${id}"`),id);
 assert.match(html,/src="\/gr3\/sd-library.js"/);
 const app=await read('web/gr3/sd-library.js');assert.match(app,/\/api\/gr3\/sd-library\/export/);
});
test('the root studio and model-bound library links preserve the verified camera context',async()=>{
 assert.equal(navigationItems('/').filter(item=>item.active).length,1);
 const app=await read('web/gr3/visual-studio.mjs');
 assert.match(app,/\/gr3\/sd-library.html#model=/);
 assert.match(app,/await importModel\(model\)/);
 assert.match(await read('web/gr3/studio.js'),/declaredPageModel/);
});

test('original and film preview buttons update the actual preview mode',async()=>{
 const vm=await import('node:vm'),source=await read('web/gr3/visual-studio.mjs');
 const buttons=[{dataset:{preview:'original'}},{dataset:{preview:'film'}}],modes=[];
 const context=vm.createContext({document:{querySelectorAll:()=>buttons},renderPreview:()=>modes.push(vm.runInContext('previewMode',context))});
 const start=source.indexOf(" for(const button of document.querySelectorAll('[data-preview]'))button.onclick");
 const end=source.indexOf(" $('film-search').oninput",start);
 vm.runInContext("let previewMode='film';"+source.slice(start,end),context);
 buttons[0].onclick();buttons[1].onclick();assert.deepEqual(modes,['original','film']);
});
test('initialization failure is visible before the adapter is available and keeps generation disabled',async()=>{
 const vm=await import('node:vm'),source=await read('web/gr3/studio.js');
 const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',hidden:true,disabled:false,classList:{add(value){this[value]=true;},toggle(){}}});return nodes.get(id);};
 const context=vm.createContext({document:{body:{classList:{contains:()=>true}},getElementById:node},$:node});
 vm.runInContext(source.slice(source.indexOf('function notice('),source.indexOf('async function api(')),context);
 context.notice('工作区载入失败。请刷新后重试。',true);
 assert.match(node('visual-action-status').textContent,/载入失败/);assert.equal(node('toast').classList.show,true);assert.match(node('visual-source-state').textContent,/失败/);assert.equal(node('generate-button').disabled,true);
 assert.match(await read('web/gr3/index.html'),/id="generate-button" disabled/);
});
test('preview controller supports the full source dimensions while keeping legacy defaults',async()=>{
 const vm=await import('node:vm');let source=await read('web/gr3/preview-controller.mjs');source=source.replace(/^import .*;\n/,'').replace('export function createFilmPreview','function createFilmPreview').replace("new URL('./preview-worker.mjs',import.meta.url)","'worker'");
 const uploaded=[],painted=[];
 class Worker{postMessage(message){if(message.kind==='source'){this.width=message.width;this.height=message.height;uploaded.push([this.width,this.height]);}else this.onmessage({data:{id:message.id,pixels:new Uint8ClampedArray(this.width*this.height*4).buffer}});}terminate(){}}
 class Image{set src(value){queueMicrotask(()=>this.onload());}}
 class ImageData{constructor(pixels,width,height){this.width=width;this.height=height;}}
 const context=vm.createContext({Worker,Image,ImageData,Uint8ClampedArray,Map,queueMicrotask,requestAnimationFrame:fn=>{fn();return 1;},cancelAnimationFrame(){},document:{createElement:()=>{const canvas={};canvas.getContext=()=>({drawImage(){},getImageData:()=>({width:canvas.width,height:canvas.height,data:new Uint8ClampedArray(canvas.width*canvas.height*4)})});return canvas;}}});
 vm.runInContext(source,context);
 const canvas={isConnected:true,getContext:()=>({putImageData:data=>painted.push([data.width,data.height])})};
 await context.createFilmPreview().request(canvas,{});await context.createFilmPreview({width:1536,height:1024}).request(canvas,{});
 assert.deepEqual(uploaded,[[620,413],[1536,1024]]);assert.deepEqual(painted,uploaded);
});
