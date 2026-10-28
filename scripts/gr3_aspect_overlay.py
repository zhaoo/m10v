"""Source-built, preimage-checked crop overlay over the pinned GR III runtime.

The cached upstream runtime remains immutable. This module runs in its existing
process-isolated build worker and cannot access a camera or publish firmware.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import array
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE, MODULE, END = 0x53000000, 0x540bc000, 0x540be000
SOURCES = ['m10v_aspect.c','m10v_aspect_dng.c','m10v_aspect_hooks.S']
TEMPLATE_SHA='e2bdc2f0873445d52642947c729031691db41affaf5ab4bd411f4780a592dd41'
FLAGS = ['--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os',
         '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables',
         '-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror']
BINDINGS = {'native_ifd_byte':0x535d04bc,'old_extract65':0x540b9828,
            'old_native_merge':0x540b9498,'old_native_ubox':0x540b9248,
            'old_native_shading':0x540b94e0,'old_shading65':0x540b90f4,
            'af_bounds_private':0x540b66d0,'af_size_private':0x540b6714,
            'af_small_private':0x540b675c,'__aeabi_uidiv':0x5313d850}
HOOKS = {
    0x540b98c4:'count',0x540b9300:'next',0x540b9428:'label',
    0x540b9450:'resolution_hook',0x540b9574:'capture_identity',
    0x540b9788:'binary_class',0x540b9770:'write',0x540b94a0:'extract',
    0x540b9478:'merge',0x540b9210:'ubox',0x540b94c4:'shading',
    0x540b94e8:'screen_origin',0x540b950c:'thumb_origin',
    0x540b8cac:'filter_hook',0x540b85b8:'live_width_hook',
    0x540b8608:'live_height_hook',0x540b9140:'face_config',
    0x540b9168:'live_select',0x540b92d0:'common_dispatch',
    0x540b89f8:'text_prepare',0x540b8bc4:'text_draw',
    0x540b66a0:'af_bounds_branch',0x540b66e4:'af_size_branch',
    0x540b672c:'af_small_branch',
}


def branch(site, target, link=False):
    delta=target-site-8
    if delta&3 or not -(1<<25)<=delta<(1<<25): raise ValueError('crop branch out of range')
    return (0xeb000000 if link else 0xea000000)|((delta>>2)&0xffffff)


def elf_image(data):
    if data[:7]!=b'\x7fELF\x01\x01\x01': raise ValueError('expected ARM ELF32')
    offset=struct.unpack_from('<I',data,32)[0]
    stride,count,names=struct.unpack_from('<HHH',data,46)
    sections=[struct.unpack_from('<10I',data,offset+i*stride) for i in range(count)]
    image=bytearray(END-MODULE);last=0;symbols={}
    for row in sections:
        if row[2]&2 and row[5]:
            start=row[3]-MODULE;stop=start+row[5]
            if row[1]!=1 or row[2]&1 or not 0<=start<stop<=len(image):
                raise ValueError('crop module has writable or out-of-range storage')
            image[start:stop]=data[row[4]:row[4]+row[5]];last=max(last,stop)
        if row[1]==2:
            strings=sections[row[6]];strings=data[strings[4]:strings[4]+strings[5]]
            for pos in range(row[4],row[4]+row[5],16):
                name,value,size,info,other,index=struct.unpack_from('<IIIBBH',data,pos)
                name=strings[name:].split(b'\0',1)[0].decode()
                if name.startswith('m10v_aspect_') and index and info>>4 in (1,2): symbols[name]=value
    return bytes(image[:(last+3)&~3]),symbols


def build_module():
    clang=os.environ.get('M10V_LLVM_CLANG') or shutil.which('clang')
    lld=os.environ.get('M10V_LLVM_LD') or shutil.which('ld.lld')
    if not lld:
        lld=next((p for p in ['/opt/homebrew/opt/lld/bin/ld.lld','/usr/local/opt/lld/bin/ld.lld','/usr/bin/ld.lld'] if Path(p).exists()),None)
    if not clang or not lld: raise ValueError('crop extension requires clang and ld.lld')
    with tempfile.TemporaryDirectory(prefix='m10v-crop-') as directory:
        directory=Path(directory);objects=[]
        for name in SOURCES:
            obj=directory/(name+'.o')
            subprocess.run([clang,*FLAGS,'-c',str(ROOT/'native/gr3'/name),'-o',str(obj)],check=True,capture_output=True)
            objects.append(str(obj))
        script=directory/'layout.ld'
        script.write_text(f'SECTIONS {{ . = {MODULE}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.comment*) *(.ARM.attributes*) }} }}')
        elf=directory/'crop.elf'
        subprocess.run([lld,'-T',str(script),*objects,*[f'--defsym={name}={address}' for name,address in BINDINGS.items()],'-o',str(elf)],check=True,capture_output=True)
        return elf_image(elf.read_bytes())


def apply_overlay(rtos):
    template=json.loads((ROOT/'.runtime/grlife-current/reconstruction/firmware_store/templates/urban160-native.json').read_text())
    old=bytes.fromhex(template['program_hex']);old_base=template['base_va']
    if hashlib.sha256(old).hexdigest()!=TEMPLATE_SHA: raise ValueError('crop template digest differs')
    code,symbols=build_module();rtos=bytearray(rtos)
    if len(rtos)>MODULE-BASE and any(rtos[MODULE-BASE:]): raise ValueError('crop extension allocation overlaps existing module')
    rtos.extend(bytes(max(0,END-BASE-len(rtos))))

    def word(address,value,expected=None):
        at=address-BASE
        if expected is None and old_base<=address<old_base+len(old):
            expected=struct.unpack_from('<I',old,address-old_base)[0]
        if expected is not None:
            allowed=expected if isinstance(expected,tuple) else (expected,)
            if struct.unpack_from('<I',rtos,at)[0] not in allowed: raise ValueError(f'crop preimage differs at {address:#x}')
        struct.pack_into('<I',rtos,at,value)

    for address,name in HOOKS.items(): word(address,branch(address,symbols['m10v_aspect_'+name]))
    # Redirect internal callers, retaining the unchanged implementations for
    # the new adapters' legacy fallbacks. Relocations distinguish code/data.
    report=json.loads((ROOT/'.runtime/grlife-current/reconstruction/firmware_store/templates/urban160-link-report.json').read_text())
    redirects={'gr_dng_default_crop_tags':'dng_tags','open_gate_mask_is_active':'mask_active','draw_overlay':'draw','gr3_sro_af_bounds_test02':'af_bounds','gr3_sro_write_active_locked':'private_active'}
    for row in report['relocations']:
        if row['type'] in ('R_ARM_CALL','R_ARM_JUMP24') and row['symbol'] in redirects:
            address=row['place'];word(address,branch(address,symbols['m10v_aspect_'+redirects[row['symbol']]],row['type']=='R_ARM_CALL'))

    def mov(address,register,value,top=False,condition=14,expected=None):
        half=value>>16 if top else value&65535
        word(address,(condition<<28)|(0x03400000 if top else 0x03000000)|((half&0xf000)<<4)|(register<<12)|(half&0xfff),expected)

    table=symbols['m10v_aspect_values']
    for address in [0x531b4e08,0x531b6bd0,0x531b82f8]:
        mov(address,3,table,expected=(0xe30938cc,0xe30a3520))
        mov(address+4,3,table,True,expected=(0xe345340b,0xe34533b5))
    classes=symbols['m10v_aspect_classes']
    word(0x534371d4,0xe3530004,(0xe3530002,0xe3530003))
    mov(0x534371dc,2,classes,expected=(0xe30c2dcc,0xe30928d0))
    mov(0x534371e4,2,classes,True,expected=(0xe34523c1,0xe345240b))
    word(0x5366944c,0xe3500004,(0xe3500002,0xe3500003))
    mov(0x53669450,3,classes,condition=9,expected=0x930533c8)
    mov(0x53669458,3,classes,True,condition=9,expected=0x934533d5)
    # XPan remains raw4 and preserves all its original output dimensions.
    descriptor=0x540b97ec-BASE
    if bytes(rtos[descriptor:descriptor+8])!=bytes.fromhex('06010000f4970b54'):
        raise ValueError('XPan caption descriptor differs')
    rtos[descriptor]=5
    rtos[0x540b97f4-BASE:0x540b9800-BASE]='XPan\0\0'.encode('utf-16le')
    rtos[MODULE-BASE:MODULE-BASE+len(code)]=code
    if struct.unpack_from('<I',rtos,0x540b97e8-BASE)[0]&1:
        struct.pack_into('<I',rtos,symbols['m10v_aspect_id_record']-BASE+8,809)
    return bytes(rtos),symbols


def extend_candidate(candidate):
    from reconstruction.gr3x_container import decode_firmware
    image=decode_firmware(candidate);original=image.decoded
    # All supported GR III/IIIx inputs have the same section layout here.
    offset=0
    while original[offset:offset+4]!=b'RTOS':
        offset+=16+struct.unpack_from('<I',original,offset+12)[0]
    size=struct.unpack_from('<I',original,offset+12)[0]
    rtos,entries=apply_overlay(original[offset+16:offset+16+size])
    target=bytearray(original[:offset+16]+rtos+original[offset+16+size:])
    struct.pack_into('<I',target,offset+12,len(rtos))
    struct.pack_into('<I',target,len(target)-4,0)
    def checksum(data):
        words=array.array('I',data)
        if sys.byteorder!='little': words.byteswap()
        return sum(words)&0xffffffff
    struct.pack_into('<I',target,len(target)-4,-checksum(target)&0xffffffff)
    # Reuse a frame only when its complete 13-bit reference history matches.
    chunks=[];insertion=offset+16+size;growth=len(rtos)-size
    for frame in image.frames:
        old_start=frame.output_offset;old_stop=old_start+frame.output_size
        start=old_start+(growth if old_start>=insertion else 0)
        stop=old_stop+(growth if old_stop>=insertion else 0)
        history=min(8191,old_start)
        if target[start-history:stop]==original[old_start-history:old_stop]:
            chunks.append(candidate[frame.input_offset:frame.input_offset+frame.input_size])
        else:
            for at in range(start,stop,0x6000):
                part=target[at:min(at+0x6000,stop)]
                chunks.append(struct.pack('>H',0x8000|len(part))+part)
    chunks.append(bytes(2));payload=b''.join(chunks);footer=bytearray(candidate[-24:])
    struct.pack_into('<III',footer,12,len(payload),len(target),0)
    result=bytearray(candidate[:128]+payload+bytes(-(128+len(payload))&3)+footer)
    struct.pack_into('<I',result,len(result)-4,-checksum(result)&0xffffffff)
    if decode_firmware(result).decoded!=bytes(target): raise ValueError('crop fresh container readback differs')
    return bytes(result),{'schema':'m10v-gr3-aspect/v1','ratios':['3:2','1:1','4:3','16:9','XPan','6x7'],
                          'raw_id':5,'module_range':[MODULE,END],'module_sha256':hashlib.sha256(rtos[MODULE-BASE:]).hexdigest(),
                          'camera_tested':False,'entries':entries}
