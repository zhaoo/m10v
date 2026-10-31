"""SHA-locked GR III native digital HDF, original Clarity owner and scheduling.

No native pixel arithmetic is reimplemented. Plan and execution get the same
immutable per-recipe setting. Only the original factory allocation grows16B.
"""
import hashlib,os,shutil,struct,subprocess
from pathlib import Path
from scripts.build_gr3_menu_patches import assembly,branch
ROOT=Path(__file__).resolve().parents[1]
SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
SITES={0x53523e0c:0xebffb2c2,0x5351aed4:0xe59420f0,0x5351b068:0xe59420f0,
       0x5351084c:branch(0x5351084c,0x535134fc,True),
       0x535033d8:0xebffff1b,0x53503aa0:0xebfffd69,
       0x5367c1b0:0xe3580008,0x5367c7e4:0xe0281893}
# Q10 detail-band gains; finest band first. Same endpoint response as GR Mod's
# published digital soft focus. These are digital creative grades, not a
# calibrated optical HDF point-spread function. Coarse/DC bands stay at unity.
ROWS=((820,740,700,700,740,840,940,1024,1024,1024,1024),
      (680,560,500,500,540,680,860,960,1024,1024,1024),
      (540,400,330,330,380,540,760,920,1024,1024,1024))
HELPERS=('m10v_hdf_alloc','m10v_hdf_producer','m10v_hdf_gate','m10v_hdf_settings')
SAVE='push {r0-r12,lr};mrs r0,cpsr;push {r0,r1};'
RESTORE='pop {r0,r1};msr cpsr_fs,r0;pop {r0-r12,lr};'

def official_rtos():
    # A build must also work on the production server without local research
    # caches. Node's exact-identity section reader validates the official BIN.
    cached=ROOT/'builds/gr3-extension-validation/official-rtos.bin'
    if cached.is_file():
        b=cached.read_bytes()
        if hashlib.sha256(b).hexdigest()==SHA:return b
    node=os.environ.get('M10V_NODE') or shutil.which('node')
    script='import{readFileSync}from"node:fs";import{readOfficialSection}from"./node/firmware.mjs";process.stdout.write(readOfficialSection(readFileSync("bin/fwdc239b-gr3-official.bin"),"RTOS"));'
    return subprocess.run([node,'--input-type=module','-e',script],cwd=ROOT,check=True,capture_output=True).stdout

def build(base,exports,rtos=None,shared_recipe=False,ui_cache=False,pure_isp_blur=False):
    if type(pure_isp_blur)is not bool:raise ValueError('pure_isp_blur must be bool')
    rom=bytes(rtos) if rtos is not None else official_rtos()
    if hashlib.sha256(rom).hexdigest()!=SHA:raise ValueError('HDF requires exact GR III 2.10 RTOS')
    for a,w in SITES.items():
        if struct.unpack_from('<I',rom,a-0x53000000)[0]!=w:raise ValueError('HDF original instruction differs at '+hex(a))
    for k in (HELPERS[1:] if shared_recipe else HELPERS):
        if type(exports.get(k))is not int or exports[k]&3:raise ValueError('HDF ARM helper missing: '+k)
    image=bytearray();patches=[];entries={}
    def emit(site,text,name,link=False):
        at=base+len(image);image.extend(assembly(text,at));entries[name]=at
        patches.append(dict(address=site,expected=SITES[site],replacement=branch(site,at,link),entry=at,name=name))
    if not shared_recipe:emit(0x53523e0c,'b '+hex(exports['m10v_hdf_alloc']),'factory',True)
    for site in (() if shared_recipe else (0x5351aed4,0x5351b068)):
        emit(site,SAVE+'ldr r0,[r4,#0xf0];bl '+hex(exports['m10v_hdf_producer'])+';'+RESTORE+
             'ldr r2,[r4,#0xf0];b '+hex(site+4),'producer_'+hex(site))
    emit(0x5351084c,'push {r4-r8,lr};mov r5,r0;mov r6,r1;bl 0x535134fc;'+SAVE+
         'mov r0,r4;mov r1,r5;mov r2,r6;bl '+hex(exports['m10v_hdf_gate'])+';'+RESTORE+
         'pop {r4-r8,pc};','request',True)
    for site,context in (() if shared_recipe else ((0x535033d8,'ip'),(0x53503aa0,'r4'))):
        emit(site,'push {r4-r6,lr};mov r5,r0;mov r6,'+context+';bl 0x5350304c;'+SAVE+
             'mov r0,r6;mov r1,r5;bl '+hex(exports['m10v_hdf_settings'])+
             ';cmp r0,#1;ldreq r0,[sp,#8];orreq r0,r0,#1;streq r0,[sp,#8];'+RESTORE+
             'pop {r4-r6,pc};','settings_'+hex(site),True)
    patches.append(dict(address=0x5367c1b0,expected=SITES[0x5367c1b0],replacement=0xe358002f if pure_isp_blur else 0xe358000b,name='clarity_bound'))
    # Append rows after the row shim so the table is inside the audited module.
    row_at=base+len(image)
    def row_code(table):
        return assembly('push {r0,ip};mrs ip,cpsr;cmp r8,#8;mlals r8,r3,r8,r1;bls original_row;'
            'sub r8,r8,#9;movw r0,#'+str(table&65535)+';movt r0,#'+str(table>>16)+';mla r8,r3,r8,r0;'
            'original_row:;msr cpsr_fs,ip;pop {r0,ip};b 0x5367c7e8',row_at)
    table=row_at+len(row_code(0));image.extend(row_code(table))
    rows=ROWS
    if pure_isp_blur:
        from scripts.build_gr3_isp_effect_blur import BLUR_ROWS
        rows=ROWS+BLUR_ROWS
    image.extend(struct.pack('<'+str(len(rows)*11)+'h',*(n for row in rows for n in row)));image.extend(bytes(-len(image)&3))
    patches.append(dict(address=0x5367c7e4,expected=SITES[0x5367c7e4],replacement=branch(0x5367c7e4,row_at),entry=row_at,name='clarity_row'))
    if len(image)>(2048 if pure_isp_blur else 1024):raise ValueError('HDF hooks exceed fixed'+('2' if pure_isp_blur else '1')+'KiB budget')
    metadata=dict(schema='m10v-gr3-digital-hdf/v1',base=base,bytes=len(image),
        patches=patches,entries=entries,rows=table,required_rtos_sha256=SHA,
        recipe_bytes=0x4778,recipe_extra_bytes=0 if shared_recipe else 16,shared_recipe=shared_recipe,shared_offset=0x5134 if shared_recipe else None,native_parameter_values=[5,6,7],
        helpers={k:exports[k] for k in (HELPERS[1:] if shared_recipe else HELPERS)},isp_filesystem_calls=0,
        ui_cache=ui_cache,producer_filesystem_calls=0 if ui_cache else None,
        producer_load='published HDF UI cache; cold/invalid fails closed' if ui_cache else 'legacy standalone journal snapshot per post-mutex producer',
        pixel_loops=0,mutable_global_bytes=0,independent_dma=False,
        stock_clarity_table=0x538f1fd4,stock_clarity_bytes=198,camera_tested=False)
    if pure_isp_blur:
        from scripts.build_gr3_isp_effect_blur import manifest
        metadata['optional_blur']=manifest()
        metadata['native_parameter_values']+=list(range(8,44))
    return bytes(image),metadata
