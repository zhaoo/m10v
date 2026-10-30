"""Compile the shared M10V film core against independently traced GR IV services."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zlib
from scripts.build_gr3_m10v_library import FLAGS,link_object
from scripts.build_gr3_menu_patches import branch
from scripts.build_gr4_settings_hooks import build_settings_hooks,ORIGINAL_ENTRIES
from scripts.build_gr4_native_detail import build_detail
ROOT=Path(__file__).resolve().parents[1]
SHA='a9a9a51530c35819df47dee1cce9f4f560a17eeed1da258950167d282884fce1'

def sha(b):return hashlib.sha256(b).hexdigest()
def gr4_renderer_source():
    source=(ROOT/'native/gr3/m10v_library.c').read_text()
    for old,new in [('image->width > 6144','image->width > 6256'),('image->height > 4096','image->height > 4176')]:
        if source.count(old)!=1:raise ValueError('shared renderer dimension guard changed')
        source=source.replace(old,new)
    return source

def default_state():
    b=bytearray(184);struct.pack_into('<IHHI',b,0,0x5630314d,5,184,0)
    for i in range(5):
        struct.pack_into('<H6B',b,12+8*i,33 if i==4 else 34+i,0,0,3,3,5,2)
        b[96+8*i]=1;b[99+8*i]=4
    struct.pack_into('<I',b,180,zlib.crc32(b[:180]));return bytes(b)

def validate_state(raw):
    if len(raw)!=184 or struct.unpack_from('<IHHI',raw)!=(0x5630314d,5,184,0) or zlib.crc32(raw[:180])!=struct.unpack_from('<I',raw,180)[0]:raise ValueError('invalid GR4 initial state')
    for i in range(10):
        slot=raw[12+i*8:20+i*8];e=raw[96+i*8:104+i*8]
        f,g,s,a,b,c,p=struct.unpack('<H6B',slot)
        if not f:
            if any(slot) or any(e):raise ValueError('disabled GR4 slots must be empty')
            continue
        if i>=5 or not 1<=f<=78 or g>3 or s>3 or max(a,b,c)>8 or p>3:raise ValueError('invalid GR4 initial slot')
        if any(x>v for x,v in zip(e,[2,8,5,8,1,2,0,0])) or (e[5]>1 if f==67 else f!=68 and e[5]):raise ValueError('invalid GR4 texture')
    if raw[92]>2 or max(raw[93:96])>3 or any(raw[176:180]):raise ValueError('invalid GR4 stamp')
    return raw

def build(out,base,initial_state_hex=None,*,rtos,debug_mode=False,debug_build_id=0):
    if sha(rtos)!=SHA:raise ValueError('GR4 exact RTOS identity required')
    if base&15 or not 0x543d0000<=base<0x54e00000:raise ValueError('GR4 runtime base out of range')
    initial=validate_state(bytes.fromhex(initial_state_hex) if initial_state_hex else default_state())
    profile=json.loads((ROOT/'native/gr4/ui-abi.json').read_text())
    for row in profile['functions']:
        at=int(row['gr4'],16)-0x53000000;raw=bytes.fromhex(row['preimage'])
        if rtos[at:at+len(raw)]!=raw:raise ValueError('GR4 UI ABI preimage differs')
    compiler=os.environ.get('M10V_LLVM_CLANG') or next((p for p in ['/opt/homebrew/opt/llvm/bin/clang','/usr/local/opt/llvm/bin/clang',shutil.which('clang')] if p and Path(p).exists()),None)
    if not compiler:raise RuntimeError('ARM LLVM clang unavailable')
    flags=[*FLAGS,'-I'+str(ROOT/'native/gr3'),'-I'+str(ROOT/'native/gr4'),f'-DM10V_DEBUG_MODE={int(debug_mode)}',f'-DM10V_DEBUG_BUILD_ID={debug_build_id}u','-DM10V_SD_LIBRARY=1','-DM10V_LEGACY_SETTINGS=1']
    symbols={};image=bytearray(0x100);sources=set()
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='m10v-gr4-compile-') as tmp:
        tmp=Path(tmp)
        def compile_source(relative,extra=()):
            source=ROOT/relative;sources.add(relative);obj=tmp/(source.name+'.o')
            if relative=='native/gr3/m10v_library.c':
                source=tmp/'gr4-renderer.c';source.write_text(gr4_renderer_source())
            result=subprocess.run([compiler,*flags,*extra,'-c',str(source),'-o',str(obj)],capture_output=True,text=True)
            if result.returncode:raise ValueError('GR4 ARM compilation failed: '+result.stderr)
            return obj.read_bytes()
        def append(code):
            at=(base+len(image)+15)&~15;image.extend(bytes(at-base-len(image)));image.extend(code);return at
        def module(relative,prefix,extra=()):
            obj=compile_source(relative,extra);at=(base+len(image)+15)&~15
            omitted={
                'm10v_menu_':('m10v_menu_recorded_icon',),
                'm10v_camera_library_':('m10v_camera_library_custom_profile','m10v_camera_library_preview','m10v_camera_library_preview_init',
                    'm10v_camera_library_preview_clear','m10v_camera_library_mutation_begin','m10v_camera_library_mutation_end','m10v_camera_library_mutation_busy','m10v_camera_library_remove','m10v_camera_library_shooting_count','m10v_camera_library_menu_index','m10v_camera_library_reconcile_legacy_selection','m10v_camera_library_select_custom','m10v_camera_library_film_name_stamp'),
                'm10v_sd_camera_':('m10v_sd_camera_custom_record','m10v_sd_camera_custom_name','m10v_sd_camera_catalog_name',
                    'm10v_sd_camera_directory_item','m10v_sd_camera_directory_install','m10v_sd_camera_directory_extent'),
            }
            blob,entries=link_object(obj,at,symbols,prefix,
                additional_exports=('m10v_menu_rows',) if prefix=='m10v_menu_' else (),
                omitted_exports=omitted.get(prefix,()))
            append(blob);symbols.update(entries)
        module('native/gr3/film_curated.c','m10v_curated_')
        module('native/gr3/film_newstocks.c','m10v_newstocks_')
        module('native/gr3/film_style_filters_0.c','m10v_style_filters_0_')
        module('native/gr3/film_style_filters_1.c','m10v_style_filters_1_')
        module('native/gr3/film_d76_0.c','m10v_d76_0_')
        module('native/gr3/film_d76_1.c','m10v_d76_1_')
        module('native/gr3/film_harman.c','m10v_harman_')
        module('native/gr3/film_5207.c','m10v_5207_')
        module('native/gr3/m10v_library.c','m10v_library_',('-DM10V_INITIAL_STATE_BYTES='+','.join(map(str,initial)),))
        module('native/gr4/m10v_library_camera.c','m10v_camera_library_')
        module('native/gr3/m10v_sd_library.c','m10v_sd_')
        module('native/gr4/m10v_sd_camera.c','m10v_sd_camera_')
        if debug_mode:module('native/gr4/m10v_debug.c','m10v_debug_')
        module('native/gr4/m10v_settings.c','m10v_settings_')
        module('native/gr4/m10v_settings_view.c','m10v_settings_view_')
        obj=compile_source('native/gr4/m10v_settings_controller.c');at=(base+len(image)+15)&~15
        external=['m10v_settings_factory_original','m10v_settings_top_dtor_original','m10v_settings_controller_vtable']
        provisional,entries=link_object(obj,at,{**symbols,**dict.fromkeys(external,at)},'m10v_settings_controller_',omitted_exports=('m10v_settings_controller_card_directory',))
        hookbase=(at+len(provisional)+15)&~15
        hooks,settings=build_settings_hooks(hookbase,{**symbols,**entries},rtos)
        code,entries=link_object(obj,at,{**symbols,**settings['exports']},'m10v_settings_controller_',omitted_exports=('m10v_settings_controller_card_directory',))
        append(code);append(hooks);symbols.update(entries)
        obj=compile_source('native/gr4/m10v_detail.c');at=(base+len(image)+15)&~15
        names=['m10v_detail_tables','m10v_detail_common_tables','m10v_detail_red_tables','m10v_detail_phoenix_tables']
        provisional,entries=link_object(obj,at,{**symbols,**dict.fromkeys(names,at)},'m10v_detail_')
        hookbase=(at+len(provisional)+15)&~15
        hooks,detail=build_detail(hookbase,{**symbols,**entries},rtos)
        tables=detail['variant_tables']
        externals=dict(zip(names,[tables['halo'],tables['common'],tables['red'],tables['phoenix']]))
        code,entries=link_object(obj,at,{**symbols,**externals},'m10v_detail_')
        append(code);append(hooks);symbols.update(entries)
        module('native/gr4/m10v_library_menu.c','m10v_menu_',(f'-DM10V_NATIVE_BASE={base}u',))
        module('native/gr4/m10v_library_capture.c','m10v_capture_')
        asm=tmp/'chain.S';sources.add('scripts/build_gr4_m10v_library.py')
        asm.write_text(''' .syntax unified
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
 ldr pc,=0x538dd430
 .ltorg
''')
        obj=tmp/'chain.o';subprocess.run([compiler,*flags,'-c',str(asm),'-o',str(obj)],check=True,capture_output=True)
        at=(base+len(image)+15)&~15;code,entries=link_object(obj.read_bytes(),at,symbols,'m10v_chain_');append(code);symbols.update(entries)
    # Continuations chain into the installed registry (custom slots), while
    # every opcode is restored exactly once before returning to entry +4.
    continuations=[]
    for offset,entry in ORIGINAL_ENTRIES.items():
        original=struct.unpack_from('<I',rtos,entry-0x53000000)[0]
        struct.pack_into('<II',image,offset,original,branch(base+offset+4,entry+4))
        continuations.append({'offset':offset,'entry':entry,'original':original})
    if len(image)>512*1024 or base+len(image)>=0x55000000:raise ValueError('GR4 runtime exceeds executable budget')
    from scripts.verify_gr3_5207_reference import verify
    from scripts.verify_gr3_harman_reference import verify as harman
    from scripts.verify_gr3_curated_reference import verify as curated
    from scripts.verify_gr3_newstocks_reference import verify as newstocks
    payloads=[verify(ROOT),*harman(ROOT),*curated(ROOT),*newstocks(ROOT)]
    if any(bytes(image).find(p)<0 for p in payloads):raise ValueError('film table readback failed')
    sources.update(str(p.relative_to(ROOT)) for p in (ROOT/'native/gr3').glob('*.h'))
    sources.update(str(p.relative_to(ROOT)) for p in (ROOT/'native/gr4').glob('*.h'))
    sources.update(['native/gr4/m10v_settings.h','native/gr4/m10v_settings_view.h','native/gr4/m10v_settings_controller.h','native/gr4/ui-abi.json','scripts/build_gr4_settings_hooks.py','scripts/build_gr4_native_detail.py'])
    m={'schema':'m10v-gr4-native-film-runtime/v1','base':base,'code_bytes':len(image),
        'code_sha256':sha(image),'symbols':symbols,'film_count':78,'slots':sum(struct.unpack_from('<H',initial,12+i*8)[0]!=0 for i in range(5)),'slot_capacity':5,'state_version':5,'carrier_tones':[36,37,38,39,40],
        'initial_state_hex':initial.hex(),'initial_state_offset':bytes(image).find(initial),
        'settings_menu':settings,'detail':detail,'continuations':continuations,
        'debug_mode':debug_mode,'debug_build_id':debug_build_id,'sd_library':True,'camera_tested':False,
        'sources':{p:sha((ROOT/p).read_bytes()) for p in sorted(sources)},
        'film_table_sha256':[sha(p) for p in payloads],'dimensions':{'width':6256,'height':4176},'renderer_transform':{'version':1,'source_sha256':sha((ROOT/'native/gr3/m10v_library.c').read_bytes()),'compiled_source_sha256':sha(gr4_renderer_source().encode()),'only_changes':['width maximum6144 to6256','height maximum4096 to4176']}}
    (out/'m10v-library-arm.bin').write_bytes(image)
    (out/'m10v-library-arm.json').write_text(json.dumps(m,indent=2)+'\n');return m
