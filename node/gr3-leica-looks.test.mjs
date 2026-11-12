import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {nativeCatalog, prepareNative, readNativeOfficial} from './gr3-native-library.mjs';
import {buildSdFilmPack, auditSdFilmPack, sdCrc, sdFilmRecord} from './gr3-sd-film-pack.mjs';
import {fullLibraryRequest} from '../web/gr3/full-library.mjs';
import {defaultConfiguration, toggleNativeFilm} from '../web/gr3/native-library-state.mjs';

const names = ['Leica Chrome', 'Leica Brass', 'Leica Teal', 'Leica Classic'];
const ids = [331, 332, 333, 334];

test('Leica looks use the same identities in the ISP catalog and SD library', async () => {
  const {films} = await nativeCatalog();
  const looks = films.filter(film => ids.includes(film.id));
  assert.deepEqual(looks.map(film => film.name), names);
  assert.ok(looks.every(film => film.group === '影像' && film.color_path === 'native-isp-only'));
  assert.deepEqual(auditSdFilmPack(buildSdFilmPack(ids)).ids, ids);
  assert.deepEqual(fullLibraryRequest('gr3', films).body.ids.filter(id => ids.includes(id)), ids);
  assert.ok(fullLibraryRequest('gr3x', films).body.ids.every(id => !ids.includes(id)));
});

test('Leica configuration requires native ISP even without live preview', async () => {
  const config = ids.reduce(toggleNativeFilm, {...defaultConfiguration(), slots: []});
  const [gr3, gr3x] = await Promise.all([readNativeOfficial(), readNativeOfficial('gr3x')]);
  const result = prepareNative(gr3, config, {live_color: false});
  assert.equal(result.capture_pipeline, 'gr3-native-v7');
  assert.deepEqual(result.configuration.slots.map(slot => slot.film), ids);
  assert.throws(() => prepareNative(gr3x, config), /莱卡胶卷需要 GR III 2.10 原生 ISP/);
});

test('Leica SD records bind the ISP preview and keep prior built-ins readable', () => {
  const readJson = path => JSON.parse(readFileSync(new URL(path, import.meta.url)));
  const {stocks} = readJson('../web/gr3/leica-luts.json');
  for (const {id, native_values: values} of stocks) {
    const digest = createHash('sha256').update(Buffer.from(values)).digest();
    assert.deepEqual(sdFilmRecord(id).subarray(64, 96), digest);
  }
  const prior = readJson('./gr3-sd-pre-leica-contract.json');
  const pack = buildSdFilmPack([33, 330]);
  for (const [index, id] of [33, 330].entries()) {
    const record = pack.subarray(4096 + index * 12288, 4096 + (index + 1) * 12288);
    Buffer.from(prior.renderer, 'hex').copy(record, 8448);
    const crc = sdCrc(record.subarray(0, -4));
    record.writeUInt32LE(crc, 12284);
    pack.writeUInt32LE(crc, 68 + index * 12);
    assert.equal(createHash('sha256').update(record).digest('hex'), prior.hashes[prior.ids.indexOf(id)]);
  }
  pack.writeUInt32LE(sdCrc(pack.subarray(0, 4092)), 4092);
  assert.deepEqual(auditSdFilmPack(pack).ids, [33, 330]);
});
