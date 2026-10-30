"""Installed candidate real Live Make recurrence; no ISP pixels/hardware."""
import argparse,hashlib,json,struct,sys,zlib
from pathlib import Path
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_gr3_isp_base import StockISP
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A

def state(film):
 b=bytearray(184);struct.pack_into('<IHHI',b,0,0x5630314d,5,184,7);struct.pack_into('<H6B',b,12,film,0,0,0,3,5,2);struct.pack_into('<I',b,180,zlib.crc32(b[:180]));return bytes(b)
def run(folder,film,stage=1,alternating=False):
 m=json.loads((folder/'manifest.json').read_text());rom=(folder/'final-rtos.bin').read_bytes();s=m['capture_lifecycle']['snapshot'];x=s['exports'];entry=next(p['entry'] for p in s['patches'] if p['address']==0x53dbd954)
 e=StockISP(rom);owner=0x550d0000;e.w32(0x55063910,1);e.w32(0x55063988,owner);e.w32(owner+0x213c,0x3856504d);e.w32(owner+0x2140,2);e.u.mem_write(owner+0x2144,state(film))
 if stage==0:
  # Only non-color hardware black-level/noise leaves are substituted.
  e.services.update((0x536decb4,0x536e4634,0x536e4de4,0x536e5070,0x536eaf80,0x536ec3e0,0x536eb0b0,0x536e9d1c))
 e.make(25,stage,True,actual_live=True);obj=0x60000000;f=0x60001400;f2=e.alloc(0x9000)
 pristine=bytes(e.u.mem_read(f,0x9000));e.u.mem_write(f2,pristine)
 hits=[];peak=[0x5effff00];e.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:peak.__setitem__(0,min(peak[0],u.reg_read(A.UC_ARM_REG_SP))))
 e.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:hits.append(a) if a in(x['m10v_isp_native_look_apply'],0x536e9000,0x536e7348) else None)
 records=[]
 for iteration in range(6):
  frame=f2 if alternating and iteration%2 else f
  e.call(entry,obj,frame)
  b=bytes(e.u.mem_read(frame,0x9000));records.append({'iteration':iteration,'frame':frame,'sha256':hashlib.sha256(b).hexdigest(),'matrix':b[0x140:0x152].hex(),'post':b[0x12a0:0x12b2].hex(),'flags':bytes(e.u.mem_read(obj,0x13)).hex(),'tone':bytes(e.u.mem_read(obj+0x1a8,2)).hex(),'gamma':hashlib.sha256(b[0x2688:0x5088]).hexdigest()})
 return {'film':film,'stage':stage,'alternating':alternating,'records':records,'native_apply_calls':hits.count(x['m10v_isp_native_look_apply']),'native_gamma_calls':hits.count(0x536e9000),'native_color_calls':hits.count(0x536e7348),'assertions':e.assertions,'peak_stack_bytes':0x5effff00-peak[0]}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,default=Path('builds/gr3-half-frame-r4-debug-final-20261030'));p.add_argument('--out',type=Path);a=p.parse_args();r=[]
 for st in(1,2):
  for film in(35,317):
   for alt in(False,True):
    try:r.append(run(a.candidate,film,st,alt))
    except Exception as ex:r.append({'film':film,'stage':st,'alternating':alt,'error':str(ex)})
 output=json.dumps(r,indent=2)+'\n'
 if a.out:a.out.write_text(output)
 print(output)
