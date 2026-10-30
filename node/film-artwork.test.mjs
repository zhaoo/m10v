import test from 'node:test';
import assert from 'node:assert/strict';
import {filmArtwork,pickerArtwork,customFilmArtwork} from '../web/gr3/film-artwork.mjs';
import {nativeCatalog} from './gr3-native-library.mjs';
import {createServer} from './server.mjs';

test('small controls use dedicated compact art while full cards retain packaging details',()=>{
 const film={icon_url:'/gr3/film-icons/33-large.png?v=large',icon_compact_url:'/gr3/film-icons/33.png?v=small'};
 assert.equal(filmArtwork(film),film.icon_url);
 assert.equal(filmArtwork(film,true),film.icon_compact_url);
 assert.equal(filmArtwork({icon_url:film.icon_url},true),film.icon_url);
 assert.equal(filmArtwork(undefined),'');
 assert.equal(pickerArtwork({dataset:{icon:film.icon_url}}),'/gr3/film-icons/33.png?v=large');
 assert.equal(pickerArtwork({dataset:{icon:film.icon_url,iconCompact:film.icon_compact_url}}),film.icon_compact_url);
 assert.equal(pickerArtwork({dataset:{icon:'/unrelated-large.png'}}),'/unrelated-large.png');
});

test('imported LUT artwork shows the actual name and safely encodes SVG text',()=>{
 const uri=customFilmArtwork('Night & <Blue>');
 const svg=decodeURIComponent(uri.split(',')[1]);
 assert.match(uri,/^data:image\/svg\+xml;charset=utf-8,/);
 assert.match(svg,/viewBox="0 0 128 128"/);
 assert.match(svg,/Night &amp;/);
 assert.match(svg,/&lt;Blue&gt;/);
 assert.doesNotMatch(svg,/<Blue>/);
 assert.doesNotMatch(svg,/CUSTOM/);
 assert.equal(customFilmArtwork('Night & <Blue>'),uri);
 assert.notEqual(customFilmArtwork('Daylight'),uri);
});

test('public film catalog exposes both square artwork sizes for every visible identity',async()=>{
 const {films}=await nativeCatalog();
 for(const film of films){
  assert.match(film.icon_url,/\/\d+-large\.png\?/);
  assert.match(film.icon_compact_url,/\/\d+\.png\?/);
 }
});

test('content-versioned artwork is served without weakening other URL guards',async()=>{
 const server=createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const {films}=await nativeCatalog();
  for(const url of [films[0].icon_url,films[0].icon_compact_url]){
   const response=await fetch(base+url);assert.equal(response.status,200);
   assert.equal(response.headers.get('content-type'),'image/png');
   const png=Buffer.from(await response.arrayBuffer());
   assert.equal(png.readUInt32BE(16),png.readUInt32BE(20));
  }
  for(const url of ['/api/status?v=123456789abc','/gr3/film-icons/33.png?v=not-a-hash','/gr3/film-icons/../33.png?v=123456789abc'])assert.equal((await fetch(base+url)).status,404);
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
