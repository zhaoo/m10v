import {readFileSync} from 'node:fs';
const data=JSON.parse(readFileSync(new URL('../web/gr3/film-directory.json',import.meta.url)));
if(data.schema!=='m10v-film-directory/v1'||data.groups.length!==6)throw Error('胶卷分组目录无效');
export const FILM_GROUPS=Object.freeze(data.groups.map(g=>Object.freeze({...g,films:Object.freeze(g.films.map(Object.freeze))})));
export const FILM_DIRECTORY=Object.freeze(FILM_GROUPS.flatMap(({name:group,films},group_index)=>films.map((f,index)=>Object.freeze({...f,group,group_index,group_number:index+1,number:1+FILM_GROUPS.slice(0,group_index).reduce((sum,g)=>sum+g.films.length,0)+index}))));
if(FILM_DIRECTORY.length!==47||new Set(FILM_DIRECTORY.map(f=>f.id)).size!==47||FILM_DIRECTORY.some(f=>!/^[\x20-\x7e]{1,23}$/.test(f.name)))throw Error('胶卷身份或名称无效');
const byId=new Map(FILM_DIRECTORY.map(f=>[f.id,f]));
export const directoryFilm=id=>byId.get(id);
// Known removed IDs follow the visible directory only for explicit legacy APIs.
// Normal exports pass the thirty visible identities; no identity is rebound.
export function orderedFilmIds(ids){return [...ids].sort((a,b)=>(byId.get(a)?.number??1000+a)-(byId.get(b)?.number??1000+b));}
