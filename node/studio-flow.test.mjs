import test from 'node:test';import assert from 'node:assert/strict';import{readFile}from'node:fs/promises';
test('single studio orders source, settings and save with the library embedded directly',async()=>{
 const html=await readFile(new URL('../web/gr3/index.html',import.meta.url),'utf8');
 const nav=html.slice(html.indexOf('<aside class="steps"'),html.indexOf('<div class="steps-foot"'));
 assert.ok(nav.indexOf('data-step="source"')<nav.indexOf('data-step="features"'));
 assert.ok(nav.indexOf('data-step="features"')<nav.indexOf('data-step="build"'));
 assert.ok(!nav.includes('experimental'));assert.ok(!nav.includes('native-library.html'));
 assert.ok(!html.includes('id="use-800t-plan"'));assert.ok(!html.includes('id="use-native-plan"'));assert.ok(html.includes('id="native-editor"'));
 const root=await readFile(new URL('../web/index.html',import.meta.url),'utf8');
 assert.ok(root.includes('href="/gr3/"'));assert.equal((root.match(/class="camera-card gr-family"/g)||[]).length,1);assert.ok(root.includes('href="/gr4/"'));
});

test('shared import derives the model from official identity and keeps local choice separate',async()=>{
 const app=await readFile(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 assert.ok(app.includes("(gr4Workbench?['GR IV']:['GR III','GR IIIx']).includes(report.model)"));
 assert.ok(app.includes("chosenModel=gr4Workbench?'gr4':report.model==='GR IIIx'?'gr3x':'gr3'"));
 assert.ok(app.includes("model:$('local-source-model').value"));
 assert.ok(!app.includes('report.model!==modelLabel'));
});
