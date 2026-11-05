import {supportsNativeFilm} from './model-capabilities.mjs';

// Both website surfaces use the API catalog's identities, names and ordering.
export function catalogFilms(films,model,{group='',query=''}={}){
 const search=query.trim().toLowerCase();
 return films.filter(film=>supportsNativeFilm(model,film.id)&&(!group||film.group===group)&&film.name.toLowerCase().includes(search));
}
export const catalogGroups=films=>[...new Set(films.map(film=>film.group))];
