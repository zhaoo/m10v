import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('product home exposes GR IV native workbench and GR II inspection with truthful limits', async () => {
  const html = await readFile(new URL('../web/index.html', import.meta.url), 'utf8');
  assert.match(html, /href="\/gr3\/"/);
  assert.match(html, /class="camera-entry primary-entry"/);
  assert.match(html,/href="\/gr4\/"/);
  assert.match(html,/href="\/gr2\/"/);
  assert.match(html,/实验固件构建/);
  assert.match(html,/原生胶卷工作台/);
  assert.match(html,/固件 1.11 · 待实机验证/);
  assert.match(html, /选择相机型号/);
  assert.doesNotMatch(html, /id="candidate-analyze"/);
  assert.doesNotMatch(html, /fonts\.googleapis\.com/);
});

test('GR III and GR IV expose distinct model workspaces', async () => {
  const [gr3, gr4] = await Promise.all([
    readFile(new URL('../web/gr3/index.html', import.meta.url), 'utf8'),
    readFile(new URL('../web/gr4/index.html', import.meta.url), 'utf8'),
  ]);
  assert.match(gr3, /class="topbar"/);
  assert.match(gr3, /class="model-nav"/);
  assert.match(gr4, /class="product-topbar"/);
  assert.match(gr4, /class="model-switch"/);
  for (const html of [gr3, gr4]) assert.doesNotMatch(html, /研究中|测试平台|半成品/);
  assert.doesNotMatch(gr4, /实验性/);
  assert.doesNotMatch(gr4, /捐赠|支持项目|export-free-notice/);
});

test('GR III shares import, settings and save without writing SD', async () => {
  const gr3 = await readFile(new URL('../web/gr3/index.html', import.meta.url), 'utf8');
  for (const step of ['features', 'source', 'build'])
    assert.match(gr3, new RegExp(`data-page="${step}"`));
  for (const id of ['feature-list', 'source-report', 'prepare-build', 'build-firmware'])
    assert.match(gr3, new RegExp(`id="${id}"`));
  assert.match(gr3, /id="plan-ledger"/);
  assert.match(gr3, /id="open-build-desk"/);
  assert.doesNotMatch(gr3, /STEP 0[1-4]|载入截图参考方案/);
  assert.doesNotMatch(gr3, /SD 卡准备|id="sd-card"|id="prepare-official-sd"|id="refresh-sd"/);
  assert.match(gr3, /保存固件/);
});

test('library opens directly and film selection uses its catalog',async()=>{
 const html=await readFile(new URL('../web/gr3/index.html',import.meta.url),'utf8');
 assert.doesNotMatch(html,/id="(?:use-800t-plan|use-native-plan|active-plan-note)"/);assert.match(html,/id="native-editor"/);
 assert.doesNotMatch(html,/data-step="experimental"/);assert.doesNotMatch(html,/href="\/gr3\/native-library.html"/);
 const app=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 assert.doesNotMatch(app,/use-800t-plan|use-native-plan|active-plan-note/);assert.match(app,/native-library/);
});

test('GR III street editor has slot controls and source-derived film preview', async () => {
  const [html, css] = await Promise.all([
    readFile(new URL('../web/gr3/index.html', import.meta.url), 'utf8'),
    readFile(new URL('../web/gr3/styles.css', import.meta.url), 'utf8'),
  ]);
  for (const id of ['recipe-dialog', 'community-select', 'recipe-parameters', 'plan-ledger'])
    assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /href="\/"[^>]*>选择机型/);
  assert.match(html, /id="local-source-model"/);
  assert.match(html, /value="gr3x"/);
  assert.match(css, /gr3-street-photo\.png/);
  assert.match(css, /#0d0e0e/);
  assert.match(css, /#d6ad69/);
  assert.doesNotMatch(css, /border-radius:\s*(?:1[0-9]|[2-9][0-9])px/);
});

test('GR IV product UI uses only namespaced APIs and exposes latest feature surfaces', async () => {
  const [html, app] = await Promise.all([
    readFile(new URL('../web/gr4/index.html', import.meta.url), 'utf8'),
    readFile(new URL('../web/gr4/app.js', import.meta.url), 'utf8'),
  ]);
  for (const id of ['nav-filters', 'nav-crops', 'nav-shutdown', 'calibration-dialog',
    'build-firmware', 'history-workspace', 'allow-older']) assert.match(html, new RegExp(`id="${id}"`));
  for (const asset of ['styles.css', 'app.js', 'calibration-ui.js'])
    assert.match(html, new RegExp(`["']/gr4/${asset.replace('.', '\\.')}["']`));
  assert.match(html, /studio-theme\.css/);
  assert.match(html, /gr4-hero/);
  assert.doesNotMatch(html, /(?:href|src)="\/(?:styles\.css|app\.js|calibration-ui\.js)"/);
  assert.doesNotMatch(html, /m10v-back/);
  assert.match(html, /m10v · GR固件工作台/);
  assert.doesNotMatch(app, /["`]\/api\/(?!gr4\/)/);
  assert.match(app, /X-M10V-Token/);
});

test('native 800T uses the same capture chain as texture and timestamp',async()=>{
 const core=await readFile(new URL('../native/gr3/m10v_library.c',import.meta.url),'utf8');
 // Pixel behavior is exercised by test_gr3_800t_energy and the ARM capture tests.
 const ui=await readFile(new URL('../web/gr3/native-library-controls.html',import.meta.url),'utf8');
 for(const id of ['slots','grain'])assert.match(ui,new RegExp(`id="${id}"`));
 assert.doesNotMatch(ui,/id="stamp"|id="format"|id="corner"|id="color"/);
 const imaging=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 assert.match(imaging,/native-stamp-fields/);assert.match(imaging,/filmNameStamp/);
 assert.doesNotMatch(ui,/id="soft"/);
});

test('HDF entry is independent of film and preserves the simplified workbench',async()=>{
 const app=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 assert.match(app,/MENU → 设置 → HDF 模拟/);
 assert.match(app,/film_library:state.features.has\('film'\)/);
 assert.match(app,/hdf_enabled:state.features.has\('digitalHdf'\)/);
 assert.match(app,/if\(!meta.globalHdf&&!meta.globalZoom\)state.features.add\('film'\)/);
 assert.match(app,/仅使用 HDF/);
 const html=await readFile(new URL('../web/gr3/index.html',import.meta.url),'utf8');
 assert.match(html,/>影像方案<\/button>/);
});

test('HDF-only feature cannot be removed until film is enabled',async()=>{
 const app=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 const guard=app.slice(app.indexOf("if(id==='digitalHdf'&&active&&!state.features.has('film'))"),app.indexOf("state.features=updateWorkbenchFeature(",app.indexOf("if(id==='digitalHdf'&&active&&!state.features.has('film'))")));
 const {default:vm}=await import('node:vm');
 for(const [features,blocked] of [[['digitalHdf'],true],[['digitalHdf','film'],false]]){
  let message='';const context=vm.createContext({id:'digitalHdf',active:true,state:{features:new Set(features)},notice:value=>{message=value;}});
  vm.runInContext('(function(){'+guard+'})()',context);
  assert.equal(Boolean(message),blocked);if(blocked)assert.match(message,/档位设为关闭.*先启用胶卷库/);
 }
});
