#!/usr/bin/env python3
"""Build/audit the GR II BE32 ABI foundation. Does not package camera firmware."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.analyze_unity_update import official_profile
ROOT=Path(__file__).resolve().parents[1]
COMPAT=ROOT/'compat/gr2-v1'
SQUARE_COMPAT=ROOT/'compat/gr2-square-v1'
BASE=0xA0798000
LIMIT=0xA0800000
FLAGS=['--target=armeb-none-eabi','-march=armv4t','-marm','-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-vectorize','-fno-slp-vectorize','-Wall','-Wextra','-Werror']

def audit_elf(data:bytes)->dict:
    if data[:7]!=b'\x7fELF\x01\x02\x01' or struct.unpack_from('>HH',data,16)!=(2,40):raise ValueError('big-endian ARM ELF32 executable required')
    flags=struct.unpack_from('>I',data,36)[0]
    if flags&0x800000:raise ValueError('BE8 instructions cannot execute as original BE32')
    phoff,shoff=struct.unpack_from('>II',data,28)
    phsize,phcount,shsize,shcount,shnames=struct.unpack_from('>5H',data,42)
    if phsize!=32 or shsize!=40 or phoff+phcount*32>len(data) or shoff+shcount*40>len(data):raise ValueError('ELF directory bounds invalid')
    loads=[]
    for i in range(phcount):
        row=struct.unpack_from('>8I',data,phoff+i*32)
        if row[0]!=1:continue
        _,offset,address,physical,filesize,memsize,permissions,alignment=row
        if offset+filesize>len(data) or filesize>memsize or address!=BASE or memsize>LIMIT-BASE:raise ValueError('runtime load range exceeds reserved window')
        loads.append((offset,address,filesize,memsize))
    if len(loads)!=1:raise ValueError('one bounded runtime load segment required')
    offset,address,filesize,memsize=loads[0]
    sections=[struct.unpack_from('>10I',data,shoff+i*40) for i in range(shcount)]
    symbols={};undefined=[]
    for row in sections:
        if row[1]!=2:continue
        if row[9]!=16 or row[6]>=shcount or row[4]+row[5]>len(data):raise ValueError('ELF symbol table invalid')
        st=sections[row[6]];strings=data[st[4]:st[4]+st[5]]
        for at in range(row[4],row[4]+row[5],16):
            name,value,size,info,other,index=struct.unpack_from('>IIIBBH',data,at)
            label=strings[name:].split(b'\0',1)[0].decode('ascii')
            if label and not index:undefined.append(label)
            if label.startswith(('gr2_','m10v_library_','m10v_sd_','m10v_settings_')) and info>>4:
                if not BASE<=value<BASE+memsize:raise ValueError('export outside runtime')
                symbols[label]=value
    if undefined:raise ValueError('unresolved runtime helpers: '+','.join(undefined))
    required={'gr2_post_load','gr2_boot_count','gr2_capture_decode','gr2_date_valid','gr2_startup_chain','gr2_native_activate','gr2_activation_ready','gr2_code_sync','gr2_cpu_state','gr2_finalize_chain','gr2_startup_complete','gr2_ui_bootstrap','gr2_ui_storage_ready','gr2_ui_boot_state'}
    if not required<=symbols.keys():raise ValueError('required GR II ABI exports missing')
    return dict(base=address,code_bytes=filesize,memory_bytes=memsize,runtime_hex=data[offset:offset+filesize].hex(),symbols=symbols,undefined_symbols=undefined,endianness='big',be8=False)

def early_bootstrap(official:bytes)->dict:
    """Identity-locked source contract: load record14 before module1 phases.

    Fits original record0 alignment padding; never emits a flashable image.
    """
    official_profile(official,'gr2')
    from scripts.analyze_unity_runtime import parse_executable_load_map
    rows=parse_executable_load_map(official);row=rows[0];address=row['address']+row['length'];source=row['source_file_offset']+row['length']
    def thumb_bl(at,target):
        delta=target-at-4
        if delta&1 or not -(1<<22)<=delta<(1<<22):raise ValueError('early bootstrap BL range/alignment differs')
        return struct.pack('>2H',0xf000|((delta>>12)&0x7ff),0xf800|((delta>>1)&0x7ff))
    old_native=rows[14]
    if old_native['length']!=4 or old_native['zero_length']!=0:raise ValueError('original record14 stub contract differs')
    old_word=official[old_native['source_file_offset']:old_native['source_file_offset']+4]
    stub=(bytes.fromhex('b502200e2100')+thumb_bl(address+6,0xA0056722)+
          bytes.fromhex('2800d10548054905600124010020bd02b002200043c0bd1046c0')+
          struct.pack('>I',old_native['address'])+old_word)
    if len(stub)!=44 or address&3 or source+len(stub)>rows[1]['source_file_offset'] or address+len(stub)>rows[1]['address']:
        raise ValueError('early bootstrap exceeds original module0 padding')
    if official[source:source+len(stub)]!=bytes(len(stub)):raise ValueError('early bootstrap padding preimage changed')
    site=0xA002094C;offset=row['source_file_offset']+site-row['address']
    if official[offset:offset+4]!=bytes.fromhex('24010020'):raise ValueError('early bootstrap startup prelude differs')
    return dict(address=address,source_file_offset=source,stub_hex=stub.hex(),site=site,site_source_offset=offset,
                site_patch_hex=thumb_bl(site,address).hex(),original_load_bytes=row['length'],extended_load_bytes=row['length']+len(stub),
                load_length_source_offset=0x28,record_index=0,preserved_stub_address=old_native['address'],preserved_stub_hex=old_word.hex(),scope='Source-only audit contract; record0 extension fits existing zero padding, no other record moves. Original indexed loader and module1 continuation; original record14 stub retained at its old address; failure returns before phase1.')

def finalize_bridge(official:bytes,symbols:dict)->dict:
    early=early_bootstrap(official);address=early['address']+44;source=early['source_file_offset']+44
    site=0xA0020AD2;offset=early['site_source_offset']+site-early['site'];target=symbols['gr2_finalize_chain']
    if target&3 or not BASE<=target<LIMIT:raise ValueError('finalize bridge target outside runtime')
    delta=address-site-4
    patch=struct.pack('>2H',0xf000|((delta>>12)&0x7ff),0xf800|((delta>>1)&0x7ff))
    if official[offset:offset+4]!=bytes.fromhex('2000bd10') or official[source:source+8]!=bytes(8):
        raise ValueError('final startup return/padding preimage differs')
    return dict(address=address,source_file_offset=source,stub_hex='4b004718'+struct.pack('>I',target).hex(),
                site=site,site_source_offset=offset,site_patch_hex=patch.hex(),extended_load_bytes=early['extended_load_bytes']+20)

def buffer_layout_hook(official:bytes,symbols:dict,code_bytes:int)->dict:
    """Cold selector entry with the live incoming r3 saved before interworking."""
    official_profile(official,'gr2')
    from scripts.analyze_unity_runtime import parse_executable_load_map
    address=0xA00E5D92;expected=bytes.fromhex('b5ff0005001fb081f7faf8300004')
    target=symbols.get('gr2_hdf_layout_chain')
    if type(target) is not int or target&3 or not BASE<=target<BASE+code_bytes:raise ValueError('HDF selector ARM entry outside native code')
    rows=[row for row in parse_executable_load_map(official)[:15] if row['address']<=address and address+14<=row['address']+row['length']]
    if len(rows)!=1:raise ValueError('original HDF selector has no unique source owner')
    offset=rows[0]['source_file_offset']+address-rows[0]['address']
    if official[offset:offset+14]!=expected:raise ValueError('original HDF selector prelude differs')
    return dict(address=address,source_file_offset=offset,expected_hex=expected.hex(),patch_hex=(bytes.fromhex('b4084b01471846c046c0')+struct.pack('>I',target)).hex(),saved_register='r3',continuation=0xA00E5DA0)

def hdf_graph_hooks(official:bytes,symbols:dict,code_bytes:int)->list:
    from scripts.analyze_unity_runtime import parse_executable_load_map
    official_profile(official,'gr2');rows=[]
    for address,expected,name,veneer in (
            (0xA014ADEE,'b5f300042000b0b79036','gr2_hdf_core_chain','4b01471846c0'),
            (0xA014ACEC,'a928902820017388a9208608','gr2_hdf_band_chain','b4084b01471846c0'),
            (0xA02AF6CE,'b5f00004b09b2000210d','gr2_hdf_postprocess_chain','4b01471846c0'),
            (0xA02ADEA6,'b5f0000426002005b0ab','gr2_hdf_production_chain','4b01471846c0'),
            (0xA02AE7F6,'002636ff200936c101806a311820','gr2_hdf_preparation_chain','b4084b01471846c046c0'),
            (0xA029DEB8,'b5f80004200d0180','gr2_hdf_policy_chain','4b004718')):
        target=symbols.get(name)
        if type(target) is not int or target&3 or not BASE<=target<BASE+code_bytes:raise ValueError('native HDF graph ARM target differs')
        owners=[row for row in parse_executable_load_map(official)[:15] if row['address']<=address and address+len(bytes.fromhex(expected))<=row['address']+row['length']]
        if len(owners)!=1:raise ValueError('native HDF graph source owner differs')
        offset=owners[0]['source_file_offset']+address-owners[0]['address']
        if official[offset:offset+len(bytes.fromhex(expected))]!=bytes.fromhex(expected):raise ValueError('native HDF graph source preimage differs')
        rows.append(dict(address=address,source_file_offset=offset,expected_hex=expected,patch_hex=veneer+struct.pack('>I',target).hex(),target=target,name=name))
    # Four bytes preserve the native direct branch into AE842. A nearby
    # module0 bridge is needed because native code exceeds Thumb BL range.
    early=early_bootstrap(official);owner=parse_executable_load_map(official)[1]
    address=early['address']+52;offset=early['source_file_offset']+52
    target=symbols['gr2_hdf_reservation_chain']
    if target&3 or not BASE<=target<BASE+code_bytes:raise ValueError('reservation ARM target differs')
    if address+12>owner['address'] or offset+12>owner['source_file_offset'] or official[offset:offset+12]!=bytes(12):
        raise ValueError('reservation bridge exceeds original zero alignment padding')
    rows.append(dict(address=address,source_file_offset=offset,expected_hex=bytes(12).hex(),
                     patch_hex='b4084b01471846c0'+struct.pack('>I',target).hex(),target=target,name='gr2_hdf_reservation_chain'))
    site=0xA02AE83E;segment=next(row for row in parse_executable_load_map(official)[:15] if row['address']<=site<site+4<=row['address']+row['length'])
    source=segment['source_file_offset']+site-segment['address'];expected=bytes.fromhex('2d00d01d')
    if official[source:source+4]!=expected:raise ValueError('reservation branch preimage differs')
    delta=address-site-4
    if delta&1 or not -(1<<22)<=delta<(1<<22):raise ValueError('reservation BL range differs')
    rows.append(dict(address=site,source_file_offset=source,expected_hex=expected.hex(),
                     patch_hex=struct.pack('>2H',0xf000|((delta>>12)&0x7ff),0xf800|((delta>>1)&0x7ff)).hex(),target=address,name='gr2_hdf_reservation_dispatch'))
    return rows

def memory_reservations(official:bytes)->list[dict]:
    """Describe source-literal edits required before the original allocators run.

    This is an identity-locked audit contract, not a firmware patch emitter.
    Editing the live pool geometry after creation is expressly not equivalent.
    """
    official_profile(official,'gr2')
    from scripts.analyze_unity_runtime import parse_executable_load_map
    segments=parse_executable_load_map(official);result=[]
    for address,record,expected,replacement,purpose in (
        (0xA0023154,0,BASE,LIMIT,'exclude runtime window from original C heap'),
        (0xA01137EC,1,0xFB0C,0xFB0C+128+12288+16,'reserve inline immutable capture state, custom record and independent HDF snapshot')):
        row=segments[record]
        if not row['address']<=address<=row['address']+row['length']-4:raise ValueError('reservation literal load owner changed')
        offset=row['source_file_offset']+address-row['address']
        if struct.unpack_from('>I',official,offset)[0]!=expected:raise ValueError('reservation literal preimage changed')
        result.append(dict(address=address,record_index=record,source_file_offset=offset,expected=expected,
                           replacement=replacement,install_stage='before_original_module_load',purpose=purpose))
    return result

def configuration_state(configuration:dict)->tuple[dict,bytes,bytes]:
    """Use the existing page normalizer; convert its LE wire value to BE32 ABI.

    HDF is a separate producer/ISP contract, never a silently ignored field.
    This emits research runtime data, not a downloadable firmware.
    """
    if not isinstance(configuration,dict):raise ValueError('five-slot configuration object required')
    node=shutil.which('node')
    if not node:raise RuntimeError('Node.js required for the shared page configuration contract')
    script="import {readFileSync} from 'node:fs';import {defaultConfiguration,normalizeConfiguration} from './web/gr2/native-library-state.mjs';import {initialState} from './compat/gr2-v1/node/gr3-native-library.mjs';const value=JSON.parse(readFileSync(0,'utf8'));const configuration=normalizeConfiguration(Object.keys(value).length?value:defaultConfiguration());console.log(JSON.stringify({configuration,wire:initialState(configuration).toString('hex')}));"
    result=subprocess.run([node,'--input-type=module','-e',script],input=json.dumps(configuration),cwd=ROOT,text=True,capture_output=True,timeout=15)
    if result.returncode:
        message=next((line[6:].strip() for line in result.stderr.splitlines() if line.startswith('Error:')),'shared normalizer rejected the configuration')
        raise ValueError('invalid shared page configuration: '+message)
    decoded=json.loads(result.stdout);normalized=decoded['configuration'];wire=bytes.fromhex(decoded['wire'])
    if len(wire)!=104 or struct.unpack_from('<IHHI',wire)!=(0x5630314d,4,104,0) or zlib.crc32(wire[:100])!=struct.unpack_from('<I',wire,100)[0]:raise ValueError('shared state wire contract changed')
    native=bytearray(wire);struct.pack_into('>IHHI',native,0,*struct.unpack_from('<IHHI',wire))
    for index in range(5):struct.pack_into('>H',native,12+8*index,struct.unpack_from('<H',wire,12+8*index)[0])
    struct.pack_into('>I',native,96,struct.unpack_from('<I',wire,96)[0]);struct.pack_into('>I',native,100,zlib.crc32(native[:100]))
    return normalized,wire,bytes(native)

def build_gr2_runtime(official:bytes,configuration:dict,out_dir:Path)->dict:
    profile=official_profile(official,'gr2')
    normalized,initial_wire,initial_native=configuration_state(configuration)
    clang=shutil.which('clang');linker=shutil.which('ld.lld')
    if not clang or not linker:raise RuntimeError('clang and ld.lld required for GR II BE32 build')
    from scripts.verify_gr3_5207_reference import verify
    from scripts.verify_gr3_harman_reference import verify as verify_harman
    from scripts.verify_gr3_curated_reference import verify as verify_curated
    from scripts.verify_gr3_newstocks_reference import verify as verify_newstocks
    for check in (verify,verify_harman,verify_curated,verify_newstocks):check(COMPAT)
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    obj=out_dir/'model.o';elf=out_dir/'model.elf';script=out_dir/'model.ld'
    script.write_text('ENTRY(gr2_post_load)\nPHDRS { image PT_LOAD FLAGS(7); }\nSECTIONS { . = 0xA0798000; .text : { *(.text*) } :image .rodata : { *(.rodata*) } :image .data : { *(.data*) . = ALIGN(4); } :image .bss (NOLOAD) : { *(.bss*) *(COMMON) } :image /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n')
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_model.c'),'-o',str(obj)],check=True,capture_output=True)
    startup=out_dir/'startup.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_startup.S'),'-o',str(startup)],check=True,capture_output=True)
    boot_ui=out_dir/'boot_ui.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_boot_ui.c'),'-o',str(boot_ui)],check=True,capture_output=True)
    boot=out_dir/'boot.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_boot.c'),'-o',str(boot)],check=True,capture_output=True)
    hdf_layout=out_dir/'hdf_layout.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_hdf_layout.c'),'-o',str(hdf_layout)],check=True,capture_output=True)
    hdf_hooks=out_dir/'hdf_hooks.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_hdf_hooks.S'),'-o',str(hdf_hooks)],check=True,capture_output=True)
    hdf_configuration=out_dir/'hdf_configuration.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_hdf_configuration.c'),'-o',str(hdf_configuration)],check=True,capture_output=True)
    hdf_storage=out_dir/'hdf_storage.o'
    subprocess.run([clang,*FLAGS,'-DGR2_HDF_INITIAL_STRENGTH='+str(normalized['hdf']),'-c',str(ROOT/'native/gr2/m10v_hdf_storage.c'),'-o',str(hdf_storage)],check=True,capture_output=True)
    hdf_scheduling=out_dir/'hdf_scheduling.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_hdf_scheduling.c'),'-o',str(hdf_scheduling)],check=True,capture_output=True)
    hdf_page=out_dir/'hdf_page.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_hdf_page.c'),'-o',str(hdf_page)],check=True,capture_output=True)
    hdf_control=out_dir/'hdf_control.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_hdf_control.c'),'-o',str(hdf_control)],check=True,capture_output=True)
    hdf_postprocess=out_dir/'hdf_postprocess.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_hdf_postprocess.c'),'-o',str(hdf_postprocess)],check=True,capture_output=True)
    hdf_graph=out_dir/'hdf_graph.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_hdf_graph.c'),'-o',str(hdf_graph)],check=True,capture_output=True)
    hdf=out_dir/'hdf.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_hdf.c'),'-o',str(hdf)],check=True,capture_output=True)
    planar=out_dir/'planar.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_planar.c'),'-o',str(planar)],check=True,capture_output=True)
    capture=out_dir/'capture.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_capture.c'),'-o',str(capture)],check=True,capture_output=True)
    storage=out_dir/'storage.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_storage.c'),'-o',str(storage)],check=True,capture_output=True)
    snapshot=out_dir/'snapshot.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_snapshot.c'),'-o',str(snapshot)],check=True,capture_output=True)
    services=out_dir/'services.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_services.c'),'-o',str(services)],check=True,capture_output=True)
    cache=out_dir/'cache.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_cache.S'),'-o',str(cache)],check=True,capture_output=True)
    files=out_dir/'files.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_files.c'),'-o',str(files)],check=True,capture_output=True)
    ui=out_dir/'ui.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_ui.c'),'-o',str(ui)],check=True,capture_output=True)
    sd=out_dir/'sd.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_sd.c'),'-o',str(sd)],check=True,capture_output=True)
    from scripts.gr2_text_contract import effect_name_contract,contract_header
    text_contract=effect_name_contract(official);(out_dir/'m10v_effect_names_contract.h').write_text(contract_header(text_contract))
    effect_names=out_dir/'effect_names.o'
    subprocess.run([clang,*FLAGS,'-I',str(out_dir),'-c',str(ROOT/'native/gr2/m10v_effect_names.c'),'-o',str(effect_names)],check=True,capture_output=True)
    configuration_object=out_dir/'configuration.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_configuration.c'),'-o',str(configuration_object)],check=True,capture_output=True)
    settings_backend=out_dir/'settings_backend.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_settings_backend.c'),'-o',str(settings_backend)],check=True,capture_output=True)
    settings_page=out_dir/'settings_page.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_settings_page.c'),'-o',str(settings_page)],check=True,capture_output=True)
    detail=out_dir/'detail.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_detail.c'),'-o',str(detail)],check=True,capture_output=True)
    artwork=out_dir/'artwork.o'
    subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr2/m10v_artwork.c'),'-o',str(artwork)],check=True,capture_output=True)
    render_objects=[str(detail),str(hdf_scheduling),str(hdf_page),str(hdf_control),str(hdf_postprocess),str(hdf_graph),str(hdf_layout),str(hdf_hooks),str(hdf_configuration),str(hdf_storage),str(hdf),str(boot_ui),str(boot),str(planar),str(capture),str(storage),str(snapshot),str(services),str(cache),str(files),str(ui),str(sd),str(effect_names),str(configuration_object),str(settings_backend),str(settings_page),str(artwork)]
    for name in ('m10v_library','halation_core','film_5207','film_harman','film_curated','film_newstocks','m10v_sd_library','m10v_settings','m10v_film_card'):
        target=out_dir/(name+'.o')
        initial_flags=['-DM10V_INITIAL_STATE_BYTES='+','.join(map(str,initial_native))] if name=='m10v_library' else []
        # Keep the accepted square artwork independent of GR III-only looks.
        source=(SQUARE_COMPAT if name=='m10v_film_card' else COMPAT)/f'native/gr3/{name}.c'
        subprocess.run([clang,*FLAGS,*initial_flags,'-c',str(source),'-o',str(target)],check=True,capture_output=True)
        render_objects.append(str(target))
    subprocess.run([linker,'-m','armelfb','--no-undefined','-T',str(script),str(obj),str(startup),*render_objects,'-o',str(elf)],check=True,capture_output=True)
    report=audit_elf(elf.read_bytes())
    report['hdf_graph_hooks']=hdf_graph_hooks(official,report['symbols'],report['code_bytes'])
    report['buffer_layout_hook']=buffer_layout_hook(official,report['symbols'],report['code_bytes'])
    report['buffer_layout_hook_patch_hex']=report['buffer_layout_hook']['patch_hex']
    report['memory_reservations']=memory_reservations(official)
    report['early_bootstrap']=early_bootstrap(official)
    report['finalize_bridge']=finalize_bridge(official,report['symbols'])
    if official[0xA0044F4C-0xA0020200:0xA0044F50-0xA0020200]!=bytes.fromhex('e12fff1e'):raise ValueError('original SVC callback identity mismatch')
    displacement=report['symbols']['gr2_cache_gateway']-0xA0044F54
    if displacement%4 or not -(1<<25)<=displacement<(1<<25):raise ValueError('cache callback ARM branch range invalid')
    report['cache_gateway_patch_hex']=struct.pack('>I',0xea000000|((displacement>>2)&0xffffff)).hex()
    from scripts.analyze_unity_runtime import parse_executable_load_map
    for row in parse_executable_load_map(official)[:15]:
        if row['address']<=0xA00AF884 and 0xA00AF888<=row['address']+row['length']:
            source=row['source_file_offset']+0xA00AF884-row['address'];break
    else:raise ValueError('original SVC5 data vector outside load ranges')
    if official[source:source+4]!=struct.pack('>I',0xA00AF8A8):raise ValueError('original SVC5 data vector differs')
    report['cache_svc_vector_patch_hex']=struct.pack('>I',report['symbols']['gr2_cache_svc_entry']).hex()
    report['cache_svc_vector_source_offset']=source

    report['startup_patch_hex']=(bytes.fromhex('4b004718')+struct.pack('>I',report['symbols']['gr2_startup_chain'])).hex()
    from scripts.analyze_unity_runtime import parse_executable_load_map
    for row in parse_executable_load_map(official)[:15]:
        if row['address']<=0xA02ADC98 and 0xA02ADCA0<=row['address']+row['length']:
            source=row['source_file_offset']+0xA02ADC98-row['address'];break
    else:raise ValueError('original JPEG hook outside executable load ranges')
    if official[source:source+8]!=bytes.fromhex('a806f684fc0e980a'):raise ValueError('original JPEG hook instructions differ')
    report['jpeg_hook_patch_hex']=(bytes.fromhex('4b004718')+struct.pack('>I',report['symbols']['gr2_jpeg_chain'])).hex()
    report['jpeg_hook_source_offset']=source
    for row in parse_executable_load_map(official)[:15]:
        if row['address']<=0xA0394950 and 0xA0394958<=row['address']+row['length']:
            source=row['source_file_offset']+0xA0394950-row['address'];break
    else:raise ValueError('original UI hook outside executable load ranges')
    if official[source:source+8]!=bytes.fromhex('0006000d24002900'):raise ValueError('original UI hook instructions differ')
    report['ui_event_hook_patch_hex']=(bytes.fromhex('4b004718')+struct.pack('>I',report['symbols']['gr2_ui_event_chain'])).hex()
    report['ui_event_hook_source_offset']=source
    for row in parse_executable_load_map(official)[:15]:
        if row['address']<=0xA02AD48C and 0xA02AD494<=row['address']+row['length']:
            source=row['source_file_offset']+0xA02AD48C-row['address'];break
    else:raise ValueError('original producer hook outside executable load ranges')
    if official[source:source+8]!=bytes.fromhex('0004000db0ad2198'):raise ValueError('original producer hook instructions differ')
    report['producer_hook_patch_hex']=(bytes.fromhex('4b004718')+struct.pack('>I',report['symbols']['gr2_producer_chain'])).hex()
    report['producer_hook_source_offset']=source



    for row in parse_executable_load_map(official)[:15]:
        if row['address']<=0xA03948C4 and 0xA03948CC<=row['address']+row['length']:
            source=row['source_file_offset']+0xA03948C4-row['address'];break
    else:raise ValueError('original menu route hook outside executable load ranges')
    if official[source:source+8]!=bytes.fromhex('0004b084f493fa65'):raise ValueError('original menu route hook instructions differ')
    report['menu_route_hook_patch_hex']=(bytes.fromhex('4b004718')+struct.pack('>I',report['symbols']['gr2_menu_route_chain'])).hex()
    report['menu_route_hook_source_offset']=source

    for row in parse_executable_load_map(official)[:15]:
        if row['address']<=0xA03C1380 and 0xA03C1388<=row['address']+row['length']:
            source=row['source_file_offset']+0xA03C1380-row['address'];break
    else:raise ValueError('original menu categories hook outside executable load ranges')
    if official[source:source+8]!=bytes.fromhex('b5f14d872601b084'):raise ValueError('original menu categories hook instructions differ')
    report['menu_categories_hook_patch_hex']=(bytes.fromhex('4b004718')+struct.pack('>I',report['symbols']['gr2_menu_categories'])).hex()
    report['menu_categories_hook_source_offset']=source

    for row in parse_executable_load_map(official)[:15]:
        if row['address']<=0xA039D168 and 0xA039D170<=row['address']+row['length']:
            source=row['source_file_offset']+0xA039D168-row['address'];break
    else:raise ValueError('original menu descriptor hook outside executable load ranges')
    if official[source:source+8]!=bytes.fromhex('0007000d694e6908'):raise ValueError('original menu descriptor instructions differ')
    report['menu_descriptor_hook_patch_hex']=(bytes.fromhex('4b004718')+struct.pack('>I',report['symbols']['gr2_menu_descriptor_chain'])).hex()
    report['menu_descriptor_hook_source_offset']=source

    for row in parse_executable_load_map(official)[:15]:
        if row['address']<=0xA039D60E and 0xA039D610<=row['address']+row['length']:
            source=row['source_file_offset']+0xA039D60E-row['address'];break
    else:raise ValueError('original menu raster classifier outside executable load ranges')
    if official[source:source+2]!=bytes.fromhex('2d68'):raise ValueError('original menu raster classifier differs')
    report['menu_raster_classifier_patch_hex']='2d6b'
    report['menu_raster_classifier_source_offset']=source

    report.update(schema='m10v-gr2-runtime-foundation/v1',official_sha256=profile['sha'],can_package=False,
                  film_detail_controller_compiled=True,film_detail_menu_compiled=True,
                  hdf_scheduling_policy_compiled=True,hdf_ui_control_compiled=True,hdf_menu_compiled=True,hdf_ui_restore_compiled=True,hdf_global_postprocess_compiled=True,hdf_graph_hooks_compiled=True,hdf_graph_preparation_compiled=True,hdf_coefficients_compiled=True,hdf_journal_compiled=True,hdf_configuration_compiled=True,hdf_capture_ready=False,hdf_coefficient_bytes=11*8192,hdf_frame_bytes=16,
                  effect_name_contract=text_contract,configuration=normalized,initial_hdf_strength=normalized['hdf'],initial_state_wire_hex=initial_wire.hex(),initial_state_native_hex=initial_native.hex(),
                  configuration_sha256=hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                  runtime_sha256=hashlib.sha256(bytes.fromhex(report['runtime_hex'])).hexdigest(),
                  limits=['GR II scalar renderer, owned capture/configuration and UI restoration have bounded CPU evidence; complete boot, physical caches and hardware capture remain researching.','Reserved C-heap window needs original literal adjustment; no firmware patch or download is emitted.','ARMv4T soft-float subset avoids assuming a newer CPU or floating-point unit.'])
    (out_dir/'runtime-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--component',required=True,type=Path);parser.add_argument('--out',required=True,type=Path);parser.add_argument('--configuration',type=Path);args=parser.parse_args()
    report=build_gr2_runtime(args.component.read_bytes(),json.loads(args.configuration.read_text()) if args.configuration else {},args.out)
    print(json.dumps({key:report[key] for key in ('code_bytes','memory_bytes','endianness','be8','can_package')}))
if __name__=='__main__':main()
