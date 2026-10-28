#!/usr/bin/env python3
"""Standalone opt-in border runtime code and20-patch plan; never camera firmware.

Default OFF does not compile or inspect firmware/externals. Enabled builds reuse
the central owned shot/capture bridge, add the indivisible18-patch guard component
and two full-context hooks. No central builder or Node export is modified.
"""
import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import build_gr3_border_wait_guard as guard
from scripts.build_gr3_m10v_library import FLAGS,link_object

MODELS={
 'gr3':{'version':'2.10','sha256':'8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'},
 'gr3x':{'version':'1.60','sha256':'0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6'},
}
REUSED=('m10v_border_shot_read','m10v_border_shot_orientation','m10v_border_shot_phase',
        'm10v_border_shot_transition','m10v_capture_library')
MODULES=(
 ('native/gr3/m10v_border.c',('m10v_border_layout','m10v_border_storage_layout','m10v_border_preview_fit')),
 ('native/gr3/m10v_border_bank.c',('m10v_border_bank_shape','m10v_border_bank_plan')),
 ('native/gr3/m10v_border_canvas.c',('m10v_border_canvas_plan',)),
 ('native/gr3/m10v_border_fill_plan.c',('m10v_border_fill_plan',)),
 ('native/gr3/m10v_border_prepare.c',('m10v_border_prepare',)),
 ('native/gr3/m10v_border_runtime.c',('m10v_border_runtime_before_submit','m10v_border_runtime_after_resize')),
)
RUNTIME_SPANS=(
 ('stillmake_configuration',0x5350177c,0x53502578,'e6fa9ea97070dc8a5bca5fc9956718ed52d9096b324db38eee091ba754305855'),
 ('backresize',0x534feb04,0x534ff4ac,'4517960ac0aeb15300ee3f47dd85545124e53fdb8837f5db50d3ddc52c8ae81c'),
 ('setup_dispatch',0x5350e624,0x5350e6f8,'d931a04d05ca9e47a512a5734f6d056524f1b92897d8c21d56693377531e65c9'),
 ('setup6',0x5350ea50,0x5350eabc,'dc584adb305128ab25ee4075c6039d2c14cc0d0520d2d96f9e1fa93ca81da56f'),
 ('cache_adapter',0x536bbc30,0x536bbd00,'bdf63f7372af0932684c5d71fb6b5ea3e66852558631c63c957a0124174ad569'),
 ('cache_backend',0x5383c4e8,0x5383ca10,'f7db4af1da59e26ca56f1b3df6d18234346dbac5249bb5363d1ef0f987db5fb5'),
 ('native_alloc',0x536af2a8,0x536af2e8,'b79730ac8a1a81adc3acf349c1617a7b77d2dc7868d72bfaef81a6bf9596002b'),
)
HOOK_EXPORTS=('m10v_border_runtime_submit_hook','m10v_border_runtime_resize_hook')
HOOKS=((0x53501f98,0xeb06a762,HOOK_EXPORTS[0],True,'before_stillmake_submit'),
       (0x534ff458,0xe51b2028,HOOK_EXPORTS[1],False,'after_backresize_cleanup'))
HOOK_ASSEMBLY=r'''.syntax unified
.arm
.text
.macro save_context
 push {r0-r12,lr}
 mrs ip,cpsr
 push {ip}
 mov ip,sp
 bic sp,sp,#7
 sub sp,sp,#8
 str ip,[sp]
.endm
.macro restore_context
 ldr sp,[sp]
 pop {ip}
 msr cpsr_fsxc,ip
 pop {r0-r12,lr}
.endm
.global m10v_border_runtime_submit_hook
.type m10v_border_runtime_submit_hook,%function
m10v_border_runtime_submit_hook:
 save_context
 sub r0,r4,#0x9000
 mov r1,r6
 bl m10v_border_runtime_before_submit
 restore_context
 b border_original_submit
.size m10v_border_runtime_submit_hook,.-m10v_border_runtime_submit_hook
.global m10v_border_runtime_resize_hook
.type m10v_border_runtime_resize_hook,%function
m10v_border_runtime_resize_hook:
 save_context
 mov r0,r7
 mov r1,r4
 bl m10v_border_runtime_after_resize
 restore_context
 ldr r2,[fp,#-0x28]
 b border_after_resize_resume
.size m10v_border_runtime_resize_hook,.-m10v_border_runtime_resize_hook
'''


def digest(data):return hashlib.sha256(data).hexdigest()
def align16(value):return (value+15)&~15
def _source_hashes():
    sources={source for source,_ in MODULES}
    sources.update(str(Path(source).with_suffix('.h')) for source,_ in MODULES)
    sources.update(guard.SOURCES)
    sources.update(('scripts/build_gr3_border_runtime.py','native/gr3/m10v_border_shot.h',
                    'native/gr3/m10v_border_wait_guard.h','native/gr3/m10v_border_fill_bundle.h'))
    return {source:digest((ROOT/source).read_bytes()) for source in sorted(sources)}
def arm_branch(at,destination,link=False):
    delta=destination-at-8
    if (at|destination)&3 or not -(1<<25)<=delta<(1<<25):raise ValueError('runtime ARM B/BL out of range')
    return (0xeb000000 if link else 0xea000000)|((delta>>2)&0xffffff)


def _externals(externals,base):
    if not isinstance(externals,dict) or not set(REUSED)<=set(externals):
        raise ValueError('runtime requires existing owned central shot and capture-library exports')
    own={symbol for _,symbols in MODULES for symbol in symbols}|set(HOOK_EXPORTS)
    result={}
    for name,address in externals.items():
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_]\w*',name) or type(address)is not int or \
           address&3 or not 0x53000000<=address<0x55000000:
            raise ValueError('invalid external ARM export '+str(name))
        if name in own or base<=address<base+65536:
            raise ValueError('external duplicates/overlaps standalone runtime '+name)
        result[name]=address
    return result


def _compile_component(base,guard_code,guard_symbols,externals):
    compiler=shutil.which('clang')
    if not compiler:raise RuntimeError('clang required for standalone border runtime')
    code=bytearray(guard_code);symbols=dict(guard_symbols);addresses={**externals,**symbols}
    sections=[{'name':'guard','address':base,'bytes':len(guard_code)}]
    with tempfile.TemporaryDirectory(prefix='border-runtime-link-') as folder:
        tmp=Path(folder)
        check=tmp/'metadata_check.h'
        check.write_text('#include "m10v_border_fill_plan.h"\n_Static_assert(sizeof(m10v_border_fill_plan_info)==5820u,"border metadata allocation changed");\n')
        for index,(source,exports) in enumerate(MODULES):
            address=align16(base+len(code));code.extend(bytes(address-base-len(code)))
            obj=tmp/f'module{index}.o'
            subprocess.run([compiler,*FLAGS,'-I',str(ROOT/'native/gr3'),'-include',str(check),
                '-c',str(ROOT/source),'-o',str(obj)],check=True,capture_output=True)
            block,entries=link_object(obj.read_bytes(),address,addresses,
                                     prefix='m10v_zoom_',additional_exports=exports)
            if set(entries)&set(symbols):raise ValueError('duplicate standalone ARM export')
            code.extend(block);symbols.update(entries);addresses.update(entries)
            sections.append({'name':source,'address':address,'bytes':len(block),'symbols':entries})
        address=align16(base+len(code));code.extend(bytes(address-base-len(code)))
        asm=tmp/'runtime_hooks.S';asm.write_text(HOOK_ASSEMBLY);obj=tmp/'runtime_hooks.o'
        subprocess.run([compiler,*FLAGS,'-c',str(asm),'-o',str(obj)],check=True,capture_output=True)
        block,entries=link_object(obj.read_bytes(),address,
            {**addresses,'border_original_submit':0x536abd28,'border_after_resize_resume':0x534ff45c},
            prefix='m10v_zoom_',additional_exports=HOOK_EXPORTS)
        code.extend(block);symbols.update(entries)
        sections.append({'name':'runtime_hooks','address':address,'bytes':len(block),'symbols':entries})
    if not code or len(code)>65536:raise ValueError('standalone runtime exceeds reserved64KiB code budget')
    return bytes(code),symbols,sections,subprocess.check_output([compiler,'--version'],text=True).splitlines()[0]


def build(base=0x54160000,stock=None,externals=None,camera_model='gr3',enabled=False,out_dir=None):
    if type(enabled)is not bool:raise ValueError('runtime enabled must be an explicit boolean')
    disabled={'schema':'m10v-border-runtime-component/v1','enabled':False,'code_bytes':0,
        'symbols':{},'patches':[],'installed_software_layer':False,'hardware_activation':False,
        'firmware_artifact':False,'camera_tested':False}
    if not enabled:return b'',disabled
    if camera_model not in MODELS:raise ValueError('runtime admits only independently pinned GR III/IIIx inputs')
    if type(base)is not int or base&15 or not 0x540b6000<=base<=0x54ef0000:
        raise ValueError('invalid caller-selected standalone runtime base')
    model=MODELS[camera_model]
    if not isinstance(stock,bytes) or digest(stock)!=model['sha256']:
        raise ValueError('runtime requires exact model-locked official RTOS')
    externals=_externals(externals,base)
    spans=[]
    for name,start,end,expected in RUNTIME_SPANS:
        if digest(stock[start-guard.RTOS_BASE:end-guard.RTOS_BASE])!=expected:
            raise ValueError('runtime touched ABI span differs: '+name)
        spans.append({'name':name,'start':start,'end':end,'sha256':expected})
    for at,expected,_,_,_ in HOOKS:
        if struct.unpack_from('<I',stock,at-guard.RTOS_BASE)[0]!=expected:
            raise ValueError('runtime hook preimage differs at '+hex(at))
    source_hashes=_source_hashes()
    guard_code,guard_report=guard.build(base,stock,border_enabled=True,internal_guard_research=True,camera_model=camera_model)
    if set(guard_report['symbols'])&set(externals):raise ValueError('caller must not duplicate standalone guard exports')
    code,symbols,sections,compiler=_compile_component(base,guard_code,guard_report['symbols'],externals)
    if _source_hashes()!=source_hashes:raise ValueError('border component sources changed during compilation; rebuild a stable snapshot')
    patches=[dict(p) for p in guard_report['patches']]
    for at,expected,symbol,link,role in HOOKS:
        patches.append({'address':at,'expected':expected,'replacement':arm_branch(at,symbols[symbol],link),
                        'target':symbols[symbol],'symbol':symbol,'role':role})
    if len(patches)!=20:raise ValueError('complete runtime requires exactly18 guard and2 stage patches')
    # Strict collision/preimage check plus instruction readback on a RAM copy.
    patched=apply_patch_plan(stock,patches)
    for p in patches:
        if struct.unpack_from('<I',patched,p['address']-guard.RTOS_BASE)[0]!=p['replacement']:
            raise ValueError('runtime patch readback differs')
    report={'schema':'m10v-border-runtime-component/v1','enabled':True,
        'base':base,'code_bytes':len(code),'code_sha256':digest(code),'code_budget_bytes':65536,
        'symbols':symbols,'sections':sections,'patches':patches,'guard':guard_report,
        'camera_model':camera_model,'original_version':model['version'],'original_rtos_sha256':model['sha256'],
        'verified_abi_spans':spans,'model_layout_verified':True,'physical_model_support_verified':False,
        'compiler':compiler,'flags':FLAGS,'compiled_sources':[source for source,_ in MODULES],
        'sources':source_hashes,
        'hook_source_sha256':digest(HOOK_ASSEMBLY.encode()),
        'reused_central_symbols':{name:externals[name] for name in REUSED},
        'external_address_ownership_verified':False,
        'metadata_allocation_bytes':5820,'metadata_allocation_scope':'per-frame fill metadata; guard worker tails reported separately',
        'mutable_static_bytes':0,'tls_bytes':0,
        'cpu_raster_pass':False,'cpu_raster_scope':'new border component; existing capture_library CPU effects are preserved',
        'native_jpeg_encoded_capacity_preserved':True,
        'installed_software_layer':True,'hardware_ready':False,'hardware_activation':False,
        'camera_tested':False,'firmware_artifact':False,'patches_applied_to_device':False,
        'integration':'Standalone code and complete checked20-patch software installation plan; central builder/Node unchanged',
        'prerequisites':['caller reserves the entire code interval without overlap with central runtime',
            'reused central exports must match owned shot/snapshot/early-library dedup ABI',
            'all20 patches install together at cold boot; no live stock-size worker singleton',
            'native bank5 capacity/lifetime, guard recovery retention and exclusive whole-frame ownership',
            'native cache handoff and exclusive photo cache lines; no CPU pixel access after hardware handoff',
            'real hardware completion/teardown, physical pixels/cache and performance acceptance remain unverified']}
    if out_dir is not None:
        out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
        (out/'m10v-border-runtime-arm.bin').write_bytes(code)
        (out/'m10v-border-runtime-arm.json').write_text(json.dumps(report,indent=2)+'\n')
    return code,report


def apply_patch_plan(stock,patches):
    return guard.apply_patch_plan(stock,patches)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=lambda value:int(value,0),default=0x54160000)
    parser.add_argument('--rtos',type=Path);parser.add_argument('--externals',type=Path)
    parser.add_argument('--camera-model',choices=sorted(MODELS),default='gr3')
    parser.add_argument('--enabled',action='store_true');parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    stock=args.rtos.read_bytes() if args.enabled and args.rtos else None
    externals=json.loads(args.externals.read_text()) if args.enabled and args.externals else None
    _,report=build(args.base,stock,externals,args.camera_model,args.enabled,args.out)
    print(json.dumps(report,indent=2))
