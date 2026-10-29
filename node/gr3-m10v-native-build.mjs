import {FILM_DIRECTORY} from './gr3-film-directory.mjs';
import {MAX_NATIVE_RTOS_GROWTH} from './gr3-native-budget.mjs';
// M10V's original runtime is injected into the exact official GR III source.
// No browser compatibility runtime, signed film file or external catalog is used.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { inspectOfficial } from './firmware.mjs';
import { decodeFrameMap, sum32 } from './gr3-frames.mjs';
import {settingsSources,settingsPatches,checkSettings,abPatches} from './gr3-settings-menu.mjs';
import {zoomPatches} from './gr3-zoom.mjs';
import {hdfSources,hdfPatches,hdfMenuPatches} from './gr3-digital-hdf.mjs';
import {hdfAdjPatches} from './gr3-hdf-adj.mjs';
import { auditGr3Candidate } from './gr3-candidate-audit.mjs';

const LOAD = 0x53000000;
const nativeBases = [0x540b6000, 0x540ba000, 0x540be000];
const sha = value => createHash('sha256').update(value).digest('hex');
const need = (condition, message) => { if (!condition) throw new Error(message); };
const hooks = [
  // Private enumeration belongs exclusively to ImageControlController.
  // Global model functions remain stock for ADJ, detail and generic consumers.
  [0x531ab78c,0xeb045cc2,'m10v_menu_count',true],
  [0x531ab7cc,0xeb045d2b,'m10v_menu_index',true],
  [0x531ab814,0xeb045ca0,'m10v_menu_count',true],
  [0x531ab834,0xeb045d11,'m10v_menu_index',true],
  [0x531ab930,0xeb045c59,'m10v_menu_count',true],
  [0x531ab96c,0xeb045cc3,'m10v_menu_index',true],
  [0x531ab9fc,0xeb045c26,'m10v_menu_count',true],
  [0x531abc2c,0xeb045bd2,'m10v_menu_max_count',true],
  [0x531abe34,0xeb045b18,'m10v_menu_count',true],
  [0x531abe88,0xeb045b7c,'m10v_menu_index',true], [0x532922b4,0xe351000a,'m10v_menu_name'],
  [0x532a985c,0xe1a0c00d,'m10v_menu_value_name'], [0x532935dc,0xe351000a,'m10v_menu_icon'],
  [0x532a9988,0xe1a0c00d,'m10v_menu_value_icon'], [0x531ab914,0xe1a0c00d,'m10v_menu_focus'],
  [0x531ac24c,0xe1a0c00d,'m10v_menu_confirm'], [0x531ac270,0xe1a0c00d,'m10v_menu_key'],
  [0x531ac140,0xe1a0c00d,'m10v_menu_enter'], [0x535048e8,0xeb069d0e,'m10v_chain_capture',true],
  [0x5320a834,0xe08ec106,'m10v_icon_pixels'],
  [0x533966e8,0xe3023bac,'m10v_resource_primary'], [0x533970fc,0xe3023bac,'m10v_resource_secondary'],
];
// Exact displaced loads and object registers, independently checked below.
const ispHooks = [
 [0x536db7f8,0xe5d3277c,2,0xe5900000,'parameters'],
 [0x536dc26c,0xe5d7277c,2,0xe5960000,'color_table'],
 [0x536dc4bc,0xe5d7377c,3,0xe5960000,'color_flags'],
 [0x536dd3e0,0xe5d7177c,1,0xe51401e0,'curve'],
 [0x535131c0,0xe5d1377c,3,0xe1a0000e,'local_process'],
];
const sources = ['native/gr3/m10v_aspect_config.h','native/gr3/m10v_half_frame_icon.rgba','native/gr3/half-frame-icon.json','scripts/generate_gr3_half_frame_icon.py','native/gr3/extra-films-reference.json','native/gr3/m10v_extra_films_native_profiles.h','native/gr3/m10v_extra_films.rgba','web/gr3/extra-films-luts.json','scripts/build_gr3_extra_films_reference.py','scripts/fit_gr3_extra_films_native.py','scripts/verify_gr3_extra_films_reference.py','native/gr3/c41-reference.json','native/gr3/m10v_c41_native_profiles.h','native/gr3/m10v_c41.rgba','web/gr3/c41-luts.json','scripts/build_gr3_c41_reference.py','scripts/fit_gr3_c41_native.py','scripts/verify_gr3_c41_reference.py','node/gr3-sd-pre-retired-anime-contract.json','node/gr3-sd-pre-c41-contract.json','native/gr3/m10v_anime.h','native/gr3/anime-e6-reference.json','native/gr3/m10v_anime_e6_native_profiles.h','native/gr3/m10v_anime_e6.rgba','native/gr3/m10v_anime_ui.rgba','native/gr3/anime-ui.json','native/gr3/anime-ui-raster.json','third_party/anime-ui-font/OFL.txt','web/gr3/anime-e6-luts.json','scripts/build_gr3_anime_e6_reference.py','scripts/fit_gr3_anime_e6_native.py','scripts/verify_gr3_anime_e6_reference.py','scripts/generate_m10v_anime_ui.py','node/gr3-sd-pre-anime-e6-contract.json','node/gr3-sd-pre-d76-mono-contract.json','native/gr3/m10v_aspect_icons.rgba','native/gr3/aspect-icons.json','scripts/generate_gr3_aspect_icons.py','native/gr3/film_d76_0.c','native/gr3/film_d76_1.c','native/gr3/film_d76_0_data.h','native/gr3/film_d76_1_data.h','native/gr3/m10v_d76.rgba','native/gr3/d76-reference.json','web/gr3/d76-luts.json','scripts/build_gr3_d76_reference.py','scripts/fit_gr3_d76_native.py','scripts/verify_gr3_d76_reference.py','native/gr3/m10v_d76_native_profiles.h','node/gr3-sd-pre-universal-halation-contract.json','node/gr3-sd-pre-d76-contract.json','native/gr3/m10v_spectral_native_profiles.h','native/gr3/m10v_film_directory.h','web/gr3/film-directory.json','node/gr3-film-directory.mjs','scripts/generate_m10v_directory.py','native/gr3/film_spectral_data.h','native/gr3/spectral-reference.json','web/gr3/spectral-luts.json','scripts/build_gr3_spectral_reference.py','scripts/fit_gr3_spectral_native.py','scripts/verify_gr3_spectral_reference.py','native/gr3/m10v_5213.rgba','docs/research/aerocolor-2460/official-medium-curves.json','node/gr3-sd-pre-aerocolor-contract.json','node/gr3-sd-pre-directory-contract.json','native/gr3/m10v_tone.h','native/gr3/m10v_pixel_world.h','native/gr3/m10v_pixel_world.rgba','native/gr3/m10v_charmera.h','native/gr3/m10v_charmera.rgba','native/gr3/m10v_charmera_ui.rgba','scripts/generate_m10v_charmera_ui.py','native/gr3/film_style_filters_0.c','native/gr3/film_style_filters_1.c','native/gr3/film_style_filters_0_data.h','native/gr3/film_style_filters_1_data.h','native/gr3/m10v_style_filters.rgba','native/gr3/style-filters-reference.json','web/gr3/style-filters-luts.json','scripts/build_gr3_style_filters_reference.py','scripts/fit_gr3_style_filters_native.py','scripts/verify_gr3_style_filters_reference.py','native/gr3/film_newstocks.c','native/gr3/film_newstocks_data.h','native/gr3/newstocks-reference.json','web/gr3/newstocks-luts.json','scripts/build_gr3_newstocks_reference.py','scripts/fit_gr3_newstocks_native.py','scripts/verify_gr3_newstocks_reference.py','native/gr3/film_curated.c','native/gr3/film_curated_data.h','native/gr3/curated-reference.json','web/gr3/curated-luts.json','scripts/verify_gr3_curated_reference.py','scripts/build_gr3_curated_reference.py','scripts/fit_gr3_curated_native.py','scripts/build_gr3_harman_reference.py','scripts/verify_gr3_harman_reference.py','native/gr3/film_harman.c','native/gr3/film_harman.h','native/gr3/film_harman_data.h','native/gr3/harman-reference.json','web/gr3/harman-luts.json','scripts/verify_gr3_5207_reference.py','scripts/build_gr3_5207_reference.py','web/gr3/5207-lut.json','native/gr3/film_5207.c','native/gr3/film_5207.h','native/gr3/m10v_color_cache.h','native/gr3/film_5207_data.h','native/gr3/5207-reference.json','scripts/generate_m10v_icons.py','native/gr3/m10v_icons.rgba','native/gr3/m10v_stock_icon_directory.bin','native/gr3/m10v_legacy_data.h','web/gr3/film-catalog.json','scripts/generate_m10v_catalog.py','native/gr3/m10v_universal_halation.h','native/gr3/halation_core.c','native/gr3/halation_core.h','native/gr3/halation_energy.h','native/gr3/m10v_detail.c','scripts/build_gr3_native_detail.py','scripts/build_gr3_menu_patches.py','scripts/build_gr3_isp_base.py','native/gr3/m10v_library.c','native/gr3/m10v_library.h',
  'native/gr3/m10v_library_camera.c','native/gr3/m10v_library_menu.c',
  'native/gr3/m10v_library_capture.c','native/gr3/m10v_debug.c','native/gr3/m10v_debug.h','native/gr3/m10v_capture_profile.h','scripts/build_gr3_m10v_library.py'];
sources.push('native/gr3/m10v_film_color_candidates.h','native/gr3/isp-film-targets.json','scripts/build_gr3_isp_film_targets.py','native/gr3/m10v_spatial_accel.c','native/gr3/m10v_spatial_accel.h');
sources.push('native/gr3/m10v_save_trace.c','native/gr3/m10v_save_trace.h','native/gr3/m10v_capture_raw_lifetime.c','native/gr3/m10v_capture_raw_lifetime.h','scripts/build_gr3_save_trace.py','scripts/build_gr3_capture_lifecycle.py','native/gr3/m10v_capture_lifecycle.c');
sources.push('native/gr3/m10v_file_trace.c','scripts/build_gr3_file_trace.py');
sources.push(...hdfSources);
sources.push('node/gr3-sd-pre-oriented-stamp-contract.json');
sources.push('native/gr3/m10v_isp_frame_color.c','native/gr3/m10v_isp_frame_color.h','native/gr3/m10v_isp_recipe_color.c','native/gr3/m10v_isp_recipe_color.h','scripts/build_gr3_isp_recipe_color.py','scripts/build_gr3_isp_color_hook.py');
const textureSources=['native/gr3/m10v_texture_accel.c','native/gr3/m10v_texture_accel.h','scripts/build_gr3_texture_accel.py'];
const nativeGrainSources=['scripts/build_gr3_native_grain_hooks.py'];
const viewDeferredSources=['native/gr3/m10v_view_deferred.c','native/gr3/m10v_view_deferred.h','native/gr3/m10v_view_recovery.h','scripts/build_gr3_view_deferred.py'];
const nativeColorSources=['native/gr3/m10v_isp_native_look.c','native/gr3/m10v_isp_native_look.h','native/gr3/m10v_isp_native_look_profiles.h','native/gr3/m10v_isp_multiaxis.c','native/gr3/m10v_isp_multiaxis.h'];
const saveChainSources=['native/gr3/m10v_module_dispatch_trace.c','scripts/build_gr3_module_dispatch_trace.py','scripts/build_gr3_pool_release_trace.py'];
const sdSources=[...settingsSources,'node/gr3-settings-menu.mjs','native/gr3/m10v_sd_library.h','native/gr3/m10v_sd_library.c','native/gr3/m10v_sd_camera.c','native/gr3/m10v_sd_contract.h','node/gr3-sd-film-pack.mjs','node/gr3-sd-texture-prior-contract.json','node/gr3-sd-pre-styles-contract.json','node/gr3-sd-20261023-contract.json','node/gr3-sd-pre-pixel-contract.json','node/gr3-sd-prior-contract.json','node/gr3-sd-20261021-contract.json','scripts/generate_gr3_sd_contract.mjs'];
export function nativeSourceFingerprint(){return sha(JSON.stringify(['scripts/build_gr3_film_slot_extension.py','native/gr3/m10v_tone_menu.c',...sources,...sdSources,...textureSources,...saveChainSources,...nativeColorSources,...nativeGrainSources,...viewDeferredSources].map(name=>[name,sha(readFileSync(new URL('../'+name,import.meta.url)))])));}
const movw = (register, value) => (0xe3000000 | ((value & 0xf000) << 4) | (register << 12) | (value & 0xfff)) >>> 0;
function branch(address, target, link=false) {
  const delta = target - address - 8;
  need(Number.isSafeInteger(target) && delta % 4 === 0 && delta >= -(2**25) && delta < 2**25,
    'native ARM branch target out of range');
  return ((link ? 0xeb000000 : 0xea000000) | ((delta >> 2) & 0xffffff)) >>> 0;
}
function checkRuntime(runtime, manifest) {
  const BASE=manifest?.base;
  need(nativeBases.includes(BASE), 'native runtime base invalid');
  need(Buffer.isBuffer(runtime) && runtime.length > 4096 && runtime.length % 4 === 0,
    'native runtime size invalid');
  need(manifest?.schema === 'm10v-gr3-native-film-runtime/v2' && manifest.base === BASE &&
    manifest.code_bytes === runtime.length && manifest.code_sha256 === sha(runtime), 'native runtime hash mismatch');
  need(manifest.film_count === 103 && manifest.slots === 10 && Array.isArray(manifest.dependencies) &&
    manifest.dependencies.length === 0 && !runtime.includes(Buffer.from('GRLIFE')), 'native runtime provenance differs');
  const expectedSources=[...(manifest.appended_slots?['scripts/build_gr3_film_slot_extension.py','native/gr3/m10v_tone_menu.c']:[]),...sources,...(manifest.sd_library?sdSources:[]),...(manifest.experimental_capture?.texture_neon?textureSources:[]),...(manifest.capture_lifecycle?.module_dispatch?saveChainSources:[]),...(manifest.experimental_capture?.native_color?nativeColorSources:[]),...(manifest.experimental_capture?.native_grain?nativeGrainSources:[]),...(manifest.capture_lifecycle?.view_deferred?viewDeferredSources:[])];
  if(manifest.experimental_capture?.texture_neon)need((manifest.debug_mode===true||manifest.experimental_capture.native_color===true)&&manifest.experimental_capture.spatial_neon===true&&Number.isInteger(manifest.symbols?.m10v_texture_block8)&&Number.isInteger(manifest.symbols?.m10v_harman_texture_table),'incomplete full texture block runtime');
  need(typeof manifest.sd_library==='boolean','missing SD capability');
  need(!manifest.sd_library||(runtime.includes(Buffer.from('C:\\M10V\\FILMS.M10'))&&['m10v_sd_camera_item','m10v_sd_camera_install'].every(n=>Number.isInteger(manifest.symbols[n])&&manifest.symbols[n]>=BASE&&manifest.symbols[n]<BASE+runtime.length)),'SD runtime incomplete');
  need(Object.keys(manifest.sources || {}).sort().join('|') === [...expectedSources].sort().join('|'), 'native source inventory differs');
  for (const name of expectedSources) need(manifest.sources[name] === sha(readFileSync(new URL('../'+name,import.meta.url))),
    'native source changed since compilation: '+name);
  need(manifest.flags.includes('-DM10V_APPENDED_SLOTS=1')===!!manifest.appended_slots,'appended compile mode differs');
  need(typeof manifest.universal_halation==='boolean'&&manifest.flags.includes('-DM10V_UNIVERSAL_HALATION=1')===manifest.universal_halation,'universal halation capability differs');
  checkIspBase(runtime,manifest);
  appendedSlotPatches(runtime,manifest);
  if(manifest.experimental_capture?.candidate_color){
    const header=readFileSync(new URL('../native/gr3/m10v_film_color_candidates.h',import.meta.url),'utf8');
    const names=['m10v_5207_candidate_lut','m10v_phoenix_ii_candidate_lut'];
    const metadata=JSON.parse(readFileSync(new URL('../native/gr3/isp-film-targets.json',import.meta.url))).cpu_candidates;
    need((manifest.debug_mode===true||manifest.experimental_capture?.native_color===true)&&manifest.color_candidates?.length===2,'color candidate requires debug runtime');
    for(let i=0;i<2;i++){
      const match=header.match(new RegExp(names[i]+'\\[3375\\]\\[3\\]\\s*=\\s*\\{([\\s\\S]*?)\\n\\};'));
      need(match,'missing candidate color table');
      const payload=Buffer.from(match[1].match(/\d+/g).map(Number)),row=manifest.color_candidates[i];
      need(metadata[['5207','phoenix_ii'][i]].table_sha256===sha(payload),'candidate color provenance differs');
      need(payload.length===10125&&row.bytes===payload.length&&row.sha256===sha(payload)&&Number.isInteger(row.offset)&&row.offset>=0&&runtime.subarray(row.offset,row.offset+payload.length).equals(payload),'candidate color readback differs');
    }
  }
  checkDetail(runtime,manifest);
  checkSettings(runtime,manifest);
  const reference=JSON.parse(readFileSync(new URL('../native/gr3/5207-reference.json',import.meta.url)));
  const table=JSON.parse(readFileSync(new URL('../web/gr3/5207-lut.json',import.meta.url)));
  need(table.size===15&&table.bits===8&&Array.isArray(table.values)&&table.values.length===10125&&table.values.every(v=>Number.isInteger(v)&&v>=0&&v<=255),'5207 reference dimensions differ');
  const payload=Buffer.from(table.values),film=manifest.film_5207;
  need(film?.bytes===payload.length&&film.sha256===sha(payload)&&reference.table_sha256===sha(payload)&&Number.isInteger(film.offset)&&film.offset>=0&&film.offset+payload.length<=runtime.length&&runtime.subarray(film.offset,film.offset+payload.length).equals(payload),'5207 compiled payload differs from reference');
  need(film.camera_calibrated===false&&film.film_calibrated===false&&reference.camera_calibrated===false&&reference.film_calibrated===false,'5207 calibration evidence unavailable');
  const harmanReference=JSON.parse(readFileSync(new URL('../native/gr3/harman-reference.json',import.meta.url)));
  const harmanWeb=JSON.parse(readFileSync(new URL('../web/gr3/harman-luts.json',import.meta.url)));
  need(harmanWeb.size===15&&harmanWeb.bits===8&&harmanWeb.stocks.length===5&&manifest.film_harman?.length===5&&harmanReference.camera_calibrated===false&&harmanReference.film_calibrated===false,'Harman reference inventory differs');
  for(let i=0;i<5;i++){
    const w=harmanWeb.stocks[i],m=manifest.film_harman[i],spec=harmanReference.stocks[i];
    need(w.values.length===10125&&w.values.every(v=>Number.isInteger(v)&&v>=0&&v<=255),'Harman table bounds differ');
    const payload=Buffer.from(w.values);
    need(m.film_id===w.id&&m.ei===w.ei&&m.bytes===payload.length&&m.sha256===sha(payload)&&spec.table_sha256===sha(payload)&&Number.isInteger(m.offset)&&m.offset>=0&&m.offset+payload.length<=runtime.length&&runtime.subarray(m.offset,m.offset+payload.length).equals(payload)&&m.camera_calibrated===false&&m.film_calibrated===false,'Harman compiled payload differs');
  }
  const curated=JSON.parse(readFileSync(new URL('../web/gr3/curated-luts.json',import.meta.url)));
  need(curated.stocks.length===4&&manifest.film_curated?.length===4,'curated inventory differs');
  for(let i=0;i<4;i++){
    const w=curated.stocks[i],m=manifest.film_curated[i],payload=Buffer.from(w.values);
    need(w.id===69+i&&m.film_id===w.id&&payload.length===10125&&m.bytes===payload.length&&m.sha256===sha(payload)&&Number.isInteger(m.offset)&&m.offset>=0&&m.offset+payload.length<=runtime.length&&runtime.subarray(m.offset,m.offset+payload.length).equals(payload)&&m.camera_calibrated===false&&m.film_calibrated===false,'curated compiled payload differs');
  }
  const newstocks=JSON.parse(readFileSync(new URL('../web/gr3/newstocks-luts.json',import.meta.url)));
  need(newstocks.stocks.length===6&&manifest.film_newstocks?.length===6,'new stocks inventory differs');
  for(let i=0;i<6;i++){
    const w=newstocks.stocks[i],m=manifest.film_newstocks[i],payload=Buffer.from(w.values);
    need(w.id===73+i&&m.film_id===w.id&&payload.length===10125&&m.bytes===payload.length&&m.sha256===sha(payload)&&Number.isInteger(m.offset)&&m.offset>=0&&m.offset+payload.length<=runtime.length&&runtime.subarray(m.offset,m.offset+payload.length).equals(payload)&&m.camera_calibrated===false&&m.film_calibrated===false,'new stock compiled payload differs');
  }
  const styles=JSON.parse(readFileSync(new URL('../web/gr3/style-filters-luts.json',import.meta.url)));
  need(styles.stocks.length===7&&manifest.film_style_filters?.length===7,'style inventory differs');
  for(let i=0;i<7;i++){
    const w=styles.stocks[i],m=manifest.film_style_filters[i],payload=Buffer.from(w.values);
    need(w.id===291+i&&m.film_id===w.id&&payload.length===10125&&m.bytes===payload.length&&m.sha256===sha(payload)&&Number.isInteger(m.offset)&&m.offset>=0&&m.offset+payload.length<=runtime.length&&runtime.subarray(m.offset,m.offset+payload.length).equals(payload)&&m.camera_calibrated===false&&m.film_calibrated===false,'style compiled payload differs');
  }
  const d76=JSON.parse(readFileSync(new URL('../web/gr3/d76-luts.json',import.meta.url)));
  need(d76.stocks.length===7&&manifest.film_d76?.length===7,'D76 inventory differs');
  for(let i=0;i<7;i++){
    const w=d76.stocks[i],m=manifest.film_d76[i],p=Buffer.from(w.values);
    need(w.id===299+i&&m.film_id===w.id&&p.length===10125&&m.bytes===p.length&&m.sha256===sha(p)&&m.storage==='mono-u8'&&m.stored_bytes===3375&&Number.isInteger(m.offset)&&m.offset>=0&&m.offset+3375<=runtime.length&&m.camera_calibrated===false&&m.film_calibrated===false,'D76 compiled payload differs');
    const mono=runtime.subarray(m.offset,m.offset+3375),expanded=Buffer.alloc(10125);
    for(let j=0;j<3375;j++)expanded.fill(mono[j],j*3,j*3+3);
    need(m.stored_sha256===sha(mono)&&expanded.equals(p),'D76 lossless mono readback differs');
  }
  const init = Buffer.from(manifest.initial_state_hex || '', 'hex'), initAt = manifest.initial_state_offset;
  need(init.length === 184 && Number.isInteger(initAt) && initAt >= 0 && runtime.subarray(initAt,initAt+184).equals(init), 'native initial settings readback differs');
  const quietDebugSinks=!!manifest.capture_lifecycle&&manifest.experimental_capture?.native_color===true&&['m10v_debug_log','m10v_debug_batch'].every(name=>{const at=manifest.symbols?.[name]-BASE;return Number.isInteger(at)&&at>=0&&at+8<=runtime.length&&runtime.readUInt32LE(at)===0xe3a00000&&runtime.readUInt32LE(at+4)===0xe12fff1e;});
  need(typeof manifest.debug_mode==='boolean' && (manifest.debug_mode?
    manifest.debug_log?.schema==='m10v-gr3-sd-debug/v1'&&manifest.debug_log?.guard_address===0x5506821f&&
    /^[0-9a-f]{8}$/.test(manifest.debug_log.build_id)&&manifest.debug_log.page_bytes===4096&&manifest.debug_log.records_per_channel===63&&
    JSON.stringify(manifest.debug_log.files)===JSON.stringify(['M10VMN0.BIN','M10VMN1.BIN','M10VCP0.BIN','M10VCP1.BIN','M10VIO0.BIN','M10VIO1.BIN','M10VAK0.BIN','M10VAK1.BIN'])&&
    manifest.debug_log.files.every(name=>runtime.includes(Buffer.from('C:\\'+name))):
    !manifest.debug_log&&((!manifest.symbols?.m10v_debug_log&&!manifest.symbols?.m10v_debug_batch)||quietDebugSinks)&&!runtime.includes(Buffer.from('C:\\M10VMN'))&&!runtime.includes(Buffer.from('C:\\M10VCP'))),'native debug contract differs');
  for (const name of [...hooks.map(row=>row[2]), 'm10v_capture_library',...(manifest.debug_mode?['m10v_debug_log','m10v_debug_batch']:[])]) {
    const address = manifest.symbols?.[name];
    need(Number.isInteger(address) && address % 4 === 0 && address >= BASE + 0x100 && address < BASE + runtime.length,
      'native symbol outside module: '+name);
  }
  const focalIcons=manifest.zoom?.enabled===true&&manifest.sd_library;
  const halfFrame=manifest.camera_model==='gr3'&&manifest.base>=0x540be000;
  const aspectFirst=focalIcons?855:782,iconCount=halfFrame?876:874+Number(!!manifest.hdf_adj),descriptorCount=121+(focalIcons?1:0)+Number(!!manifest.hdf_adj)+Number(halfFrame);
  const icons=manifest.icons, stock=readFileSync(new URL('../native/gr3/m10v_stock_icon_directory.bin',import.meta.url)), artwork=readFileSync(new URL('../native/gr3/m10v_icons.rgba',import.meta.url));
  need(icons?.first_id===671&&icons.last_id===748&&icons.width===40&&icons.height===40&&artwork.length===78*6400&&icons.sha256===sha(artwork),'native icon inventory differs');
  const retired=manifest.sd_library?32:0, packedArt=artwork.subarray(retired*6400), packedCount=78-retired;
  need(icons.catalog_count===iconCount&&icons.descriptor_count===descriptorCount&&icons.payload_bytes===packedArt.length&&icons.retired_generic_count===retired,'native packed icon inventory differs');
  for(const [address,length] of [[icons.table,iconCount*4],[icons.descriptors,descriptorCount*8],[icons.pixels,packedArt.length]])need(Number.isInteger(address)&&address%4===0&&address>=BASE&&address+length<=BASE+runtime.length,'native icon address outside module');
  need(icons.descriptors===icons.table+iconCount*4&&icons.pixels===icons.descriptors+descriptorCount*8&&runtime.subarray(icons.table-BASE,icons.table-BASE+stock.length).equals(stock)&&runtime.subarray(icons.pixels-BASE,icons.pixels-BASE+packedArt.length).equals(packedArt),'native icon readback differs');
  if(focalIcons){
    const f=icons.focal,descriptor=icons.descriptors+111*8,at=descriptor-BASE;
    need(f?.first_id===782&&f.last_id===854&&f.width===60&&f.height===20&&f.descriptor===descriptor&&f.storage==='draw-owned-heap'&&f.heap_bytes===4800&&f.owner_fp_offset===-0x80&&runtime.readUInt16LE(at)===60&&runtime.readUInt16LE(at+2)===20&&runtime.readUInt32LE(at+4)===0,'native focal icon descriptor differs');
    for(let id=782;id<=854;id++)need(runtime.readUInt32LE(icons.table-BASE+id*4)===descriptor,'native focal directory differs');
  }else need(icons.focal===null,'unexpected focal icons');
  if(manifest.hdf_adj){
    const a=manifest.hdf_adj.icon,art=readFileSync(new URL('../native/gr3/m10v_hdf_adj.rgba',import.meta.url));
    const d=icons.descriptors+(121+(focalIcons?1:0))*8,at=d-BASE;
    need(a?.id===874&&a.descriptor===d&&a.width===40&&a.height===40&&a.bytes===6400&&art.length===6400&&a.sha256===sha(art)&&
      Number.isInteger(a.pixels)&&a.pixels>=BASE&&a.pixels+6400<=BASE+runtime.length&&
      runtime.readUInt32LE(icons.table-BASE+874*4)===d&&runtime.readUInt16LE(at)===40&&runtime.readUInt16LE(at+2)===40&&
      runtime.readUInt32LE(at+4)*4===a.pixels&&runtime.subarray(a.pixels-BASE,a.pixels-BASE+6400).equals(art),'HDF ADJ icon readback differs');
  }
  {
    const art=readFileSync(new URL('../native/gr3/m10v_aspect_icons.rgba',import.meta.url)),a=manifest.aspect_icons,p=a?.pixels;
    need(a?.first_id===aspectFirst&&a.last_id===aspectFirst+1&&a.width===60&&a.height===40&&art.length===19200&&a.sha256===sha(art)&&Number.isInteger(p)&&runtime.subarray(p-BASE,p-BASE+art.length).equals(art),'aspect artwork differs');
    for(let i=0;i<2;i++){
      const d=icons.descriptors+(111+(focalIcons?1:0)+i)*8,at=d-BASE;
      need(runtime.readUInt32LE(icons.table-BASE+(aspectFirst+i)*4)===d&&runtime.readUInt16LE(at)===60&&runtime.readUInt16LE(at+2)===40&&runtime.readUInt32LE(at+4)*4===p+i*9600,'aspect icon descriptor differs');
    }
  }
  if(halfFrame){
    const a=manifest.half_frame_icon,art=readFileSync(new URL('../native/gr3/m10v_half_frame_icon.rgba',import.meta.url));
    const d=icons.descriptors+(121+Number(focalIcons)+Number(!!manifest.hdf_adj))*8,at=d-BASE;
    need(a?.id===875&&a.descriptor===d&&a.width===60&&a.height===40&&art.length===9600&&a.sha256===sha(art)&&
      runtime.readUInt32LE(icons.table-BASE+875*4)===d&&runtime.readUInt16LE(at)===60&&runtime.readUInt16LE(at+2)===40&&
      runtime.readUInt32LE(at+4)*4===a.pixels&&runtime.subarray(a.pixels-BASE,a.pixels-BASE+art.length).equals(art),'half-frame icon readback differs');
  }else need(!manifest.half_frame_icon,'half-frame icon outside GR III aspect build');
  for(let i=0;i<78;i++){
    const descriptor=icons.descriptors+i*8,at=descriptor-BASE;
    need(runtime.readUInt32LE(icons.table-BASE+(671+i)*4)===descriptor&&runtime.readUInt16LE(at)===40&&runtime.readUInt16LE(at+2)===40&&runtime.readUInt32LE(at+4)*4===icons.pixels+(i<retired?packedCount:i-retired)*6400,'native icon descriptor differs');
  }
  const styleArt=readFileSync(new URL('../native/gr3/m10v_style_filters.rgba',import.meta.url)),styleAt=manifest.style_icons?.pixels;
  need(manifest.style_icons?.first_id===762&&manifest.style_icons?.last_id===768&&styleArt.length===44800&&manifest.style_icons.sha256===sha(styleArt)&&Number.isInteger(styleAt)&&styleAt>=BASE&&styleAt+styleArt.length<=BASE+runtime.length&&runtime.subarray(styleAt-BASE,styleAt-BASE+styleArt.length).equals(styleArt),'style artwork readback differs');
  for(let i=0;i<7;i++){const d=icons.descriptors+(91+i)*8,at=d-BASE;
    need(runtime.readUInt32LE(icons.table-BASE+(762+i)*4)===d&&runtime.readUInt16LE(at)===40&&runtime.readUInt16LE(at+2)===40&&runtime.readUInt32LE(at+4)*4===styleAt+i*6400,'style icon descriptor differs');
  }
  {
    const extra=readFileSync(new URL('../native/gr3/m10v_pixel_world.rgba',import.meta.url));
    const id=manifest.sd_library?761:755,descriptor=icons.descriptors+(id-671)*8,at=descriptor-BASE;
    const pixels=icons.pixels+(packedCount+(manifest.sd_library?2:1))*6400+35584;
    need(extra.length===6400&&runtime.readUInt32LE(icons.table-BASE+id*4)===descriptor&&runtime.readUInt16LE(at)===40&&runtime.readUInt16LE(at+2)===40&&runtime.readUInt32LE(at+4)*4===pixels&&runtime.subarray(pixels-BASE,pixels-BASE+6400).equals(extra),'native Pixel World icon differs');
  }
  {
    const extra=readFileSync(new URL('../native/gr3/m10v_charmera.rgba',import.meta.url));
    const id=manifest.sd_library?755:749,descriptor=icons.descriptors+(manifest.sd_library?84:78)*8,at=descriptor-BASE,pixels=icons.pixels+(packedCount+(manifest.sd_library?1:0))*6400;
    need(extra.length===6400&&runtime.readUInt32LE(icons.table-BASE+id*4)===descriptor&&runtime.readUInt16LE(at)===40&&runtime.readUInt16LE(at+2)===40&&runtime.readUInt32LE(at+4)*4===pixels&&runtime.subarray(pixels-BASE,pixels-BASE+6400).equals(extra),'native Charmera icon differs');
  }
  {
    const artwork=readFileSync(new URL('../native/gr3/m10v_charmera_ui.rgba',import.meta.url));
    let pixel=icons.pixels+(packedCount+(manifest.sd_library?2:1))*6400,offset=0;
    for(let i=0;i<5;i++){
      const id=(manifest.sd_library?756:750)+i,descriptor=icons.descriptors+((manifest.sd_library?85:79)+i)*8,at=descriptor-BASE;
      const width=i<4?64:400,height=i<4?16:12,bytes=width*height*4;
      need(runtime.readUInt32LE(icons.table-BASE+id*4)===descriptor&&runtime.readUInt16LE(at)===width&&runtime.readUInt16LE(at+2)===height&&runtime.readUInt32LE(at+4)*4===pixel&&runtime.subarray(pixel-BASE,pixel-BASE+bytes).equals(artwork.subarray(offset,offset+bytes)),'native Charmera color artwork differs');
      offset+=bytes;pixel+=bytes;
    }
    need(offset===artwork.length,'native Charmera color artwork extent differs');
  }
  if(manifest.sd_library){
    const custom=manifest.custom_film_display,icon=readFileSync(new URL('../native/gr3/m10v_custom_icon.rgba',import.meta.url));
    const descriptor=icons.descriptors+83*8,at=descriptor-BASE,pixels=icons.pixels+packedCount*6400;
    need(custom?.icon_id===754&&custom.icon_sha256===sha(icon)&&icon.length===6400&&
      runtime.readUInt32LE(icons.table-BASE+754*4)===descriptor&&
      runtime.readUInt16LE(at)===40&&runtime.readUInt16LE(at+2)===40&&
      runtime.readUInt32LE(at+4)*4===pixels&&runtime.subarray(pixels-BASE,pixels-BASE+icon.length).equals(icon),'native custom LUT icon differs');
    need(JSON.stringify(custom.name_resources)==='[1007,1011]'&&custom.name_storage==='getter-stack-80-bytes'&&Number.isInteger(manifest.symbols.m10v_menu_custom_resource),'native custom LUT name resources differ');
    const c=manifest.film_cards;
    need(c?.first_id===749&&c.last_id===773&&c.width===120&&c.height===148&&c.artwork_height===148&&c.caption_height===0&&c.heap_bytes===710580&&c.descriptor_storage==='view-owned-heap'&&c.descriptor_offset===710400&&c.directory_offset===710480&&c.directory_provider===manifest.symbols.m10v_settings_controller_card_directory,'native film card ownership differs');
    for(const name of ['width','height','draw']){
      const at=c.directory_hooks?.[name];need(Number.isInteger(at)&&at>=BASE&&at+100<=BASE+runtime.length&&at===manifest.symbols['m10v_icon_directory_'+name],'native dynamic directory hook differs');
      need(runtime.readUInt32LE(at-BASE)===0xe92d5fff&&runtime.readUInt32LE(at-BASE+4)===0xe10fc000,'native dynamic directory register guard differs');
    }
    for(const [i,index] of [32,65,66,67,34].entries())need(runtime.readUInt32LE(icons.table-BASE+(749+i)*4)===icons.descriptors+index*8,'native immutable card fallback differs');
  }else need(manifest.film_cards===null,'unexpected native film cards');
  {
    const art=readFileSync(new URL('../native/gr3/m10v_d76.rgba',import.meta.url)),p=manifest.d76_icons?.pixels;
    need(manifest.d76_icons?.first_id===775&&manifest.d76_icons?.last_id===781&&art.length===7*6400&&manifest.d76_icons.sha256===sha(art)&&Number.isInteger(p)&&p>=BASE&&p+art.length<=BASE+runtime.length&&runtime.subarray(p-BASE,p-BASE+art.length).equals(art),'D76 artwork differs');
    for(let i=0;i<7;i++){const d=icons.descriptors+(104+i)*8,at=d-BASE;need(runtime.readUInt32LE(icons.table-BASE+(775+i)*4)===d&&runtime.readUInt16LE(at)===40&&runtime.readUInt16LE(at+2)===40&&runtime.readUInt32LE(at+4)*4===p+i*6400,'D76 icon descriptor differs');}
  }
  {
    // Bind each newly appended film/enum descriptor and every pixel byte to
    // checked-in artwork, independent of a rehashed runtime manifest.
    const art=Buffer.concat([readFileSync(new URL('../native/gr3/m10v_anime_e6.rgba',import.meta.url)).subarray(3*6400),readFileSync(new URL('../native/gr3/m10v_c41.rgba',import.meta.url)),readFileSync(new URL('../native/gr3/m10v_extra_films.rgba',import.meta.url))]);
    const shapes=Array.from({length:8},()=>[40,40]);
    for(const id of [858,859,860,864,865,866,867,868])need(runtime.readUInt32LE(icons.table-BASE+id*4)===0,'retired anime enum still bound');
    const firstDescriptor=113+(focalIcons?1:0);let pixel=manifest.aspect_icons.pixels+19200,offset=0;
    for(let i=0;i<8;i++){
      const id=i<3?861+i:869+i-3,d=icons.descriptors+(firstDescriptor+i)*8,at=d-BASE,[w,h]=shapes[i],bytes=w*h*4;
      need(runtime.readUInt32LE(icons.table-BASE+id*4)===d&&runtime.readUInt16LE(at)===w&&runtime.readUInt16LE(at+2)===h&&runtime.readUInt32LE(at+4)*4===pixel,'native anime icon descriptor differs');
      need(runtime.subarray(pixel-BASE,pixel-BASE+bytes).equals(art.subarray(offset,offset+bytes)),'native anime artwork differs');
      pixel+=bytes;offset+=bytes;
    }
    need(offset===art.length,'native anime artwork extent differs');
  }
  const resourceCount=369;
  need(manifest.resources?.first_id === 786 && manifest.resources.last_id === 785+resourceCount &&
    manifest.resources.texts?.length === resourceCount && manifest.resources.descriptors?.length === resourceCount, 'native resources incomplete');
  for (let i=0;i<resourceCount;i++) {
    const at = manifest.resources.descriptors[i] - BASE, text = manifest.resources.texts[i];
    need(Number.isInteger(at) && at >= 0 && at + 8 < runtime.length && typeof text === 'string', 'native text pointer invalid');
    const encoded = Buffer.from(text+'\0','utf16le');
    need(runtime[at] === encoded.length/2 && runtime[at+1] === 1 && runtime.readUInt16LE(at+2) === 0 &&
      runtime.readUInt32LE(at+4) === BASE + at + 8 && runtime.subarray(at+8,at+8+encoded.length).equals(encoded),
      'native UTF16 resource differs');
  }
}
const detailHooks=[
 [0x531afc20,0xebffffa4,'capacity',true],
 [0x531afa24,0xe345c3b3,'table_ip',true],[0x531afacc,0xe34533b3,'table_r3',true],
 [0x531affa8,0xe345c3b3,'table_ip',true],[0x531b01f8,0xe34533b3,'table_selected',true],
 [0x531b0008,0x979ff103,'row_dispatch',false],[0x531b000c,0xea000066,'row',false],[0x531b03f8,0xea000065,'current',false],
 [0x531b05e4,0xea00005c,'setup',false],[0x531b0bf4,0xea000093,'callback',false],
 [0x531acd24,0xeb0456c0,'reset',true]];
const detailInstructions={"capacity":[0xe3a00016,0xe12fff1e],"table_ip":[3912065023,3775856640,3912040451,3852271624,[14,true,"m10v_detail_table"],3851223096,3904700419,3777818624,0xe3a0e00c,3904741375],"table_r3":[3912065023,3775856640,3912040451,3852271624,[14,true,"m10v_detail_table"],3851223060,3904700419,3777818624,3904741375],"table_selected":[3912065023,3775856640,3912040451,3852271640,[14,true,"m10v_detail_table"],3851223060,3904700419,3777818624,3904741375],"row":[3796090898,3814457356,[8,false,1394278828],3912060943,3785359365,[14,true,"m10v_detail_table"],3808741516,3813000115,3780116492,3904720911,[0,false,1394278828],3796049938,3785369602,3783401476,3785363461,3818913795,[14,true,"m10v_detail_control"],[14,false,1394278500]],"current":[3796156434,3814457356,[8,false,1394279828],3912060943,3785359365,[14,true,"m10v_detail_table"],3808741516,3813000115,3780116492,3904720911,[0,false,1394279828],3796115474,3785363461,3818913793,[14,true,"m10v_detail_control"],3785375744,[14,false,1394279516]],"default":[3785363456,3818913796,3818921984,[14,false,"m10v_detail_control"]],"setup":[0xe240c012,0xe35c000c,[8,false,0x531b075c],0xe92d500f,0xe1a00004,[14,true,"m10v_detail_table"],0xe304c88c,0xe345c3b3,0xe150000c,0xe8bd500f,[0,false,0x531b075c],0xe1a0c000,0xe1a00004,0xe24bd010,0xe89d6810,[14,false,"slider_dispatch"]],"callback":[3796221970,3814457356,[8,false,1394282056],3912060943,3785359364,[14,true,"m10v_detail_table"],3808741516,3813000115,3780116492,3904720911,[0,false,1394282056],3796181010,3785368578,3783401478,3785363460,3818913794,[14,true,"m10v_detail_control"],3813670912,[1,false,1394281580],3796619292,3902646512],"reset":[3912056848,[14,true,1395402796],3785363461,3818913799,3818921984,[14,true,"m10v_detail_control"],3904733200]};
detailInstructions.exposure_dispatch=[0xe92d5011,0xe1a01000,0xe3a00009,0xe3a02000,[14,true,'m10v_detail_control'],0xe3500001,0xe8bd5011,[0,false,'slider1'],[14,false,'slider2']];
detailInstructions.row_dispatch=[0xe92d500f,0xe1a02803,0xe1822004,0xe1a01005,0xe3a00008,[14,true,'m10v_detail_control'],0xe8bd500f,0xe3530011,0x979ff103,[14,false,0x531b000c],
 0x531b009c,0x531b00ac,0x531b00bc,0x531b00cc,0x531b00dc,0x531b00ec,0x531b00fc,0x531b010c,0x531b011c,0x531b012c,0x531b013c,0x531b014c,0x531b015c,0x531b016c,0x531b017c,0x531b018c,0x531b019c,0x531b0058];
function checkDetail(runtime,manifest,raw) {
 const d=manifest.detail,base=manifest.base;
 const grain=manifest.experimental_capture?.native_grain===true;
 const halo=manifest.universal_halation;
 const ids=[18,19,20,...(grain?[21]:[]),...(halo?[22]:[]),28,29];
 const fields=['Halation Gain','Halation Spread','Highlight Gate',...(grain?['Film Grain']:[]),...(halo?['Halation Mode']:[]),'RED Exposure','Charmera Color'];
 need(d?.schema==='m10v-gr3-native-detail/v2'&&d.backend==='m10v_camera_library_detail'&&d.native_grain===grain&&
  JSON.stringify(d.ids)===JSON.stringify(ids)&&JSON.stringify(d.fields)===JSON.stringify(fields),'native detail contract differs');
 const read=(a,n)=>{need(Number.isInteger(a)&&a%4===0&&a>=base&&a+n<=base+runtime.length,'native detail address outside module');return runtime.subarray(a-base,a-base+n);};
 const captions=read(d.captions,120);
 const variants={halo:[18,19,20,...(grain?[21]:[])],common:grain?[21]:[],red:[...(grain?[21]:[]),28],charmera:[29],phoenix:[18,19,20,...(grain?[21]:[]),28],pixel:[]};
 if(halo)for(const name of Object.keys(variants))variants[name]=[22,18,19,20,...variants[name].filter(id=>![18,19,20].includes(id))];
 need(d.universal_halation===halo,'native detail capability differs');
 need(d.tables===d.variant_tables?.halo&&JSON.stringify(d.variant_ids)===JSON.stringify(variants),"native detail variants differ");
 const expectedIds=[862,863,864,827,halo?1137:828,913,913,913,913,913,933,manifest.sd_library?1013:948];
 for(let i=0;i<expectedIds.length;i++)need(captions.readUInt16LE(72+i*4)===expectedIds[i]&&captions.readUInt16LE(74+i*4)===expectedIds[i],'native detail caption differs');
 for(const name of ['m10v_detail_table','m10v_detail_control','m10v_camera_library_detail'])read(manifest.symbols[name],4);
 for(const [name,template] of Object.entries(detailInstructions)){
  const at=d.entries?.[name],code=read(at,template.length*4);
  for(let i=0;i<template.length;i++){
   const instruction=template[i];let word=instruction;
   if(Array.isArray(instruction)){
    const [condition,link,target]=instruction,to=typeof target==='string'?(manifest.symbols[target]??(target==='slider1'?d.sliders[1]:target==='slider2'?d.sliders[2]:d[target])):target;
    word=((branch(at+i*4,to,link)&0x0fffffff)|(condition<<28))>>>0;
   }
   need(code.readUInt32LE(i*4)===word,'native detail instruction differs: '+name+' '+i);
  }
 }
 // Exact stock entry bytes and list prefix are compared to the freshly decoded
 // official source, never to a manifest-supplied preimage or instruction list.
 if(raw){
  need(captions.subarray(0,72).equals(raw.subarray(0xb34bd8,0xb34c20)),'native detail stock captions differ');
  for(const [variant,ids] of Object.entries(variants)){
   const table=read(d.variant_tables[variant],manifest.appended_slots?368:288),suffix=Buffer.from(ids.flatMap(id=>[0,id]));
   for(let i=0;i<(manifest.appended_slots?46:36);i++){
    const old=0xb3488c+(i%36)*8,p=raw.readUInt32LE(old),n=manifest.appended_slots?0:raw.readUInt32LE(old+4),fresh=table.readUInt32LE(i*8);
    need(table.readUInt32LE(i*8+4)===n+ids.length,'native detail count differs');
    const list=read(fresh,n*2+suffix.length);
    need(list.subarray(0,n*2).equals(raw.subarray(p-LOAD,p-LOAD+n*2))&&list.subarray(n*2).equals(suffix),'native detail list differs');
   }
  }
  const maxima=[8,8,8,3,halo?2:3,2,8,5,8,1,2,3,3],dispatch=read(d.slider_dispatch,(ids.length*2+1)*4);
  for(let i=0;i<ids.length;i++){
   const id=ids[i];
   need(dispatch.readUInt32LE(i*8)===(0xe35c0000|id)>>>0,'native detail slider selector differs');
   need(dispatch.readUInt32LE(i*8+4)===(branch(d.slider_dispatch+i*8+4,(id===29?d.charmera_colors.slider:id===28?d.entries.exposure_dispatch:d.sliders[maxima[id-18]]))&0x0fffffff),'native detail slider target differs');
  }
  need(dispatch.readUInt32LE(ids.length*8)===branch(d.slider_dispatch+ids.length*8,d.sliders[8]),'native detail slider fallback differs');
  need(JSON.stringify(d.charmera_colors?.names)==='["RED","YELLOW","BLUE","GRAY"]'&&JSON.stringify(d.charmera_colors.value_icons)===JSON.stringify([0,1,2,3].map(i=>(manifest.sd_library?756:750)+i))&&d.charmera_colors.scale_icon===(manifest.sd_library?760:754),'native Charmera enum differs');
  for(const [maximum,target,color,anime] of [...[8,3,2,1].map(n=>[n,d.sliders[n],false]),[3,d.charmera_colors.slider,true,false]]){
   const start=0x531acfec,stop=0x531ad12c,code=read(target,stop-start+8),mapped=a=>target+a-start+(a>=0x531ad0b4?8:0);
   for(let a=start;a<stop;a+=4){
    const at=mapped(a);let word=raw.readUInt32LE(a-LOAD);
    if((word&0x0e000000)===0x0a000000){let delta=(word&0xffffff)<<2;if(delta&0x2000000)delta-=0x4000000;let to=a+8+delta;if(to>=start&&to<=stop)to=mapped(to);word=((word&0xf0000000)|((word&0x1000000)?0x0b000000:0x0a000000)|(((to-at-8)>>2)&0xffffff))>>>0;}
    if(a===0x531ad01c)word=0xe1a00006;
    if(a===0x531ad020)word=branch(at,d.entries.default,true);
    if(a===0x531ad024)word=0xe1a00000;
    if(a===0x531ad03c&&maximum===3)word=0xe3a03039;
    if(a===0x531ad03c&&color)word=movw(3,manifest.sd_library?760:754);
    if(a===0x531ad060)word=(0xe3a02000|maximum)>>>0;
    if(a===0x531ad064)word=movw(3,360/maximum);
    need(code.readUInt32LE(at-target)===word,'native detail slider relocation differs at '+a.toString(16)+' expected '+word.toString(16)+' got '+code.readUInt32LE(at-target).toString(16));
   }
   const guard=0x531ad0b4-start;
   need(code.readUInt32LE(guard)===0xe3500000&&code.readUInt32LE(guard+4)===(branch(target+guard+4,mapped(0x531ad110))&0x0fffffff),'native detail null guard differs');
  }
 }
}
function checkIspBase(runtime,manifest) {
 const m=manifest.isp_base, base=manifest.base;
 need(m?.schema==='m10v-gr3-isp-base/v2'&&m.bytes===504&&m.base%16===0&&m.base>=base&&m.base+504<=base+runtime.length&&
  m.base_tone===11&&m.still_vtable===0x53dbd8a0&&m.live_vtable===0x53dbd938&&m.live_view==='standard'&&m.still_plan_return===0x53513620&&JSON.stringify(m.carriers)===(manifest.appended_slots?'[25,26,27,28,29,30,31,32,33,34]':'[12,18,19,20,21]'), 'native ISP base contract differs');
 need(Object.keys(m.entries||{}).sort().join('|')===ispHooks.map(h=>h[4]).sort().join('|')&&m.patches?.length===5,'native ISP inventory differs');
 for(const [i,[address,expected,reg,object,name]] of ispHooks.entries()) {
  const at=m.base+i*104, off=4+reg*4, compare=name==='local_process'?0x53513620:0x53dbd8a0;
  need(m.entries[name]===at&&JSON.stringify(m.patches[i])===JSON.stringify({address,expected,entry:at}),'native ISP entry differs');
  const words=[0xe92d500f,0xe10fc000,0xe52dc004,expected,(0xe58d0000|(reg<<12)|off)>>>0,object,
   movw(1,compare&65535),(0xe3401000|(((compare>>>16)&0xf000)<<4)|((compare>>>16)&0xfff))>>>0,
   0xe1500001,0x1a000007,0xe59d2000|off,0xe352000c,0x0a000002,0xe2422012,0xe3520003,0x8a000001,
   0xe3a0200b,0xe58d2000|off,0xe49dc004,0xe12cf00c,0xe8bd500f];
  if(manifest.appended_slots){words.splice(11,5,0xe2422019,0xe3520009,0x8a000003,0xe320f000,0xe320f000);if(name==='parameters')words[16]=0xe3a02019;}
  if(name!=='local_process')words.splice(9,0,0x0a000003,movw(1,0xd938),0xe34513db,0xe1500001);
  words.push(branch(at+words.length*4,address+4));
  for(const [j,word] of words.entries())need(runtime.readUInt32LE(at-base+j*4)===(word>>>0),'native ISP instruction differs: '+name+'+'+j*4);
 }
}
function lifecyclePatches(manifest,runtime){
 const m=manifest.capture_lifecycle;if(!m)return [];
 const inRuntime=a=>Number.isInteger(a)&&!(a&3)&&a>=manifest.base&&a<manifest.base+manifest.code_bytes;
 need((manifest.debug_mode===true||manifest.experimental_capture?.native_color===true)&&m.owner?.schema===2&&m.owner.storage?.recipe_bytes===0x4778&&m.owner.storage?.extended_recipe_bytes===0x5150&&m.owner.storage?.trace_offset===0x4778&&m.owner.storage?.color_offset===0x4a08&&m.owner.storage?.stamp_offset===0x5140&&m.owner.storage?.stamp_bytes===16&&m.buffer_policy_changed===false,'invalid recipe lifetime contract');
 const calls=[[0x53523e0c,0x5351091c,'m10v_save_trace_recipe_alloc'],
  ...[0x535153ec,0x53516e14,0x53516ebc,0x5351897c,0x5351af20,0x5351feb4].map(a=>[a,0x535216d0,'m10v_save_trace_recipe_allocate']),
  ...[0x5351703c,0x535170cc,0x535182f8,0x5351f3a8,0x5351fd50].map(a=>[a,0x53521d14,'m10v_save_trace_recipe_release'])];
 const expected=calls.map(([address,original,name])=>{
  const target=m.owner.exports?.[name];need(inRuntime(target),'recipe trace target outside runtime');
  return {address,expected:branch(address,original,true),replacement:branch(address,target,true),name};
 });
 const setter=m.owner.exports?.m10v_save_trace_recipe_set;need(inRuntime(setter),'recipe setter outside runtime');
 expected.push({address:0x53d0fd00,expected:0x5350d7e8,replacement:setter,name:'recipe raw setter'});
 need(m.jpeg?.patches?.length===2,'missing JPEG lifetime borders');
 for(const [i,address,word,link] of [[0,0x535048ec,0xe51b5060,false],[1,0x53504948,branch(0x53504948,0x536bbc30,true),true]]){
  const row=m.jpeg.patches[i];need(row.address===address&&inRuntime(row.entry),'invalid JPEG lifetime hook');
  expected.push({address,expected:word,replacement:branch(address,row.entry,link),name:'JPEG lifetime '+row.event});
 }
 if(m.file){
 need(m.file?.patches?.length===4&&m.file.owner?.extended_frame_sub===0x34&&m.file.owner?.pointer_fp_offset===-0x50&&m.file.callback_filesystem_calls===0,'invalid file trace ownership');
 expected.push({address:0x534e87a4,expected:0xe24dd024,replacement:0xe24dd034,name:'file caller owned trace pointer'});
 for(const [address,original,name]of [[0x534e8828,0x534eb8b4,'m10v_file_trace_prewrite'],[0x534eba44,0x534ecb3c,'m10v_file_trace_bridge'],[0x534e8834,0x534eb7e4,'m10v_file_trace_postcleanup']]){
  const target=m.file.exports?.[name];need(inRuntime(target),'file trace target outside runtime');
  expected.push({address,expected:branch(address,original,true),replacement:branch(address,target,true),name});
 }
 }else need(manifest.experimental_capture?.native_color===true,'file trace absent without native pipeline');
 if(m.module_dispatch){
  need(m.module_dispatch.patches?.length===3&&m.raw_lifetime_attestation===true,'invalid module/raw lifetime contract');
  for(const [address,word,name,link]of [[0x53505d78,0xe12fff39,'m10v_module_trace_pre',true],[0x53505d7c,0xe51b7034,'m10v_module_trace_post',false],[0x53505dbc,0xe5950010,'m10v_module_trace_sink',false]]){
   const target=m.module_dispatch.exports?.[name];need(inRuntime(target),'module target outside runtime');
   expected.push({address,expected:word,replacement:branch(address,target,link),name});
  }
  const target=m.pool_release?.exports?.m10v_pool_release_return;
  need(inRuntime(target)&&m.pool_release.stock_call_preserved===0x53521e14&&m.pool_release.filesystem_calls===0&&m.pool_release.patches?.length===1,'invalid pool release observer');
  expected.push({address:0x53521e18,expected:0xe58d5008,replacement:branch(0x53521e18,target),name:'raw pool dispatch return'});
 }
 if(m.snapshot){
  const o=m.snapshot.stamp_orientation;
  need(o?.source==='this recipe ShootingInfo +0xc8'&&o.shooting_pointer_offset===0x44c8&&o.field_offset===0xc8&&
    JSON.stringify(o.normalized_directions)==='[0,1,2,3]'&&JSON.stringify(o.exif_mapping)==='[1,8,3,6]'&&o.unknown_direction===0&&
    o.freeze==='first original processing-task producer before enqueue'&&o.live_direction_reads===0&&o.stamp_offset===0x5140&&o.stamp_bytes===16&&o.extended_recipe_bytes===0x5150&&o.exif_table===0x53d30190&&
    JSON.stringify(o.guard_words)===JSON.stringify({'0x53491528':'0xe5d000c8','0x53491530':'0xe5c010c8','0x534322f0':'0xe2524000','0x53432360':'0xe5c41946','0x535f63d0':'0xe28320c8','0x535f63d4':'0xe5842014','0x535f67ac':'0xe5923014','0x535f67b0':'0xe5d33000'}),'invalid per-exposure stamp orientation contract');
  need((m.snapshot.observer===true||(manifest.experimental_capture?.native_color===true&&m.snapshot.native_color===true&&m.snapshot.observer===false))&&m.snapshot.snapshot_ingress_installed===true&&m.snapshot.isp_filesystem_calls===0&&m.snapshot.color_bytes===1796&&m.snapshot.patches?.length===2+(m.snapshot.shared_hdf?2:0)+(m.snapshot.live_color?1:0),'invalid frame snapshot contract');
  need(m.snapshot.producer_sites?.length===1&&m.snapshot.producer_sites[0]===0x5351ea9c&&m.snapshot.filesystem_calls===0,'snapshot must freeze at processing-task submission without storage');
  for(const [i,address,word,link]of [[0,0x53501d68,0xe12fff33,true],[1,0x5351ea9c,0xe1a0c00d,false],...(m.snapshot.shared_hdf?[[2,0x5351aed4,0xe59420f0,false],[3,0x5351b068,0xe59420f0,false]]:[])]){
   const row=m.snapshot.patches[i];need(row.address===address&&inRuntime(row.entry),'invalid snapshot hook');
   expected.push({address,expected:word,replacement:branch(address,row.entry,link),name:'per-frame snapshot '+address.toString(16)});
  }
  const at=m.snapshot.patches[1].entry,helper=m.snapshot.exports.m10v_isp_frame_recipe_producer;
  need(inRuntime(helper),'snapshot submission helper outside runtime');
  const words=[0xe92d5fff,0xe10fc000,0xeef1ea10,0xe92d5000,0xed2d0b20,0xed6d0b20,0xe1a00001,branch(at+28,helper,true),0xecfd0b20,0xecbd0b20,0xe8bd5000,0xeee1ea10,0xe128f00c,0xe8bd5fff,0xe1a0c00d,branch(at+60,0x5351eaa0)];
  words.forEach((word,i)=>need(runtime.readUInt32LE(at-manifest.base+i*4)===(word>>>0),'snapshot submission wrapper instruction differs'));
  if(m.snapshot.shared_hdf){
   const reserve=manifest.symbols.m10v_hdf_reserve,freeze=manifest.symbols.m10v_hdf_task_snapshot;
   need(inRuntime(reserve)&&inRuntime(freeze),'HDF task ownership helper outside runtime');
   for(const row of m.snapshot.patches.slice(2,4)){
    const a=row.entry,shim=[0xe92d5fff,0xe10fc000,0xe92d5000,0xe59400f0,branch(a+16,reserve,true),0xe8bd5000,0xe128f00c,0xe8bd5fff,0xe59420f0,branch(a+36,row.address+4)];
    shim.forEach((w,i)=>need(runtime.readUInt32LE(a-manifest.base+i*4)===(w>>>0),'HDF reservation must reset without freezing settings'));
   }
   let callsFreeze=false;
   for(let i=0;i<Math.min(256,manifest.base+runtime.length-helper);i+=4){
    const w=runtime.readUInt32LE(helper-manifest.base+i);if(w>>>24!==0xeb)continue;
    let d=(w&0xffffff)<<2;if(d&0x2000000)d-=0x4000000;
    if(helper+i+8+d===freeze)callsFreeze=true;
   }
   need(callsFreeze,'actual task producer must freeze HDF before color admission');
  }
 }
 if(m.snapshot?.live_color){
  need(manifest.sd_library&&manifest.settings_menu?.owner_bytes===0x223c,'preview requires owned parameter cache');
  const row=m.snapshot.patches.at(-1);need(row.address===0x53dbd954&&inRuntime(row.entry),'invalid Live Make entry');
  expected.push({address:0x53dbd954,expected:0x536ddecc,replacement:row.entry,name:'native Live Make color'});
  const at=row.entry,ex=m.snapshot.exports;
  const words=[0xe92d500f,branch(at+4,ex.m10v_isp_frame_live_prepare,true),0xe8bd500f,0xe92d4070,0xe1a04000,0xe1a05001,branch(at+24,0x536ddecc,true),0xe92d5fff,0xe10fc000,0xeef1ea10,0xe92d5000,0xed2d0b20,0xed6d0b20,0xe1a00004,0xe1a01005,branch(at+60,ex.m10v_isp_frame_live_color,true),0xecfd0b20,0xecbd0b20,0xe8bd5000,0xeee1ea10,0xe128f00c,0xe8bd5fff,0xe8bd8070];
  need(inRuntime(ex.m10v_isp_frame_live_prepare)&&inRuntime(ex.m10v_isp_frame_live_color),'preview helpers outside runtime');
  words.forEach((word,i)=>need(runtime.readUInt32LE(at-manifest.base+i*4)===(word>>>0),'Live Make wrapper instruction differs'));

 }

 if(m.native_grain){
  need(manifest.experimental_capture?.native_grain===true&&m.native_grain.patches?.length===4&&m.native_grain.independent_dma===false&&m.native_grain.filesystem_calls===0,'invalid native grain stage');
  for(const [i,address,word,link]of [[0,0x53513620,0xe1a00004,false],[1,0x535033d8,0xebffff1b,true],[2,0x53503aa0,0xebfffd69,true],[3,0x53503ab4,0xeb05f4c0,true]]){
   const row=m.native_grain.patches[i];need(row.address===address&&inRuntime(row.entry),'invalid grain hook');expected.push({address,expected:word,replacement:branch(address,row.entry,link),name:'native grain '+address.toString(16)});
  }
  need(!m.native_grain_noise&&m.native_grain.cpu_noise_processing===false&&m.native_grain.software_fallback===false,'retired CPU grain processing must not be installed');
 }
 if(m.view_deferred){
  const v=m.view_deferred;need(v.patches?.length===6&&v.mutable_global_bytes===0&&v.filesystem_calls===0&&v.storage?.token_offset===0x184&&v.storage.extended_bytes===0x194,'invalid view recovery ownership');
  expected.push({address:0x531709fc,expected:0xe3a00f61,replacement:0xe3000194,name:'QuickView owner extension'});
  for(const [address,word,name,link]of [[0x531cbdf0,0xe5c0316c,'m10v_view_hook_enter',false],[0x5323abf8,0xe5c0202f,'m10v_view_hook_capture',false],[0x53239bc0,0xe5c43030,'m10v_view_hook_reply',false],[0x53236768,branch(0x53236768,0x532288b0,true),'m10v_view_hook_producer',true],[0x531cc1cc,branch(0x531cc1cc,0x531cbe78,true),'m10v_view_deferred_on_169',true]]){
   const target=v.exports?.[name];need(inRuntime(target),'view recovery outside runtime');expected.push({address,expected:word,replacement:branch(address,target,link),name});
  }
 }
 need(m.patches?.length===expected.length,'unexpected lifetime patch inventory');
 for(let i=0;i<expected.length;i++){
  const row=m.patches[i],want=expected[i];
  need(row.address===want.address&&/^[0-9a-f]{8}$/.test(row.expected_hex)&&/^[0-9a-f]{8}$/.test(row.replacement_hex)&&Buffer.from(row.expected_hex,'hex').readUInt32LE()===want.expected&&Buffer.from(row.replacement_hex,'hex').readUInt32LE()===want.replacement,'lifetime patch differs');
 }
 return expected;
}
function appendedSlotPatches(runtime,manifest,raw) {
 const m=manifest.appended_slots;if(!m)return [];
 need(manifest.sd_library&&manifest.film_library_enabled!==false&&m.schema==='m10v-gr3-appended-slots/v2'&&
  JSON.stringify(m.tones)==='[25,26,27,28,29,30,31,32,33,34]'&&m.stock_choices===12&&m.shooting_choices==='12+enabled_films'&&m.shooting_choices_max===22&&
  m.library_index==='14+enabled_films'&&m.stock_parameter_proxy===false&&m.state_version===5,'invalid appended slot contract');
 const read=(at,n)=>{need(Number.isInteger(at)&&!(at&3)&&at>=manifest.base&&at+n<=manifest.base+runtime.length,'appended code outside runtime');return runtime.subarray(at-manifest.base,at-manifest.base+n);};
 read(m.base,m.bytes);
 const rows=[[0x532c2a9c,0xe1a0c00d,'count'],[0x532c2c80,0xe1a0c00d,'index'],
  [0x532c2f08,0xe1a0c00d,'position'],[0x532c2b7c,0xe30d3368,'maximum'],
  [0x5326c240,branch(0x5326c240,0x5326c2a0),'display']];
 const dynamicCount=manifest.symbols.m10v_camera_library_shooting_count;read(dynamicCount,4);
 const exact=(name,words)=>{const body=read(m.entries[name],words.length*4);need(words.every((w,i)=>body.readUInt32LE(i*4)===(w>>>0)),'appended '+name+' instructions differ');};
 const at=(name,i)=>m.entries[name]+i*4;
 exact('count',[0xe5d0c01b,0xe35c0000,0x1a000002,0xe92d4010,branch(at('count',4),dynamicCount,true),0xe8bd8010,0xe1a0c00d,branch(at('count',7),0x532c2aa0)]);
 exact('index',[0xe5d0c01b,0xe35c0000,0x1a00000c,0xe92d4070,0xe1a04000,0xe1a05001,branch(at('index',6),dynamicCount,true),0xe355000c,0x3a000003,0xe1550000,0x3245000c,0x32800019,0x38bd8070,0xe1a00004,0xe1a01005,0xe8bd4070,0xe1a0c00d,branch(at('index',17),0x532c2c84)]);
 exact('position',[0xe5d0c01b,0xe35c0000,0x1a00000b,0xe92d4070,0xe1a04000,0xe1a05001,branch(at('position',6),dynamicCount,true),0xe240000c,0xe245c019,0xe15c0000,0x328c000c,0x38bd8070,0xe1a00004,0xe1a01005,0xe8bd4070,0xe1a0c00d,branch(at('position',16),0x532c2f0c)]);
 exact('maximum',[branch(at('maximum',0),dynamicCount)]);
 exact('display',[0xe2430019,0xe350000a,0x31a00003,((branch(at('display',3),0x5326c22c)&0x0fffffff)|0x30000000),branch(at('display',4),0x5326c2a0)]);
 const patches=rows.map(([address,expected,name])=>{read(m.entries[name],4);return {address,expected,replacement:branch(address,m.entries[name]),name:'appended '+name};});
 for(const [address,old,name] of [[0x531ab7a8,0x532a985c,'menu_name'],[0x531ab894,0x532a9988,'menu_icon'],[0x531ab8bc,0x532a9988,'menu_icon'],[0x531a05ac,0x532c2c80,'index'],[0x531a070c,0x532c2c80,'index'],[0x531a0588,0x532a985c,'adj_name'],[0x531a06e0,0x532a9988,'adj_icon']]){const to=manifest.symbols['m10v_tone_menu_'+name];read(to,4);patches.push({address,expected:branch(address,old,true),replacement:branch(address,to,true),name:'appended visible '+name});}
 for(const [address,name] of [[0x531abe0c,'menu_matches'],[0x531a1500,'adj_matches'],[0x531a0ba0,'adj_select']]){const to=manifest.symbols['m10v_tone_menu_'+name];read(to,4);patches.push({address,expected:0xe1a0c00d,replacement:branch(address,to),name:'appended visible '+name});}
 need(m.exif_bytes===88,'appended EXIF capacity differs');
 const table=read(m.exif_table,88);
 if(raw)need(table.subarray(0,48).equals(raw.subarray(0xd2b6f4,0xd2b724)),'stock EXIF pairs changed');
 for(let i=0;i<10;i++)need(table.readUInt32LE(48+i*4)===((0x10c+i)<<16|25+i),'appended EXIF mapping differs');
 const movt=(r,v)=>(0xe3400000|((v&0xf000)<<4)|(r<<12)|(v&0xfff))>>>0;
 for(const [address,expected,replacement] of [
  [0x53599df4,0xe3a00030,0xe3a00058],[0x53599e20,0xe30bc6f4,movw(12,m.exif_table&65535)],
  [0x53599e2c,0xe345c3d2,movt(12,m.exif_table>>>16)],[0x53599e30,0xe2801030,0xe2801058],
  [0x53599e4c,0xe353000c,0xe3530016],[0x53599e60,0xe2800030,0xe2800058],
 ])patches.push({address,expected,replacement,name:'appended EXIF '+address.toString(16)});
 const playback=m.playback;
 need(playback?.icon_id===754&&playback.metadata_key===0x25&&JSON.stringify(playback.recorded_codes)==='[268,277]'&&playback.identity==='recorded-slot-generic-film','playback identity contract differs');
 const checkPlayback=(name,words)=>{const start=playback[name],body=read(start,words.length*4);words.forEach((w,i)=>{if(Array.isArray(w))w=branch(start+4*i,w[0],true);need(body.readUInt32LE(4*i)===(w>>>0),'playback '+name+' instructions differ');});};
 checkPlayback('icon',[0xe92d4010,[0x532b6eec],0xe3500000,0x1a00000a,[0x5320ad88],[0x5320b97c],0xe3500000,0x0a000006,0xe5902220,0xe300c00c,0xe340c001,0xe042200c,0xe3520009,0x930002f2,0x83a00000,0xe8bd8010]);
 checkPlayback('detail',[0xe92d4013,[0x532b44bc],0xe3500000,0x1a00000b,0xe59d2000,0xe5922220,0xe300c00c,0xe340c001,0xe042200c,0xe3520009,0x8a000004,0xe59d1004,0xe3510000,0x13a0200b,0x15c12000,0xe3a00001,0xe28dd008,0xe8bd8010]);
 for(const [address,expected,name] of [[0x53179b7c,0xeb04f4da,'icon'],[0x532b7cfc,0xebfff1ee,'detail']])patches.push({address,expected,replacement:branch(address,playback[name],true),name:'recorded film playback '+name});
 need(m.patches.length===patches.length&&patches.every((p,i)=>p.address===m.patches[i].address&&p.expected===m.patches[i].expected&&p.replacement===m.patches[i].replacement),'appended patch inventory differs');
 return patches;
}
function patchList(manifest,runtime) {
  const abHooks=abPatches(manifest).filter(p=>!manifest.hdf_adj||p.address!==0x531a4db8);
  const table=manifest.icons.table, movt=(reg,v)=>(0xe3400000|((v&0xf000)<<4)|(reg<<12)|(v&0xfff))>>>0;
  const iconPatches=[[0x53209fcc,0xe30230fc,3,false],[0x53209fd0,0xe3453500,3,true],[0x5320a000,0xe30230fc,3,false],[0x5320a004,0xe3453500,3,true],[0x5320a804,0xe30220fc,2,false],[0x5320a808,0xe3452500,2,true]].map(([address,expected,reg,upper])=>({address,expected,replacement:upper?movt(reg,table>>>16):movw(reg,table&65535),name:'M10V icon directory '+address.toString(16)}));
  if(manifest.sd_library){
    const names=new Map([[0x53209fcc,'width'],[0x5320a000,'height'],[0x5320a804,'draw']]);
    for(const p of iconPatches){
      if(names.has(p.address))p.replacement=branch(p.address,manifest.film_cards.directory_hooks[names.get(p.address)]);
      else p.replacement=0xe1a00000;
    }
  }
  for(const [address,expected,reg] of [[0x53209fb8,0xe300329e,3],[0x53209fec,0xe300329e,3],[0x5320a7cc,0xe300129e,1]])iconPatches.push({address,expected,replacement:movw(reg,manifest.icons.catalog_count-1),name:'M10V icon maximum '+address.toString(16)});
  const detailPatches=detailHooks.map(([address,expected,name,link])=>({address,expected,replacement:branch(address,manifest.detail.entries[name],link),name:'native detail '+name}));
  detailPatches.push({address:0x531b0248,expected:0xe3043bd8,replacement:movw(3,manifest.detail.captions&65535),name:'detail captions low'},{address:0x531b024c,expected:0xe34533b3,replacement:movt(3,manifest.detail.captions>>>16),name:'detail captions high'});
  if(manifest.film_library_enabled===false){
    need(manifest.sd_library&&manifest.hdf_menu,'independent HDF menu required');
    return [...appendedSlotPatches(runtime,manifest),...abHooks,...hdfPatches(runtime,manifest),...hdfMenuPatches(runtime,manifest),...hdfAdjPatches(runtime,manifest),...(manifest.hdf_adj?iconPatches:[]),
      ...hooks.filter(row=>row[2].startsWith('m10v_resource_')||(manifest.hdf_adj&&row[2]==='m10v_icon_pixels')).map(([address,expected,name,link])=>({address,expected,replacement:branch(address,manifest.symbols[name],link),name})),
      {address:0x533966d4,expected:0xe3003311,replacement:movw(3,manifest.resources.last_id),name:'resource bound primary'},
      {address:0x533970ec,expected:0xe3003311,replacement:movw(3,manifest.resources.last_id),name:'resource bound secondary'}];
  }
  return [...zoomPatches(runtime,manifest),...appendedSlotPatches(runtime,manifest),...abHooks,...hdfPatches(runtime,manifest),...hdfAdjPatches(runtime,manifest),...lifecyclePatches(manifest,runtime),...ispHooks.map(([address,expected,,,name])=>({address,expected,replacement:branch(address,manifest.isp_base.entries[name]),name:'Standard still ISP '+name})),...(manifest.hdf_menu?hdfMenuPatches(runtime,manifest):settingsPatches(manifest)),...detailPatches,...iconPatches,...hooks.map(([address,expected,name,link])=>({address, expected,
    replacement:branch(address,manifest.symbols[name],link),name})),
    {address:0x533966d4,expected:0xe3003311,replacement:movw(3,manifest.resources.last_id),name:'resource maximum primary'},
    {address:0x533970ec,expected:0xe3003311,replacement:movw(3,manifest.resources.last_id),name:'resource maximum secondary'},
    ...(manifest.sd_library?[]:[{address:0x531abd24,expected:0xe300110a,replacement:movw(1,823),name:'M10V menu title'}])];
}
function sectionMap(decoded, report, growth=0) {
  let offset=0; const rows=[];
  for (const original of report.sections) {
    const size=original.size+(original.name==='RTOS'?growth:0);
    need(decoded.toString('ascii',offset,offset+8).split('\0')[0]===original.name && offset+size<=decoded.length-4,
      'native section boundaries differ');
    rows.push({name:original.name,offset,size}); offset+=size;
  }
  need(offset+4===decoded.length,'native decoded trailer position differs'); return rows;
}
function encodeExtended(source, original, target, insertion, growth) {
  const frames=decodeFrameMap(source).frames, chunks=[];
  for (const frame of frames) {
    const start=frame.decoded_start+(frame.decoded_start>insertion?growth:0);
    const end=frame.decoded_end+(frame.decoded_end>insertion?growth:0);
    const bytes=target.subarray(start,end), old=original.subarray(frame.decoded_start,frame.decoded_end);
    // Back references may cross frame boundaries. Reuse only when the entire
    // The codec has a 13-bit (8191-byte) backward-reference window.
    const history=Math.min(8191,frame.decoded_start);
    const sameHistory=target.subarray(start-history,start).equals(original.subarray(frame.decoded_start-history,frame.decoded_start));
    if(bytes.equals(old)&&sameHistory) chunks.push(source.subarray(128+frame.encoded_start,128+frame.encoded_end));
    else for(let at=0;at<bytes.length;at+=0x6000){
      const part=bytes.subarray(at,at+0x6000),prefix=Buffer.alloc(2);
      prefix.writeUInt16BE(0x8000|part.length);chunks.push(prefix,part);
    }
  }
  chunks.push(Buffer.alloc(2)); const payload=Buffer.concat(chunks),footer=Buffer.from(source.subarray(-24));
  footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(target.length,16);footer.writeUInt32LE(0,20);
  const candidate=Buffer.concat([source.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);
  candidate.writeUInt32LE(-sum32(candidate)>>>0,candidate.length-4);
  need(decodeFrameMap(candidate,target.length).decoded.equals(target),'native fresh decode differs'); return candidate;
}
export function buildNativeLibrary(source,runtime,manifest) {
  const BASE=manifest?.base;
  const report=inspectOfficial(source);need(report.model==='GR III','native detail requires exact GR III 2.10 official source');checkRuntime(runtime,manifest);
  const {decoded}=decodeFrameMap(source),rows=sectionMap(decoded,report),rtos=rows.find(row=>row.name==='RTOS');
  const programOffset=BASE-LOAD,newPayload=programOffset+runtime.length;
  // The bounded allowance includes all immutable LUT/icon banks and native profiles.
  // Mapping/readback/section preservation checks below still cover the whole extent.
  const growth=newPayload-(rtos.size-16);need(growth>0&&growth<=MAX_NATIVE_RTOS_GROWTH,`native RTOS growth invalid: ${growth} bytes exceeds budget ${MAX_NATIVE_RTOS_GROWTH}`);
  const insertion=rtos.offset+rtos.size;
  const target=Buffer.concat([decoded.subarray(0,insertion),Buffer.alloc(growth),decoded.subarray(insertion)]);
  target.writeUInt32LE(newPayload,rtos.offset+12);
  runtime.copy(target,rtos.offset+16+programOffset);
  for(const patch of patchList(manifest,runtime)) {
    const at=rtos.offset+16+patch.address-LOAD;
    need(decoded.readUInt32LE(at)===patch.expected,'official native hook preimage differs: '+patch.name);
    target.writeUInt32LE(patch.replacement,at);
  }
  target.writeUInt32LE(0,target.length-4);target.writeUInt32LE(-sum32(target)>>>0,target.length-4);
  const candidate=encodeExtended(source,decoded,target,insertion,growth);
  return {candidate,receipt:auditNativeLibrary(source,candidate,runtime,manifest)};
}
export function auditNativeLibrary(source,candidate,runtime,manifest) {
  const BASE=manifest?.base;
  const report=inspectOfficial(source);need(report.model==='GR III','native detail requires exact GR III 2.10 official source');checkRuntime(runtime,manifest);
  const structural=auditGr3Candidate(source,candidate,{maxRtosGrowth:MAX_NATIVE_RTOS_GROWTH});
  const before=decodeFrameMap(source).decoded,after=decodeFrameMap(candidate,candidate.readUInt32LE(candidate.length-8)).decoded;
  const oldRows=sectionMap(before,report),newRows=sectionMap(after,report,structural.rtosGrowth);
  const old=oldRows.find(row=>row.name==='RTOS'),fresh=newRows.find(row=>row.name==='RTOS');
  const raw=before.subarray(old.offset+16,old.offset+old.size);
  checkDetail(runtime,manifest,raw);
  appendedSlotPatches(runtime,manifest,raw);
  const stockDirectory=raw.subarray(0x107b540+0x20fc,0x107b540+0x20fc+671*4);
  need(stockDirectory.equals(runtime.subarray(manifest.icons.table-BASE,manifest.icons.table-BASE+671*4)),'official icon directory differs');
  const table=raw.readUInt32LE(0x434)-LOAD,domains=raw.readUInt32LE(0x438);
  for(let address=BASE;address<BASE+runtime.length;address=(address&0xfff00000)+0x100000){
    const descriptor=raw.readUInt32LE(table+(address>>>20)*4),domain=(descriptor>>>5)&15;
    need((descriptor&3)===2&&!(descriptor&16)&&((descriptor>>>10)&3)===2&&(descriptor&(1<<15))&&((domains>>>(domain*2))&3)===1&&
      (descriptor>>>20)===(address>>>20),'native full runtime/data mapping differs');
  }

  need(fresh.size-16===BASE-LOAD+runtime.length,'native RTOS extent differs');
  need(after.readUInt32LE(fresh.offset+8)===before.readUInt32LE(old.offset+8),'native RTOS flags differ');
  const expected=Buffer.from(before.subarray(old.offset+16,old.offset+old.size));
  for(const patch of patchList(manifest,runtime)) {
    const at=patch.address-LOAD;
    need(expected.readUInt32LE(at)===patch.expected,'native audit stock preimage differs');
    expected.writeUInt32LE(patch.replacement,at);
  }
  need(after.subarray(fresh.offset+16,fresh.offset+old.size).equals(expected),'native RTOS non-target bytes changed');
  const padding=after.subarray(fresh.offset+old.size,fresh.offset+16+BASE-LOAD);
  need(padding.every(value=>value===0),'native extension gap is not zero');
  need(after.subarray(fresh.offset+16+BASE-LOAD,fresh.offset+fresh.size).equals(runtime),'native full module readback differs');
  for(let i=0;i<oldRows.length;i++)if(oldRows[i].name!=='RTOS') {
    const a=oldRows[i],b=newRows[i];need(after.subarray(b.offset,b.offset+b.size).equals(before.subarray(a.offset,a.offset+a.size)),
      'native changed unrelated section '+a.name);
  }
  for(const [a,b] of [[0x620000,0x640000],[0x820000,0x840000],[0x2038,0x203c]])
    need(after.subarray(fresh.offset+16+a,fresh.offset+16+b).equals(before.subarray(old.offset+16+a,old.offset+16+b)),
      'native updater/version protection differs');
  return {schema:'m10v-gr3-native-library-candidate/v2',source_sha256:report.sha256,candidate_sha256:sha(candidate),
    candidate_bytes:candidate.length,runtime_sha256:sha(runtime),runtime_bytes:runtime.length,
    rtos_growth:structural.rtosGrowth,changed_sections:structural.changedSections,
    verified_hooks:patchList(manifest,runtime).length,universal_halation:manifest.universal_halation?{modes:['off','spill','streak'],per_film:true,default:'off',special_spill_films:[33,67],camera_tested:false}:null,film_library_enabled:manifest.film_library_enabled!==false,digital_hdf:manifest.hdf_enabled?{menu:'MENU > 设置 > HDF 模拟',scope:'global; independent of film library',journal:['M10VHD0.BIN','M10VHD1.BIN'],native:'original Clarity pyramid',adj:manifest.hdf_adj?{function_id:20,original_functions_preserved:20,levels:['off','weak','medium','strong'],assignment:'user chooses an existing ADJ slot'}:null,camera_tested:false}:null,icon_count:manifest.film_library_enabled===false?0:manifest.film_count,icon_dimensions:[40,40],icon_storage:'embedded RTOS; original ICONBIN unchanged',mapping_verified:true,state_version:5,film_count:manifest.film_library_enabled===false?0:manifest.film_count,active_slots:manifest.film_library_enabled===false?0:Array.from({length:10},(_,i)=>Buffer.from(manifest.initial_state_hex,'hex').readUInt16LE(12+i*8)).filter(Boolean).length,external_film_pack:manifest.film_library_enabled!==false&&manifest.sd_library,sd_film_library:manifest.film_library_enabled!==false&&manifest.sd_library?{format:2,accepted_formats:[1,2],path:"M10V/FILMS.M10",supported_films:FILM_DIRECTORY.length,max_records:256,custom_lut:true,page_rows:10}:null,
    stamp_orientation:manifest.capture_lifecycle?.snapshot?.stamp_orientation?{source:'per-exposure ShootingInfo',directions:[0,90,180,270],default:'automatic',image_rotation:false,camera_tested:false}:null,
    menu_entry:manifest.film_library_enabled===false?'MENU > 设置 > HDF 模拟':manifest.sd_library?'MENU > 设置 > 胶卷库 / 水印 / 效果':'MENU > Image Control > M10V Library',appended_slots:manifest.appended_slots?{tones:Array.from({length:10},(_,i)=>25+i),stock_choices:12,shooting_choices:'12+enabled_films',capacity:10,stock_presets_preserved:true}:null,adj_scope:manifest.appended_slots?'12 stock choices plus up to ten selected M10V films':'12 stock entries only; no private IDs',
    still_isp_base:manifest.film_library_enabled===false?null:{tone:11,carriers:manifest.appended_slots?Array.from({length:10},(_,i)=>25+i):[12,18,19,20,21],verified_dispatches:5,shooting_tone_preserved:true},
    live_view_base:manifest.film_library_enabled===false?null:{tone:11,carriers:manifest.appended_slots?Array.from({length:10},(_,i)=>25+i):[12,18,19,20,21],film_color_preview:!!manifest.capture_lifecycle?.snapshot?.live_color},
    camera_tested:false,debug_mode:manifest.debug_mode,debug_log:manifest.debug_log,status:'OFFLINE_VERIFIED_EXPERIMENTAL_CANDIDATE',
    camera_scope:manifest.film_library_enabled===false?'still JPEG digital HDF only; original ImageControl, LiveView, RAW and metadata preserved':manifest.capture_lifecycle?.snapshot?.live_color?'still JPEG; native live color initialized at normal UI live entry; preview excludes grain/halo; RAW pixels protected':'still JPEG; original RAW pixels protected; live view uses Standard base; film-color preview and RAW-development effects not integrated'};
}
