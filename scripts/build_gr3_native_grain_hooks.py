"""Borrow the original grain planning/execution stages at four exact callsites.

No independent DMA, allocation, SD or mutable globals. The two displaced
functions have verified three-register AAPCS arguments and no stack arguments.
"""
import hashlib,json,struct
from pathlib import Path
from scripts.build_gr3_menu_patches import assembly,branch
ROOT=Path(__file__).resolve().parents[1]
SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
SITES={0x53513620:0xe1a00004,0x535033d8:0xebffff1b,0x53503aa0:0xebfffd69,0x53503ab4:0xeb05f4c0}
HELPERS=('m10v_isp_frame_recipe_grain_settings','m10v_isp_frame_recipe_grain_done')
# 56 GPR bytes, 8 flags/FPSCR bytes, 256 VFP bytes; original r0 at+264.
SAVE='push {r0-r12,lr};mrs r0,cpsr;vmrs r1,fpscr;push {r0,r1};vpush {d0-d15};vpush {d16-d31};'
RESTORE='vpop {d16-d31};vpop {d0-d15};pop {r0,r1};vmsr fpscr,r1;msr cpsr_f,r0;pop {r0-r12,lr};'

def build(out,base,exports,rtos=None,appended_slots=False,pure_isp_effects=False):
    if type(pure_isp_effects)is not bool:raise ValueError('pure ISP option must be boolean')
    if type(base)is not int or base&3 or not 0x540b6000<=base<=0x54fe0000:raise ValueError('invalid isolated appendRX base')
    if any(type(exports.get(k))is not int or exports[k]&3 or not 0x53000000<=exports[k]<0x55000000 for k in HELPERS):raise ValueError('both recipe grain ARM helper exports required')
    pure_helpers=('m10v_isp_effects_pipeline_workspace','m10v_isp_effects_pipeline_execute')
    if pure_isp_effects and any(type(exports.get(k))is not int or exports[k]&3 or not 0x53000000<=exports[k]<0x55000000 for k in pure_helpers):raise ValueError('pure ISP workspace/execution exports required')
    rom=bytes(rtos) if rtos is not None else (ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
    for at,word in SITES.items():
        if at-0x53000000+4>len(rom) or struct.unpack_from('<I',rom,at-0x53000000)[0]!=word:raise ValueError('grain hook preimage differs at '+hex(at))
    if hashlib.sha256(rom).hexdigest()!=SHA:raise ValueError('requires exact original RTOS hash')
    code=b'';patches=[]
    def emit(site,text,link=True):
        nonlocal code
        entry=base+len(code);fragment=assembly(".fpu neon\n"+text,entry);code+=fragment
        patches.append(dict(address=site,entry=entry,expected_hex=struct.pack('<I',SITES[site]).hex(),replacement_hex=struct.pack('<I',branch(site,entry,link=link)).hex()))
    gate='sub r0,r0,#25;cmp r0,#9;bhi grain_gate_end;' if appended_slots else 'cmp r0,#12;beq grain_request;sub r0,r0,#18;cmp r0,#3;bhi grain_gate_end;'
    if pure_isp_effects:
        gate='cmp r0,#14;beq grain_gate_end;cmp r0,#11;blo grain_gate_end;cmp r0,#22;bls grain_request;'+('sub r0,r0,#25;cmp r0,#9;bhi grain_gate_end;' if appended_slots else 'b grain_gate_end;')
    emit(0x53513620,SAVE+'ldrb r0,[r5,#0x77c];'+gate+'grain_request:;mov r0,#1;strb r0,[r4,#0x24];grain_gate_end:;'+RESTORE+'mov r0,r4;b 0x53513624',False)
    for site,phase in ((0x535033d8,0),(0x53503aa0,1)):
        # The fixed sixteen-byte wrapper frame keeps SP aligned. Original
        # register arguments are untouched; only callee-saved scratch is used.
        capture='mov r6,ip;' if phase==0 else 'mov r6,r4;'
        finish='pop {r4,r5,r6,lr};bx lr;' if pure_isp_effects else 'pop {r4,r5,r6,pc};'
        emit(site,'push {r4,r5,r6,lr};mov r5,r0;'+capture+'bl 0x5350304c;'+SAVE+'mov r0,r6;mov r1,r5;mov r2,#'+str(phase)+';bl '+hex(exports[HELPERS[0]])+';cmp r0,#1;ldreq r0,[sp,#264];orreq r0,r0,#1;streq r0,[sp,#264];'+RESTORE+finish)
    if pure_isp_effects:
        emit(0x53503ab4,'push {r4,r5,r6,lr};mov r5,r1;mov r6,r4;mov r4,r0;bl 0x53680dbc;'+SAVE+
            'ldr r0,[sp,#288];ldr r0,[r0,#0x30];cmp r0,#0x1a8;blo pure_no_execute;sub r0,r0,#0x1a8;ldr r2,[sp,#284];ldr ip,[r2,#0x20];cmp ip,r0;bne pure_no_execute;'+
            'ldr r1,[sp,#280];ldr r3,[sp,#264];bl '+hex(exports[pure_helpers[1]])+';cmp r0,#1;movne r0,#0;strne r0,[sp,#264];pure_no_execute:;'+
            'ldr r0,[sp,#288];ldr r1,[sp,#284];ldr r2,[sp,#264];bl '+hex(exports[HELPERS[1]])+';'+RESTORE+'pop {r4,r5,r6,lr};bx lr;')
    else:
        emit(0x53503ab4,'push {r4,r5,r6,lr};mov r5,r1;mov r6,r4;bl 0x53680dbc;'+SAVE+'mov r0,r6;mov r1,r5;ldr r2,[sp,#264];bl '+hex(exports[HELPERS[1]])+';'+RESTORE+'pop {r4,r5,r6,pc};')
    query_patch=None
    if pure_isp_effects:
        site=0x535033e8;expected=0xeb05f673
        if struct.unpack_from('<I',rom,site-0x53000000)[0]!=expected:raise ValueError('pure ISP sizing preimage differs')
        query_entry=base+len(code)
        code+=assembly('.fpu neon\npush {r4,r5,r6,lr};mov r5,r1;mov r6,r2;bl 0x53680dbc;'+SAVE+
            'ldr r0,[sp,#284];ldr r1,[sp,#288];ldr r2,[sp,#264];bl '+hex(exports[pure_helpers[0]])+';'+RESTORE+'pop {r4,r5,r6,lr};bx lr;',query_entry)
        query_patch=dict(address=site,entry=query_entry,expected_hex=struct.pack('<I',expected).hex(),replacement_hex=struct.pack('<I',branch(site,query_entry,link=True)).hex())
    if len(code)>700:raise ValueError('grain hooks exceed700-byte budget')
    manifest=dict(schema='gr3-native-grain-hooks/v1',base=base,bytes=len(code),patches=patches,exports={k:exports[k] for k in HELPERS},required_rtos_sha256=SHA,mutable_global_bytes=0,filesystem_calls=0,allocator_calls=0,independent_dma=False,cpu_noise_processing=False,software_fallback=False,camera_tested=False,
      appended_slots=appended_slots,original_abi={'settings':0x5350304c,'execution':0x53680dbc,'arguments':'verified r0,r1,r2 only; no stack arguments','wrapper_frame_bytes':16,'helper_save_bytes':320,'vfp':'all d0-d31 and FPSCR restored to original postcall state','result':'original r0; settings may OR1 only when helper returns1','post_gate':'all GPR/flags/VFP preserved except displaced mov r0,r4 and legal request+24=1','zero_grain':'postgate only enables traversal, original plan sizing remains0'})
    if pure_isp_effects:
        manifest.update(pure_isp_effects=True,pure_isp_query_patch=query_patch,query_entry=query_entry)
        manifest['exports'].update({k:exports[k] for k in pure_helpers})
        manifest['original_abi']['result']='original query r0 retained; execution may fail closed to0, never changes failure to success'
    out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'native-grain-hooks.bin').write_bytes(code);(out/'native-grain-hooks.json').write_text(json.dumps(manifest,indent=2)+'\n');return code,manifest
