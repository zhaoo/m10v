import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {navigationItems,renderNavigation} from '../web/shared/navigation.js';
import {gr4WorkbenchHtml} from './gr4-native-routes.mjs';
import {renderChangelog} from './changelog.mjs';
test('all public locations use one ordered navigation and at most one current page',()=>{
 for(const path of ['/','/gr3/','/gr3/index.html','/gr4/','/gr4/reference/','/gr2/','/gr3/sd-library.html','/gr4/sd-library.html','/guide/','/changelog/','/test-packages/','/support/']){
  const items=navigationItems(path);
  assert.deepEqual(items.map(i=>i.id),['gr3','gr4','gr2','sd','test-packages','guide','changelog','support']);
  assert.equal(items.filter(i=>i.active).length,path==='/'?0:1);
  assert.equal((renderNavigation(path).match(/aria-current="page"/g)||[]).length,path==='/'?0:1);
 }
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
  assert.match(html,/href="\/shared\/navigation.css"/);
 }
 const gr4=gr4WorkbenchHtml(source);
 assert.match(gr4,/<option value="gr4">GR IV · 1.11<\/option>/);
 assert.match(gr4,/id="studio-model-status"/);
});
test('GR II SD navigation stays in its own experimental workbench',()=>{
 assert.equal(navigationItems('/gr2/').find(i=>i.id==='sd').href,'/gr2/#sd');
 assert.equal(navigationItems('/gr2/inspect/').find(i=>i.id==='sd').href,'/gr2/#sd');
});
