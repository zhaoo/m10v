import {previewPixelWorld} from './pixel-world.mjs';
// Browser approximation from the film tables read from the supplied firmware.
const clamp = (value) => Math.min(255, Math.max(0, Math.round(value)));

function tone(table, value) {
  const index = Math.min(255, Math.max(0, value));
  if (table.length === 256) {
    const left = Math.floor(index);
    return (table[left] + (table[Math.min(255, left + 1)] - table[left]) * (index - left)) * 255 / 16383;
  }
  const position = index * 32 / 255;
  const left = Math.floor(position);
  return (table[left] + (table[Math.min(32, left + 1)] - table[left]) *
    (position - left)) * 255 / 16383;
}

export function previewFilmPixels(source, look) {
  const output = new Uint8ClampedArray(source.length);
  const tables = look.curves || look.knots;
  const first = tables[0], second = tables[1], third = tables[2];
  const m = look.matrixQ13, p = look.postQ512;
  for (let index = 0; index < source.length; index += 4) {
    const r = source[index], g = source[index + 1], b = source[index + 2];
    const cr = tone(first, (r * m[0] + g * m[1] + b * m[2]) / 8192);
    const cg = tone(second, (r * m[3] + g * m[4] + b * m[5]) / 8192);
    const cb = tone(third, (r * m[6] + g * m[7] + b * m[8]) / 8192);
    output[index] = clamp((cr * p[0] + cg * p[1] + cb * p[2]) / 512);
    output[index + 1] = clamp((cr * p[3] + cg * p[4] + cb * p[5]) / 512);
    output[index + 2] = clamp((cr * p[6] + cg * p[7] + cb * p[8]) / 512);
    output[index + 3] = source[index + 3];
  }
  return output;
}

// RGB colour approximation only: these tables do not simulate spatial halation,
// grain or diffusion, and do not establish a camera/film calibration.
export function previewHarmanPixels(source, lut, film, filmExposure=0) {
  if(![67,68].includes(film)||!Number.isInteger(filmExposure)||filmExposure<0||filmExposure>2||(film===67&&filmExposure>1))throw new RangeError('Harman 胶卷或模拟曝光EI无效');
  const size=lut.size,table=lut.stocks[film===67?(filmExposure===1?4:0):filmExposure+1]?.values;
  return previewRgbLutPixels(source,lut,table);
}
export function previewCuratedPixels(source,lut,film){
  if(!Number.isInteger(film)||film<69||film>72)throw new RangeError('精选胶卷无效');
  return previewRgbLutPixels(source,lut,lut.stocks[film-69]?.values);
}
export function previewNewStocksPixels(source,lut,film){
  if(!Number.isInteger(film)||!((film>=73&&film<=78)||film===298))throw new RangeError('新增胶卷无效');
  return previewRgbLutPixels(source,lut,lut.stocks.find(s=>s.id===film)?.values);
}
export function previewStyleFiltersPixels(source,lut,film){
  if(!Number.isInteger(film)||film<291||film>297)throw new RangeError('精选滤镜无效');
  return previewRgbLutPixels(source,lut,lut.stocks.find(s=>s.id===film)?.values);
}
export function previewD76Pixels(source,lut,film){
  if(!Number.isInteger(film)||film<299||film>305)throw new RangeError('D76 film identity invalid');
  return previewRgbLutPixels(source,lut,lut.stocks.find(s=>s.id===film)?.values);
}
function previewRgbLutPixels(source,lut,table){
  const size=lut.size;
  if(size!==15||lut.bits!==8||table?.length!==size**3*3)throw new RangeError('Harman 预览色表无效');
  const output=new Uint8ClampedArray(source.length),stride=[size*size*3,size*3,3];
  for(let i=0;i<source.length;i+=4){
    const positions=[source[i],source[i+1],source[i+2]].map(v=>v*(size-1)/255);
    const base=positions.map(v=>Math.min(size-2,Math.floor(v))),fraction=positions.map((v,c)=>v-base[c]);
    const axes=[0,1,2].sort((a,b)=>fraction[b]-fraction[a]);
    const weights=[1-fraction[axes[0]],fraction[axes[0]]-fraction[axes[1]],fraction[axes[1]]-fraction[axes[2]],fraction[axes[2]]];
    const first=base.reduce((sum,v,c)=>sum+v*stride[c],0),corners=[first];
    for(const axis of axes)corners.push(corners.at(-1)+stride[axis]);
    for(let c=0;c<3;c++)output[i+c]=clamp(corners.reduce((sum,p,j)=>sum+table[p+c]*weights[j],0));
    output[i+3]=source[i+3];
  }
  return output;
}
let animeE6TablesPromise,c41TablesPromise,extraFilmsTablesPromise;
let harmanTablesPromise,curatedTablesPromise,newstocksTablesPromise,styleFiltersTablesPromise,spectralTablesPromise,d76TablesPromise;
export async function renderPreviewPixels(source, look, width, height) {
  const film=look.film??look.id;
  if(Number.isInteger(film)&&film>=314&&film<=316){
    extraFilmsTablesPromise??=fetch(new URL('./extra-films-luts.json',import.meta.url)).then(r=>{if(!r.ok)throw Error('Film LUT unavailable');return r.json();}).catch(e=>{extraFilmsTablesPromise=undefined;throw e;});
    const lut=await extraFilmsTablesPromise;return previewRgbLutPixels(source,lut,lut.stocks.find(s=>s.id===film)?.native_values);
  }
  if(Number.isInteger(film)&&film>=312&&film<=313){
    c41TablesPromise??=fetch(new URL('./c41-luts.json',import.meta.url)).then(r=>{if(!r.ok)throw Error('C41 LUT unavailable');return r.json();}).catch(e=>{c41TablesPromise=undefined;throw e;});
    const lut=await c41TablesPromise;return previewRgbLutPixels(source,lut,lut.stocks.find(s=>s.id===film)?.native_values);
  }
  if(Number.isInteger(film)&&film>=309&&film<=311){
    animeE6TablesPromise??=fetch(new URL('./anime-e6-luts.json',import.meta.url)).then(r=>{if(!r.ok)throw Error('滤镜色表载入失败');return r.json();}).catch(e=>{animeE6TablesPromise=undefined;throw e;});
    const lut=await animeE6TablesPromise;return previewRgbLutPixels(source,lut,lut.stocks.find(s=>s.id===film)?.native_values);
  }
  if(Number.isInteger(film)&&film>=299&&film<=305){
    d76TablesPromise??=fetch(new URL('./d76-luts.json',import.meta.url)).then(r=>{if(!r.ok)throw Error('D76 LUT unavailable');return r.json();}).catch(e=>{d76TablesPromise=undefined;throw e;});
    return previewD76Pixels(source,await d76TablesPromise,film);
  }
  if(film===298){
    spectralTablesPromise??=fetch(new URL('./spectral-luts.json',import.meta.url)).then(r=>{if(!r.ok)throw Error('胶卷预览色表载入失败');return r.json();}).catch(e=>{spectralTablesPromise=undefined;throw e;});
    return previewNewStocksPixels(source,await spectralTablesPromise,film);
  }
  if(Number.isInteger(film)&&film>=291&&film<=297){
    styleFiltersTablesPromise??=fetch(new URL('./style-filters-luts.json',import.meta.url)).then(r=>{if(!r.ok)throw new Error('精选滤镜预览色表载入失败');return r.json();}).catch(e=>{styleFiltersTablesPromise=undefined;throw e;});
    return previewStyleFiltersPixels(source,await styleFiltersTablesPromise,film);
  }
  if(film===290)return previewPixelWorld(source,width,height);
  if(film===289){
    const color=look.effects?.charmeraColor??0,palette=[[253,1,0],[249,211,78],[1,0,249],[224,224,224]];
    if(!Number.isInteger(color)||color<0||color>3)throw new RangeError('Charmera 颜色无效');
    const out=new Uint8ClampedArray(source.length);
    for(let i=0;i<source.length;i+=4){const on=((77*source[i]+150*source[i+1]+29*source[i+2]+128)>>8)>=128;
      for(let c=0;c<3;c++)out[i+c]=on?palette[color][c]:0;out[i+3]=source[i+3];}
    return out;
  }
  if(Number.isInteger(film)&&film>=73&&film<=78){
    newstocksTablesPromise??=fetch(new URL('./newstocks-luts.json',import.meta.url)).then(r=>{if(!r.ok)throw new Error('新增胶卷预览色表载入失败');return r.json();}).catch(error=>{newstocksTablesPromise=undefined;throw error;});
    return previewNewStocksPixels(source,await newstocksTablesPromise,film);
  }
  if([69,70,71,72].includes(film)){
    curatedTablesPromise??=fetch(new URL('./curated-luts.json',import.meta.url)).then(r=>{
      if(!r.ok)throw new Error('精选胶卷预览色表载入失败');return r.json();
    }).catch(error=>{curatedTablesPromise=undefined;throw error;});
    return previewCuratedPixels(source,await curatedTablesPromise,film);
  }
  if(![67,68].includes(film))return previewFilmPixels(source,look);
  harmanTablesPromise??=fetch(new URL('./harman-luts.json',import.meta.url)).then(r=>{
    if(!r.ok)throw new Error('Harman 预览色表载入失败');return r.json();
  }).catch(error=>{harmanTablesPromise=undefined;throw error;});
  return previewHarmanPixels(source,await harmanTablesPromise,film,look.effects?.filmExposure??0);
}
