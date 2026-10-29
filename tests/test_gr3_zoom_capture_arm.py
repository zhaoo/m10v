"""Execute installed focal hooks in a final RTOS; never fabricate a firmware.

M10V_ZOOM_RTOS=/abs/final-rtos.bin M10V_ZOOM_MANIFEST=/abs/manifest.json
.venv/bin/python tests/test_gr3_zoom_capture_arm.py

Native storage/app boundaries are isolated. Actual final image, hook words,
trampolines, mm conversion, caption IDs, geometry and marker code execute.
"""
import json,struct
from pathlib import Path
from unicorn import *
from unicorn import arm_const as A
import unittest

def verify_final_runtime():
    import os
    final_rtos=os.environ.get('M10V_ZOOM_RTOS')
    final_manifest=os.environ.get('M10V_ZOOM_MANIFEST')
    if not final_rtos or not final_manifest:
        raise unittest.SkipTest('Set M10V_ZOOM_RTOS and M10V_ZOOM_MANIFEST to a built final RTOS and manifest')
    manifest=json.loads(Path(final_manifest).read_text())
    zoom=manifest['zoom']
    ROM=Path(final_rtos).read_bytes();BASE=0x53000000;RAM=0x55000000;STOP=RAM+0xff000
    symbols=zoom['symbols']
    for patch in zoom['patches']:
        assert struct.unpack_from('<I',ROM,patch['address']-BASE)[0]==patch['replacement'],patch['name']
    stubs={k:v for k,v in zoom['bindings'].items() if k.startswith('m10v_zoom_native_')}
    # These two native display fallbacks require app objects unrelated to the
    # metadata ABI. Intercept after the displaced MOV ip,sp, preserving the
    # actual installed hook and original-instruction trampoline execution.
    stubs.update({'m10v_zoom_original_crop_icon':0x532aa4b4,'m10v_zoom_original_crop_caption':0x532aa66c})
    originals={p['name']:p['address'] for p in zoom['patches']}
    caption_base=zoom['focal_first_id']-28
    bits=lambda mm:struct.unpack('<I',struct.pack('<f',mm/28))[0]
    results=[]
    ratios=([0,3,1,4,5]+([6] if manifest['camera_model']=='gr3' else [])) if zoom['aspect'] else [0,3,1]
    def machine(mm=41):
     u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(BASE,(len(ROM)+4095)&~4095);u.mem_write(BASE,ROM);u.mem_map(RAM,0x100000)
     u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000);u.reg_write(A.UC_ARM_REG_SP,RAM+0xd0000);u.reg_write(A.UC_ARM_REG_LR,STOP)
     calls=[];reverse={v:k for k,v in stubs.items()}
     def hook(uc,a,size,unused):
      if a not in reverse or a in (0x540b9450,0x5313d850):return
      name=reverse[a];r=[uc.reg_read(x) for x in [A.UC_ARM_REG_R0,A.UC_ARM_REG_R1,A.UC_ARM_REG_R2,A.UC_ARM_REG_R3]];calls.append((name,r))
      val=0
      if name=='m10v_zoom_native_ifd_byte':val=uc.mem_read(r[0]+16+r[1],1)[0]
      elif name=='m10v_zoom_native_ifd_write_byte':uc.mem_write(r[0]+16+r[1],bytes([r[2]&255]))
      elif name=='m10v_zoom_native_raw_mag':uc.reg_write(A.UC_ARM_REG_S0,bits(mm))
      elif name.startswith('m10v_zoom_original'):val=0x12345678
      uc.reg_write(A.UC_ARM_REG_R0,val);uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
     u.hook_add(UC_HOOK_CODE,hook);return u,calls
    regs=[A.UC_ARM_REG_R0,A.UC_ARM_REG_R1,A.UC_ARM_REG_R2,A.UC_ARM_REG_R3]
    def run(u,name,*args):
     for r,v in zip(regs,args):u.reg_write(r,v)
     u.reg_write(A.UC_ARM_REG_LR,STOP);u.emu_start(originals.get(name,symbols[name]),STOP,count=200000)
    for mm in range(28,101):
     u,calls=machine(mm);ctx=RAM+0x100;props=RAM+0x1000;IFD=RAM+0x3000;state=RAM+0x4000
     u.mem_write(ctx+0x1c,struct.pack('<I',props));u.mem_write(props+0x7b8,struct.pack('<I',bits(mm)));u.mem_write(IFD+8,struct.pack('<I',3));u.mem_write(IFD+16,b'\x09'*3)
     run(u,'m10v_zoom_capture_marker_write',ctx,IFD)
     if mm in (28,35,50):
      assert bytes(u.mem_read(IFD+16,3))==bytes([0,{28:0,35:5,50:6}[mm],0])
      run(u,'m10v_zoom_capture_marker_read',ctx,IFD,state)
      assert struct.unpack('<I',u.mem_read(state+0x7b8,4))[0]==bits(mm)
      continue
     assert bytes(u.mem_read(IFD+16,3))==bytes([0,128|(mm-28),1])
     run(u,'m10v_zoom_capture_marker_read',ctx,IFD,state)
     assert struct.unpack('<I',u.mem_read(state+0x7b8,4))[0]==bits(mm)
     run(u,'m10v_zoom_capture_marker_summary',ctx,state,IFD)
     assert calls[-1]==('m10v_zoom_native_summary_write',[state,17,mm*100//28,calls[-1][1][3]])
     run(u,'m10v_zoom_capture_raw_count',ctx);count=u.reg_read(A.UC_ARM_REG_R0);assert count==(4 if mm<35 else 3 if mm<50 else 2)
     for i in range(count):run(u,'m10v_zoom_capture_raw_value',ctx,i);assert u.reg_read(A.UC_ARM_REG_R0)==4-count+i
    results.append('marker all custom28..100 writer/read/summary and raw quality chains pass; defaults writer passthrough')
    for mm in [28,30,35,36,41,49,50,51,100]:
     for ratio in ratios:
      for quality in range(4):
       u,calls=machine(mm);u.reg_write(A.UC_ARM_REG_S0,bits(mm));u.mem_write(RAM+0xd0000,struct.pack('<I',RAM+0x102));u.reg_write(A.UC_ARM_REG_R4,0x12344321)

       try: run(u,'m10v_zoom_capture_resolution_hook',0xabcd,quality,ratio,RAM+0x100)
       except Exception:
        print('FAIL',mm,ratio,quality,hex(u.reg_read(A.UC_ARM_REG_PC)),[hex(u.reg_read(r)) for r in regs]);raise
       w,h=struct.unpack('<HH',u.mem_read(RAM+0x100,4));assert 0<w<=6000 and 0<h<=4000,(mm,ratio,quality,w,h)
       assert u.reg_read(A.UC_ARM_REG_SP)==RAM+0xd0000 and u.reg_read(A.UC_ARM_REG_R4)==0x12344321
       if mm not in (28,35,50):assert w*mm<=6000*28 and h*mm<=4000*28
       orig,oc=machine(mm);orig.mem_write(RAM+0xd0000,struct.pack('<I',RAM+0x102));orig.reg_write(A.UC_ARM_REG_S0,bits(mm if mm in (28,35,50) else 28))
       for r,v in zip(regs,[0xabcd,quality,ratio,RAM+0x100]):orig.reg_write(r,v)
       orig.emu_start(zoom['bindings']['m10v_zoom_original_resolution'],STOP,count=200000)
       ow,oh=struct.unpack('<HH',orig.mem_read(RAM+0x100,4))
       if mm in (28,35,50): assert (w,h)==(ow,oh)
       else:
        orig.reg_write(A.UC_ARM_REG_SP,RAM+0xd0000);orig.reg_write(A.UC_ARM_REG_LR,STOP);orig.reg_write(A.UC_ARM_REG_S0,bits(28))
        for r,v in zip(regs,[0xabcd,0,ratio,RAM+0x100]):orig.reg_write(r,v)
        orig.emu_start(zoom['bindings']['m10v_zoom_original_resolution'],STOP,count=200000)
        sw,sh=struct.unpack('<HH',orig.mem_read(RAM+0x100,4))
        assert (w,h)==(min(ow,(sw*28//mm)&~15),min(oh,(sh*28//mm)&~15)),(mm,ratio,quality,w,h,ow,oh,sw,sh)
    results.append(f'resolution ARM installed route passes9 focals x{len(ratios)} ratios x4 qualities; stack and r4 preserved')
    for mm in [28,30,35,41,50,100]:
     for name in ['m10v_zoom_capture_caption_hook','m10v_zoom_capture_icon_hook']:
      u,calls=machine(mm);u.reg_write(A.UC_ARM_REG_S0,bits(mm));run(u,name,0xaabbccdd)
      value=u.reg_read(A.UC_ARM_REG_R0)
      assert value==(0x12345678 if mm in (28,35,50) else caption_base+mm if 'caption' in name else 762+mm-28)
    results.append('custom caption resource and per-mm live icon IDs; originals preserved')
    for invalid_bits in [0,0x3fbae148,0x7fc00000,0x7f800000,0xbf800000]:
     for name in ['m10v_zoom_capture_caption_hook','m10v_zoom_capture_icon_hook']:
      u,calls=machine();u.reg_write(A.UC_ARM_REG_S0,invalid_bits);run(u,name,0xaabbccdd)
      assert u.reg_read(A.UC_ARM_REG_R0)==0,(name,hex(invalid_bits),'noncanonical unknown metadata must not enter native assertions')
    results.append('invalid/rounded/NaN magnifications omitted from display with no native assert path; exact validation unchanged')
    rectangles={}
    for mm in [30,36,41,49,51,100]:
     for ratio in ratios:
      u,calls=machine(mm);ctx=RAM+0x100;state=RAM+0x2000
      u.mem_write(ctx+8,struct.pack('<I',state));u.mem_write(state+0x7b8,struct.pack('<I',bits(mm)));u.mem_write(state+0x7b6,bytes([ratio]))
      run(u,'m10v_zoom_capture_replay_rect',ctx)
      w,h,x,y=struct.unpack('<4I',u.mem_read(state+0x6a0,16))
      assert abs(w+2*x-2949120)<=1 and abs(h+2*y-1966080)<=1
      assert w and h
      rectangles[(mm,ratio)]=(w,h,x,y)
    assert rectangles[(36,0)]!=rectangles[(41,0)]
    results.append(f'per-image replayAF rectangles6 custom focals x{len(ratios)} ratios centered Q16,36 differs41; not sensor crop evidence')
    native_windows={}
    for mm in [30,36,41,49,51,100]:
     for ratio in ratios:
      u,calls=machine(mm)
      delta=symbols['m10v_zoom_capture_resolution_hook']-0x536a2a30-8
      assert struct.unpack('<I',u.mem_read(0x536a2a30,4))[0]==0xea000000|((delta>>2)&0xffffff)
      u.reg_write(A.UC_ARM_REG_S0,bits(mm));u.mem_write(RAM+0xd0000,struct.pack('<I',ratio))
      for r,v in zip(regs,[RAM+0x100,RAM+0x102,RAM+0x104,RAM+0x106]):u.reg_write(r,v)
      u.emu_start(0x5365f0ec,STOP,count=200000)
      w,h,x,y=struct.unpack('<4H',u.mem_read(RAM+0x100,8))
      assert w+2*(x-68)==6000 and h+2*(y-40)==4000
      assert w*mm<=6000*28 and h*mm<=4000*28
      native_windows[(mm,ratio)]=(w,h,x,y)
    assert native_windows[(36,0)]!=native_windows[(41,0)]
    results.append(f'actual native5365f0ec image-map/DNG crop window derives custom dimensions and centered origins with68x40sensor margins,6focals x{len(ratios)}ratios')
    return {'checks':results,'camera_tested':False,'native_windows':{f'{mm}mm_ratio{ratio}':v for (mm,ratio),v in native_windows.items()}}

class FinalZoomRuntimeTests(unittest.TestCase):
    def test_installed_capture_metadata_and_geometry(self):
        result=verify_final_runtime()
        self.assertFalse(result['camera_tested'])
        print(json.dumps(result,indent=2))

if __name__=='__main__':unittest.main()
