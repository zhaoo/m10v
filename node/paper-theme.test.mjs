import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const read=path=>readFile(new URL('../'+path,import.meta.url),'utf8');
test('legacy pages retain their paper theme after earlier themes',async()=>{
 const navigation=await read('web/shared/navigation.js');
 assert.match(navigation,/paper-theme\.css/);assert.match(navigation,/document\.head\.append\(paper\)/);
 const css=await read('web/shared/paper-theme.css');
 assert.match(css,/--paper:#f5f4f0/);assert.match(css,/--accent:#e85332/);
 assert.match(css,/\.cinematic-scene/);assert.match(css,/prefers-reduced-motion/);
});
test('workbench keeps real source, configuration, build and camera confirmation controls in the new layout',async()=>{
 const html=await read('web/gr3/index.html');
 for(const id of ['local-source-model','use-local-source','source-report','native-editor','imaging-settings','undo-edit','redo-edit','prepare-build','build-firmware','cancel-build','build-completion','install-camera-model','install-camera-version','install-camera-origin','disclaimer-confirm'])assert.ok(html.includes(`id="${id}"`),id);
 assert.match(html,/visual-v5/);assert.match(html,/href="\/gr3\/downgrade.html"/);
 assert.doesNotMatch(html,/不提供适配、降级|不提供适配或降级/);
});
test('public entry pages keep shared navigation and the actual downgrade route',async()=>{
 for(const file of ['web/index.html','web/guide.html','web/skills.html','web/changelog.html','web/gr3/sd-library.html']){
  const html=await read(file);assert.match(html,/src="\/shared\/navigation.js"/);assert.match(html,/content="light"/);
 }
 for(const file of ['web/index.html','web/skills.html']){const html=await read(file);assert.match(html,/href="\/gr3\/downgrade.html"/);assert.doesNotMatch(html,/不提供适配或降级|不提供适配或降级包/);}
});

test('paper preview binds existing table order without changing catalog or firmware configuration',async()=>{
 const {paperPreviewLook}=await import('../web/gr3/paper-preview.mjs');
 const legacy=[{id:'ektar100',curves:[[1]],matrixQ13:[8192],postQ512:[512]}];
 assert.deepEqual(paperPreviewLook({id:34},legacy),{...legacy[0],film:34,effects:{}});
 assert.deepEqual(paperPreviewLook({id:289},legacy,{charmeraColor:2}),{film:289,effects:{charmeraColor:2}});
 assert.equal(paperPreviewLook({id:33},legacy),null);
 assert.equal(paperPreviewLook({id:66},legacy),null);
 assert.equal(paperPreviewLook({id:35},legacy),null);
});
