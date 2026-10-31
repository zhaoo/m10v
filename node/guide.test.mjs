import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {createServer} from './server.mjs';
test('guide is served at both URLs and includes concise usage, limits, risk and four project credits',async()=>{
 const server=createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  const base=`http://127.0.0.1:${server.address().port}`;
  for(const path of ['/guide','/guide/']){
   const res=await fetch(base+path);assert.equal(res.status,200);assert.match(res.headers.get('content-type'),/text\/html/);const html=await res.text();
   for(const text of ['gr-custom-tool','GRLife','gr3-film-mods','darkslide-gr','47 套内置胶卷','fwdc239b.bin','fwdc243b.bin','变砖','已有记录优先'])assert.ok(html.includes(text),text);
   assert.deepEqual([...html.matchAll(/<script\b[^>]*src="([^"]+)"[^>]*><\/script>/g)].map(match=>match[1]), ['/shared/navigation.js']);
   assert.equal((html.match(/<script\b/g)||[]).length,1,'guide only needs the optional shared navigation module');
   assert.match(html,/<main class="guide">[\s\S]*怎么使用[\s\S]*刷机风险[\s\S]*<\/main>/,'instructions and risks remain readable in the static HTML');
  }
 }finally{await new Promise(r=>server.close(r));}
});
test('guide is linked from home and studio, and active model uses the same centered menu styling',async()=>{
 for(const name of ['index.html','gr3/index.html'])assert.match(await readFile(new URL('../web/'+name,import.meta.url),'utf8'),/href="\/guide\/"/);
 const css=await readFile(new URL('../web/gr3/styles.css',import.meta.url),'utf8');assert.match(css,/\.model-nav a,\.model-nav>span\{display:inline-flex;align-items:center/);
});
