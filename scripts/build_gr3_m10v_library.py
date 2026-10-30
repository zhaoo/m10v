"""Compile and link the original M10V runtime; this emits no camera firmware."""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
FLAGS = ['--target=armv7-none-eabi', '-mcpu=cortex-a9', '-marm', '-mfloat-abi=soft',
         '-Os', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
         '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
         '-fno-vectorize', '-fno-slp-vectorize', '-Wall', '-Wextra', '-Werror']
# Saved-image CPU loops must optimize for throughput. Keep the UI/ABI modules
# size-optimized, and keep scalar soft-float ARM (no unproved NEON/FPU state).
AB_CONTROLLER_EXPORTS=tuple('m10v_settings_controller_ab_'+n for n in ['selector','mapper','live_enter','live_leave','live_destroy','live_event','adj_event','setup','render','adj_refresh','adj_exit','adj_destroy','adj_changed','dispatch'])
RENDER_FLAGS = ['-O2' if flag == '-Os' else flag for flag in FLAGS]


def capture_stock_rtos(model='gr3'):
    """Derive the locked hook preimage from the installed official input."""
    node = os.environ.get('M10V_NODE') or shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is unavailable; set M10V_NODE to its absolute executable path')
    script = "import{readFileSync}from'node:fs';import{officialResources}from'./node/gr3-stock-presets.mjs';const{decoded:d,sections:s}=officialResources(readFileSync(process.argv[1]));process.stdout.write(d.subarray(s.RTOS.offset,s.RTOS.offset+s.RTOS.size));"
    inputs={'gr3':('fwdc239b-gr3-official.bin','8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'),
            'gr3x':('fwdc243b-gr3x-official.bin','0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6')}
    if model not in inputs:raise ValueError('unsupported capture RTOS model')
    filename,expected=inputs[model]
    stock = subprocess.check_output([node,'--input-type=module','-e',script,str(ROOT/'bin'/filename)],cwd=ROOT)
    if hashlib.sha256(stock).hexdigest() != expected:
        raise ValueError('capture hooks require exact official RTOS')
    return stock


def link_object(elf, base, externals=None, prefix='m10v_library_', additional_exports=(), omitted_exports=()):
    """Bounded ELF32 ARM relocator for our freestanding .text/.rodata module.

    Unknown sections, symbols, addends or relocation kinds fail closed. This
    does not invoke or imitate any third-party camera-mod linker/template.
    """
    if elf[:7] != b'\x7fELF\x01\x01\x01' or struct.unpack_from('<HH', elf, 16) != (1, 40):
        raise ValueError('expected a relocatable little-endian ARM ELF32')
    shoff = struct.unpack_from('<I', elf, 32)[0]
    entsize, count, names_index = struct.unpack_from('<HHH', elf, 46)
    if entsize != 40 or shoff + entsize * count > len(elf) or names_index >= count:
        raise ValueError('invalid section directory')
    sections = [struct.unpack_from('<10I', elf, shoff + i * entsize) for i in range(count)]
    names_row = sections[names_index]; names = elf[names_row[4]:names_row[4] + names_row[5]]
    image_sections = []; symbols = {}; starts = {}; cursor = base; tables = {}
    for index, row in enumerate(sections):
        name = names[row[0]:].split(b'\0', 1)[0].decode('ascii')
        if row[2] & 2 and row[5]:
            if name.startswith('.ARM.exidx'): continue
            if row[1] != 1 or row[2] & 1 or not (name in ('.text', '.rodata') or name.startswith('.rodata.')) or row[8] > 16 or not row[8]:
                raise ValueError('unexpected allocated section: ' + name)
            cursor = (cursor + row[8] - 1) & ~(row[8] - 1)
            starts[index] = cursor; image_sections.append((index, row)); cursor += row[5]
            if cursor > base + 65536: raise ValueError('runtime exceeds code budget')
    image = bytearray((cursor - base + 3) & ~3)
    for index, row in image_sections:
        at = starts[index] - base
        image[at:at + row[5]] = elf[row[4]:row[4] + row[5]]
    for index, row in enumerate(sections):
        if row[1] != 2: continue
        strings_row = sections[row[6]]; strings = elf[strings_row[4]:strings_row[4] + strings_row[5]]
        table = []
        for at in range(row[4], row[4] + row[5], 16):
            n, value, size, info, other, section = struct.unpack_from('<IIIBBH', elf, at)
            symbol = strings[n:].split(b'\0', 1)[0].decode('ascii')
            if section == 0 and symbol and symbol not in (externals or {}):
                raise ValueError('undefined symbol: ' + symbol)
            address = starts[section] + value if section in starts else (externals or {}).get(symbol)
            table.append((symbol, address))
            if (symbol.startswith(prefix) or symbol in additional_exports) and info & 15 == 2 and section in starts:
                if address is None or not base <= address < base + 65536 or address & 3:
                    raise ValueError('invalid ARM entry')
                symbols[symbol] = address
        tables[index] = table
    for row in sections:
        if row[1] not in (4, 9) or not row[5] or row[7] not in starts: continue
        if row[1] != 9 or row[9] != 8 or row[6] not in tables: raise ValueError('unsupported relocation directory')
        target = row[7]
        for at in range(row[4], row[4] + row[5], 8):
            offset, info = struct.unpack_from('<II', elf, at); symbol_index, kind = info >> 8, info & 255
            if offset & 3 or offset + 4 > sections[target][5] or symbol_index >= len(tables[row[6]]):
                raise ValueError('relocation out of range')
            name, value = tables[row[6]][symbol_index]
            if value is None: raise ValueError('relocation targets unloaded section: ' + name)
            place = starts[target] + offset; out_at = place - base
            word = struct.unpack_from('<I', image, out_at)[0]
            if kind == 2:  # R_ARM_ABS32: compiler-generated local ARM switch labels only
                target_address = value + word
                text_ranges = [(starts[i], starts[i]+s[5]) for i,s in image_sections
                               if names[s[0]:].split(b'\0',1)[0] == b'.text']
                if target_address & 3 or not any(lo <= target_address < hi for lo,hi in text_ranges):
                    raise ValueError(f'absolute switch relocation leaves local ARM text: {name} value={value:#x} addend={word:#x} place={place:#x}')
                word = target_address
            elif kind in (28, 29):  # R_ARM_CALL / R_ARM_JUMP24
                if word & 0x0f000000 != (0x0b000000 if kind == 28 else 0x0a000000):
                    raise ValueError('branch relocation is not ARM B/BL')
                addend = (word & 0xffffff) << 2
                if addend & 0x02000000: addend -= 0x04000000
                delta = value + addend - place
                if delta & 3 or not -(1 << 25) <= delta < (1 << 25): raise ValueError('ARM call out of range')
                word = (word & 0xff000000) | ((delta >> 2) & 0xffffff)
            elif kind in (43, 44):  # R_ARM_MOVW_ABS_NC / R_ARM_MOVT_ABS
                expected = 0x03000000 if kind == 43 else 0x03400000
                if word & 0x0ff00000 != expected or ((word >> 4) & 0xf000) | (word & 0xfff):
                    raise ValueError('unsupported MOV relocation instruction/addend')
                immediate = value & 65535 if kind == 43 else value >> 16
                word = (word & ~0x000f0fff) | ((immediate & 0xf000) << 4) | (immediate & 0xfff)
            else: raise ValueError('unsupported ARM relocation: ' + str(kind))
            struct.pack_into('<I', image, out_at, word)
    required = {
        'm10v_zoom_': set(),  # Checked against the zoom module's explicit ABI registry.
        'm10v_border_': {'m10v_border_camera_refresh','m10v_border_camera_save','m10v_border_camera_cached','m10v_border_camera_snapshot'},
        'm10v_border_shot_': {'m10v_border_shot_freeze','m10v_border_shot_read','m10v_border_shot_orientation','m10v_border_shot_phase','m10v_border_shot_transition'},
        'm10v_isp_frame_': {'m10v_isp_frame_apply'},
        'm10v_lifecycle_': {'m10v_lifecycle_phase','m10v_lifecycle_file_flush'},
        'm10v_spatial_': {'m10v_spatial_blur_u16','m10v_spatial_grain_work_bytes','m10v_spatial_stock_grain_execute'},
        'm10v_texture_': {'m10v_texture_block8','m10v_texture_block8_cached','m10v_texture_mono_block8_cached','m10v_texture_effects_block8'},
        'm10v_halation': {'m10v_halation'},
        'm10v_5207_': {'m10v_5207_rgb','m10v_5207_render','m10v_5207_texture','m10v_5207_texture_q8','m10v_5207_texture_cached_q8','m10v_5207_texture_cached_stats_q8'},
        'm10v_curated_': {'m10v_curated_table'},
        'm10v_newstocks_': {'m10v_newstocks_table'},
        'm10v_d76_0_': {'m10v_d76_0_table'},
        'm10v_d76_1_': {'m10v_d76_1_table'},
        'm10v_style_filters_0_': {'m10v_style_filters_0_table'},
        'm10v_style_filters_1_': {'m10v_style_filters_1_table'},
        'm10v_harman_': {'m10v_harman_rgb'},
        'm10v_library_': {'m10v_library_init','m10v_library_count','m10v_library_remove', 'm10v_library_valid', 'm10v_library_name',
            'm10v_library_reset','m10v_library_detail','m10v_library_effects','m10v_library_select','m10v_library_select_custom', 'm10v_library_texture', 'm10v_library_halation', 'm10v_library_tables', 'm10v_library_stamp','m10v_library_film_name_stamp', 'm10v_library_render','m10v_library_render_native','m10v_library_render_custom','m10v_library_render_oriented'},
        'm10v_camera_library_': {'m10v_camera_library_load','m10v_camera_library_shooting_count','m10v_camera_library_menu_index','m10v_camera_library_reconcile_legacy_selection','m10v_camera_library_mutation_begin','m10v_camera_library_mutation_end','m10v_camera_library_mutation_busy','m10v_camera_library_remove', 'm10v_camera_library_select','m10v_camera_library_select_custom',
            'm10v_camera_library_preview','m10v_camera_library_preview_init','m10v_camera_library_preview_clear','m10v_camera_library_custom_profile','m10v_camera_library_reset','m10v_camera_library_detail','m10v_camera_library_effects','m10v_camera_library_texture', 'm10v_camera_library_halation', 'm10v_camera_library_stamp','m10v_camera_library_film_name_stamp'},
        'm10v_menu_': {'m10v_menu_count', 'm10v_menu_max_count', 'm10v_menu_index', 'm10v_menu_name',
            'm10v_menu_value_name', 'm10v_menu_icon', 'm10v_menu_value_icon', 'm10v_menu_focus',
            'm10v_menu_confirm', 'm10v_menu_key', 'm10v_menu_enter','m10v_menu_recorded_icon'} | ({'m10v_menu_custom_resource'} if 'm10v_sd_camera_custom_name' in (externals or {}) else set()),
        'm10v_tone_menu_': {'m10v_tone_menu_'+n for n in ['index','menu_name','menu_icon','adj_name','adj_icon','menu_matches','adj_matches','adj_select']},
        'm10v_capture_': {'m10v_capture_library'},
        'm10v_half_pair_': {'m10v_half_pair_plan','m10v_half_pair_compose'},
        'm10v_half_pair_iip_': {'m10v_half_pair_iip_ready','m10v_half_pair_iip_copy','m10v_half_pair_iip_compose'},
        'm10v_half_pair_camera': {'m10v_half_pair_camera','m10v_half_pair_reset','m10v_half_pair_init','m10v_half_pair_select','m10v_half_pair_destroy'},
        'm10v_resource_': {'m10v_resource_primary', 'm10v_resource_secondary'},
        'm10v_chain_': {'m10v_chain_capture'},
        'm10v_icon_': {'m10v_icon_pixels'},
        'm10v_film_card_': {'m10v_film_card_render','m10v_film_card_custom'},
        'm10v_sd_': {'m10v_sd_u32','m10v_sd_crc','m10v_sd_header','m10v_sd_record'},
        'm10v_sd_camera_': {'m10v_sd_camera_directory_extent','m10v_sd_camera_directory_item','m10v_sd_camera_directory_install','m10v_sd_camera_item','m10v_sd_camera_install','m10v_sd_camera_custom_record','m10v_sd_camera_custom_name','m10v_sd_camera_catalog_name'},
        'm10v_debug_': {'m10v_debug_log','m10v_debug_batch'},
        'm10v_settings_': {'m10v_settings_open','m10v_settings_key'},
        'm10v_settings_view_': {'m10v_settings_view_create','m10v_settings_view_draw','m10v_settings_view_destroy'},
        'm10v_settings_controller_': {'m10v_settings_controller_card_directory','m10v_settings_controller_owner_size','m10v_settings_controller_top_ctor','m10v_settings_controller_top_dtor','m10v_settings_controller_destroy','m10v_settings_controller_factory','m10v_settings_controller_ready','m10v_settings_controller_enter','m10v_settings_controller_key','m10v_settings_controller_key_route'},
        'm10v_detail_': {'m10v_detail_table','m10v_detail_control'},
        'm10v_hdf_': {'m10v_hdf_alloc','m10v_hdf_producer','m10v_hdf_gate','m10v_hdf_settings','m10v_hdf_load','m10v_hdf_save','m10v_hdf_done','m10v_hdf_cached','m10v_hdf_bootstrap','m10v_hdf_reserve','m10v_hdf_task_snapshot'},
        'm10v_hdf_adj_': {'m10v_hdf_adj_'+n for n in ('enter','draw','current','set','count','available','event')},
        'm10v_hdf_menu_': {'m10v_hdf_menu_top_ctor','m10v_hdf_menu_top_dtor','m10v_hdf_menu_cache_init','m10v_hdf_menu_destroy','m10v_hdf_menu_factory','m10v_hdf_menu_ready','m10v_hdf_menu_enter','m10v_hdf_menu_key','m10v_hdf_menu_key_route'},
        'm10v_level_': {'m10v_level_callback','m10v_level_draw','m10v_level_quarter'},
    }[prefix]
    if not set(omitted_exports)<=required:raise ValueError('unknown omitted API')
    if set(symbols) != (required-set(omitted_exports)) | set(additional_exports) or not image_sections: raise ValueError('runtime API incomplete: '+prefix+' missing='+str(required-set(symbols))+' extra='+str(set(symbols)-required))
    return bytes(image), symbols


def build(out_dir, base=0x540b6000, initial_state_hex=None, debug_mode=False, debug_build_id=0, sd_library=False, profile_mode=False, candidate_color=False, spatial_neon=False, lifecycle_trace=False, recipe_snapshot=False, texture_neon=False, save_chain_trace=False,native_color=False,native_grain=False,view_deferred=False,film_library=True,hdf_default=0,hdf_enabled=None,live_color=False,appended_slots=False,custom_zoom=True,zoom_seed=None,universal_halation=False,camera_model='gr3',adj_exit_trace=False,border_enabled=False,border_hardware=False):
    if type(border_enabled)is not bool or (border_enabled and not(sd_library and film_library)):raise ValueError('border requires boolean opt-in and the owned film/SD UI lifecycle')
    if camera_model not in ('gr3','gr3x'):raise ValueError('invalid camera model')
    if type(custom_zoom)is not bool:raise ValueError('custom zoom must be boolean')
    if zoom_seed is not None and not (custom_zoom and film_library and sd_library):raise ValueError('zoom seed requires GR III film/SD library')
    custom_zoom=custom_zoom and film_library
    if type(appended_slots)is not bool or (appended_slots and (not film_library or not sd_library)):raise ValueError('appended slots require the film/SD library')
    if type(universal_halation)is not bool or (universal_halation and (not film_library or not sd_library or not live_color)):raise ValueError('universal halation requires GR III live-color film library')
    halo_flags=['-DM10V_UNIVERSAL_HALATION=1'] if universal_halation else []
    compile_flags=FLAGS+halo_flags+(['-DM10V_APPENDED_SLOTS=1'] if appended_slots else [])
    render_flags=RENDER_FLAGS+halo_flags+(['-DM10V_APPENDED_SLOTS=1'] if appended_slots else [])
    half_pair_enabled=bool(camera_model=='gr3' and base>=0x540be000 and film_library and sd_library and recipe_snapshot and lifecycle_trace)
    pair_flags=[f'-DM10V_HALF_PAIR_ENABLED={int(half_pair_enabled)}']
    native_owned=bool(native_color and native_grain and recipe_snapshot and lifecycle_trace)
    if type(border_hardware)is not bool or (border_hardware and not(border_enabled and native_owned and save_chain_trace and view_deferred)):
        raise ValueError('border hardware requires explicit opt-in, owned native pipeline, RAW lifetime and view recovery')
    if live_color and (not native_color or not sd_library):raise ValueError('live color requires native color and owned settings')
    if type(texture_neon) is not bool or (texture_neon and (not spatial_neon or not (debug_mode or native_owned))):raise ValueError('full texture blocks require debug NEON ownership')
    if type(native_grain)is not bool or (native_grain and not native_color):raise ValueError('native grain requires native color/snapshot ownership')
    if type(view_deferred)is not bool or (view_deferred and not lifecycle_trace):raise ValueError('view recovery requires diagnostic owned pipeline')
    if type(native_color)is not bool or (native_color and not recipe_snapshot):raise ValueError('native color requires per-recipe snapshot')
    if type(save_chain_trace) is not bool or (save_chain_trace and not lifecycle_trace):raise ValueError('save chain trace requires owned lifecycle tracing')
    if type(recipe_snapshot) is not bool or (recipe_snapshot and not lifecycle_trace):raise ValueError('per-frame snapshot requires owned lifecycle storage')
    if type(lifecycle_trace) is not bool or (lifecycle_trace and not (debug_mode or native_owned)):raise ValueError('lifecycle tracing requires debug mode')
    if type(candidate_color) is not bool or type(spatial_neon) is not bool or ((candidate_color or spatial_neon) and not (debug_mode or native_owned)):
        raise ValueError('experimental color/NEON requires explicit debug mode')
    if type(profile_mode) is not bool or (profile_mode and not debug_mode):
        raise ValueError('capture profiling requires debug mode')
    # Camera/controller M10V_LIVE_COLOR owns only the published state cache.
    # Still snapshots require it even when the separate ISP Live Make is off.
    owner_cache=bool(live_color or (recipe_snapshot and sd_library))
    effects_owner_offset=(0x613c if owner_cache else 0x213c) if film_library else 0x13bc
    border_cache_offset=effects_owner_offset+0x1a8
    border_flags=['-DM10V_BORDER_ENABLED=1',f'-DM10V_BORDER_CACHE_OWNER_OFFSET={hex(border_cache_offset)}'] if border_enabled else []
    profile_flags=[f'-DM10V_CAPTURE_PROFILE={int(profile_mode)}',f'-DM10V_SPATIAL_NEON={int(spatial_neon)}']
    color_flags=[f'-DM10V_FILM_COLOR_CANDIDATE={int(candidate_color)}',f'-DM10V_SPATIAL_NEON={int(spatial_neon)}',f'-DM10V_TEXTURE_NEON={int(texture_neon)}']
    if type(adj_exit_trace)is not bool or (adj_exit_trace and not debug_mode):raise ValueError('ADJ exit trace requires explicit debug mode')
    if type(debug_mode) is not bool or not isinstance(debug_build_id,int) or not 0<=debug_build_id<=0xffffffff:
        raise ValueError('invalid debug build options')
    if initial_state_hex is None:
        initial=bytearray(184)
        struct.pack_into('<IHHI',initial,0,0x5630314d,5,184,0)
        for i in range(5):struct.pack_into('<H6B',initial,12+i*8,33 if i==4 else i+34,0,0,0,3,5,2)
        for i in range(5):initial[99+i*8]=4
        struct.pack_into('<I',initial,180,zlib.crc32(initial[:180]))
    else:
        initial=bytes.fromhex(initial_state_hex)
        if len(initial)!=184 or struct.unpack_from('<IHHI',initial)!=(0x5630314d,5,184,0):raise ValueError('invalid initial state header')
        seen=set();empty=False
        for i in range(10):
            film,grain,soft,gain,spread,threshold,profile=struct.unpack_from('<H6B',initial,12+i*8)
            if not film:
                empty=True
                if any(initial[12+i*8:20+i*8]) or any(initial[96+i*8:104+i*8]):raise ValueError('disabled film must be empty')
                continue
            if empty or film in seen or not (1<=film<=78 or 289<=film<=305 or 309<=film<=317) or grain>3 or soft>3 or gain>8 or spread>8 or threshold>8 or profile>3:raise ValueError('invalid enabled film')
            if (film==294 or 309<=film<=317) and not native_owned:raise ValueError('New looks require ISP still ownership')
            seen.add(film)
        if initial[92]>2 or any(v>3 for v in initial[93:96]) or struct.unpack_from('<I',initial,176)[0] not in (0,1) or struct.unpack_from('<I',initial,180)[0]!=zlib.crc32(initial[:180]):raise ValueError('invalid initial settings/checksum')
    if not native_grain and any(initial[14+i*8] for i in range(10)):raise ValueError('Grain requires the GR III native processing pipeline')
    if type(hdf_default) is not int or not 0<=hdf_default<=3:
        raise ValueError('invalid HDF default')
    if hdf_enabled is None:hdf_enabled=not lifecycle_trace
    if type(hdf_enabled)is not bool or (not hdf_enabled and (hdf_default or not film_library)):
        raise ValueError('invalid HDF enablement')
    if lifecycle_trace and hdf_enabled and not (native_color and native_grain and recipe_snapshot):
        raise ValueError('Shared HDF requires native color/grain snapshot owners')
    for i in range(10):
        e=initial[96+i*8:104+i*8]
        film=struct.unpack_from('<H',initial,12+i*8)[0]
        exposure_limit=2 if film==68 else 1 if film==67 else 0
        if e[5]>exposure_limit or any(v>limit for v,limit in zip(e,[2,8,5,8,1,2,0,3 if film==289 or 306<=film<=308 else 0])):raise ValueError('invalid film texture effects')
    if universal_halation:
        initial=bytearray(initial)
        for i in range(10):
            if struct.unpack_from('<H',initial,12+i*8)[0]:initial[16+i*8]=0;initial[19+i*8]=2
        struct.pack_into('<I',initial,180,zlib.crc32(initial[:180]))
    initial = bytes(initial)
    from scripts.verify_gr3_5207_reference import verify
    film_payload=verify(ROOT)
    from scripts.verify_gr3_harman_reference import verify as verify_harman
    harman_payloads=verify_harman(ROOT)
    from scripts.verify_gr3_curated_reference import verify as verify_curated
    curated_payloads=verify_curated(ROOT)
    from scripts.verify_gr3_newstocks_reference import verify as verify_newstocks
    newstocks_payloads=verify_newstocks(ROOT)
    from scripts.verify_gr3_style_filters_reference import verify as verify_styles
    style_payloads=verify_styles(ROOT)
    from scripts.verify_gr3_d76_reference import verify as verify_d76
    d76_payloads=verify_d76(ROOT)
    from scripts.verify_gr3_anime_e6_reference import verify as verify_anime_e6
    verify_anime_e6(ROOT)
    from scripts.verify_gr3_c41_reference import verify as verify_c41
    verify_c41(ROOT)
    from scripts.verify_gr3_extra_films_reference import verify as verify_extra_films
    verify_extra_films(ROOT)
    if base & 4095: raise ValueError('runtime base must be page aligned')
    configured = os.environ.get('M10V_LLVM_CLANG')
    candidates = [configured] if configured else [
        '/opt/homebrew/opt/llvm/bin/clang', '/usr/local/opt/llvm/bin/clang', shutil.which('clang')]
    compiler = next((p for p in candidates if p and Path(p).is_file()), None)
    if not compiler: raise RuntimeError('LLVM clang unavailable')
    from scripts.generate_m10v_catalog import generate
    if (ROOT/'native/gr3/m10v_legacy_data.h').read_text()!=generate(): raise ValueError('legacy tables header does not match exact source')
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='m10v-native-library-') as folder:
        folder = Path(folder); obj = folder / 'library.o'
        subprocess.run([compiler, *render_flags, *profile_flags, '-DM10V_INITIAL_STATE_BYTES=' + ','.join(str(v) for v in initial), '-c', str(ROOT / 'native/gr3/m10v_library.c'), '-o', str(obj)],
                       check=True, capture_output=True)
        spatial=b'';spatial_base=base+0x100;spatial_symbols={}
        if spatial_neon:
            spatial_obj=folder/'spatial.o'
            spatial_flags=[f for f in RENDER_FLAGS if not f.startswith('-mfloat-abi=')]+['-mfpu=neon','-mfloat-abi=softfp']
            subprocess.run([compiler,*spatial_flags,'-c',str(ROOT/'native/gr3/m10v_spatial_accel.c'),'-o',str(spatial_obj)],check=True,capture_output=True)
            spatial,spatial_symbols=link_object(spatial_obj.read_bytes(),spatial_base,prefix='m10v_spatial_')
            if texture_neon:
                texture_obj=folder/'texture.o'
                subprocess.run([compiler,*spatial_flags,'-c',str(ROOT/'native/gr3/m10v_texture_accel.c'),'-o',str(texture_obj)],check=True,capture_output=True)
                texture_base=(spatial_base+len(spatial)+15)&~15
                texture,texture_symbols=link_object(texture_obj.read_bytes(),texture_base,prefix='m10v_texture_')
                spatial+=bytes(texture_base-spatial_base-len(spatial))+texture;spatial_symbols.update(texture_symbols)
        curated_base=(spatial_base+len(spatial)+15)&~15
        curated_obj=folder/'curated.o'
        subprocess.run([compiler,*render_flags,'-c',str(ROOT/'native/gr3/film_curated.c'),'-o',str(curated_obj)],check=True,capture_output=True)
        curated,curated_symbols=link_object(curated_obj.read_bytes(),curated_base,prefix='m10v_curated_')
        spatial+=bytes(curated_base-spatial_base-len(spatial))+curated;spatial_symbols.update(curated_symbols)
        newstocks_base=(spatial_base+len(spatial)+15)&~15
        newstocks_obj=folder/'newstocks.o'
        subprocess.run([compiler,*render_flags,'-c',str(ROOT/'native/gr3/film_newstocks.c'),'-o',str(newstocks_obj)],check=True,capture_output=True)
        newstocks,newstocks_symbols=link_object(newstocks_obj.read_bytes(),newstocks_base,prefix='m10v_newstocks_')
        spatial+=bytes(newstocks_base-spatial_base-len(spatial))+newstocks;spatial_symbols.update(newstocks_symbols)
        for bank in range(2):
            style_base=(spatial_base+len(spatial)+15)&~15
            style_obj=folder/f'style-filters-{bank}.o'
            subprocess.run([compiler,*render_flags,'-c',str(ROOT/f'native/gr3/film_style_filters_{bank}.c'),'-o',str(style_obj)],check=True,capture_output=True)
            style,style_symbols=link_object(style_obj.read_bytes(),style_base,prefix=f'm10v_style_filters_{bank}_')
            spatial+=bytes(style_base-spatial_base-len(spatial))+style;spatial_symbols.update(style_symbols)
        for bank in range(2):
            d76_base=(spatial_base+len(spatial)+15)&~15
            d76_obj=folder/f'd76-{bank}.o'
            subprocess.run([compiler,*render_flags,'-c',str(ROOT/f'native/gr3/film_d76_{bank}.c'),'-o',str(d76_obj)],check=True,capture_output=True)
            d76,d76_symbols=link_object(d76_obj.read_bytes(),d76_base,prefix=f'm10v_d76_{bank}_')
            spatial+=bytes(d76_base-spatial_base-len(spatial))+d76;spatial_symbols.update(d76_symbols)
        harman_base=(spatial_base+len(spatial)+15)&~15
        harman_obj=folder/'harman.o'
        subprocess.run([compiler,*render_flags,*color_flags,'-c',str(ROOT/'native/gr3/film_harman.c'),'-o',str(harman_obj)],check=True,capture_output=True)
        halo,halo_symbols=link_object(harman_obj.read_bytes(),harman_base,externals=spatial_symbols,prefix='m10v_harman_',additional_exports=('m10v_harman_texture_table',) if texture_neon else ())
        halo_symbols.update(spatial_symbols)
        film_obj=folder/'5207.o'
        subprocess.run([compiler,*render_flags,*color_flags,'-c',str(ROOT/'native/gr3/film_5207.c'),'-o',str(film_obj)],check=True,capture_output=True)
        film_base=(harman_base+len(halo)+15)&~15
        film,film_symbols=link_object(film_obj.read_bytes(),film_base,halo_symbols,prefix='m10v_5207_')
        halo_symbols.update(film_symbols)
        core_base = (film_base+len(film)+15)&~15
        core, symbols = link_object(obj.read_bytes(), core_base, halo_symbols, additional_exports=('m10v_library_render_profiled','m10v_library_render_native_profiled','m10v_library_render_oriented_profiled') if profile_mode else ())
        symbols.update(halo_symbols)
        image = bytearray(0x100)+spatial+bytes(harman_base-spatial_base-len(spatial))+halo+bytes(film_base-harman_base-len(halo))+film+bytes(core_base-film_base-len(film))+core
        # Single-instruction entry trampolines, before the new C module. Each
        # reproduces the displaced official instruction then returns to +4.
        original = {
            0x00: (0x532c26c0, 0xe1a0c00d), 0x10: (0x532922b4, 0xe351000a),
            0x20: (0x532a985c, 0xe1a0c00d), 0x30: (0x532935dc, 0xe351000a),
            0x40: (0x532a9988, 0xe1a0c00d), 0x50: (0x531ac270, 0xe1a0c00d),
            0x60: (0x531ac24c, 0xe1a0c00d), 0x80: (0x532c2a9c, 0xe1a0c00d),
            0x90: (0x532c2c80, 0xe1a0c00d), 0xa0: (0x531ab914, 0xe1a0c00d),
            0xb0: (0x531ac140, 0xe1a0c00d),
        }
        if appended_slots:original.update({0xc0:(0x531abe0c,0xe1a0c00d),0xd0:(0x531a1500,0xe1a0c00d),0xe0:(0x531a0ba0,0xe1a0c00d)})
        for offset, (address, word) in original.items():
            delta = address + 4 - (base + offset + 4) - 8
            if delta & 3 or not -(1 << 25) <= delta < 1 << 25: raise ValueError('trampoline branch out of range')
            struct.pack_into('<II', image, offset, word, 0xea000000 | ((delta >> 2) & 0xffffff))
        (out / 'm10v-library-arm.o').write_bytes(obj.read_bytes())
        camera_obj = folder / 'camera.o'
        subprocess.run([compiler, *compile_flags, '-DM10V_LIVE_COLOR='+str(int(owner_cache)), '-DM10V_SD_LIBRARY='+str(int(sd_library)), '-DM10V_ISP_NATIVE_GRAIN_MODE='+str(int(native_grain)), '-c', str(ROOT / 'native/gr3/m10v_library_camera.c'), '-o', str(camera_obj)],
                       check=True, capture_output=True)
        camera_base = (base + len(image) + 15) & ~15
        # Forward-only veneers occupy the final reserved16 bytes; the SD
        # module itself consumes camera APIs and is linked afterward.
        camera_externals={**symbols,**({'m10v_sd_camera_custom_record':base+0xf0,'m10v_sd_u32':base+0xf4} if sd_library else {})}
        camera, camera_symbols = link_object(camera_obj.read_bytes(), camera_base, camera_externals, 'm10v_camera_library_')
        image += bytes(camera_base - base - len(image)) + camera
        symbols.update(camera_symbols)
        (out / 'm10v-library-camera-arm.o').write_bytes(camera_obj.read_bytes())
        if border_enabled:
            border_obj=folder/'border-camera.o'
            subprocess.run([compiler,*compile_flags,*border_flags,'-c',str(ROOT/'native/gr3/m10v_border_camera.c'),'-o',str(border_obj)],check=True,capture_output=True)
            border_base=(base+len(image)+15)&~15
            border_code,border_symbols=link_object(border_obj.read_bytes(),border_base,symbols,'m10v_border_')
            image+=bytes(border_base-base-len(image))+border_code;symbols.update(border_symbols)
            if recipe_snapshot:
                shot_obj=folder/'border-shot.o'
                subprocess.run([compiler,*compile_flags,*border_flags,'-c',str(ROOT/'native/gr3/m10v_border_shot.c'),'-o',str(shot_obj)],check=True,capture_output=True)
                shot_base=(base+len(image)+15)&~15
                shot_code,shot_symbols=link_object(shot_obj.read_bytes(),shot_base,symbols,'m10v_border_shot_')
                image+=bytes(shot_base-base-len(image))+shot_code;symbols.update(shot_symbols)
        hdf_report=None
        if hdf_enabled:
            hdf_obj=folder/'digital-hdf.o'
            hdf_owner_offset=(0x613c if owner_cache else 0x213c) if film_library else 0x13bc
            subprocess.run([compiler,*compile_flags,'-DM10V_HDF_DEFAULT='+str(hdf_default),'-DM10V_HDF_SHARED_RECIPE='+str(int(lifecycle_trace)),'-DM10V_HDF_UI_CACHE='+str(int(sd_library)),'-DM10V_HDF_OWNER_OFFSET='+hex(hdf_owner_offset),'-c',str(ROOT/'native/gr3/m10v_digital_hdf.c'),'-o',str(hdf_obj)],check=True,capture_output=True)
            hdf_base=(base+len(image)+15)&~15
            hdf_code,hdf_symbols=link_object(hdf_obj.read_bytes(),hdf_base,symbols,'m10v_hdf_',omitted_exports=('m10v_hdf_alloc',) if lifecycle_trace else ())
            image+=bytes(hdf_base-base-len(image))+hdf_code;symbols.update(hdf_symbols)
            from scripts.build_gr3_digital_hdf import build as build_digital_hdf
            hdf_base=(base+len(image)+15)&~15
            hdf_code,hdf_report=build_digital_hdf(hdf_base,symbols,shared_recipe=lifecycle_trace,ui_cache=sd_library)
            image+=bytes(hdf_base-base-len(image))+hdf_code
        if sd_library:
            node = os.environ.get('M10V_NODE') or shutil.which('node')
            if not node:
                raise RuntimeError('Node.js is unavailable; set M10V_NODE to its absolute executable path')
            subprocess.run([node,'scripts/generate_gr3_sd_contract.mjs','--check'],cwd=ROOT,check=True,capture_output=True)
            for sd_source,sd_prefix in [('m10v_sd_library.c','m10v_sd_'),('m10v_sd_camera.c','m10v_sd_camera_')]:
                sd_obj=folder/(sd_source+'.o')
                subprocess.run([compiler,*compile_flags,'-c',str(ROOT/'native/gr3'/sd_source),'-o',str(sd_obj)],check=True,capture_output=True)
                sd_base=(base+len(image)+15)&~15
                sd_code,sd_symbols=link_object(sd_obj.read_bytes(),sd_base,symbols,sd_prefix)
                image+=bytes(sd_base-base-len(image))+sd_code;symbols.update(sd_symbols)
            from scripts.build_gr3_menu_patches import branch as sd_branch
            for off,name in [(0xf0,'m10v_sd_camera_custom_record'),(0xf4,'m10v_sd_u32')]:
                struct.pack_into('<I',image,off,sd_branch(base+off,symbols[name]))
        capture_recipe_bytes='M10V_SAVE_RECIPE_EXTENDED_BYTES' if lifecycle_trace else '(M10V_SAVE_RECIPE_BYTES+16u)' if hdf_enabled else 'M10V_SAVE_RECIPE_BYTES'
        debug_flags = [*profile_flags,*border_flags,f'-DM10V_HDF_UI_CACHE={int(sd_library and hdf_enabled)}',f'-DM10V_ADJ_EXIT_TRACE={int(adj_exit_trace)}',f'-DM10V_CAPTURE_RECIPE_BYTES={capture_recipe_bytes}',f'-DM10V_HDF_SHARED_RECIPE={int(hdf_enabled and lifecycle_trace)}',f'-DM10V_DEBUG_MODE={int(debug_mode)}',f'-DM10V_DEBUG_BUILD_ID={debug_build_id}u',f'-DM10V_SD_LIBRARY={int(sd_library)}',f'-DM10V_RECIPE_SNAPSHOT={int(recipe_snapshot)}',f'-DM10V_RAW_LIFETIME={int(save_chain_trace)}',f'-DM10V_ISP_NATIVE_LOOK={int(native_color)}',f'-DM10V_ISP_NATIVE_GRAIN_MODE={int(native_grain)}']
        if debug_mode or lifecycle_trace:
            debug_obj = folder / 'debug.o'
            debug_source=ROOT/'native/gr3/m10v_debug.c'
            if not debug_mode:
                debug_source=folder/'debug-disabled.c'
                debug_source.write_text('#include <stdint.h>\nint m10v_debug_batch(const uint32_t *e,uint32_t n){(void)e;(void)n;return 0;}\nint m10v_debug_log(uint32_t e,uint32_t a,uint32_t b,uint32_t c,uint32_t d){(void)e;(void)a;(void)b;(void)c;(void)d;return 0;}\n')
            subprocess.run([compiler,*compile_flags,*debug_flags,'-c',str(debug_source),'-o',str(debug_obj)],check=True,capture_output=True)
            debug_base=(base+len(image)+15)&~15
            debug,debug_symbols=link_object(debug_obj.read_bytes(),debug_base,prefix='m10v_debug_')
            image+=bytes(debug_base-base-len(image))+debug;symbols.update(debug_symbols)
        lifecycle_report=None
        if lifecycle_trace:
            from scripts.build_gr3_save_trace import build as build_save_trace
            stock=capture_stock_rtos()
            stock_path=folder/'capture-original-rtos.bin';stock_path.write_bytes(stock)
            trace_base=(base+len(image)+15)&~15
            trace,owner_report=build_save_trace(out/'save-trace',trace_base,rtos=stock_path,
                                               border_debug=border_enabled and debug_mode)
            image+=bytes(trace_base-base-len(image))+trace;symbols.update(owner_report['exports'])
            phase_obj=folder/'lifecycle.o'
            subprocess.run([compiler,*compile_flags,*debug_flags,'-c',str(ROOT/'native/gr3/m10v_capture_lifecycle.c'),'-o',str(phase_obj)],check=True,capture_output=True)
            phase_base=(base+len(image)+15)&~15
            phase,phase_symbols=link_object(phase_obj.read_bytes(),phase_base,symbols,'m10v_lifecycle_')
            image+=bytes(phase_base-base-len(image))+phase;symbols.update(phase_symbols)
            from scripts.build_gr3_capture_lifecycle import build_hooks
            hook_base=(base+len(image)+15)&~15
            hook,phase_report=build_hooks(hook_base,symbols['m10v_lifecycle_phase'])
            image+=bytes(hook_base-base-len(image))+hook
            file_report=None
            file_patches=[]
            if not native_color:
                from scripts.build_gr3_file_trace import build as build_file_trace
                file_base=(base+len(image)+15)&~15
                file_code,file_report=build_file_trace(out/'file-trace',file_base,owner_report['exports'],symbols['m10v_lifecycle_file_flush'],rtos=stock_path)
                image+=bytes(file_base-base-len(image))+file_code
                file_patches=file_report['patches']
            lifecycle_report={'owner':owner_report,'jpeg':phase_report,'file':file_report,'patches':owner_report['patches']+phase_report['patches']+file_patches,'filesystem_flush':'owned capture borders and actual Store handler post-return sink','buffer_policy_changed':False}
            if save_chain_trace:
                from scripts.build_gr3_module_dispatch_trace import build as build_module_trace
                module_base=(base+len(image)+15)&~15
                module_code,module_report=build_module_trace(out/'module-dispatch-trace',module_base,owner_report['exports']['m10v_save_trace_recipe_mark'],take=owner_report['exports']['m10v_save_trace_recipe_take'],batch=symbols['m10v_debug_batch'],rtos=stock_path,border_debug=border_enabled and debug_mode)
                image+=bytes(module_base-base-len(image))+module_code
                from scripts.build_gr3_pool_release_trace import build as build_pool_trace
                pool_base=(base+len(image)+15)&~15
                pool_code,pool_report=build_pool_trace(out/'pool-release-trace',pool_base,owner_report['exports']['m10v_save_trace_recipe_mark'],raw_pool_return=owner_report['exports']['m10v_save_trace_recipe_pool_return'],rtos=stock_path)
                image+=bytes(pool_base-base-len(image))+pool_code
                lifecycle_report.update(module_dispatch=module_report,pool_release=pool_report,raw_lifetime_attestation=True)
                lifecycle_report['patches']+=module_report['patches']+pool_report['patches']
            if recipe_snapshot:
                from scripts.build_gr3_isp_recipe_color import build as build_recipe_color
                snapshot_base=(base+len(image)+15)&~15
                snapshot_code,snapshot_report=build_recipe_color(out/'recipe-snapshot',stock,symbols,owner_report,snapshot_base,observer=not native_color,producer_snapshot=True,native_color=native_color,native_grain=native_grain,external_noise=False,live_color=live_color,shared_hdf=hdf_enabled,appended_slots=appended_slots,border_snapshot=border_enabled)
                image+=bytes(snapshot_base-base-len(image))+snapshot_code;symbols.update(snapshot_report['exports'])
                lifecycle_report['snapshot']=snapshot_report
                lifecycle_report['patches']+=snapshot_report['patches']
            if native_grain:
                from scripts.build_gr3_native_grain_hooks import build as build_grain_hooks
                grain_base=(base+len(image)+15)&~15
                grain_code,grain_report=build_grain_hooks(out/'native-grain-hooks',grain_base,symbols,rtos=stock,appended_slots=appended_slots)
                image+=bytes(grain_base-base-len(image))+grain_code
                lifecycle_report['native_grain']=grain_report
                lifecycle_report['patches']+=grain_report['patches']
            if view_deferred:
                from scripts.build_gr3_view_deferred import build as build_view_deferred
                view_base=(base+len(image)+15)&~15
                view_code,view_report=build_view_deferred(out/'view-deferred',view_base,rtos=stock_path)
                image+=bytes(view_base-base-len(image))+view_code
                lifecycle_report['view_deferred']=view_report
                lifecycle_report['patches']+=view_report['patches']
        half_pair_report=None
        if half_pair_enabled:
            # The guard is placed later (or shared with borders). Relink this
            # retained object against its final exports before publishing code.
            guard_header=(ROOT/'native/gr3/m10v_border_wait_guard.h').read_text()
            guard_asm=(ROOT/'scripts/border_recovery_wait_guard.S').read_text()
            guard_names=set(re.findall(r'\b(m10v_border_\w+)\s*\(',guard_header))
            guard_names.update(re.findall(r'^\.global\s+(\w+)',guard_asm,re.M))
            forward_guard={name:base for name in guard_names}
            for source,prefix in [('m10v_half_pair.c','m10v_half_pair_'),('m10v_half_pair_iip.c','m10v_half_pair_iip_'),('m10v_half_pair_camera.c','m10v_half_pair_camera')]:
                pair_obj=folder/(source+'.o')
                plan_only=['-DM10V_HALF_PAIR_PLANS_ONLY=1'] if prefix=='m10v_half_pair_' else []
                subprocess.run([compiler,*render_flags,*debug_flags,*pair_flags,*plan_only,'-fno-jump-tables','-c',str(ROOT/'native/gr3'/source),'-o',str(pair_obj)],check=True,capture_output=True)
                pair_start=(base+len(image)+15)&~15
                pair_code,pair_symbols=link_object(pair_obj.read_bytes(),pair_start,{**symbols,**forward_guard},prefix,additional_exports=('m10v_half_pair_reset','m10v_half_pair_init','m10v_half_pair_select','m10v_half_pair_destroy') if prefix=='m10v_half_pair_camera' else (),omitted_exports=('m10v_half_pair_compose',) if prefix=='m10v_half_pair_' else ())
                if prefix=='m10v_half_pair_iip_':
                    iip_object=pair_obj.read_bytes();iip_start=pair_start;iip_size=len(pair_code);iip_symbols=pair_symbols
                image+=bytes(pair_start-base-len(image))+pair_code;symbols.update(pair_symbols)
        settings_report = None
        zoom_report = None
        if sd_library:
            from scripts.build_gr3_zoom import build as build_zoom
            zoom_base=(base+len(image)+15)&~15
            zoom_code,zoom_report=build_zoom(zoom_base,capture_stock_rtos(),aspect=base>=0x540be000,seed=zoom_seed,debug_log=symbols['m10v_debug_log'] if debug_mode else None,camera_model=camera_model)
            zoom_report['enabled']=custom_zoom
            image+=bytes(zoom_base-base-len(image))+zoom_code
            symbols.update(zoom_report['symbols'])
            from scripts.generate_m10v_film_cards import generate as card_data
            if (ROOT/'native/gr3/m10v_film_card_data.h').read_text()!=card_data():raise ValueError('film card labels differ from catalog')
            for name,prefix in [('m10v_film_card.c','m10v_film_card_'),('m10v_settings.c','m10v_settings_'),('m10v_settings_view.c','m10v_settings_view_')]:
                obj_path=folder/(name+'.o')
                subprocess.run([compiler,*compile_flags,f'-DM10V_NATIVE_BASE={base}u','-c',str(ROOT/'native/gr3'/name),'-o',str(obj_path)],check=True,capture_output=True)
                start=(base+len(image)+15)&~15
                code,entries=link_object(obj_path.read_bytes(),start,symbols,prefix,
                    additional_exports=('m10v_settings_view_zoom',) if prefix=='m10v_settings_view_' else ())
                image+=bytes(start-base-len(image))+code;symbols.update(entries)
            controller_obj=folder/'settings-controller.o'
            subprocess.run([compiler,*compile_flags,*debug_flags,*border_flags,*pair_flags,'-DM10V_LIVE_COLOR='+str(int(owner_cache)),'-c',str(ROOT/'native/gr3/m10v_settings_controller.c'),'-o',str(controller_obj)],check=True,capture_output=True)
            start=(base+len(image)+15)&~15
            placeholders={name:start for name in ['m10v_settings_factory_original','m10v_settings_top_dtor_original','m10v_settings_controller_vtable',*[f'm10v_ab_{n}_original' for n in ['selector','mapper','live_enter','live_leave','live_destroy','live_event','adj_event','adj_refresh','adj_exit','adj_destroy','adj_changed','dispatch']]]}
            provisional,entries=link_object(controller_obj.read_bytes(),start,{**symbols,**placeholders},'m10v_settings_controller_',additional_exports=AB_CONTROLLER_EXPORTS)
            from scripts.build_gr3_settings_hooks import build_settings_hooks
            hook_start=(start+len(provisional)+15)&~15
            hook_code,settings_report=build_settings_hooks(hook_start,{**symbols,**entries},live_color=owner_cache,appended_slots=appended_slots,custom_zoom=custom_zoom)
            code,entries=link_object(controller_obj.read_bytes(),start,{**symbols,**settings_report['exports']},'m10v_settings_controller_',additional_exports=AB_CONTROLLER_EXPORTS)
            image+=bytes(start-base-len(image))+code
            image+=bytes(hook_start-base-len(image))+hook_code;symbols.update(entries)
        hdf_menu_report=None
        hdf_adj_report=None
        if sd_library and (hdf_enabled or border_enabled):
            menu_obj=folder/'hdf-menu.o';start=(base+len(image)+15)&~15
            subprocess.run([compiler,*compile_flags,*border_flags,f'-DM10V_DEBUG_MODE={int(debug_mode)}',f'-DM10V_HDF_ENABLED={int(hdf_enabled)}',f'-DM10V_HDF_GROUPED={int(film_library)}','-DM10V_HDF_OWNER_OFFSET='+hex(effects_owner_offset),'-c',str(ROOT/'native/gr3/m10v_hdf_menu.c'),'-o',str(menu_obj)],check=True,capture_output=True)
            names=['m10v_hdf_menu_parent_'+n for n in ['ctor','dtor','factory','key_route']]+['m10v_hdf_menu_vtable']
            provisional,entries=link_object(menu_obj.read_bytes(),start,{**symbols,**dict.fromkeys(names,start)},'m10v_hdf_menu_')
            from scripts.build_gr3_hdf_menu import build_hooks as build_hdf_menu
            hook_start=(start+len(provisional)+15)&~15
            hook,hdf_menu_report=build_hdf_menu(hook_start,{**symbols,**entries},settings_report,film_library,live_color=owner_cache,custom_zoom=custom_zoom)
            if border_enabled:hdf_menu_report.update(border_enabled=True,hdf_enabled=hdf_enabled,border_resource_ids=[1155,1156,1157],effects_children=(['HDF'] if hdf_enabled else [])+['Border'])
            code,entries=link_object(menu_obj.read_bytes(),start,{**symbols,**hdf_menu_report['exports']},'m10v_hdf_menu_')
            image+=bytes(start-base-len(image))+code+bytes(hook_start-start-len(code))+hook;symbols.update(entries)
            # Compose the added ADJ function with the already audited A/B
            # event wrapper. The Node writer replaces this ONE original site,
            # retaining all other A/B hooks and their original trampolines.
            if hdf_enabled:
                adj_obj=folder/'hdf-adj.o';adj_start=(base+len(image)+15)&~15
                subprocess.run([compiler,*compile_flags,'-DM10V_HDF_UI_CACHE=1',
                    '-DM10V_HDF_OWNER_OFFSET='+hex(hdf_owner_offset),'-c',
                    str(ROOT/'native/gr3/m10v_hdf_adj.c'),'-o',str(adj_obj)],check=True,capture_output=True)
                parent_event=symbols['m10v_settings_controller_ab_adj_event']
                adj_code,adj_symbols=link_object(adj_obj.read_bytes(),adj_start,
                    {**symbols,'m10v_hdf_adj_parent_event':parent_event},'m10v_hdf_adj_')
                image+=bytes(adj_start-base-len(image))+adj_code;symbols.update(adj_symbols)
                from scripts.build_gr3_hdf_adj import build as build_hdf_adj
                adj_base=(base+len(image)+15)&~15
                adj_hooks,hdf_adj_report=build_hdf_adj(adj_base,symbols,icon_id=874,parent_event=parent_event)
                image+=bytes(adj_base-base-len(image))+adj_hooks
        # Link dedicated stock-detail backend against the same camera journal.
        from scripts.build_gr3_native_detail import build_detail, STOCK_TABLE
        detail_obj=folder/'detail.o'
        subprocess.run([compiler,*compile_flags,*debug_flags,'-c',str(ROOT/'native/gr3/m10v_detail.c'),'-o',str(detail_obj)],check=True,capture_output=True)
        detail_base=(base+len(image)+15)&~15
        provisional,detail_symbols=link_object(detail_obj.read_bytes(),detail_base,{**symbols,**{n:detail_base for n in ['m10v_detail_tables','m10v_detail_common_tables','m10v_detail_red_tables','m10v_detail_phoenix_tables','m10v_detail_charmera_tables','m10v_detail_pixel_tables']}},'m10v_detail_')
        shims_base=(detail_base+len(provisional)+15)&~15
        shims,detail_report=build_detail(shims_base,{**symbols,**detail_symbols},sd_library=sd_library,appended_slots=appended_slots,native_grain=native_grain,universal_halation=universal_halation)
        detail,detail_symbols=link_object(detail_obj.read_bytes(),detail_base,{**symbols,'m10v_detail_tables':detail_report['tables'],'m10v_detail_common_tables':detail_report['variant_tables']['common'],'m10v_detail_red_tables':detail_report['variant_tables']['red'],'m10v_detail_phoenix_tables':detail_report['variant_tables']['phoenix'],'m10v_detail_charmera_tables':detail_report['variant_tables']['charmera'],'m10v_detail_pixel_tables':detail_report['variant_tables']['pixel']},'m10v_detail_')
        image+=bytes(detail_base-base-len(image))+detail
        image+=bytes(shims_base-base-len(image))+shims
        symbols.update(detail_symbols)
        menu_obj = folder / 'menu.o'
        subprocess.run([compiler, *compile_flags, *debug_flags, f'-DM10V_NATIVE_BASE={base}u', '-c',
                        str(ROOT / 'native/gr3/m10v_library_menu.c'), '-o', str(menu_obj)], check=True, capture_output=True)
        menu_base = (base + len(image) + 15) & ~15
        menu, menu_symbols = link_object(menu_obj.read_bytes(), menu_base, symbols, 'm10v_menu_')
        image += bytes(menu_base - base - len(image)) + menu
        symbols.update(menu_symbols)
        (out / 'm10v-library-menu-arm.o').write_bytes(menu_obj.read_bytes())
        if appended_slots:
            tone_obj=folder/'tone-menu.o'
            subprocess.run([compiler,*compile_flags,f'-DM10V_NATIVE_BASE={base}u','-c',str(ROOT/'native/gr3/m10v_tone_menu.c'),'-o',str(tone_obj)],check=True,capture_output=True)
            tone_base=(base+len(image)+15)&~15
            tone_code,tone_symbols=link_object(tone_obj.read_bytes(),tone_base,symbols,'m10v_tone_menu_')
            image+=bytes(tone_base-base-len(image))+tone_code;symbols.update(tone_symbols)
        capture_obj = folder / 'capture.o'
        subprocess.run([compiler, *compile_flags, *debug_flags, '-c', str(ROOT / 'native/gr3/m10v_library_capture.c'),
                        '-o', str(capture_obj)], check=True, capture_output=True)
        capture_base = (base + len(image) + 15) & ~15
        capture, capture_symbols = link_object(capture_obj.read_bytes(), capture_base, symbols, 'm10v_capture_')
        image += bytes(capture_base - base - len(image)) + capture
        symbols.update(capture_symbols)
        (out / 'm10v-library-capture-arm.o').write_bytes(capture_obj.read_bytes())
        names = re.findall(r'\{"([^"\n]+)",[-0-9]', (ROOT / 'native/gr3/m10v_library.c').read_text())
        if len(names) != 33 or len(set(names)) != 33: raise ValueError('original catalog names incomplete')
        texts = names[:32] + [f'M10V Slot {i}' for i in range(1, 6)] + [
            'M10V Film Library', 'Save failed. Try again.', 'M10V Library',
            'Choose Film', '颗粒', '已停用', 'Timestamp', 'Choose Slot',
            'Grain Off', 'Grain Weak', 'Grain Medium', 'Grain Strong',
            'Diffusion Off', 'Diffusion Weak', 'Diffusion Medium', 'Diffusion Strong',
            'Timestamp Off', 'Date Only', 'Date and Time', 'Date Format', 'Stamp Corner', 'Stamp Color', 'Back',
            'YYYY.MM.DD', 'DD.MM.YYYY', 'YYYY-MM-DD', 'YY.MM.DD',
            'Top Left', 'Top Right', 'Bottom Left', 'Bottom Right',
            'White', 'Orange', 'Red', 'Yellow', 'Back', 'Done', names[32],
            '800T Halation','光晕强度','扩散范围','高光阈值','Halation Profile',
            *[str(i) for i in range(9)],'Off','Weak','Natural','Strong',
            *[f['name'] for f in json.loads((ROOT/'web/gr3/film-catalog.json').read_text())['looks']], '5207','Light Leak','Grain Size','Leak Gain','Leak Position','Leak Spread','Leak Variation','Fine','Standard','Coarse','Left','Right','Top','Bottom','Corner','Random','Fixed','Per Shot','Reset Texture','Phoenix II','HARMAN RED','Phoenix II Halation','Film Exposure','EI 125','EI 64','EI 250']
        texts=['' if text in ('Light Leak','Grain Size','Leak Gain','Leak Position','Leak Spread','Leak Variation') else text for text in texts]
        if len(texts) != 151: raise ValueError('private resource inventory differs')
        if sd_library:
            translations={'M10V Film Library':'胶卷库','Save failed. Try again.':'读取或保存失败，请检查存储卡','M10V Library':'胶卷设置',
                'Choose Film':'内置胶卷','Timestamp':'时间戳','Choose Slot':'已启用胶卷',
                'Grain Off':'颗粒关闭','Grain Weak':'颗粒弱','Grain Medium':'颗粒中','Grain Strong':'颗粒强',
                'Diffusion Off':'HDF 关闭','Diffusion Weak':'HDF 弱','Diffusion Medium':'HDF 中','Diffusion Strong':'HDF 强',
                'Timestamp Off':'时间戳关闭','Date Only':'仅日期','Date and Time':'日期和时间','Date Format':'日期格式',
                'Stamp Corner':'显示位置','Stamp Color':'文字颜色','Back':'返回','Done':'完成','Top Left':'左上','Top Right':'右上',
                'Bottom Left':'左下','Bottom Right':'右下','White':'白色','Orange':'橙色','Red':'红色','Yellow':'黄色',
                '800T Halation':'800T 光晕','Halation Profile':'光晕模式','Light Leak':'','Grain Size':'','Leak Gain':'','Leak Position':'','Leak Spread':'','Leak Variation':'','Fine':'细','Standard':'标准','Coarse':'粗','Left':'左','Right':'右','Top':'上','Bottom':'下','Corner':'角落','Random':'随机','Fixed':'固定','Per Shot':'每张变化','Reset Texture':'重置质感','Phoenix II':'蓝凤凰','Phoenix II Halation':'Harman Phoenix II 光晕','Film Exposure':'模拟曝光EI','Off':'关闭','Weak':'弱','Natural':'自然','Strong':'强'}
            texts=[translations.get(t,t) for t in texts]
        if sd_library:
            texts += ['胶卷库','水印','方向键选择 OK启停 MENU返回 DISP拍摄','方向键选择 OK启停 MENU返回 DISP拍摄','上下选择 OK设置 MENU返回','左右调整 OK保存 MENU取消','存储卡中没有可用胶卷','胶卷库已变化，请重新选择','保存失败，请检查存储卡','水印模式','日期格式','显示位置','文字颜色','关闭','仅日期','日期和时间','YYYY.MM.DD','DD.MM.YYYY','YYYY-MM-DD','YY.MM.DD','左上','右上','左下','右下','白色','橙色','红色','黄色','编辑：水印模式','编辑：日期格式','编辑：显示位置','编辑：文字颜色','选择胶卷']
        if sd_library:texts+=['HDF 模拟','左右选择 OK保存 MENU取消','关闭','弱','中','强','读取或保存失败','']
        texts+=['Portra 160','富士业务用 100','乐凯 C200','CCD Classic','富士 C200','ProImage 100','T-Max 100','Aerochrome','2460','5203']
        if sd_library:
            texts+=['胶卷名称：关闭','胶卷名称：开启','胶卷名称水印']
            texts+=['A/B 快速对比','A 风格','B 风格','开始对比','退出对比','上下选择 左右换风格 OK确定 MENU返回','槽位 1','槽位 2','槽位 3','槽位 4','槽位 5']
            texts+=['页面验证（只读）','原厂页面显示验证','返回与重复进入验证','请检查正常关机','未启用滤镜切换']
            texts+=['Custom LUT']*5
        texts+=['Kodak Charmera','颜色','红','黄','蓝','灰']
        if sd_library:texts+=['A/B 请选择不同风格','OK选定 MENU返回 DISP退出快切','上下选项 左右换风格 OK进入','A/B 已启用 · DISP切换','A/B 未启用']
        texts+=['方块世界' if sd_library else 'Pixel World']
        if sd_library:
            if 786+len(texts)!=1024:raise ValueError('zoom resource allocation differs')
            texts+=['裁切焦距','第一档','第二档','上下选档 左右1mm OK确定 MENU返回',
                    '左右1mm OK保存 MENU取消','保存或应用失败','读取失败']
            texts+=[f'{mm}mm' for mm in range(28,101)]
        texts+=[s['name'] for s in json.loads((ROOT/'web/gr3/style-filters-luts.json').read_text())['stocks']]
        if sd_library:
            if 786+len(texts)!=1111:raise ValueError('multiselect text base differs')
            texts+=['Custom LUT']*5+[f'胶卷库  已启用 {n}/10' for n in range(11)]+['已达启用上限，请先停用一卷']
        from scripts.generate_m10v_directory import directory as display_directory
        from scripts.generate_m10v_card_captions import resource as film_resource_id
        if sd_library:
            texts += ['5213','Fn清旧卷 OK启停 MENU返回 DISP拍摄']
            texts += [s['name'] for s in json.loads((ROOT/'web/gr3/d76-luts.json').read_text())['stocks']]
            for g in display_directory():
                for film in g['films']:
                    if film['id']<306:texts[film_resource_id(film['id'])-786]=film['name']
        else:texts+=['5213']+[s['name'] for s in json.loads((ROOT/'web/gr3/d76-luts.json').read_text())['stocks']]
        if sd_library and not universal_halation:texts+=['光晕模式']
        if universal_halation:
            if not sd_library or 786+len(texts)!=1137:raise ValueError('halation mode resource allocation differs')
            texts+=['光晕 0关 1溢出 2拉丝']
        if sd_library:texts+=['日期时间','胶卷名称','效果','HDF']
        if 786+len(texts)<1142:texts+=['']*(1142-786-len(texts))
        if 786+len(texts)!=1142:raise ValueError('anime resource allocation differs')
        texts += [s['name'] if s['id']>=309 else '' for s in json.loads((ROOT/'web/gr3/anime-e6-luts.json').read_text())['stocks']]+['','']
        texts += [s['name'] for s in json.loads((ROOT/'web/gr3/c41-luts.json').read_text())['stocks']]
        extras=json.loads((ROOT/'web/gr3/extra-films-luts.json').read_text())['stocks']
        texts += [s['name'] for s in extras if s['id']<317]
        if border_enabled:
            if 786+len(texts)!=1155:raise ValueError('border resource allocation differs')
            texts+=['边框','拍立得','胶卷']
        else:texts+=['','',''] # Keep border identities 1155..1157 reserved.
        if 786+len(texts)!=1158:raise ValueError('Instax resource allocation differs')
        texts += [s['name'] for s in extras if s['id']==317]
        last_resource=786+len(texts)-1
        if sd_library:
            from scripts.generate_m10v_card_captions import resource as caption_resource
            captions=json.loads((ROOT/'native/gr3/m10v_card_captions.json').read_text())
            if any(row['name']!=texts[caption_resource(row['film'])-786] for row in captions['captions']):raise ValueError('card caption names differ from native resources')
        resource_base = (base + len(image) + 3) & ~3
        resources = bytearray(4 * len(texts)); descriptors = []
        for index, text in enumerate(texts):
            encoded = (text + '\0').encode('utf-16le')
            record = resource_base + len(resources); descriptors.append(record)
            resources += struct.pack('<BBHI', len(encoded) // 2, 1, 0, record + 8) + encoded
            resources += bytes(-len(resources) & 3)
            struct.pack_into('<I', resources, index * 4, record)
        image += bytes(resource_base - base - len(image)) + resources
        resource_asm = folder / 'resources.S'; resource_obj = folder / 'resources.o'
        resource_asm.write_text('''
            .syntax unified
            .arm
            .text
            .global m10v_resource_primary
            .type m10v_resource_primary,%function
        m10v_resource_primary:
            sub r8,fp,#0xb0
            mov r0,r8
            movw r3,#786
            cmp r7,r3
            blo 1f
            movw r3,#936
            cmp r7,r3
            bhi 1f
            movw r3,#786
            sub r7,r7,r3
            movw r3,:lower16:m10v_string_descriptors
            movt r3,:upper16:m10v_string_descriptors
            ldr r7,[r3,r7,lsl #2]
            ldr pc,=0x53396700
        1:  movw r3,#0x2bac
            movt r3,#0x5500
            ldr r3,[r3,r9,lsl #2]
            ldr r7,[r3,r7,lsl #2]
            ldr pc,=0x53396700
            .global m10v_resource_secondary
            .type m10v_resource_secondary,%function
        m10v_resource_secondary:
            movw r3,#786
            cmp r7,r3
            blo 2f
            movw r3,#936
            cmp r7,r3
            bhi 2f
            movw r3,#786
            sub r12,r7,r3
            movw r3,:lower16:m10v_string_descriptors
            movt r3,:upper16:m10v_string_descriptors
            ldr r3,[r3,r12,lsl #2]
            ldr pc,=0x5339710c
        2:  movw r3,#0x2bac
            movt r3,#0x5500
            ldr r3,[r3,r0,lsl #2]
            ldr r3,[r3,r7,lsl #2]
            ldr pc,=0x5339710c
            .ltorg
        '''.replace('#936',f'#{last_resource}'))
        if sd_library:
            text=resource_asm.read_text()
            for name,target,register in [('primary',0x53396700,7),('secondary',0x5339710c,3)]:
                code=f"""movw r3,#1007
            cmp r7,r3
            blo .L{name}_static
            movw r3,#1011
            cmp r7,r3
            bhi .L{name}_extended
            b .L{name}_custom
        .L{name}_extended:
            movw r3,#1111
            cmp r7,r3
            blo .L{name}_static
            movw r3,#1115
            cmp r7,r3
            bhi .L{name}_static
        .L{name}_custom:
            sub sp,sp,#80
            push {{r0-r12,lr}}
            mov r0,r7
            add r1,sp,#72
            bl m10v_menu_custom_resource
            str r0,[sp,#{register*4}]
            pop {{r0-r12,lr}}
"""
                if name=='primary':code+="sub r8,fp,#0xb0\nmov r0,r8\n"
                code+=f"ldr pc,={hex(target)}\n.L{name}_static:\n"
                text=text.replace('m10v_resource_'+name+':','m10v_resource_'+name+':\n'+code)
            resource_asm.write_text(text)
        subprocess.run([compiler, *compile_flags, '-c', str(resource_asm), '-o', str(resource_obj)], check=True, capture_output=True)
        resource_code_base = (base + len(image) + 15) & ~15
        resource_code, resource_symbols = link_object(resource_obj.read_bytes(), resource_code_base,
            {'m10v_string_descriptors': resource_base,**symbols}, 'm10v_resource_')
        image += bytes(resource_code_base - base - len(image)) + resource_code; symbols.update(resource_symbols)
        chain_asm = folder / 'chain.S'; chain_obj = folder / 'chain.o'
        chain_asm.write_text('''
            .syntax unified
            .arm
            .text
            .global m10v_chain_capture
            .type m10v_chain_capture,%function
        m10v_chain_capture:
            push {r0-r12,lr}
            mrs r0,cpsr
            mov r1,sp
            bic sp,sp,#7
            sub sp,sp,#8
            stm sp,{r0,r1}
            mov r0,r4
            bl m10v_capture_library
            ldm sp,{r0,r1}
            mov sp,r1
            msr cpsr_fs,r0
            pop {r0-r12,lr}
            ldr pc,=0x536abd28
            .ltorg
        '''.replace('            bl m10v_capture_library',
            '            mov r1,#193\n            mov r2,#0\n            bl m10v_lifecycle_phase\n            mov r0,r4\n            bl m10v_capture_library\n            mov r2,r0\n            mov r0,r4\n            mov r1,#194\n            bl m10v_lifecycle_phase\n            mov r0,r4\n            mov r1,#190\n            mov r2,#0\n            bl m10v_lifecycle_phase' if lifecycle_trace else '            bl m10v_capture_library'))
        if half_pair_enabled:
            chain_asm.write_text(chain_asm.read_text().replace('            ldm sp,{r0,r1}', '            mov r0,r4\n            bl m10v_half_pair_camera\n            ldm sp,{r0,r1}'))
        subprocess.run([compiler, *compile_flags, '-c', str(chain_asm), '-o', str(chain_obj)], check=True, capture_output=True)
        chain_base = (base + len(image) + 15) & ~15
        chain, chain_symbols = link_object(chain_obj.read_bytes(), chain_base, symbols, 'm10v_chain_')
        image += bytes(chain_base - base - len(image)) + chain; symbols.update(chain_symbols)
        if half_pair_enabled:
            def pair_bl(at,target):return 0xeb000000|(((target-at-8)>>2)&0xffffff)
            pair_calls=[at for at in range(chain_base,chain_base+len(chain)-3,4) if struct.unpack_from('<I',chain,at-chain_base)[0]==pair_bl(at,symbols['m10v_half_pair_camera'])]
            if len(pair_calls)!=1:raise ValueError('half-pair JPEG handoff differs')
            half_pair_report={'enabled':True,'schema':'m10v-half-pair/v1','handoff':{'callsite':pair_calls[0],'target':symbols['m10v_half_pair_camera']},'storage':'owned-native-bank','backend':'native-IIP','frame_filesystem_calls':0,'cpu_pixel_reads':0,'cpu_pixel_writes':0,'first_original_preserved':True,'camera_tested':False}
        # All artwork stays inside the appended RTOS ROM, leaving ICONBIN and
        # its fixed flash partition unchanged. Stock directory entries remain exact.
        icon_table = base + len(image)
        stock_directory = (ROOT/'native/gr3/m10v_stock_icon_directory.bin').read_bytes()
        icon_pixels = (ROOT/'native/gr3/m10v_icons.rgba').read_bytes()
        if len(stock_directory)!=671*4 or len(icon_pixels)!=78*6400: raise ValueError('icon inventory differs')
        # Retired IDs 1..32 keep their descriptors and decoder identity, but
        # use the generic LUT thumbnail. Only current artwork occupies ROM.
        icon_artwork_sha = hashlib.sha256(icon_pixels).hexdigest()
        retired_icon_count = 32 if sd_library else 0
        icon_pixels = icon_pixels[retired_icon_count*6400:]
        focal_icons=bool(sd_library and custom_zoom)
        aspect_icon_first = 855 if focal_icons else 782
        old_icon_count = aspect_icon_first+2
        old_descriptor_count=113+int(focal_icons)
        half_frame=bool(camera_model=='gr3' and base>=0x540be000)
        half_pixels=(ROOT/'native/gr3/m10v_half_frame_icon.rgba').read_bytes() if half_frame else b''
        if half_frame and len(half_pixels)!=9600:raise ValueError('half-frame icon extent differs')
        icon_count = 878 if half_frame else 877
        descriptor_count=old_descriptor_count+10+int(hdf_adj_report is not None)+int(half_frame)
        icon_descriptors = icon_table + icon_count*4
        icon_data = icon_descriptors + descriptor_count*8
        image += stock_directory + b''.join(struct.pack('<I',icon_descriptors+i*8) for i in range(111))
        if focal_icons:image+=struct.pack('<I',icon_descriptors+111*8)*73
        image += b''.join(struct.pack('<I',icon_descriptors+(111+int(focal_icons)+i)*8) for i in range(2))
        image += bytes(4*(858-old_icon_count))
        image += bytes(3*4) # Retired styles 858..860 are not bound.
        image += b''.join(struct.pack('<I',icon_descriptors+(old_descriptor_count+i)*8) for i in range(3))
        image += bytes(5*4) # Retired anime enum resources 864..868 remain unbound.
        image += b''.join(struct.pack('<I',icon_descriptors+(old_descriptor_count+3+i)*8) for i in range(2))
        image += b''.join(struct.pack('<I',icon_descriptors+(old_descriptor_count+5+i)*8) for i in range(3))
        image+=struct.pack('<I',icon_descriptors+(old_descriptor_count+8)*8) if hdf_adj_report else bytes(4)
        image+=struct.pack('<I',icon_descriptors+(old_descriptor_count+8+int(hdf_adj_report is not None))*8)
        image+=struct.pack('<I',icon_descriptors+(old_descriptor_count+9+int(hdf_adj_report is not None))*8)
        if half_frame:image+=struct.pack('<I',icon_descriptors+(old_descriptor_count+10+int(hdf_adj_report is not None))*8)
        image += b''.join(struct.pack('<HHI',40,40,(icon_data+(len(icon_pixels) if i<retired_icon_count else (i-retired_icon_count)*6400))//4) for i in range(78))
        if sd_library:
            image += bytes(5*8) # Reserved ROM padding; dynamic metadata is in owned RAM.
            image += struct.pack('<HHI',40,40,(icon_data+len(icon_pixels))//4)
        image += struct.pack('<HHI',40,40,(icon_data+len(icon_pixels)+(6400 if sd_library else 0))//4)
        color_pixels=(ROOT/'native/gr3/m10v_charmera_ui.rgba').read_bytes()
        if len(color_pixels)!=35584:raise ValueError('Charmera color artwork extent differs')
        color_at=icon_data+len(icon_pixels)+(12800 if sd_library else 6400)
        for width,height in [(64,16)]*4+[(400,12)]:
            image += struct.pack('<HHI',width,height,color_at//4);color_at+=width*height*4
        pixel_pixels=(ROOT/'native/gr3/m10v_pixel_world.rgba').read_bytes()
        if len(pixel_pixels)!=6400:raise ValueError('Pixel World icon extent differs')
        pixel_icon_data=icon_data+len(icon_pixels)+(12800 if sd_library else 6400)+len(color_pixels)
        image += struct.pack('<HHI',40,40,pixel_icon_data//4)
        if not sd_library:image += bytes(6*8) # keep sparse style icons at 762 in both layouts
        style_pixels=(ROOT/'native/gr3/m10v_style_filters.rgba').read_bytes()
        if len(style_pixels)!=7*6400:raise ValueError('style icon extent differs')
        style_icon_data=pixel_icon_data+len(pixel_pixels)
        image += b''.join(struct.pack('<HHI',40,40,(style_icon_data+i*6400)//4) for i in range(7))
        image += bytes(5*8) # immutable spare descriptors for second grid row
        spectral_icon=(ROOT/'native/gr3/m10v_5213.rgba').read_bytes()
        if len(spectral_icon)!=6400:raise ValueError('5213 icon extent differs')
        image += struct.pack('<HHI',40,40,(style_icon_data+len(style_pixels))//4)
        d76_icon_pixels=(ROOT/'native/gr3/m10v_d76.rgba').read_bytes()
        if len(d76_icon_pixels)!=7*6400:raise ValueError('D76 icon extent differs')
        d76_icon_data=style_icon_data+len(style_pixels)+len(spectral_icon)
        image += b''.join(struct.pack('<HHI',40,40,(d76_icon_data+i*6400)//4) for i in range(7))
        if focal_icons:image+=struct.pack('<HHI',60,20,0) # UI bitmap, after existing111 descriptors.
        aspect_pixels=(ROOT/'native/gr3/m10v_aspect_icons.rgba').read_bytes()
        if len(aspect_pixels)!=19200:raise ValueError('aspect icon extent differs')
        aspect_icon_data=d76_icon_data+len(d76_icon_pixels)
        image += b''.join(struct.pack('<HHI',60,40,(aspect_icon_data+i*9600)//4) for i in range(2))
        anime_pixels=(ROOT/'native/gr3/m10v_anime_e6.rgba').read_bytes()[3*6400:]
        if len(anime_pixels)!=3*6400:raise ValueError('anime artwork extent differs')
        anime_data=aspect_icon_data+len(aspect_pixels)
        for i in range(3):image+=struct.pack('<HHI',40,40,(anime_data+i*6400)//4)
        c41_pixels=(ROOT/'native/gr3/m10v_c41.rgba').read_bytes()
        if len(c41_pixels)!=12800:raise ValueError('C41 artwork extent differs')
        c41_data=anime_data+len(anime_pixels)
        for i in range(2):image+=struct.pack('<HHI',40,40,(c41_data+i*6400)//4)
        extra_pixels=(ROOT/'native/gr3/m10v_extra_films.rgba').read_bytes()
        if len(extra_pixels)!=25600:raise ValueError('extra film artwork extent differs')
        for i in range(3):image+=struct.pack('<HHI',40,40,(c41_data+len(c41_pixels)+i*6400)//4)
        hdf_adj_pixels=(ROOT/'native/gr3/m10v_hdf_adj.rgba').read_bytes() if hdf_adj_report else b''
        if hdf_adj_report:
            if len(hdf_adj_pixels)!=6400:raise ValueError('HDF ADJ icon extent differs')
            hdf_adj_icon_data=c41_data+len(c41_pixels)+len(extra_pixels)
            image+=struct.pack('<HHI',40,40,hdf_adj_icon_data//4)
            hdf_adj_report['icon']={'id':874,'descriptor':icon_descriptors+(old_descriptor_count+8)*8,
                'pixels':hdf_adj_icon_data,'bytes':6400,'width':40,'height':40,'sha256':hashlib.sha256(hdf_adj_pixels).hexdigest()}
        image+=struct.pack('<HHI',40,40,(c41_data+len(c41_pixels)+3*6400)//4)
        unknown_pixels=(ROOT/'native/gr3/m10v_unknown_film.rgba').read_bytes()
        if len(unknown_pixels)!=6400:raise ValueError('unknown recorded film icon extent differs')
        unknown_data=c41_data+len(c41_pixels)+len(extra_pixels)+len(hdf_adj_pixels)
        image+=struct.pack('<HHI',40,40,unknown_data//4)
        if half_frame:
            half_icon_data=c41_data+len(c41_pixels)+len(extra_pixels)+len(hdf_adj_pixels)+len(unknown_pixels)
            image+=struct.pack('<HHI',60,40,half_icon_data//4)
        image += icon_pixels
        if sd_library:
            from scripts.generate_m10v_film_cards import custom_icon
            custom_pixels=(ROOT/'native/gr3/m10v_custom_icon.rgba').read_bytes()
            if custom_pixels!=custom_icon():raise ValueError('custom LUT icon differs from source')
            image += custom_pixels
        image += (ROOT/'native/gr3/m10v_charmera.rgba').read_bytes()
        image += color_pixels+pixel_pixels+style_pixels+spectral_icon+d76_icon_pixels+aspect_pixels+anime_pixels+c41_pixels+extra_pixels+hdf_adj_pixels+unknown_pixels+half_pixels
        icon_asm=folder/'icons.S';icon_obj=folder/'icons.o'
        icon_asm.write_text("""
            .syntax unified
            .arm
            .text
            .global m10v_icon_pixels
            .type m10v_icon_pixels,%function
        m10v_icon_pixels:
            push {r0,r1}
            mrs r0,cpsr
            ldrh r1,[r5,#0x24]
            FOCAL_ICON_DISPATCH
            movw ip,#671
            cmp r1,ip
            blo 1f
            movw ip,#ICON_LAST
            cmp r1,ip
            bhi 1f
            lsl ip,r6,#2
            b 2f
        1:  add ip,lr,r6,lsl #2
        2:  msr cpsr_fs,r0
            pop {r0,r1}
            ldr pc,=0x5320a838
            .ltorg
        """.replace('ICON_LAST',str(icon_count-1)).replace('FOCAL_ICON_DISPATCH','movw ip,#855\n            cmp r1,ip\n            bhs 4f\n            movw ip,#782\n            cmp r1,ip\n            bhs .Lfocal_pixels\n        4:' if focal_icons else ''))
        if focal_icons:
            icon_asm.write_text(icon_asm.read_text()+'''
        .Lfocal_pixels:
            msr cpsr_fs,r0
            pop {r0,r1}
            push {r0-r12,lr}
            mrs ip,cpsr
            push {ip,lr}
            ldrh r0,[r5,#0x24]
            bl m10v_zoom_icon_decode
            cmp r0,#0
            beq 3f
            str r0,[fp,#-0x80]
            str r0,[sp,#56]
            pop {ip,lr}
            msr cpsr_fs,ip
            pop {r0-r12,lr}
            ldr pc,=0x5320a838
        3:  pop {ip,lr}
            msr cpsr_fs,ip
            pop {r0-r12,lr}
            ldr pc,=0x5320a9b4
            .ltorg
        ''')
        if sd_library:
            # Private resources fall back to immutable 40px icons unless their
            # live view owner has published a valid RAM descriptor directory.
            for i,index in enumerate((32,65,66,67,34)):
                struct.pack_into('<I',image,icon_table-base+(749+i)*4,icon_descriptors+index*8)
            text=icon_asm.read_text()
            for name,reg,idreg,ret in [('width',3,1,0x53209fd4),('height',3,1,0x5320a008),('draw',2,3,0x5320a80c)]:
                text+=f"\n.global m10v_icon_directory_{name}\n.type m10v_icon_directory_{name},%function\nm10v_icon_directory_{name}:\n"
                text+="push {r0-r12,lr}\nmrs ip,cpsr\npush {ip,lr}\n"
                text+=f"movw r0,#{icon_table&65535}\nmovt r0,#{icon_table>>16}\nstr r0,[sp,#{8+reg*4}]\nldr r1,[sp,#{8+idreg*4}]\n"
                text+=f"movw ip,#749\ncmp r1,ip\nblo .L{name}_done\nmovw ip,#753\ncmp r1,ip\nbls .L{name}_dynamic\nmovw ip,#769\ncmp r1,ip\nblo .L{name}_done\nmovw ip,#773\ncmp r1,ip\nbhi .L{name}_done\n.L{name}_dynamic:\n"
                text+=f"bl m10v_settings_controller_card_directory\ncmp r0,#0\nstrne r0,[sp,#{8+reg*4}]\n.L{name}_done:\npop {{ip,lr}}\nmsr cpsr_fs,ip\npop {{r0-r12,lr}}\nldr pc,={hex(ret)}\n.ltorg\n"
            icon_asm.write_text(text)

        subprocess.run([compiler,*compile_flags,'-c',str(icon_asm),'-o',str(icon_obj)],check=True,capture_output=True)
        icon_base=(base+len(image)+15)&~15
        icon_code,icon_symbols=link_object(icon_obj.read_bytes(),icon_base,externals=symbols,prefix='m10v_icon_',additional_exports=tuple('m10v_icon_directory_'+n for n in ('width','height','draw')) if sd_library else ())
        image += bytes(icon_base-base-len(image))+icon_code; symbols.update(icon_symbols)
        from scripts.build_gr3_isp_base import build_isp_base
        isp_base = (base + len(image) + 15) & ~15
        isp_code, isp_report = build_isp_base(isp_base,appended_slots=appended_slots)
        image += bytes(isp_base-base-len(image)) + isp_code
    sha = lambda data: hashlib.sha256(data).hexdigest()
    appended_report=None
    if appended_slots:
        from scripts.build_gr3_film_slot_extension import build_appended_slots
        append_base=(base+len(image)+15)&~15
        append_code,appended_report=build_appended_slots(append_base,base,capture_stock_rtos(),symbols)
        image+=bytes(append_base-base-len(image))+append_code
    border_component=None
    if border_hardware:
        from scripts.build_gr3_border_runtime import build as build_border_runtime, REUSED
        border_base=(base+len(image)+15)&~15
        border_code,border_component=build_border_runtime(border_base,capture_stock_rtos(camera_model),
            {name:symbols[name] for name in REUSED},camera_model=camera_model,enabled=True,
            out_dir=out/'border-runtime')
        image+=bytes(border_base-base-len(image))+border_code
        symbols.update(border_component['symbols'])
        # Redirect only the owned chain's single capture-library call. The
        # adapter calls the same library first, then checks the frozen shot and
        # bank provenance before publishing an outward hardware canvas.
        def chain_bl(at,target):
            delta=target-at-8
            if (at|target)&3 or not -(1<<25)<=delta<(1<<25):
                raise ValueError('border JPEG handoff branch out of range')
            return 0xeb000000|((delta>>2)&0xffffff)
        callsites=[at for at in range(chain_base,chain_base+len(chain)-3,4)
                   if struct.unpack_from('<I',image,at-base)[0]==chain_bl(at,symbols['m10v_capture_library'])]
        if len(callsites)!=1:
            raise ValueError('owned JPEG chain library callsite changed')
        struct.pack_into('<I',image,callsites[0]-base,
                         chain_bl(callsites[0],symbols['m10v_border_runtime_jpeg']))
        if struct.unpack_from('<I',image,callsites[0]-base)[0]!=chain_bl(callsites[0],symbols['m10v_border_runtime_jpeg']):
            raise ValueError('border JPEG adapter readback failed')
        border_component['jpeg_handoff']={'callsite':callsites[0],
            'target':symbols['m10v_border_runtime_jpeg'],'original_target':symbols['m10v_capture_library']}
    if half_pair_enabled:
        if border_component:
            pair_guard=border_component['guard']
        else:
            from scripts.build_gr3_border_wait_guard import build as build_pair_guard
            guard_base=(base+len(image)+15)&~15
            guard_code,pair_guard=build_pair_guard(guard_base,capture_stock_rtos(camera_model),border_enabled=True,internal_guard_research=True,camera_model=camera_model)
            image+=bytes(guard_base-base-len(image))+guard_code
            symbols.update(pair_guard['symbols'])
        iip_code,linked_iip_symbols=link_object(iip_object,iip_start,symbols,'m10v_half_pair_iip_')
        if len(iip_code)!=iip_size or linked_iip_symbols!=iip_symbols:
            raise ValueError('IIP forward-link layout changed')
        image[iip_start-base:iip_start-base+iip_size]=iip_code
        half_pair_report.update(iip_guard=pair_guard,iip_component={'base':iip_start,'code_bytes':len(iip_code),'code_sha256':sha(iip_code),'symbols':iip_symbols})
    manifest = {'camera_model':camera_model,'schema': 'm10v-gr3-native-film-runtime/v2', 'base': base, 'symbols': symbols,
                'code_bytes': len(image), 'code_sha256': sha(image), 'film_count': 103, 'slots': 10,
                'sources': {p: sha((ROOT / p).read_bytes()) for p in
                            ('native/gr3/extra-films-reference.json','native/gr3/m10v_extra_films_native_profiles.h','native/gr3/m10v_extra_films.rgba','web/gr3/extra-films-luts.json','scripts/build_gr3_extra_films_reference.py','scripts/fit_gr3_extra_films_native.py','scripts/verify_gr3_extra_films_reference.py','native/gr3/c41-reference.json','native/gr3/m10v_c41_native_profiles.h','native/gr3/m10v_c41.rgba','web/gr3/c41-luts.json','scripts/build_gr3_c41_reference.py','scripts/fit_gr3_c41_native.py','scripts/verify_gr3_c41_reference.py','node/gr3-sd-pre-instax-contract.json','node/gr3-sd-pre-retired-anime-contract.json','node/gr3-sd-pre-c41-contract.json','native/gr3/m10v_anime.h','native/gr3/anime-e6-reference.json','native/gr3/m10v_anime_e6_native_profiles.h','native/gr3/m10v_anime_e6.rgba','native/gr3/m10v_anime_ui.rgba','native/gr3/anime-ui.json','native/gr3/anime-ui-raster.json','third_party/anime-ui-font/OFL.txt','web/gr3/anime-e6-luts.json','scripts/build_gr3_anime_e6_reference.py','scripts/fit_gr3_anime_e6_native.py','scripts/verify_gr3_anime_e6_reference.py','scripts/generate_m10v_anime_ui.py','node/gr3-sd-pre-anime-e6-contract.json','node/gr3-sd-pre-d76-mono-contract.json','native/gr3/film_d76_0.c','native/gr3/film_d76_1.c','native/gr3/film_d76_0_data.h','native/gr3/film_d76_1_data.h','native/gr3/m10v_d76.rgba','native/gr3/d76-reference.json','web/gr3/d76-luts.json','scripts/build_gr3_d76_reference.py','scripts/fit_gr3_d76_native.py','scripts/verify_gr3_d76_reference.py','native/gr3/m10v_d76_native_profiles.h','node/gr3-sd-pre-universal-halation-contract.json','node/gr3-sd-pre-d76-contract.json','native/gr3/m10v_spectral_native_profiles.h','native/gr3/m10v_film_directory.h','web/gr3/film-directory.json','node/gr3-film-directory.mjs','scripts/generate_m10v_directory.py','native/gr3/film_spectral_data.h','native/gr3/spectral-reference.json','web/gr3/spectral-luts.json','scripts/build_gr3_spectral_reference.py','scripts/fit_gr3_spectral_native.py','scripts/verify_gr3_spectral_reference.py','native/gr3/m10v_5213.rgba','docs/research/aerocolor-2460/official-medium-curves.json','node/gr3-sd-pre-aerocolor-contract.json','node/gr3-sd-pre-directory-contract.json','native/gr3/film_style_filters_0.c','native/gr3/film_style_filters_1.c','native/gr3/film_style_filters_0_data.h','native/gr3/film_style_filters_1_data.h','native/gr3/m10v_style_filters.rgba','native/gr3/style-filters-reference.json','web/gr3/style-filters-luts.json','scripts/build_gr3_style_filters_reference.py','scripts/fit_gr3_style_filters_native.py','scripts/verify_gr3_style_filters_reference.py','native/gr3/film_newstocks.c','native/gr3/film_newstocks_data.h','native/gr3/newstocks-reference.json','web/gr3/newstocks-luts.json','scripts/build_gr3_newstocks_reference.py','scripts/fit_gr3_newstocks_native.py','scripts/verify_gr3_newstocks_reference.py','native/gr3/film_curated.c','native/gr3/film_curated_data.h','native/gr3/curated-reference.json','web/gr3/curated-luts.json','scripts/verify_gr3_curated_reference.py','scripts/build_gr3_curated_reference.py','scripts/fit_gr3_curated_native.py','scripts/build_gr3_harman_reference.py','scripts/verify_gr3_harman_reference.py','native/gr3/film_harman.c','native/gr3/film_harman.h','native/gr3/film_harman_data.h','native/gr3/harman-reference.json','web/gr3/harman-luts.json','scripts/verify_gr3_5207_reference.py','scripts/build_gr3_5207_reference.py','web/gr3/5207-lut.json','native/gr3/film_5207.c','native/gr3/film_5207.h','native/gr3/m10v_color_cache.h','native/gr3/film_5207_data.h','native/gr3/5207-reference.json','native/gr3/m10v_pixel_world.h','native/gr3/m10v_pixel_world.rgba','native/gr3/m10v_charmera.h','native/gr3/m10v_charmera.rgba','native/gr3/m10v_charmera_ui.rgba','scripts/generate_m10v_charmera_ui.py','native/gr3/m10v_library.c', 'native/gr3/m10v_library.h',
                             'native/gr3/m10v_universal_halation.h','native/gr3/halation_core.c', 'native/gr3/halation_core.h', 'native/gr3/halation_energy.h','native/gr3/m10v_detail.c','scripts/build_gr3_native_detail.py','scripts/build_gr3_menu_patches.py','scripts/build_gr3_isp_base.py',
                             'native/gr3/m10v_legacy_data.h','web/gr3/film-catalog.json','scripts/generate_m10v_catalog.py',
                             'native/gr3/m10v_library_camera.c', 'native/gr3/m10v_library_menu.c',
                             'native/gr3/m10v_library_capture.c',
                             'native/gr3/m10v_debug.c','native/gr3/m10v_debug.h','native/gr3/m10v_capture_profile.h',
                             'scripts/build_gr3_m10v_library.py','scripts/generate_m10v_icons.py',
                             'native/gr3/m10v_icons.rgba','native/gr3/m10v_stock_icon_directory.bin')},
                'compiler': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
                'flags': compile_flags, 'render_flags': render_flags, 'debug_compile_flags': debug_flags, 'firmware_artifact': False, 'camera_tested': False,
                'abi': 'M10V state184 + explicit semiplanar CbCr422 image + date6',
                'dependencies': [], 'scratch_max_bytes': 589824}
    if half_pair_report:manifest['half_pair']=half_pair_report
    if half_pair_enabled:
        from scripts.build_gr3_border_wait_guard import SOURCES as PAIR_GUARD_SOURCES
        pair_sources=[*PAIR_GUARD_SOURCES,'native/gr3/m10v_border_fill_plan.h','native/gr3/m10v_border_canvas.h','native/gr3/m10v_border.h','native/gr3/m10v_half_pair_iip.c','native/gr3/m10v_half_pair_iip.h','native/gr3/m10v_half_pair.c','native/gr3/m10v_half_pair.h','native/gr3/m10v_half_pair_camera.c','native/gr3/m10v_half_pair_camera.h']
        manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in pair_sources})
    if sd_library:
        manifest['custom_isp']={'schema':'m10v-custom-isp/v1','record_offset':6688,'payload_bytes':1572,
            'preview_offset':0x213c,'preview_bytes':0x4000,'storage':'inline TopMenu allocation',
            'recipe_offset':0x5150,'recipe_bytes':1576,'frame_filesystem_calls':0,
            'reader_veneers':{'record':base+0xf0,'u32':base+0xf4}}
        manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_film_card.c','native/gr3/m10v_film_card.h','native/gr3/m10v_film_card_data.h','native/gr3/m10v_film_font_raster.json','native/gr3/m10v_square_icon_raster.json','native/gr3/m10v_card_captions.json','scripts/generate_m10v_film_cards.py','scripts/generate_m10v_card_captions.py','native/gr3/m10v_custom_icon.rgba','third_party/noto-sans/NotoSans-Bold.ttf','third_party/noto-sans/OFL.txt','third_party/noto-cjk/OFL.txt']})
    manifest['appended_slots']=appended_report
    manifest['sources']['native/gr3/m10v_tone.h']=sha((ROOT/'native/gr3/m10v_tone.h').read_bytes())
    if appended_slots:manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['scripts/build_gr3_film_slot_extension.py','native/gr3/m10v_tone_menu.c']})
    manifest['sd_library']=sd_library
    manifest['film_library_enabled']=film_library
    manifest['hdf_menu']=hdf_menu_report
    manifest['hdf_adj']=hdf_adj_report
    manifest['digital_hdf']=hdf_report
    manifest['hdf_default']=hdf_default
    manifest['hdf_enabled']=hdf_enabled
    manifest['border']={'enabled':border_enabled,'hardware_ready':False,'pixel_pipeline_enabled':border_hardware,
                        'hardware_component':border_component,
                        'compile_flags':border_flags,
                        'journal_files':['BORDERA.BIN','BORDERB.BIN'] if border_enabled else [],
                        'cache_owner_offset':border_cache_offset if border_enabled else None,
                        'cache_bytes':16 if border_enabled else 0,'resource_ids':[1155,1156,1157] if border_enabled else [],
                        'startup_refresh':'LiveView UI enter route08000000, only if cache unavailable' if border_enabled else None,
                        'capture_selection':('immutable per-recipe word; ISP/IIP border component installed; camera acceptance pending' if border_hardware else 'immutable per-recipe word; compositor not installed') if border_enabled and recipe_snapshot else 'status-bearing cached snapshot only; compositor not installed',
                        'snapshot_installed':bool(border_enabled and recipe_snapshot),
                        'shot_offset':0x510c if border_enabled and recipe_snapshot else None,
                        'shot_orientation':'saved capture SI; EXIF1/3/6/8; frozen with style' if border_enabled and recipe_snapshot else None}
    if border_enabled:manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_border_camera.c','native/gr3/m10v_border_camera.h','native/gr3/m10v_border.h']})
    if border_enabled and recipe_snapshot:manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_border_shot.c','native/gr3/m10v_border_shot.h']})
    if border_component:
        manifest['sources'].update(border_component['sources'])
        manifest['sources'].update(border_component['guard']['sources'])
    manifest['universal_halation']=universal_halation
    manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_digital_hdf.c','scripts/build_gr3_digital_hdf.py','native/gr3/m10v_hdf_menu.c','scripts/build_gr3_hdf_menu.py','native/gr3/m10v_hdf_state.h','native/gr3/m10v_hdf_adj.c','native/gr3/m10v_hdf_adj.rgba','scripts/build_gr3_hdf_adj.py','node/gr3-sd-pre-oriented-stamp-contract.json']})
    manifest['capture_lifecycle']=lifecycle_report
    manifest['experimental_capture']={'candidate_color':candidate_color,'spatial_neon':spatial_neon,'full_isp_effects':False,'save_chain_fixed':False}
    if native_color:manifest['experimental_capture']['native_color']=True
    if native_grain:manifest['experimental_capture']['native_grain']=True
    if texture_neon:manifest['experimental_capture']['texture_neon']=True
    extra_sources=['native/gr3/m10v_aspect_config.h','native/gr3/m10v_half_frame_icon.rgba','native/gr3/half-frame-icon.json','scripts/generate_gr3_half_frame_icon.py','native/gr3/m10v_aspect_icons.rgba','native/gr3/aspect-icons.json','scripts/generate_gr3_aspect_icons.py','native/gr3/m10v_film_color_candidates.h','native/gr3/isp-film-targets.json','scripts/build_gr3_isp_film_targets.py','native/gr3/m10v_spatial_accel.c','native/gr3/m10v_spatial_accel.h','native/gr3/m10v_save_trace.c','native/gr3/m10v_save_trace.h','native/gr3/m10v_capture_raw_lifetime.c','native/gr3/m10v_capture_raw_lifetime.h','scripts/build_gr3_save_trace.py','scripts/build_gr3_capture_lifecycle.py','native/gr3/m10v_capture_lifecycle.c','native/gr3/m10v_file_trace.c','scripts/build_gr3_file_trace.py']
    manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in extra_sources})
    manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_film_identity.h','native/gr3/m10v_unknown_film.rgba','node/gr3-sd-pre-square-art-contract.json']})
    if texture_neon:manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_texture_accel.c','native/gr3/m10v_texture_accel.h','scripts/build_gr3_texture_accel.py']})
    if save_chain_trace:manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_module_dispatch_trace.c','scripts/build_gr3_module_dispatch_trace.py','scripts/build_gr3_pool_release_trace.py']})
    manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_custom_isp.h','native/gr3/m10v_isp_frame_color.c','native/gr3/m10v_isp_frame_color.h','native/gr3/m10v_isp_recipe_color.c','native/gr3/m10v_isp_recipe_color.h','scripts/build_gr3_isp_recipe_color.py','scripts/build_gr3_isp_color_hook.py']})
    if native_color:manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_isp_native_look.c','native/gr3/m10v_isp_native_look.h','native/gr3/m10v_isp_native_look_profiles.h','native/gr3/m10v_isp_multiaxis.c','native/gr3/m10v_isp_multiaxis.h']})
    if native_grain:manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['scripts/build_gr3_native_grain_hooks.py']})
    if view_deferred:manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_view_deferred.c','native/gr3/m10v_view_deferred.h','native/gr3/m10v_view_recovery.h','scripts/build_gr3_view_deferred.py']})
    if candidate_color:
        header=(ROOT/'native/gr3/m10v_film_color_candidates.h').read_text()
        manifest['color_candidates']=[]
        metadata=json.loads((ROOT/'native/gr3/isp-film-targets.json').read_text())['cpu_candidates']
        for name,symbol,key in [('5207','m10v_5207_candidate_lut','5207'),('Phoenix II','m10v_phoenix_ii_candidate_lut','phoenix_ii')]:
            match=re.search(symbol+r'\[3375\]\[3\]\s*=\s*\{(.*?)\n\};',header,re.S)
            payload=bytes(int(v) for v in re.findall(r'\d+',match.group(1)))
            offset=image.find(payload)
            if len(payload)!=10125 or offset<0 or metadata[key]['table_sha256']!=sha(payload):raise ValueError('candidate color provenance/readback differs')
            manifest['color_candidates'].append({'name':name,'bytes':len(payload),'offset':offset,'sha256':sha(payload),'camera_calibrated':False})
    if sd_library:
        manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_sd_library.h','native/gr3/m10v_sd_library.c','native/gr3/m10v_sd_camera.c','native/gr3/m10v_sd_contract.h','node/gr3-sd-film-pack.mjs','node/gr3-sd-texture-prior-contract.json','node/gr3-sd-pre-styles-contract.json','node/gr3-sd-20261023-contract.json','node/gr3-sd-pre-pixel-contract.json','node/gr3-sd-prior-contract.json','node/gr3-sd-20261021-contract.json','scripts/generate_gr3_sd_contract.mjs']})
    manifest['settings_menu']=settings_report
    manifest['zoom']=zoom_report
    if zoom_report:manifest['sources'].update(zoom_report['sources'])
    if sd_library:
        manifest['sources'].update({p:sha((ROOT/p).read_bytes()) for p in ['native/gr3/m10v_settings.c','native/gr3/m10v_settings.h','native/gr3/m10v_settings_view.c','native/gr3/m10v_settings_view.h','native/gr3/m10v_settings_controller.c','native/gr3/m10v_settings_controller.h','native/gr3/m10v_ab.h','native/gr3/m10v_ab_camera.inc','native/gr3/m10v_ab_host.inc','scripts/build_gr3_settings_hooks.py','node/gr3-settings-menu.mjs']})
    manifest['detail']=detail_report
    manifest['isp_base']=isp_report
    manifest['debug_mode']=debug_mode
    manifest['capture_profile']={'schema':'m10v-capture-profile/v1','counter_service':0x53050b7c,'units':'milliseconds','flush':'once after render and cache writeback','max_batch':32} if profile_mode else None
    manifest['debug_log']={'schema':'m10v-gr3-sd-debug/v1','build_id':f'{debug_build_id:08x}',
        'files':['M10VMN0.BIN','M10VMN1.BIN','M10VCP0.BIN','M10VCP1.BIN','M10VIO0.BIN','M10VIO1.BIN','M10VAK0.BIN','M10VAK1.BIN'],
        'page_bytes':4096,'records_per_channel':63,'guard_address':0x5506821f,'adj_exit_trace':adj_exit_trace} if debug_mode else None
    initial_offset = bytes(image).find(initial)
    if initial_offset < 0 or bytes(image).find(initial, initial_offset+1) >= 0: raise ValueError('initial state not uniquely embedded')
    manifest['initial_state_hex'] = initial.hex()
    manifest['initial_state_offset'] = initial_offset
    film_offset=bytes(image).find(film_payload)
    if film_offset<0:raise ValueError('5207 compiled table readback differs')
    reference_harman=json.loads((ROOT/'native/gr3/harman-reference.json').read_text())
    manifest['film_harman']=[]
    for spec,payload in zip(reference_harman['stocks'],harman_payloads):
        offset=image.find(payload)
        if offset<0:raise ValueError('Harman compiled table readback differs')
        manifest['film_harman'].append({'film_id':spec['id'],'ei':spec['ei'],'offset':offset,'bytes':len(payload),'sha256':sha(payload),'camera_calibrated':False,'film_calibrated':False})
    manifest['film_5207']={'offset':film_offset,'bytes':len(film_payload),'sha256':sha(film_payload),'camera_calibrated':False,'film_calibrated':False}
    manifest['resources'] = {'first_id': 786, 'last_id': last_resource, 'table': resource_base,
                              'descriptors': descriptors, 'texts': texts}
    manifest['film_cards']={'first_id':749,'last_id':773,'ids':[749,750,751,752,753,769,770,771,772,773],'width':128,'height':128,'artwork_height':128,'caption_height':0,'descriptor_storage':'view-owned-heap','descriptor_offset':655360,'directory_offset':655440,'directory_provider':symbols['m10v_settings_controller_card_directory'],'directory_hooks':{n:symbols['m10v_icon_directory_'+n] for n in ('width','height','draw')},'heap_bytes':655540} if sd_library else None
    manifest['film_curated']=[]
    for i,payload in enumerate(curated_payloads):
        offset=bytes(image).find(payload)
        if offset<0:raise ValueError('curated LUT absent from compiled image')
        manifest['film_curated'].append({'film_id':69+i,'offset':offset,'bytes':len(payload),'sha256':sha(payload),'camera_calibrated':False,'film_calibrated':False})
    from scripts.verify_gr3_spectral_reference import verify as verify_spectral
    spectral_payloads=verify_spectral(ROOT)
    manifest['film_spectral']=[]
    for film_id,payload in zip((77,298),spectral_payloads):
        offset=bytes(image).find(payload)
        if offset<0:raise ValueError('spectral LUT absent from compiled image')
        manifest['film_spectral'].append({'film_id':film_id,'offset':offset,'bytes':len(payload),'sha256':sha(payload),'camera_calibrated':False,'film_calibrated':False})
    manifest['film_newstocks']=[]
    for i,payload in enumerate(newstocks_payloads):
        offset=bytes(image).find(payload)
        if offset<0:raise ValueError('new stock LUT absent from compiled image')
        manifest['film_newstocks'].append({'film_id':73+i,'offset':offset,'bytes':len(payload),'sha256':sha(payload),'camera_calibrated':False,'film_calibrated':False})
    manifest['film_style_filters']=[]
    for i,payload in enumerate(style_payloads):
        offset=bytes(image).find(payload)
        if offset<0:raise ValueError('style LUT absent from compiled image')
        manifest['film_style_filters'].append({'film_id':291+i,'offset':offset,'bytes':len(payload),'sha256':sha(payload),'camera_calibrated':False,'film_calibrated':False})
    manifest['film_d76']=[]
    for i,payload in enumerate(d76_payloads):
        mono=payload[::3]
        if any(payload[k]!=payload[k+1] or payload[k]!=payload[k+2] for k in range(0,len(payload),3)):raise ValueError('D76 is not neutral')
        offset=bytes(image).find(mono)
        if offset<0:raise ValueError('D76 mono LUT absent from compiled image')
        manifest['film_d76'].append({'film_id':299+i,'offset':offset,'bytes':len(payload),'sha256':sha(payload),'storage':'mono-u8','stored_bytes':len(mono),'stored_sha256':sha(mono),'camera_calibrated':False,'film_calibrated':False})
    manifest['d76_icons']={'first_id':775,'last_id':781,'pixels':d76_icon_data,'sha256':sha(d76_icon_pixels)}
    manifest['style_icons']={'first_id':762,'last_id':768,'pixels':style_icon_data,'sha256':sha(style_pixels)}
    manifest['aspect_icons']={'first_id':aspect_icon_first,'last_id':aspect_icon_first+1,'width':60,'height':40,'pixels':aspect_icon_data,'sha256':sha(aspect_pixels)}
    manifest['half_frame_icon']={'id':877,'width':60,'height':40,'pixels':half_icon_data,'descriptor':icon_descriptors+(old_descriptor_count+10+int(hdf_adj_report is not None))*8,'sha256':sha(half_pixels)} if half_frame else None
    manifest['icons']={'catalog_count':icon_count,'descriptor_count':descriptor_count,'focal':{'first_id':782,'last_id':854,'width':60,'height':20,'descriptor':icon_descriptors+111*8,'storage':'draw-owned-heap','heap_bytes':4800,'owner_fp_offset':-0x80} if focal_icons else None,'first_id':671,'last_id':748,'width':40,'height':40,'table':icon_table,'descriptors':icon_descriptors,'pixels':icon_data,'sha256':icon_artwork_sha,'payload_bytes':len(icon_pixels),'retired_generic_count':retired_icon_count}
    if sd_library:manifest['custom_film_display']={'name_resources':[1007,1011],'appended_name_resources':[1111,1115],'name_storage':'getter-stack-80-bytes','icon_id':754,'icon_sha256':sha(custom_icon()),'card_art':'name-fitted-inside-square-box-and-stable-palette','legacy_sd_compatible':True,'camera_tested':False}
    (out / 'm10v-library-arm.bin').write_bytes(image)
    (out / 'm10v-library-arm.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'builds/gr3-m10v-library')
    parser.add_argument('--universal-halation',action='store_true')
    parser.add_argument('--appended-slots',action='store_true')
    parser.add_argument('--base',type=lambda v:int(v,0),default=0x540b6000)
    parser.add_argument('--initial-state-hex')
    parser.add_argument('--sd-library',action='store_true')
    parser.add_argument('--profile',action='store_true')
    parser.add_argument('--candidate-color',action='store_true')
    parser.add_argument('--spatial-neon',action='store_true')
    parser.add_argument('--texture-neon',action='store_true')
    parser.add_argument('--save-chain-trace',action='store_true')
    parser.add_argument('--lifecycle-trace',action='store_true')
    parser.add_argument('--recipe-snapshot',action='store_true')
    parser.add_argument('--debug',action='store_true')
    parser.add_argument('--adj-exit-trace',action='store_true')
    parser.add_argument('--debug-build-id',type=lambda v:int(v,0),default=0)
    parser.add_argument('--native-color',action='store_true')
    parser.add_argument('--live-color',action='store_true')
    parser.add_argument('--native-grain',action='store_true')
    parser.add_argument('--view-deferred',action='store_true')
    parser.add_argument('--hdf-only',action='store_true')
    parser.add_argument('--hdf-default',type=int,default=0)
    parser.add_argument('--no-hdf',action='store_true')
    parser.add_argument('--with-hdf',action='store_true')
    parser.add_argument('--border-enabled',action='store_true',help='Include the independent border menu/cache; compositor needs explicit --border-hardware')
    parser.add_argument('--border-hardware',action='store_true',help='Include the complete guarded ISP border pipeline for a camera-test candidate')
    parser.add_argument('--zoom-seed',help='Validated one-time two-slot preset JSON')
    parser.add_argument('--camera-model',choices=['gr3','gr3x'],default='gr3')
    parser.add_argument('--no-custom-zoom',action='store_true',help='Keep original focal crop hooks and hide custom zoom menu (GR IIIx)')
    args = parser.parse_args(); print(json.dumps(build(args.out, base=args.base, initial_state_hex=args.initial_state_hex,debug_mode=args.debug,adj_exit_trace=args.adj_exit_trace,debug_build_id=args.debug_build_id,sd_library=args.sd_library,profile_mode=args.profile,candidate_color=args.candidate_color,spatial_neon=args.spatial_neon,lifecycle_trace=args.lifecycle_trace,recipe_snapshot=args.recipe_snapshot,texture_neon=args.texture_neon,save_chain_trace=args.save_chain_trace,native_color=args.native_color,live_color=args.live_color,appended_slots=args.appended_slots,custom_zoom=not args.no_custom_zoom,zoom_seed=json.loads(args.zoom_seed) if args.zoom_seed else None,universal_halation=args.universal_halation,camera_model=args.camera_model,native_grain=args.native_grain,view_deferred=args.view_deferred,film_library=not args.hdf_only,hdf_default=args.hdf_default,hdf_enabled=False if args.no_hdf else True if args.with_hdf else None,border_enabled=args.border_enabled,border_hardware=args.border_hardware), indent=2))
