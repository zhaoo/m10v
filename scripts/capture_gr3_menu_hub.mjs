// Capture the approved offline HTML at the GR III display's exact viewport.
import {mkdir} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import path from 'node:path';

const [preview, output] = process.argv.slice(2);
if (!preview || !output) throw new Error('usage: capture_gr3_menu_hub.mjs preview.html output');
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.M10V_PLAYWRIGHT || 'playwright');
await mkdir(output, {recursive: true});
const browser = await chromium.launch({executablePath: process.env.M10V_CHROME || undefined});
try {
 const page = await browser.newPage({viewport: {width: 744, height: 600}, reducedMotion: 'reduce'});
 await page.goto(pathToFileURL(path.resolve(preview)).href);
 await page.addStyleTag({content: `
  #camera{border:0;border-radius:0}
  #carousel .deck-card[data-slot="center"]:not(.selected){border-color:#484750;box-shadow:0 1.35cqw 3cqw #0004}
  #carousel .deck-card.selected{border-color:var(--card-accent);box-shadow:0 2cqw 4cqw #0006,inset 0 .35cqw 0 var(--card-accent)}
  #interface.expanded .bar strong{font-size:32px}
  #interface.expanded .overview-list{position:absolute;top:85px;left:33px;right:33px}
  #interface.expanded .overview-list .row{height:53px;min-height:53px;padding:0 15px;gap:12px}
  #interface.expanded .overview-list .row .name{font-size:29px;font-weight:600}
  #interface.expanded .overview-list .row .value{font-size:24px;color:#c3c5d1}
  #interface.expanded .overview-list .row .value.on{color:var(--accent)}
  #interface.expanded .overview-list .row .icon{width:32px;height:32px;font-size:23px}
  #interface.expanded .overview-list .row .chev{width:10px;height:10px;border-width:0 2px 2px 0}
 `});
 await page.mouse.move(0, 0);
 async function capture(id, layout, style = null) {
  await page.evaluate(({layout, style}) => {
   layers.length = 0; settings.clear(); abActive = false;
   surface.classList.remove('expanded');
   for (const film of assets.films.slice(0, 10)) picked.add(film.id);
   if (layout < 4) {
    if (style !== null) for (const film of assets.films.slice(style, 10)) picked.delete(film.id);
    page = layout; deckPage = Number(layout === 3); render();
    return;
   }
   if (layout === 10 || layout === 12) {
    page = layout === 10 ? 3 : 4;
    open(layout === 10 ? '说明' : '打赏');
    return;
   }
   if (layout === 11) {page = 4; deckPage = 1; render(); return;}
   const effect = layout < 8;
   if (style) {
    for (const [key,value] of Object.entries(style)) settings.set(key,value);
    abActive = Boolean(style.abActive);
   }
   page = effect ? 1 : 2;
   open(effect ? '效果' : '设置', {type: 'overview'});
   surface.classList.add('expanded');
   document.querySelector('#title').textContent = effect ? '效果' : '设置';
   const rows = [...view.querySelectorAll('.overview-list .row')];
   for (const row of rows) row.querySelector('.sub')?.remove();
   if (effect) {
    if (!(layout & 1)) rows[4].remove();
    if (!(layout & 2)) rows[6].remove();
   } else if (layout === 8) rows[1].remove();
   if (style?.replace) {
    const val = rows[style.replace.index].querySelector('.value');
    val.textContent = style.replace.label;
    val.classList.toggle('on', Boolean(style.replace.active));
   }
  }, {layout, style});
  if (layout >= 4 && layout < 10) {
   const [camera, rows] = await Promise.all([
    page.locator('#camera').boundingBox(),
    page.locator('.overview-list .row').evaluateAll(elements => elements.map(el => el.getBoundingClientRect().toJSON())),
   ]);
   if (rows.some((row, i) => row.y-camera.y !== 86+53*i || row.height !== 53))
    throw new Error('Overview rows differ from firmware hitboxes');
  }
  await page.locator('#camera').screenshot({path: path.join(output, id + '.png')});
 }
 for (let layout = 0; layout <= 12; layout++) await capture(layout, layout);
 for (const layout of [0,1,2])
  for (let n = 0; n < 10; n++) await capture(16+layout*11+n,layout,n);
 const effectOptions = [
  [0,['关闭','弱','中','强','—']],
  [1,['关闭','拍立得','胶卷','—']],
  [2,['关','小猫吃鱼','樱花纷飞','绚烂彩虹','深海水母','小猫爪爪','呆头大鹅','宝可梦']],
  [3,['关','弱','中','强','—']],
  [4,['关','开','—']],
  [6,['未启用','已启用','—']],
 ];
 for (let layout = 4; layout < 8; layout++) {
  for (const [type,[index, options]] of effectOptions.entries()) {
   if ((index === 4 && !(layout&1)) || (index === 6 && !(layout&2))) continue;
   for (let value = 1; value < options.length; value++)
    await capture(64+(layout-4)*48+type*8+value, layout, {replace:{index,label:options[value],active:(index>=3&&options[value]!=='—')}});
  }
 }
 const settingOptions = [
  ['关闭','仅日期','日期和时间','胶卷名称','—'],
  ['原厂画面','图片 1','图片 2','图片 3','—'],
  ['3:2','4:3','16:9','1:1','XPan','6x7','Half','—'],
  ['关闭',...Array.from({length:23},(_,i)=>(28+i)+' mm'),'—'],
  ['沿用原厂','黄金分割','黄金螺旋（左上）','黄金螺旋（右上）','黄金螺旋（左下）','黄金螺旋（右下）','—'],
 ];
 for (let layout = 8; layout <= 9; layout++) {
  for (const [type, start, index] of [[0,0,0],[1,8,1],[2,16,2],[3,24,5],[4,49,4]]) {
   if (type===1&&layout===8) continue;
   const options=settingOptions[type];
   for (let value = 1; value < options.length; value++)
    await capture(256+(layout-8)*64+start+value,layout,{replace:{index,label:options[value]}});
  }
 }
} finally {
 await browser.close();
}
