"""Install original Develop Still Make callback with per-recipe state ingress.

Requires the extended recipe allocator from build_gr3_save_trace. ISP helpers
never call filesystem services. The submission adapter freezes the recipe at
the genuine processing-task producer, before its first message is queued.
"""
import hashlib,json,os,shutil,struct,subprocess,tempfile
from pathlib import Path
from scripts.build_gr3_m10v_library import ROOT,FLAGS,link_object
from scripts.build_gr3_menu_patches import assembly,branch
from scripts.build_gr3_isp_color_hook import SHA
SITE=0x53501d68
EXPECTED=0xe12fff33
COLOR_BYTES=1796

def stamp_orientation_contract(rom):
    # Same model-locked RTOS used by the capture adapter. Read-only anchors:
    # per-shot field getter/setter, exposure metadata destination, EXIF binding
    # and EXIF table. The direction source is the queued shot, not live config.
    words={0x53491528:0xe5d000c8,0x53491530:0xe5c010c8,
           0x534322f0:0xe2524000,0x53432360:0xe5c41946,
           0x535f63d0:0xe28320c8,0x535f63d4:0xe5842014,
           0x535f67ac:0xe5923014,0x535f67b0:0xe5d33000}
    for at,value in words.items():
        if struct.unpack_from('<I',rom,at-0x53000000)[0]!=value:
            raise ValueError('official per-exposure orientation contract differs at '+hex(at))
    if struct.unpack_from('<3H',rom,0x53d30190-0x53000000)!=(8,3,6):
        raise ValueError('official EXIF orientation mapping differs')
    return dict(source='this recipe ShootingInfo +0xc8',shooting_pointer_offset=0x44c8,
        field_offset=0xc8,normalized_directions=[0,1,2,3],exif_mapping=[1,8,3,6],
        unknown_direction=0,freeze='first original processing-task producer before enqueue',
        live_direction_reads=0,stamp_offset=0x5140,stamp_bytes=16,extended_recipe_bytes=0x5778,
        guard_words={hex(k):hex(v) for k,v in words.items()},exif_table=0x53d30190)

def build(out,rom,library_exports,owner_manifest,base=0x54180000,observer=True,producer_snapshot=False,native_color=False,native_grain=False,external_noise=False,live_color=False,shared_hdf=False,appended_slots=False,border_snapshot=False,pure_isp_effects=False):
    rom=bytes(rom)
    if hashlib.sha256(rom).hexdigest()!=SHA:raise ValueError('wrong official RTOS')
    stamp_contract=stamp_orientation_contract(rom)
    if struct.unpack_from('<I',rom,SITE-0x53000000)[0]!=EXPECTED:raise ValueError('Develop Still Make callback differs')
    if type(base)!=int or base&3 or not 0x540b6000<=base<=0x54fe0000:raise ValueError('invalid appendRX base')
    owner=owner_manifest.get('storage',{})
    if type(pure_isp_effects)is not bool or (pure_isp_effects and not (native_color and native_grain and producer_snapshot)):
        raise ValueError('pure ISP requires native color/grain and genuine producer ingress')
    if owner.get('color_offset')!=0x4a08 or owner.get('color_bytes')!=COLOR_BYTES or owner.get('extended_recipe_bytes')!=(0x57d8 if pure_isp_effects else 0x5778) or owner.get('stamp_offset')!=0x5140 or owner.get('stamp_bytes')!=16 or not any(p.get('address')==0x53523e0c for p in owner_manifest.get('patches',[])):
        raise ValueError('matching extended recipe factory hook required')
    if type(observer)is not bool or type(producer_snapshot)is not bool:raise ValueError('invalid hook mode')
    if type(external_noise)is not bool or external_noise:raise ValueError('CPU grain noise shaping has been removed')
    if type(native_grain)is not bool or (native_grain and not native_color):raise ValueError('native grain requires native per-recipe color mode')
    if type(native_color)is not bool or (native_color and observer):raise ValueError('native color requires apply mode')
    if type(border_snapshot)is not bool or (border_snapshot and not producer_snapshot):raise ValueError('border snapshot requires producer ingress')
    required=(('m10v_hdf_reserve','m10v_hdf_task_snapshot','m10v_hdf_settings','m10v_hdf_done') if shared_hdf else ())+ (('m10v_camera_library_preview','m10v_camera_library_custom_profile') if live_color or producer_snapshot else ())+('m10v_library_valid',)+(('m10v_library_tables',) if not observer else ())+(('m10v_camera_library_mutation_busy',) if producer_snapshot else ())+(('m10v_border_shot_freeze',) if border_snapshot else ())
    if pure_isp_effects:
        required+=('m10v_isp_effects_shot_freeze','m10v_isp_effects_shot_reserve','m10v_isp_effects_shot_read','m10v_isp_effects_pipeline_settings')
    if any(type(library_exports.get(k))!=int or library_exports[k]&3 for k in required):raise ValueError('real library decoder/validator ARM exports required')
    compiler=os.environ.get('M10V_LLVM_CLANG') or '/opt/homebrew/opt/llvm/bin/clang'
    if not Path(compiler).is_file():compiler=shutil.which('clang')
    with tempfile.TemporaryDirectory() as d:
        d=Path(d);src=d/'module.c';obj=d/'module.o'
        src.write_text(''.join('#include "'+str(ROOT/'native/gr3'/name)+'"\n' for name in (('m10v_isp_frame_color.c','m10v_isp_multiaxis.c','m10v_isp_native_look.c','m10v_isp_recipe_color.c') if native_color else ('m10v_isp_frame_color.c','m10v_isp_recipe_color.c'))))
        pure_flags=['-DM10V_PURE_ISP_EFFECTS=1','-DM10V_ISP_EFFECTS_SHOT_OFFSET=0x5778'] if pure_isp_effects else []
        subprocess.run([compiler,*FLAGS,*pure_flags,'-DM10V_BORDER_SHOT='+str(int(border_snapshot)),'-DM10V_APPENDED_SLOTS='+str(int(appended_slots)),'-DM10V_ISP_SHARED_HDF='+str(int(shared_hdf)),'-DM10V_ISP_LIVE_COLOR='+str(int(live_color)),'-DM10V_ISP_RECIPE_COLOR_OBSERVER='+str(int(observer)),'-DM10V_ISP_RECIPE_COLOR_PRODUCER='+str(int(producer_snapshot)),'-DM10V_ISP_NATIVE_LOOK='+str(int(native_color)),'-DM10V_ISP_NATIVE_GRAIN_MODE='+str(int(native_grain)),'-c',str(src),'-o',str(obj)],check=True,capture_output=True)
        code,exports=link_object(obj.read_bytes(),base,externals={k:library_exports[k] for k in required},prefix='m10v_isp_frame_',additional_exports=('m10v_isp_frame_identity_code','m10v_isp_frame_identity_clear','m10v_isp_frame_live_prepare','m10v_isp_frame_live_color','m10v_isp_frame_recipe_snapshot','m10v_isp_frame_recipe_state','m10v_isp_frame_recipe_begin','m10v_isp_frame_recipe_finish','m10v_isp_frame_recipe_producer','m10v_isp_frame_recipe_direction','m10v_isp_frame_recipe_completed','m10v_isp_frame_recipe_grain_settings','m10v_isp_frame_recipe_grain_done')+(('m10v_isp_multiaxis_apply','m10v_isp_native_look_prepare','m10v_isp_native_look_apply','m10v_isp_native_look_matches') if native_color else ()))
    entry=base+len(code)
    # Both preparation and finish preserve all original result/caller registers.
    # Pop before displaced BLX so original main Make sees exactly its stock SP.
    code+=assembly('push {r0-r12,lr};mov r2,r1;mov r1,r0;mov r0,r6;bl '+hex(exports['m10v_isp_frame_recipe_begin'])+';pop {r0-r12,lr};blx r3;push {r0-r12,lr};mov r0,r6;bl '+hex(exports['m10v_isp_frame_recipe_finish'])+';pop {r0-r12,lr};movw lr,#0x1d6c;movt lr,#0x5350;b 0x53501d6c',entry)
    patch=dict(address=SITE,expected_hex=struct.pack('<I',EXPECTED).hex(),replacement_hex=struct.pack('<I',branch(SITE,entry,link=True)).hex(),entry=entry)
    patches=[patch]
    if producer_snapshot:
        # Original5351ea9c(owner,r1=recipe) creates message+metadata and sends
        # them via536abd28. In contrast5351ae2c retires owner+f0 buffers via
        # 5352197c and only then reserves another recipe. Device879dccce
        # reached Develop/JPEG with no snapshot from that former hook.
        site=0x5351ea9c;expected=0xe1a0c00d
        if struct.unpack_from('<I',rom,site-0x53000000)[0]!=expected:raise ValueError('processing task producer prologue differs')
        at=base+len(code)
        code+=assembly('push {r0-r12,lr};mrs ip,cpsr;.word 0xeef1ea10;push {ip,lr};.word 0xed2d0b20;.word 0xed6d0b20;mov r0,r1;bl '+hex(exports['m10v_isp_frame_recipe_producer'])+';.word 0xecfd0b20;.word 0xecbd0b20;pop {ip,lr};.word 0xeee1ea10;msr cpsr_f,ip;pop {r0-r12,lr};.word '+hex(expected)+';b '+hex(site+4),at)
        patches.append(dict(address=site,expected_hex=struct.pack('<I',expected).hex(),replacement_hex=struct.pack('<I',branch(site,at)).hex(),entry=at))
        # Reservation marks a fresh exposure only. The exact5351ea9c task
        # producer freezes HDF from the UI cache, independently of color.
        for site in ((0x5351aed4,0x5351b068) if shared_hdf or pure_isp_effects else ()):
            expected=0xe59420f0
            if struct.unpack_from('<I',rom,site-0x53000000)[0]!=expected:raise ValueError('post-mutex recipe load differs')
            at=base+len(code)
            if pure_isp_effects:
                calls=('ldr r0,[sp,#280];ldr r0,[r0,#0xf0];bl '+hex(library_exports['m10v_hdf_reserve'])+';' if shared_hdf else '')
                calls+='ldr r0,[sp,#280];ldr r0,[r0,#0xf0];bl '+hex(library_exports['m10v_isp_effects_shot_reserve'])+';'
                code+=assembly('push {r0-r12,lr};mrs ip,cpsr;.word 0xeef1ea10;push {ip,lr};.word 0xed2d0b20;.word 0xed6d0b20;'+calls+'.word 0xecfd0b20;.word 0xecbd0b20;pop {ip,lr};.word 0xeee1ea10;msr cpsr_f,ip;pop {r0-r12,lr};.word '+hex(expected)+';b '+hex(site+4),at)
            else:
                code+=assembly('push {r0-r12,lr};mrs ip,cpsr;push {ip,lr};ldr r0,[r4,#0xf0];bl '+hex(library_exports['m10v_hdf_reserve'])+';pop {ip,lr};msr cpsr_f,ip;pop {r0-r12,lr};.word '+hex(expected)+';b '+hex(site+4),at)
            patches.append(dict(address=site,expected_hex=struct.pack('<I',expected).hex(),replacement_hex=struct.pack('<I',branch(site,at)).hex(),entry=at))
    if live_color:
        # Original Live Make takes r0/r1 only. Keep original outputs, flags,
        # caller stack alignment and all FP registers around the added helper.
        at=base+len(code)
        code+=assembly('push {r0-r3,ip,lr};bl '+hex(exports['m10v_isp_frame_live_prepare'])+';pop {r0-r3,ip,lr};push {r4-r6,lr};mov r4,r0;mov r5,r1;bl 0x536ddecc;push {r0-r12,lr};mrs ip,cpsr;.word 0xeef1ea10;push {ip,lr};.word 0xed2d0b20;.word 0xed6d0b20;mov r0,r4;mov r1,r5;bl '+hex(exports['m10v_isp_frame_live_color'])+';.word 0xecfd0b20;.word 0xecbd0b20;pop {ip,lr};.word 0xeee1ea10;msr cpsr_f,ip;pop {r0-r12,lr};pop {r4-r6,pc}',at)
        site=0x53dbd954;expected=0x536ddecc
        if struct.unpack_from('<I',rom,site-0x53000000)[0]!=expected:raise ValueError('Live Make vtable differs')
        patches.append(dict(address=site,expected_hex=struct.pack('<I',expected).hex(),replacement_hex=struct.pack('<I',at).hex(),entry=at))
    manifest=dict(stamp_orientation=stamp_contract,schema=1,base=base,bytes=len(code),exports=exports,patches=patches,required_rtos_sha256=SHA,required_owner_factory=0x53523e0c,color_offset=0x4a08,color_bytes=COLOR_BYTES,mutable_global_bytes=0,filesystem_calls=0,isp_filesystem_calls=0,allocator_calls=0,camera_tested=False,quality_equivalence_proven=False,activation_requires=['Install matching owner factory allocation hook.','Snapshot current recipe before submission; never snapshot the next reserved raw buffer.' if producer_snapshot else 'Snapshot184-byte state before queueing on a proven safe producer.','CPU fallback uses recipe_state(), never reload another selected state.'],context_contract={'site':SITE,'stock_instruction':'blx r3','r0':'ImageTuningStill','r1':'module+40 R2Y info','r6':'Develop context C','C+30':'sourceRecipe+1a8','C+34':'ShootingInfo','scope':'only actual Develop process caller, stage0 or stage1','color_space':'shot+7be==1 as original536dc474..494'},unsupported='Observer preserves all film engines; experimental apply rejects IDs outside34..65 without3D LUT fit',native_color=native_color,native_grain=native_grain,live_color=live_color,shared_hdf=shared_hdf,snapshot_ingress_installed=producer_snapshot,observer=observer,producer_sites=[0x5351ea9c] if producer_snapshot else [],producer_lock_contract='Processing-task producer; cached state only, no filesystem/allocator/mutex; preserves all GPRs, SP/LR, NZCV, d0-d31 and FPSCR')
    if pure_isp_effects:
        manifest.update(pure_isp_effects=True,effects_shot_offset=0x5778,effects_shot_bytes=96,extended_recipe_bytes=0x57d8)
        stamp_contract['extended_recipe_bytes']=0x57d8
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'isp-recipe-color.bin').write_bytes(code);(out/'isp-recipe-color.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return code,manifest

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True);p.add_argument('--rtos',required=True)
    p.add_argument('--runtime-manifest',required=True);p.add_argument('--owner-manifest',required=True)
    p.add_argument('--base',type=lambda s:int(s,0),default=0x54180000)
    p.add_argument('--producer-snapshot',action='store_true')
    p.add_argument('--experimental-apply',action='store_true')
    a=p.parse_args();runtime=json.loads(Path(a.runtime_manifest).read_text())
    code,m=build(a.out,Path(a.rtos).read_bytes(),runtime.get('symbols',runtime.get('exports',{})),json.loads(Path(a.owner_manifest).read_text()),a.base,observer=not a.experimental_apply,producer_snapshot=a.producer_snapshot)
    print(json.dumps({'bytes':len(code),'patches':m['patches'],'observer':m['observer'],'snapshot_ingress_installed':m['snapshot_ingress_installed']},indent=2))
