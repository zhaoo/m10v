import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {navigationItems,renderNavigation,mountGRemoteLink} from '../web/shared/navigation.js';
import {gr4WorkbenchHtml} from './gr4-native-routes.mjs';
import {renderChangelog} from './changelog.mjs';
test('all public locations use one ordered navigation and at most one current page',()=>{
 for(const path of ['/','/gr3/','/gr3/index.html','/gr4/','/gr4/reference/','/gr2/','/gr3/sd-library.html','/gr4/sd-library.html','/gr3/downgrade.html','/guide/','/skills/','/changelog/','/support/']){
  const items=navigationItems(path);
  assert.deepEqual(items.map(i=>i.id),['gr3','gr4','gr2','sd','downgrade','guide','skills','changelog','support']);
  assert.equal(items.filter(i=>i.active).length,1);
  assert.equal((renderNavigation(path).match(/aria-current="page"/g)||[]).length,1);
 }
});
test('the shared skills entry opens installation instructions with the public ZIP download',async()=>{
 const {createServer}=await import('./server.mjs'),server=createServer();
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  const base=`http://127.0.0.1:${server.address().port}`;
  for(const route of ['/skills','/skills/']){
   const response=await fetch(base+route);assert.equal(response.status,200);
   assert.match(await response.text(),/href="\/downloads\/m10v-firmware-safety-skill.zip"/);
  }
  assert.match(renderNavigation('/skills/'),/<a href="\/skills\/" class="current" aria-current="page">技能<\/a>/);
 }finally{await new Promise(r=>server.close(r));}
});
test('SD navigation preserves model context and is selected independently of model editor',()=>{
 for(const model of ['gr3','gr4']){
  const items=navigationItems(`/${model}/sd-library.html`);
  assert.equal(items.find(i=>i.id==='sd').href,`/${model}/sd-library.html`);
  assert.equal(items.find(i=>i.active).id,'sd');
 }
});
test('derived GR IV and generated changelog include the same shared navigation assets',()=>{
 const source=readFileSync(new URL('../web/gr3/index.html',import.meta.url),'utf8');
 for(const html of [gr4WorkbenchHtml(source),renderChangelog()]){
  assert.match(html,/src="\/shared\/navigation.js"/);
  assert.match(html,/href="\/shared\/(?:navigation|visual-v5).css"/);
 }
 const gr4=gr4WorkbenchHtml(source);
 assert.match(gr4,/<option value="gr4">GR IV · 1.11<\/option>/);
 assert.match(gr4,/id="studio-model-status"/);
});
test('GR II SD navigation stays in its own experimental workbench',()=>{
 assert.equal(navigationItems('/gr2/').find(i=>i.id==='sd').href,'/gr2/#sd');
 assert.equal(navigationItems('/gr2/inspect/').find(i=>i.id==='sd').href,'/gr2/#sd');
});

test('only workbench and film library are primary; utilities and downgrade are collapsed in More',()=>{
 const html=renderNavigation('/gr3/downgrade.html');
 const primary=html.match(/<div class="navigation-primary">([\s\S]*?)<\/div>/)[1];
 assert.deepEqual([...primary.matchAll(/>([^<]+)<\/a>/g)].map(match=>match[1]),['工作台','胶卷库']);
 assert.match(html,/<details class="navigation-more">/);
 assert.doesNotMatch(html,/<details class="navigation-more" open/);
 for(const href of ['/gr3/downgrade.html','/guide/','/skills/','/changelog/','/support/','https://github.com/zhaoo/m10v'])assert.ok(html.slice(html.indexOf('<details class="navigation-more">')).includes(`href="${href}"`));
 assert.equal((html.match(/aria-current="page"/g)||[]).length,1);
});

test('public navigation links to GRemote exactly once with a safe external target',()=>{
 for(const path of ['/','/gr3/','/gr4/','/guide/']){
  const html=renderNavigation(path);
  assert.equal((html.match(/href="https:\/\/gremote\.izhaoo\.com"/g)||[]).length,1);
  assert.match(html,/<a[^>]*href="https:\/\/gremote\.izhaoo\.com"[^>]*target="_blank"[^>]*rel="noopener noreferrer"[^>]*>GRemote/);
 }
});

test('visual compact menu mounts one GRemote link across repeated navigation initialization',()=>{
 let html='';
 const menu={querySelector:()=>html.includes('https://gremote.izhaoo.com')?{}:null,insertAdjacentHTML:(where,value)=>{assert.equal(where,'beforeend');html+=value;}};
 mountGRemoteLink(menu);mountGRemoteLink(menu);
 assert.equal((html.match(/href="https:\/\/gremote\.izhaoo\.com"/g)||[]).length,1);
 assert.match(html,/target="_blank" rel="noopener noreferrer"/);
});
