import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {renderNavigation} from '../web/shared/navigation.js';
const read=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
test('power images expand within the imaging plan and the workflow has three steps',()=>{
 const html=read('web/gr3/index.html');
 assert.deepEqual([...html.matchAll(/data-step="([^"]+)"/g)].map(m=>m[1]),['source','features','build']);
 const imaging=html.slice(html.indexOf('id="imaging-settings"'),html.indexOf('id="native-editor"'));
 assert.match(imaging,/id="power-images"/);
 assert.doesNotMatch(html,/data-page="power"|data-back="power"/);
});
test('all models remain reachable inside one model menu with progress labels',()=>{
 for(const path of ['/','/gr3/','/gr4/','/gr2/']){
  const html=renderNavigation(path);
  assert.match(html,/<details class="model-menu"/);
  assert.match(html,/GR IV.*进行中/);
  assert.match(html,/GR II.*进行中/);
  for(const model of ['gr3','gr4','gr2'])assert.match(html,new RegExp(`href="/${model}/"`));
 }
});
