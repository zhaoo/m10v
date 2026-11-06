// Original M10V patterns; Pokemon uses separately attributed official sprites.
export const filmImprintStyles=Object.freeze(["小猫吃鱼","樱花纷飞","绚烂彩虹","深海水母","小猫爪爪","呆头大鹅","宝可梦"]);
const W=1536,H=1024;const gold='#ffe29b',pink='#ff9cb6',cream='#fff1bd',salmon='#ff9b77',blue='#75dafa';
const path=(d,c,sw=4.5,fill='none')=>`<path d="${d}" fill="${fill}" stroke="${c}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round"/>`;
const ellipse=(x,y,rx,ry,c)=>`<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="${c}"/>`;
const circle=(x,y,r,c)=>ellipse(x,y,r,r,c);
const place=(art,x,y,s=1,a=0)=>`<g transform="translate(${x} ${y}) rotate(${a}) scale(${s})">${art}</g>`;
function cat(variant=0){return path('M-39-10 L-47-44 Q-43-50-17-32 Q0-39 21-31 L42-46 Q49-48 46-15 Q62 4 50 28 Q40 47 0 48 Q-39 47-49 28 Q-59 9-39-10Z',gold,4.7)+path('M-42-3L-65-8M-45 9L-68 12M41-5L65-12M47 8L69 8',gold,3.6)+ellipse(-19,2,10,13,gold)+ellipse(19,2,10,13,gold)+ellipse(-16,2,3.8,6,'#705c84')+ellipse(22,2,3.8,6,'#705c84')+path('M-4 19Q0 14 4 19L0 23Z',pink,1,pink)+path('M0 24Q-7 32-12 25M0 24Q6 32 12 25',gold,3)+ (variant%2?path('M-23-36Q-34-57-22-62L23-62Q36-57 24-36M-19-58L-15-43M0-59L0-44M20-58L15-43',gold,3.8):'');}
function fish(c=salmon){return path('M-28 0Q-4-31 31-5Q43 0 31 8Q0 30-28 0L-49 17L-49-15Z',c,2.2,c)+circle(25,-3,2.8,'#766786')+path('M-2-12L4-21L13-14M-6 14L0 22L13 14',c,2.1,c);}
function flower(c=cream){let a='';for(let i=0;i<5;i++)a+=place(ellipse(0,-10,6.5,11,c),0,0,1,i*72);return a+circle(0,0,3.6,'#ffd27a');}
function star(c=gold){return path('M0-21L6-6L21 0L6 6L0 21L-6 6L-21 0L-6-6Z',c,3.3);}
function sakura(c=pink){let a='';for(let i=0;i<5;i++)a+=place(path('M0 1C-20-8-19-28-7-29L0-24L7-29C20-27 19-8 0 1Z',c,1.7,c),0,0,1,i*72);for(let i=0;i<5;i++)a+=place(path('M0-2L0-14',cream,1.4)+circle(0,-15,2,cream),0,0,1,i*72);return a+circle(0,0,3.8,'#ffe8ac');}
function petal(c=pink){return path('M0 13C-24-3-13-20 0-13C13-22 21-4 0 13Z',c,0,c);}
function rainbow(){let a='';['#ff928e','#ffd784','#fff6a8','#a8e4bc','#84cfe9','#c8a8f0'].forEach((c,i)=>{let r=62-i*8;a+=path(`M${-r} 15A${r} ${r} 0 0 1 ${r} 15`,c,5)});return a+path('M-75 19C-83 9-72 0-63 7C-61-8-42-7-40 5C-24 0-22 22-37 23H-72M39 23C27 18 31 5 42 7C47-8 66-7 68 7C85 4 86 23 72 24Z',cream,3.5);}
function jelly(c=blue,variant=0){let a=path('M-43 0C-47-62 41-72 44 0Q35 12 25 1Q15 12 5 1Q-5 12-15 1Q-27 13-37 1Z',c,3.6);a+=path('M-28-7C-31-31-16-47-6-46M12-47C25-34 32-19 30-7M-8-44C-17-29-15-13-14-6M5-45C13-29 12-13 12-6',c,1.7);[-28,-13,3,19,31].forEach((x,i)=>{let l=[64,100,76,107,66][i];a+=path(`M${x} 5C${x+22} 30 ${x-25} 37 ${x} 59S${x+15} ${l-2} ${x-4} ${l+10}`,c,i%2?2.4:1.8)});return a+circle(-13,-21,3,cream)+circle(15,-22,3,cream);}
function paw(c=pink,outline=false){let a=path('M-24 17C-28 5-17-1-12-8C-8-15 1-15 7-8C15-1 29 6 25 18C22 29 8 23 0 24C-9 24-19 31-24 17Z',c,outline?3.4:1.1,outline?'none':c);[[-26,-11,7.8,10,-30],[-10,-27,8.3,11.5,-12],[11,-27,8.3,11.5,12],[28,-11,7.8,10,30]].forEach(([x,y,rx,ry,r])=>{a+=place(outline?`<ellipse rx="${rx}" ry="${ry}" fill="none" stroke="${c}" stroke-width="3.4"/>`:ellipse(0,0,rx,ry,c),x,y,1,r)});return a;}
function heart(c=pink){return path('M0 14C-31-4-18-25 0-12C18-25 31-4 0 14Z',c,3.2);}
function goose(){return path('M-30 25C-61 3-40-20-4-12L6-48C8-75 42-78 46-56C49-44 34-38 29-38L24-9C50 4 43 39 13 42C-9 46-26 38-30 25Z',cream,4.4)+path('M43-60L67-53L43-47Z',salmon,2,salmon)+circle(33,-59,3.3,gold)+path('M-28 8Q-12 34 10 12M-12 42L-16 60L-31 60M16 41L22 59L38 59',cream,3.8)+path('M-28-13L-48-28L-41-4',cream,3.8);}
// Original film-imprint artwork. Layout is compiled on the computer, never
// generated over camera pixels. Irregular clusters, large gaps and cut edges
// replace the first draft's uniform two-row pattern.
export function filmImprintSvg(style,{pokemonSprites}={}){
 if(!Number.isInteger(style)||style<1||style>7)throw new RangeError("film imprint style must be1..7");
 if(style===7&&(!Array.isArray(pokemonSprites)||pokemonSprites.length!==4||pokemonSprites.some(s=>typeof s!=='string'||!s.startsWith('data:image/png;base64,'))))throw new TypeError('four embedded Pokemon sprites required');
 let state=0x51a7e93d+(style*2173);const rand=()=>{state^=state<<13;state^=state>>>17;state^=state<<5;return(state>>>0)/4294967296},range=(a,b)=>a+(b-a)*rand();let a='';
 const put=(art,x,y,s=1,r=0,opacity=1)=>a+=`<g opacity="${opacity}">${place(art,x,y,s,r)}</g>`;
 const tilt=()=>style===7?range(-24,24):range(-63,63)+(rand()<.19?180:0);
 // Asymmetric anchors follow a wandering strip, with no matching upper/lower
 // spacing. Large blank intervals are deliberate, as are the clipped motifs.
 const anchors=style===7?[[115,127],[385,138],[1077,130],[1403,296],[1369,921],[806,903],[249,937],[83,679]]:[[-25,112],[307,62],[965,107],[1533,314],[1396,962],[786,941],[171,1000],[-10,710]];
 const primary=(i)=>{
  if(style===1)return cat(i);
  if(style===2)return sakura([pink,'#ffc3cd','#ffd8d2'][i%3]);
  if(style===3)return rainbow();
  if(style===4)return jelly([blue,'#d4b1ff','#ffaed6'][i%3]);
  if(style===6)return goose();
  if(style===7)return `<image href="${pokemonSprites[i%4]}" x="-75" y="-75" width="150" height="150"/>`;
  return paw([pink,cream,'#ffc0a1'][i%3],i%4===2);
 };
 if(style){
  anchors.forEach(([ax,ay],i)=>{
   if((style===3&&i===3)||(style===4&&i===6))return;
   const x=ax+range(-64,64),y=ay+(style===7?range(-12,12):range(-74,55)),scale=range(style===7?.8:.58,1.27)*(style===2?1.25:style===5?.91:1);
   put(primary(i),x,y,scale,tilt(),range(.79,1));
   // Paired paw tracks are staggered, with changing stride and turning angle.
   if(style===5)put(primary(i),x+range(35,88),y+range(-61,48),scale*range(.62,.94),tilt(),range(.72,.97));
   const count=style===1?3:style===2?4:style===3?3:style===4?4:2;
   for(let k=0;k<count;k++){
    let sx=x+range(-152,149),sy=y+range(-102,113);
    // Keep the primary subject area clear, but allow motifs to stray inward
    // near corners instead of forming a straight boundary.
    if(sx>410&&sx<1110&&sy>258&&sy<755)continue;
    if(style===1){const art=k===0?fish(i%2?salmon:gold):flower([cream,gold,'#ffad87','#cce2a0'][(i+k)%4]);put(art,sx,sy,range(.35,.88),tilt());}
    if(style===2)put(k===0?sakura(i%2?pink:'#ffd8d2'):petal(i%2?pink:cream),sx,sy,k===0?range(.32,.65):range(.23,.58),tilt(),range(.65,.98));
    if(style===3)put(k===0?star([gold,pink,blue][i%3]):k===1?heart(i%2?cream:pink):star(cream),sx,sy,range(.32,.84),tilt(),range(.74,1));
    if(style===4){put(`<circle r="${range(3,9)}" fill="none" stroke="${i%2?blue:'#dfbfff'}" stroke-width="1.8"/>`,sx,sy);if(k===0&&i%3===0)put(jelly(pink),sx+24,sy+15,range(.25,.4),tilt());}
    if(style===5)put(k===0?heart(i%2?cream:pink):paw(cream,true),sx,sy,k===0?range(.24,.43):range(.23,.37),tilt(),range(.68,.96));
    if(style===6)put(k===0?flower(gold):heart(cream),sx,sy,range(.28,.58),tilt(),range(.7,.95));
    if(style===7)put(k===0?star(gold):k===1?heart(pink):star(blue),sx,sy,range(.28,.59),tilt(),range(.75,1));
   }
  });
  // A few isolated elements break up the visual rhythm of the clusters.
  const loose=[[595,58],[1191,192],[1416,637],[1077,1002],[403,842],[31,377]];
  loose.forEach(([x,y],i)=>{
   if(rand()<.25)return;
   const art=style===1?(i%2?flower(gold):fish(salmon)):style===2?petal(pink):style===3?star(gold):style===4?star(blue):style===5?paw(pink):style===6?flower(gold):star(cream);
   put(art,x+range(-32,32),y+range(-37,37),range(.25,.57),tilt(),range(.72,.95));
  });
 }
 return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${a}</svg>`;
}
