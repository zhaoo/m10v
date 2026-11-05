import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {catalogFilms} from '../web/gr3/film-catalog-view.mjs';

const source=(await readFile(new URL('../web/gr3/sd-library.js',import.meta.url),'utf8')).replace(/^import .*;\n/gm,'');
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.value='';this.disabled=false;this.textContent='';}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 setAttribute(name,value){this[name]=value;}
 querySelectorAll(tag){return walk(this).filter(n=>n.tagName===tag);}
 remove(){}
 click(){return this.onclick?.();}
}
const walk=node=>node.children.flatMap(child=>typeof child==='object'?[child,...walk(child)]:[]);
async function page(search=''){
 const elements=new Map();
 const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
 const requests=[];
 const document={getElementById:$,createElement:tag=>new Element(tag),body:new Element(),
  querySelector:()=>new Element(),querySelectorAll:selector=>selector==='#sd-films input'?walk($('sd-films')).filter(n=>n.tagName==='input'):[]};
 const location={pathname:'/gr3/sd-library.html',search:search.startsWith('#')?'':search,hash:search.startsWith('#')?search:'',href:'http://localhost/gr3/sd-library.html'+search};
 const fetch=async(url,options)=>{
  if(url==='/api/status')return Response.json({session_token:'test-session'});
  if(url==='/api/gr3/native-library/catalog')return Response.json({films:[
   {id:33,name:'800T',group:'ECN2',icon_url:'33.png'},
   {id:318,name:'2383',group:'ECN2',icon_url:'318.png'},
   {id:37,name:'Portra 400',group:'C41',icon_url:'37.png'},
  ]});
  requests.push({url,body:JSON.parse(options.body)});
  return new Response(new Blob(['resource fixture']),{headers:{'Content-Type':'application/zip'}});
 };
 await vm.runInNewContext('(async()=>{'+source+'})()',{
  document,location,URLSearchParams,URL:class extends URL{static createObjectURL(){return 'blob:test';}static revokeObjectURL(){}},
  history:{replaceState(){}},fetch,catalogFilms,customFilmArtwork:()=>'',setTimeout(){},console,
  FileReader:class {readAsDataURL(file){file.arrayBuffer().then(bytes=>{this.result='data:text/plain;base64,'+Buffer.from(bytes).toString('base64');this.onload();});}},
 });
 return {$,requests,inputs:()=>document.querySelectorAll('#sd-films input')};
}

test('IIIx library URL filters unsupported stocks and exports the declared camera model',async()=>{
 const p=await page('#model=gr3x');
 await p.$('sd-download').click();
 assert.equal(p.requests[0].body.model,'gr3x');
 assert.deepEqual(p.requests[0].body.ids,[33,37]);
 assert.deepEqual(p.inputs().map(n=>n.value),[33,37]);
});

test('switching library camera rebuilds full selection without leaking GR III-only recipes',async()=>{
 const p=await page();
 p.$('sd-model').value='gr3x';p.$('sd-model').onchange();
 p.$('sd-none').click();assert.equal(p.$('sd-download').disabled,true);
 p.$('sd-all').click();await p.$('sd-download').click();
 assert.deepEqual(p.requests[0].body,{model:'gr3x',ids:[33,37],customFilms:[]});
 p.$('sd-model').value='gr3';p.$('sd-model').onchange();
 await p.$('sd-download').click();
 assert.deepEqual(p.requests[1].body.ids,[33,318,37]);
});

test('unknown model query blocks export until an explicit supported camera is selected',async()=>{
 const p=await page('?model=gr4');
 assert.equal(p.$('sd-download').disabled,true);
 assert.equal(p.inputs().length,0);
 p.$('sd-model').value='gr3x';p.$('sd-model').onchange();
 assert.equal(p.$('sd-download').disabled,false);
 await p.$('sd-download').click();
 assert.equal(p.requests[0].body.model,'gr3x');
});

test('IIIx custom LUT is exported and remains removable after the file read finishes',async()=>{
 const p=await page('#model=gr3x');
 p.$('custom-name').value='My Film';
 p.$('custom-file').files=[new File(['LUT_3D_SIZE 2\n'],'my.cube')];
 await p.$('custom-add').click();
 const remove=p.$('custom-films').querySelectorAll('button')[0];
 assert.equal(remove.disabled,false);
 await p.$('sd-download').click();
 assert.equal(p.requests[0].body.customFilms[0].name,'My Film');
 remove.click();
 assert.equal(p.$('custom-films').querySelectorAll('button').length,0);
});

test('export all selects and downloads all model-supported films in one action',async()=>{
 const p=await page('#model=gr3x');p.$('sd-none').click();
 await p.$('sd-export-all').click();
 assert.equal(p.requests.length,1);
 assert.deepEqual(p.requests[0].body,{model:'gr3x',ids:[33,37],customFilms:[]});
 assert.equal(p.$('sd-download').disabled,false);
});
