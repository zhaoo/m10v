import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
test('seven deterministic irregular imprints, with no photograph in source',async()=>{
 const target=path.resolve('web/shared/film-imprints.mjs');
 assert.ok(await fs.stat(target).catch(()=>null),'original film imprint generator must exist');
 const {filmImprintSvg,filmImprintStyles}=await import(pathToFileURL(target));
 assert.deepEqual(filmImprintStyles,['小猫吃鱼','樱花纷飞','绚烂彩虹','深海水母','小猫爪爪','呆头大鹅','宝可梦']);
 const pokemonSprites=await Promise.all(['025','001','004','007'].map(async id=>'data:image/png;base64,'+(await fs.readFile(`native/gr3/film-imprints/pokemon/${id}.png`)).toString('base64')));
 for(let i=1;i<=7;i++){
  const svg=filmImprintSvg(i,{pokemonSprites});assert.equal(svg,filmImprintSvg(i,{pokemonSprites}));
  assert.match(svg,/viewBox="0 0 1536 1024"/);assert.doesNotMatch(svg,/(?:href|src)="https?:|<text/);
  if(i===7)for(const sprite of pokemonSprites)assert.ok(svg.includes(sprite));else assert.doesNotMatch(svg,/<image/);
  const scales=[...svg.matchAll(/scale\(([.\d]+)\)/g)].map(m=>+m[1]);
  assert.ok(Math.max(...scales)>Math.min(...scales)*2,'sizes must visibly vary');
  const turns=[...svg.matchAll(/rotate\(([-.\d]+)\)/g)].map(m=>+m[1]);
  if(i!==7)assert.ok(turns.some(v=>v>120),'some motifs drift upside down');
 }
 for(const bad of [-1,0,8,1.1,'1',null])assert.throws(()=>filmImprintSvg(bad));
});
