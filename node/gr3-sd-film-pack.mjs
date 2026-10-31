import {FILM_DIRECTORY,directoryFilm,orderedFilmIds} from './gr3-film-directory.mjs';
// Original M10V data-only SD format. No third-party runtime or signing service.
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {CUSTOM_ISP_OFFSET,CUSTOM_ISP_BYTES,CUSTOM_ISP_PAYLOAD_BYTES,CUSTOM_ISP_MAGIC,decodeCustomIspPayload} from './gr3-custom-isp.mjs';
export const SD_RECORD_BYTES=12288;
export const SD_HEADER_BYTES=4096;
export const SD_MAX_FILMS=256;
const CUSTOM_FIRST_ID=79;
const read=p=>readFileSync(new URL('../'+p,import.meta.url));
const looks=JSON.parse(read('web/gr3/film-catalog.json')).looks;
const fourLooksStocks=JSON.parse(read('web/gr3/four-looks-luts.json')).stocks;
const fourLooksId=id=>Number.isInteger(id)&&id>=318&&id<=321;
const preFourLooksContract=JSON.parse(read('node/gr3-sd-pre-four-looks-contract.json'));
const preFourLooksHash=id=>preFourLooksContract.hashes[preFourLooksContract.ids.indexOf(id)];
const extraStocks=JSON.parse(read('web/gr3/extra-films-luts.json')).stocks;
const extraId=id=>Number.isInteger(id)&&id>=314&&id<=317;
const c41Stocks=JSON.parse(read('web/gr3/c41-luts.json')).stocks;
const c41Id=id=>Number.isInteger(id)&&id>=312&&id<=313;
const preSquareArtContract=JSON.parse(read('node/gr3-sd-pre-square-art-contract.json'));
const preSquareArtHash=id=>preSquareArtContract.hashes[preSquareArtContract.ids.indexOf(id)];
const preInstaxContract=JSON.parse(read('node/gr3-sd-pre-instax-contract.json'));
const preInstaxHash=id=>preInstaxContract.hashes[preInstaxContract.ids.indexOf(id)];
const preOrientationContract=JSON.parse(read('node/gr3-sd-pre-oriented-stamp-contract.json'));
const preOrientationHash=id=>preOrientationContract.hashes[preOrientationContract.ids.indexOf(id)];
const preRetiredAnimeContract=JSON.parse(read('node/gr3-sd-pre-retired-anime-contract.json'));
const preRetiredAnimeHash=id=>preRetiredAnimeContract.hashes[preRetiredAnimeContract.ids.indexOf(id)];
const preC41Contract=JSON.parse(read('node/gr3-sd-pre-c41-contract.json'));
const preC41Hash=id=>preC41Contract.hashes[preC41Contract.ids.indexOf(id)];
const animeE6Stocks=JSON.parse(read('web/gr3/anime-e6-luts.json')).stocks;
const animeE6Id=id=>Number.isInteger(id)&&id>=306&&id<=311;
const preMonoContract=JSON.parse(read('node/gr3-sd-pre-d76-mono-contract.json'));
const preMonoHash=id=>preMonoContract.hashes[preMonoContract.ids.indexOf(id)];
const preAnimeE6Contract=JSON.parse(read('node/gr3-sd-pre-anime-e6-contract.json'));
const preAnimeE6Hash=id=>preAnimeE6Contract.hashes[preAnimeE6Contract.ids.indexOf(id)];
const d76Stocks=JSON.parse(read('web/gr3/d76-luts.json')).stocks;
const d76Id=id=>Number.isInteger(id)&&id>=299&&id<=305;
const preIspContract=JSON.parse(read('node/gr3-sd-pre-isp-still-contract.json'));
const preIspHash=id=>preIspContract.hashes[preIspContract.ids.indexOf(id)];
const preHaloContract=JSON.parse(read('node/gr3-sd-pre-universal-halation-contract.json'));
const preHaloHash=id=>preHaloContract.hashes[preHaloContract.ids.indexOf(id)];
const preD76Contract=JSON.parse(read('node/gr3-sd-pre-d76-contract.json'));
const preD76Hash=id=>preD76Contract.hashes[preD76Contract.ids.indexOf(id)];
const styleFilters=JSON.parse(read('web/gr3/style-filters-luts.json')).stocks;
const spectralStocks=JSON.parse(read('web/gr3/spectral-luts.json')).stocks;
const preAerocolorContract=JSON.parse(read('node/gr3-sd-pre-aerocolor-contract.json'));
const preAerocolorHash=id=>preAerocolorContract.hashes[preAerocolorContract.ids.indexOf(id)];
const preDirectoryContract=JSON.parse(read('node/gr3-sd-pre-directory-contract.json'));
const preDirectoryHash=id=>preDirectoryContract.hashes[preDirectoryContract.ids.indexOf(id)];
const styleId=id=>Number.isInteger(id)&&id>=291&&id<=297;
const icons=read('native/gr3/m10v_icons.rgba');
const source=read('native/gr3/m10v_library.c').toString();
// Fingerprint the complete renderer and recursively included local data/headers.
// Length framing and paths make the binding independent of concatenation ambiguity.
const rendererFiles=new Map();
function collectRenderer(path){
 if(rendererFiles.has(path))return;
 const bytes=read(path);rendererFiles.set(path,bytes);
 for(const match of bytes.toString().matchAll(/^#include "([^"\n]+)"/gm))collectRenderer(path.slice(0,path.lastIndexOf('/')+1)+match[1]);
}
for(const path of ['native/gr3/m10v_library.c','native/gr3/film_5207.c','native/gr3/film_harman.c','native/gr3/film_curated.c','native/gr3/film_newstocks.c','native/gr3/film_style_filters_0.c','native/gr3/film_style_filters_1.c','native/gr3/film_d76_0.c','native/gr3/film_d76_1.c','native/gr3/m10v_spatial_accel.c','native/gr3/m10v_texture_accel.c','native/gr3/m10v_isp_native_look.c'])collectRenderer(path);
const rendererHash=createHash('sha256');
for(const [path,bytes] of [...rendererFiles].sort(([a],[b])=>a.localeCompare(b))){rendererHash.update(path+'\0'+bytes.length+'\0').update(bytes);}
const rendererContract=rendererHash.digest();
// Freeze the final v1 record digests. The film-name renderer changes its source
// fingerprint, but the original built-in recipes remain supported on the card.
const preMultiselectContract=JSON.parse(read('node/gr3-sd-pre-multiselect-contract.json'));
const preMultiselectHash=id=>preMultiselectContract.hashes[preMultiselectContract.ids.indexOf(id)];
const texturePriorContract=JSON.parse(read('node/gr3-sd-texture-prior-contract.json'));
const texturePriorHash=id=>texturePriorContract.hashes[texturePriorContract.ids.indexOf(id)];
const priorContract=JSON.parse(read('node/gr3-sd-prior-contract.json'));
const previousContract=JSON.parse(read('node/gr3-sd-20261021-contract.json'));
const preStylesContract=JSON.parse(read('node/gr3-sd-pre-styles-contract.json'));
const preStylesHash=id=>preStylesContract.hashes[preStylesContract.ids.indexOf(id)];
const recentContract=JSON.parse(read('node/gr3-sd-20261023-contract.json'));
const recentHash=id=>recentContract.hashes[recentContract.ids.indexOf(id)];
const previousHash=id=>previousContract.hashes[previousContract.ids.indexOf(id)];
const legacyHashes=JSON.parse(read('node/gr3-sd-v1-legacy-hashes.json'));
needLegacyHashes();
function needLegacyHashes(){if(legacyHashes.length!==40||legacyHashes.some(h=>!/^[a-f0-9]{64}$/.test(h)))throw Error('旧版 SD 配方摘要无效');}
const SD_RECIPE_IDS=Object.freeze([...Array.from({length:46},(_,i)=>33+i),289,290,...styleFilters.map(s=>s.id),298,...d76Stocks.map(s=>s.id),...animeE6Stocks.map(s=>s.id),...c41Stocks.map(s=>s.id),...extraStocks.map(s=>s.id),...fourLooksStocks.map(s=>s.id)]);
export const SD_FILM_IDS=Object.freeze(FILM_DIRECTORY.map(f=>f.id));
const appendedNames=['5207','Phoenix II','HARMAN RED','Portra 160','Fuji Industrial 100','Lucky C200','CCD Classic','Fuji C200','ProImage 100','T-Max 100','Aerochrome','2460','5203'];
const engineRecipeContracts=[
 createHash('sha256').update(read('native/gr3/film_5207_data.h')).digest(),
 ...[0,1].map(variant=>createHash('sha256').update(read('native/gr3/film_harman_data.h')).update(Buffer.from([variant])).digest()),
 ...[0,1,2,3].map(variant=>createHash('sha256').update(read('native/gr3/film_curated_data.h')).update(Buffer.from([variant])).digest()),
 ...[0,1,2,3,4,5].map(variant=>createHash('sha256').update(read('native/gr3/film_newstocks_data.h')).update(Buffer.from([variant])).digest())
];
const originals=[...source.matchAll(/\{"([^"\n]+)",(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+)\}/g)];
const need=(ok,message)=>{if(!ok)throw Error(message);};
export function sdCrc(bytes){let c=0xffffffff;for(const v of bytes){c^=v;for(let i=0;i<8;i++)c=(c>>>1)^(0xedb88320&-(c&1));}return ~c>>>0;}
const digest=b=>createHash('sha256').update(b).digest('hex');
export function sdFilmRecord(id){
 need(Number.isInteger(id)&&id>=33&&(id<=78||id===289||id===290||id===298||d76Id(id)||styleId(id)||animeE6Id(id)||c41Id(id)||extraId(id)||fourLooksId(id)),'胶卷不在当前平台目录中');
 need(originals.length===33&&looks.length===32&&icons.length===78*6400,'胶卷源目录不一致');
 const b=Buffer.alloc(SD_RECORD_BYTES),look=id>=34&&id<=65?looks[id-34]:null;
 b.write('M10VREC1');b.writeUInt32LE(id,8);b.writeUInt32LE(id===33?1:id<=65?2:3,12);
 const name=directoryFilm(id)?.name??(animeE6Id(id)?animeE6Stocks[id-306].name:id===290?'Pixel World':styleId(id)?styleFilters[id-291].ascii_name:id===289?'Kodak Charmera':id>=66?appendedNames[id-66]:look?.name||originals[32][1]);need(Buffer.byteLength(name,'ascii')<24&&/^[\x20-\x7e]+$/.test(name),'胶卷名称不支持');
 b.write(name,16,'ascii');b.write('M10V',40,'ascii');
 if(id===33)originals[32].slice(2).map(Number).forEach((v,i)=>b.writeInt16LE(v,64+i*2));
 else if(look){
  [...look.matrixQ13,...look.postQ512].forEach((v,i)=>b.writeInt16LE(v,80+i*2));
  look.curves.flat().forEach((v,i)=>b.writeUInt16LE(v,116+i*2));
  look.knots.flat().forEach((v,i)=>b.writeUInt16LE(v,1652+i*2));
 }
 // Kind 3 is an identity snapshot of an engine builtin LUT, not a portable LUT.
 // Bytes 64..95 bind the complete source LUT data (all RED exposure variants),
 // while the renderer digest also locks interpolation, texture and defaults.
 if(fourLooksId(id)){createHash('sha256').update(Buffer.from(fourLooksStocks[id-318].native_values)).digest().copy(b,64);}
 else if(extraId(id)){createHash('sha256').update(Buffer.from(extraStocks[id-314].native_values)).digest().copy(b,64);}
 else if(c41Id(id)){createHash('sha256').update(Buffer.from(c41Stocks[id-312].native_values)).digest().copy(b,64);}
 else if(animeE6Id(id)){createHash('sha256').update(Buffer.from(animeE6Stocks[id-306].native_values)).digest().copy(b,64);}
 else if(d76Id(id)){createHash('sha256').update(Buffer.from(d76Stocks[id-299].values)).digest().copy(b,64);}
 else if(styleId(id)){const stock=styleFilters[id-291];createHash('sha256').update(Buffer.from(stock.values)).digest().copy(b,64);}
 else if(id===298)createHash('sha256').update(Buffer.from(spectralStocks.find(s=>s.id===298).values)).digest().copy(b,64);
 else if(id===290)createHash('sha256').update(read('native/gr3/m10v_pixel_world.h')).digest().copy(b,64);
 else if(id===289)createHash('sha256').update(read('native/gr3/m10v_charmera.h')).digest().copy(b,64);
 else if(id>=66)engineRecipeContracts[id-66].copy(b,64);
 if(fourLooksId(id))read('native/gr3/m10v_four_looks.rgba').copy(b,2048,(id-318)*6400,(id-317)*6400);else if(extraId(id))read('native/gr3/m10v_extra_films.rgba').copy(b,2048,(id-314)*6400,(id-313)*6400);else if(c41Id(id))read('native/gr3/m10v_c41.rgba').copy(b,2048,(id-312)*6400,(id-311)*6400);else if(animeE6Id(id))read('native/gr3/m10v_anime_e6.rgba').copy(b,2048,(id-306)*6400,(id-305)*6400);else if(d76Id(id))read('native/gr3/m10v_d76.rgba').copy(b,2048,(id-299)*6400,(id-298)*6400);else if(styleId(id))read('native/gr3/m10v_style_filters.rgba').copy(b,2048,(id-291)*6400,(id-290)*6400);else if(id===298)read('native/gr3/m10v_5213.rgba').copy(b,2048);else if(id===290)read('native/gr3/m10v_pixel_world.rgba').copy(b,2048);else if(id===289)read('native/gr3/m10v_charmera.rgba').copy(b,2048);else icons.copy(b,2048,(id-1)*6400,id*6400);
 // Bind the color/energy renderer as well as its parameters: old engines must
 // reject new records even when a particular numeric recipe is unchanged.
 rendererContract.copy(b,8448);
 b.writeUInt32LE(sdCrc(b.subarray(0,-4)),SD_RECORD_BYTES-4);return b;
}
export function customFilmRecord(film,id){
 need(film&&typeof film.name==='string'&&/^[\x20-\x7e]{1,23}$/.test(film.name)&&Buffer.isBuffer(film.rgb)&&film.rgb.length===6591,'自定义 LUT 数据无效');
 need(Number.isInteger(id)&&id>=CUSTOM_FIRST_ID&&id<=288,'自定义 LUT ID 无效');
 const b=Buffer.alloc(SD_RECORD_BYTES);b.write('M10VREC2');b.writeUInt32LE(id,8);b.writeUInt32LE(4,12);
 b.write(film.name,16,'ascii');b.write('M10V',40,'ascii');film.rgb.copy(b,64);
 createHash('sha256').update(film.name+'\0').update(film.rgb).digest().copy(b,6656);
 if(film.ispProfile!==undefined){
  decodeCustomIspPayload(film.ispProfile);
  b.writeUInt32LE(CUSTOM_ISP_MAGIC,CUSTOM_ISP_OFFSET);b.writeUInt32LE(1,CUSTOM_ISP_OFFSET+4);
  b.writeUInt32LE(CUSTOM_ISP_PAYLOAD_BYTES,CUSTOM_ISP_OFFSET+8);b.writeUInt32LE(sdCrc(film.ispProfile),CUSTOM_ISP_OFFSET+12);
  film.ispProfile.copy(b,CUSTOM_ISP_OFFSET+16);
 }
 rendererContract.copy(b,8448);b.writeUInt32LE(sdCrc(b.subarray(0,-4)),SD_RECORD_BYTES-4);return b;
}
export function sdExpectedHeader(){
 const table=hashes=>hashes.map(h=>'{'+[...Buffer.from(h,'hex')].join(',')+'}').join(',\n');
 return 'static const unsigned char m10v_sd_pre_four_looks_renderer[32]={'+[...Buffer.from(preFourLooksContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_four_looks_hashes[75][32]={\n'+table(preFourLooksContract.hashes)+'\n};\n'+'static const unsigned char m10v_sd_pre_square_art_hashes[75][32]={\n'+table(preSquareArtContract.hashes)+'\n};\n'+'static const unsigned char m10v_sd_pre_instax_renderer[32]={'+[...Buffer.from(preInstaxContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_instax_hashes[74][32]={\n'+table(preInstaxContract.hashes)+'\n};\n'+'static const unsigned char m10v_sd_pre_orientation_renderer[32]={'+[...Buffer.from(preOrientationContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_orientation_hashes[74][32]={\n'+table(preOrientationContract.hashes)+'\n};\n'+'static const unsigned char m10v_sd_pre_retired_anime_renderer[32]={'+[...Buffer.from(preRetiredAnimeContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_retired_anime_hashes[71][32]={\n'+table(preRetiredAnimeContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_pre_c41_renderer[32]={'+[...Buffer.from(preC41Contract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_c41_hashes[69][32]={\n'+table(preC41Contract.hashes)+'\n};\nstatic const unsigned char m10v_sd_pre_mono_renderer[32]={'+[...Buffer.from(preMonoContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_mono_hashes[69][32]={\n'+table(preMonoContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_pre_anime_e6_renderer[32]={'+[...Buffer.from(preAnimeE6Contract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_anime_e6_hashes[63][32]={\n'+table(preAnimeE6Contract.hashes)+'\n};\nstatic const unsigned char m10v_sd_pre_isp_renderer[32]={'+[...Buffer.from(preIspContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_isp_hashes[63][32]={\n'+table(preIspContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_pre_halo_renderer[32]={'+[...Buffer.from(preHaloContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_halo_hashes[63][32]={\n'+table(preHaloContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_pre_d76_renderer[32]={'+[...Buffer.from(preD76Contract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_d76_hashes[56][32]={\n'+table(preD76Contract.hashes)+'\n};\n/* Generated by scripts/generate_gr3_sd_contract.mjs; complete recipe SHA-256. */\nstatic const unsigned char m10v_sd_pre_aerocolor_renderer[32]={'+[...Buffer.from(preAerocolorContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_aerocolor_hashes[56][32]={\n'+table(preAerocolorContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_pre_directory_renderer[32]={'+[...Buffer.from(preDirectoryContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_directory_hashes[55][32]={\n'+table(preDirectoryContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_hashes[79][32]={\n'+table(SD_RECIPE_IDS.map(id=>digest(sdFilmRecord(id))))+'\n};\nstatic const unsigned char m10v_sd_pre_multiselect_hashes[55][32]={\n'+table(preMultiselectContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_pre_multiselect_renderer[32]={'+[...Buffer.from(preMultiselectContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_texture_prior_hashes[55][32]={\n'+table(texturePriorContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_texture_prior_renderer[32]={'+[...Buffer.from(texturePriorContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_pre_styles_hashes[48][32]={\n'+table(preStylesContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_pre_styles_renderer[32]={'+[...Buffer.from(preStylesContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_recent_hashes[47][32]={\n'+table(recentContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_recent_renderer[32]={'+[...Buffer.from(recentContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_prior_hashes[46][32]={\n'+table(priorContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_previous_hashes[47][32]={\n'+table(previousContract.hashes)+'\n};\nstatic const unsigned char m10v_sd_previous_renderer[32]={'+[...Buffer.from(previousContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_prior_renderer[32]={'+[...Buffer.from(priorContract.renderer,'hex')].join(',')+'};\nstatic const unsigned char m10v_sd_legacy_hashes[40][32]={\n'+table(legacyHashes)+'\n};\nstatic const unsigned char m10v_sd_renderer_hash[32]={'+[...rendererContract].join(',')+'};\n';
}
export function buildSdFilmPack(ids=[...SD_FILM_IDS],customFilms=[]){
 need(Array.isArray(customFilms)&&Array.isArray(ids)&&ids.length+customFilms.length>0&&ids.length+customFilms.length<=SD_MAX_FILMS,'请选择至少一款胶卷');
 need(new Set(ids).size===ids.length,'胶卷不能重复');
 need(Array.from(ids).every(id=>Number.isInteger(id)&&directoryFilm(id)),'胶卷不在当前平台目录中');
 need(new Set(customFilms.map(f=>f.name.toLowerCase())).size===customFilms.length,'自定义胶卷名称不能重复');
 need(new Set(customFilms.map(f=>f.sha256)).size===customFilms.length,'自定义 LUT 不能重复');
 // Display order is the user-defined directory; stable identities never sort it.
 ids=orderedFilmIds(ids);
 const custom=[...customFilms].sort((a,b)=>a.sha256.localeCompare(b.sha256));
 const customIds=custom.map((_,i)=>CUSTOM_FIRST_ID+i),allIds=[...ids,...customIds];
 const records=[...ids.map(sdFilmRecord),...custom.map((f,i)=>customFilmRecord(f,customIds[i]))],h=Buffer.alloc(SD_HEADER_BYTES);
 h.write(custom.length?'M10VSD2\0':'M10VSD1\0');h.writeUInt32LE(custom.length?2:1,8);h.writeUInt32LE(4096+records.length*SD_RECORD_BYTES,12);
 h.writeUInt32LE(records.length,16);h.writeUInt32LE(SD_RECORD_BYTES,20);h.writeUInt32LE(239,24);h.writeUInt32LE(1,28);
 records.forEach((b,i)=>{h.writeUInt32LE(allIds[i],64+12*i);h.writeUInt32LE(b.readUInt32LE(b.length-4),68+12*i);h.writeUInt32LE(1,72+12*i);});
 h.writeUInt32LE(sdCrc(h.subarray(0,-4)),4092);return Buffer.concat([h,...records]);
}
export function auditSdFilmPack(bytes){
 need(Buffer.isBuffer(bytes)&&bytes.length>=4096,'胶卷包被截断');
 const version=bytes.readUInt32LE(8);
 need(bytes.subarray(0,8).equals(Buffer.from(version===2?'M10VSD2\0':'M10VSD1\0'))&&[1,2].includes(version)&&bytes.readUInt32LE(24)===239&&bytes.readUInt32LE(28)===1,'胶卷包机型或版本不兼容');
 const count=bytes.readUInt32LE(16);need(count>0&&count<=SD_MAX_FILMS&&bytes.readUInt32LE(20)===SD_RECORD_BYTES,'胶卷数量或长度无效');
 need(bytes.length===4096+count*SD_RECORD_BYTES&&bytes.readUInt32LE(12)===bytes.length,'胶卷包长度不一致');
 const ids=Array.from({length:count},(_,i)=>bytes.readUInt32LE(64+i*12));
 // Reconstruct the canonical header from the indexed record CRCs. This rejects
 // changed reserved fields, duplicate identities and reordered built-ins.
 if(version===1){
  need(ids.every(id=>id>=33&&(id<=78||id===289||id===290||id===298||d76Id(id)||styleId(id)||animeE6Id(id)||c41Id(id)||extraId(id)||fourLooksId(id)))&&new Set(ids).size===ids.length,'胶卷 ID 无效或重复');
  const canonical=Buffer.alloc(4096);canonical.write('M10VSD1\0');canonical.writeUInt32LE(1,8);canonical.writeUInt32LE(bytes.length,12);canonical.writeUInt32LE(count,16);canonical.writeUInt32LE(SD_RECORD_BYTES,20);canonical.writeUInt32LE(239,24);canonical.writeUInt32LE(1,28);
  ids.forEach((id,i)=>{canonical.writeUInt32LE(id,64+i*12);canonical.writeUInt32LE(1,72+i*12);});
  ids.forEach((_,i)=>canonical.writeUInt32LE(bytes.readUInt32LE(68+i*12),68+i*12));
  canonical.writeUInt32LE(sdCrc(canonical.subarray(0,4092)),4092);
  need(bytes.subarray(0,4096).equals(canonical),'胶卷包头校验失败');
  ids.forEach((id,i)=>{
   const record=bytes.subarray(4096+i*SD_RECORD_BYTES,4096+(i+1)*SD_RECORD_BYTES);
   need(record.readUInt32LE(SD_RECORD_BYTES-4)===bytes.readUInt32LE(68+i*12)&&sdCrc(record.subarray(0,-4))===record.readUInt32LE(SD_RECORD_BYTES-4),'记录校验不一致');
   need([digest(sdFilmRecord(id)),preFourLooksHash(id),preSquareArtHash(id),preInstaxHash(id),preOrientationHash(id),preRetiredAnimeHash(id),preC41Hash(id),preMonoHash(id),preAnimeE6Hash(id),preIspHash(id),preHaloHash(id),preD76Hash(id),preAerocolorHash(id),preDirectoryHash(id),legacyHashes[id-33],priorContract.hashes[id-33],previousHash(id),recentHash(id),preStylesHash(id),texturePriorHash(id),preMultiselectHash(id)].includes(digest(record)),'胶卷包校验失败或配方版本不兼容');
  });
 } else {
  need(sdCrc(bytes.subarray(0,4092))===bytes.readUInt32LE(4092),'胶卷包头校验失败');
  need(new Set(ids).size===ids.length,'胶卷 ID 重复');
  const names=new Set(),hashes=new Set();
  ids.forEach((id,i)=>{
   const record=bytes.subarray(4096+i*SD_RECORD_BYTES,4096+(i+1)*SD_RECORD_BYTES);
   need(record.readUInt32LE(SD_RECORD_BYTES-4)===bytes.readUInt32LE(68+i*12),'记录校验不一致');
   if(id<=78||id===289||id===290||id===298||d76Id(id)||styleId(id)||animeE6Id(id)||c41Id(id)||extraId(id)||fourLooksId(id))need(record.equals(sdFilmRecord(id))||[preFourLooksHash(id),preSquareArtHash(id),preInstaxHash(id),preOrientationHash(id),preRetiredAnimeHash(id),preC41Hash(id),preMonoHash(id),preAnimeE6Hash(id),preIspHash(id),preHaloHash(id),preD76Hash(id),preAerocolorHash(id),preDirectoryHash(id),priorContract.hashes[id-33],previousHash(id),recentHash(id),preStylesHash(id),texturePriorHash(id),preMultiselectHash(id)].includes(digest(record)),'胶卷包校验失败或配方版本不兼容');
   else {
    need(id>=79&&id<=288&&record.subarray(0,8).equals(Buffer.from('M10VREC2'))&&record.readUInt32LE(8)===id&&record.readUInt32LE(12)===4,'自定义胶卷记录无效');
    const name=record.subarray(16,40).toString('ascii').split('\0')[0],rgb=record.subarray(64,6655);
    need(/^[\x20-\x7e]{1,23}$/.test(name)&&!names.has(name.toLowerCase()),'自定义胶卷名称无效或重复');names.add(name.toLowerCase());
    const hash=createHash('sha256').update(name+'\0').update(rgb).digest('hex');
    need(record.subarray(6656,6688).toString('hex')===hash&&!hashes.has(hash),'自定义 LUT 摘要无效或重复');hashes.add(hash);
    need((record.subarray(8448,8480).equals(rendererContract)||[preFourLooksContract.renderer,preInstaxContract.renderer,preRetiredAnimeContract.renderer,preC41Contract.renderer,preMonoContract.renderer,preAnimeE6Contract.renderer,preIspContract.renderer,preHaloContract.renderer,preD76Contract.renderer,preAerocolorContract.renderer,preDirectoryContract.renderer,priorContract.renderer,previousContract.renderer,recentContract.renderer,preStylesContract.renderer,texturePriorContract.renderer,preMultiselectContract.renderer].includes(record.subarray(8448,8480).toString('hex')))&&sdCrc(record.subarray(0,-4))===record.readUInt32LE(SD_RECORD_BYTES-4),'自定义 LUT 配方版本不兼容');
    const extension=record.subarray(CUSTOM_ISP_OFFSET,CUSTOM_ISP_OFFSET+CUSTOM_ISP_BYTES);let ispProfile;
    if(extension.some(v=>v!==0)){
     need(extension.readUInt32LE(0)===CUSTOM_ISP_MAGIC&&extension.readUInt32LE(4)===1&&extension.readUInt32LE(8)===CUSTOM_ISP_PAYLOAD_BYTES,'自定义 ISP 版本无效');
     ispProfile=extension.subarray(16,16+CUSTOM_ISP_PAYLOAD_BYTES);
     need(sdCrc(ispProfile)===extension.readUInt32LE(12),'自定义 ISP 校验失败');decodeCustomIspPayload(ispProfile);
    }
    const canonical=customFilmRecord({name,rgb,...(ispProfile?{ispProfile}:{})},id);record.copy(canonical,8448,8448,8480);canonical.writeUInt32LE(sdCrc(canonical.subarray(0,-4)),SD_RECORD_BYTES-4);
    need(record.equals(canonical),'自定义 LUT 保留字段无效');
   }
  });
 }
 return {schema:'m10v-sd-film-pack/v1',model:'gr3',count,ids,bytes:bytes.length,sha256:digest(bytes),path:'M10V/FILMS.M10',camera_tested:false,renderer_sha256:rendererContract.toString('hex')};
}
