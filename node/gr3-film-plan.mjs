import {validateQualityBinding} from './gr3-fit-binding.mjs';
import { readFileSync } from 'node:fs';

const catalog = JSON.parse(readFileSync(new URL('../web/gr3/film-catalog.json', import.meta.url))).looks;
const byId = new Map(catalog.map((film) => [film.id, film]));
const slots = [
  { mode: 'vivid', nameRoom: 12 }, { mode: 'retro', nameRoom: 8 },
  { mode: 'hdr', nameRoom: 14 }, { mode: 'cross', nameRoom: 19 },
  { mode: 'bleach', nameRoom: 20 },
];

function eachOrder(values) {
  if (values.length === 0) return [[]];
  return values.flatMap((value, index) => eachOrder(values.filter((_, at) => at !== index))
    .map((tail) => [value, ...tail]));
}

function comesBefore(left, right) {
  const firstDifference = left.findIndex((value, index) => value !== right[index]);
  return firstDifference >= 0 && left[firstDifference] < right[firstDifference];
}

function fittedFilm(entry) {
  if (!entry || !/^lut-[a-z0-9-]{1,40}$/.test(entry.id) ||
    typeof entry.name !== 'string' || !/^[\x20-\x7e]{1,12}$/.test(entry.name) ||
    entry.name.trim() !== entry.name) throw new Error('invalid custom LUT name or ID');
  for (const [key, unit] of [['matrixQ13', 8192], ['postQ512', 512]]) {
    if (!Array.isArray(entry[key]) || entry[key].length !== 9 ||
      entry[key].some((value) => !Number.isInteger(value) || value < -32768 || value > 32767) ||
      [0, 1, 2].some((row) => entry[key].slice(row * 3, row * 3 + 3)
        .reduce((sum, value) => sum + value, 0) !== unit)) throw new Error(`invalid LUT ${key}`);
  }
  for (const [key, count] of [['curves', 256], ['knots', 33]]) {
    if (!Array.isArray(entry[key]) || entry[key].length !== 3 || entry[key].some((curve) =>
      !Array.isArray(curve) || curve.length !== count || curve.some((value, index) =>
        !Number.isInteger(value) || value < 0 || value > 16383 ||
        (index > 0 && value < curve[index - 1])))) throw new Error(`invalid LUT ${key}`);
  }
  if (entry.iconPixelsBase64 && (!/^[A-Za-z0-9+/]{8534}==$/.test(entry.iconPixelsBase64) ||
    Buffer.from(entry.iconPixelsBase64, 'base64').length !== 6400)) throw new Error('invalid LUT icon');
  validateQualityBinding(entry,entry.quality);
  return { ...entry, assessment:entry.quality?'assessed':'legacy-unassessed', home: null };
}

export function assignFilmSlots(ids, library = []) {
  if (!Array.isArray(ids) || ids.length !== slots.length) throw new Error('select exactly five films');
  if (new Set(ids).size !== ids.length) throw new Error('film choices must be unique');
  if (!Array.isArray(library) || library.length > 8) throw new Error('at most eight custom LUTs');
  const customFilms = library.map(fittedFilm);
  if (new Set(customFilms.map((film) => film.id)).size !== customFilms.length) throw new Error('duplicate LUT ID');
  const choices = new Map([...byId, ...customFilms.map((film) => [film.id, film])]);
  const chosen = ids.map((id) => {
    const film = choices.get(id);
    if (!film) throw new Error(`unknown film: ${id}`);
    return film;
  });
  let best;
  for (const order of eachOrder([0, 1, 2, 3, 4])) {
    if (order.some((index, slot) => chosen[index].name.length > slots[slot].nameRoom)) continue;
    const homeCount = order.filter((index, slot) => chosen[index].home === slots[slot].mode).length;
    const key = [-homeCount, ...order];
    if (!best || comesBefore(key, best.key)) best = { order, key };
  }
  if (!best) throw new Error('Retro slot needs one film name of at most 8 characters');
  return best.order.map((index, slotIndex) => ({ ...chosen[index], ...slots[slotIndex] }));
}

export function createFilmPlan(ids, library = [], texture = {}) {
  const assignment = assignFilmSlots(ids, library);
  if (!texture || typeof texture !== 'object' || Array.isArray(texture) ||
      Object.keys(texture).some((id) => !ids.includes(id))) throw new Error('invalid film texture IDs');
  const resolved = {};
  for (const film of assignment) {
    const entry = texture[film.id];
    if (entry === undefined) continue;
    if (!entry || typeof entry !== 'object' || Array.isArray(entry) ||
        Object.keys(entry).some((key) => !['grain', 'hdf'].includes(key)))
      throw new Error('invalid film texture fields');
    const grain = entry.grain ?? 0, hdf = entry.hdf ?? 0;
    if (![grain, hdf].every((value) => Number.isInteger(value) && value >= 0 && value <= 3))
      throw new Error('invalid film texture intensity');
    if (grain || hdf) resolved[film.mode] = { grain, hdf };
  }
  const custom = assignment.flatMap((film) => {
    const slot = film;
    if (film.home === slot.mode) return [];
    return [{ mode: slot.mode, name: film.name,
      matrixQ13: film.matrixQ13, postQ512: film.postQ512,
      [slot.mode === 'bleach' ? 'knots' : 'curves']:
        film[slot.mode === 'bleach' ? 'knots' : 'curves'],
      iconPixelsBase64: film.iconPixelsBase64 }];
  });
  return { bundle: 'films-v10', ...(custom.length ? { custom } : {}),
    ...(Object.keys(resolved).length ? { texture: resolved } : {}) };
}
