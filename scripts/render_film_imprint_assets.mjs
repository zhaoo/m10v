// Development-only regeneration. The firmware builder consumes the checked
// PNGs and never needs a browser, resvg, network, SVG parser or rasterizer.
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {filmImprintSvg} from '../web/shared/film-imprints.mjs';
const {Resvg}=await import(process.env.M10V_RESVG_MODULE||'@resvg/resvg-js');
const output=new URL('../native/gr3/film-imprints/',import.meta.url);await mkdir(output,{recursive:true});
const hashes={};
const pokemonSprites=await Promise.all(['025','001','004','007'].map(async id=>'data:image/png;base64,'+(await readFile(new URL(`pokemon/${id}.png`,output))).toString('base64')));
for(let style=1;style<=7;style++){
 const svg=filmImprintSvg(style,{pokemonSprites});
 const bytes=new Resvg(svg,{fitTo:{mode:'width',value:768}}).render().asPng();
 await writeFile(new URL(`${style}.png`,output),bytes);
 if(style===7&&process.env.M10V_IMPRINT_PREVIEW)await writeFile(process.env.M10V_IMPRINT_PREVIEW,new Resvg(svg).render().asPng());
 hashes[style]=createHash('sha256').update(bytes).digest('hex');
}
console.log(JSON.stringify(hashes,null,2));
