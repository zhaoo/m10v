"""Read-only original ARM proof of JPEG metadata dimensions and orientation.

Executes native frame-info creation, EXIF A002/A003 setters, MakerNote preview
size setter, and orientation setter. No RTOS image is changed or generated.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
def probe(blob):
 assert hashlib.sha256(blob).hexdigest()==SHA
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,(len(blob)+4095)&~4095);u.mem_write(0x53000000,blob)
 u.mem_map(0x55000000,0x100000)
 def put(a,v):u.mem_write(a,struct.pack('<I',v))
 def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 def half(a,v):u.mem_write(a,struct.pack('<H',v))
 def byte(a,v):u.mem_write(a,bytes([v]))
 def boundary(u,a,n,d):
  if a in (0x536b93d0,0x5369be50):u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,boundary)
 def call(a,*args):
  for i,r in enumerate((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)):u.reg_write(r,args[i] if i<len(args) else 0)
  u.reg_write(UC_ARM_REG_SP,0x550ff000);u.reg_write(UC_ARM_REG_LR,0x550fff00)
  u.emu_start(a,0x550fff00,count=100000)
  assert u.reg_read(UC_ARM_REG_PC)==0x550fff00
  return u.reg_read(UC_ARM_REG_R0)
 config,desc,encoded,frame,si,setter,entry,registry,image= [0x55000000+i*0x10000 for i in range(9)]
 # mode0 main-JPEG frame-info creator uses config+40 descriptor and +50 encoded output.
 put(config+0x40,desc);put(config+0x50,encoded);byte(desc,2)
 half(desc+0x10,6320);half(desc+0x12,4640);half(desc+0x14,6336)
 put(encoded,0x60000000);put(encoded+0xc,123456)
 call(0x5350afec,0,frame,config,0)
 assert [get(frame),get(frame+4)]==[6320,4640]
 # Real metadata registry associates slot2 with this frame, independently of SI.
 call(0x535fc234,registry);call(0x535fc2e0,registry,2,frame)
 assert call(0x535fc308,registry,2)==frame
 put(setter+4,registry);call(0x535ff8ec,setter)
 assert get(setter+0x24)==frame
 dims=[]
 for tag in (0xa002,0xa003):
  u.mem_write(entry,b'\0'*24);half(entry+4,tag);half(entry+6,4);put(entry+8,1)
  assert call(0x535ff9dc,setter,entry)==1;dims.append(get(entry+0xc))
 assert dims==[6320,4640]
 # Actual capture Store registry setup, not the separate WriteStillFile path.
 # Normal record byte2 chooses main frame. Status service is an explicit boundary.
 record=frame-4;byte(record,2)
 assert call(0x53695408,image,record,0)==1
 actual_registry=record+0x3f0
 assert call(0x535fc308,actual_registry,2)==frame
 assert call(0x535fc308,actual_registry,1)==record+0x50
 assert call(0x535fc308,actual_registry,0)==record+0x9c
 put(setter+4,actual_registry);call(0x535ff8ec,setter)
 for tag,want in ((0xa002,6320),(0xa003,4640)):
  u.mem_write(entry,b'\0'*24);half(entry+4,tag);half(entry+6,4);put(entry+8,1)
  assert call(0x535ff9dc,setter,entry)==1 and get(entry+0xc)==want
 # Pentax MakerNote tag2 uses separate preview-frame width/height, not main frame.
 preview=frame+0x100;put(preview,720);put(preview+4,480)
 u.mem_write(entry,b'\0'*24);half(entry+6,3);put(entry+8,2)
 call(0x535c7590,setter,entry,preview)
 assert struct.unpack('<2H',u.mem_read(entry+0xc,4))==(720,480)
 # Common TIFF orientation helper source SI+c8 plus optional SI71e03/4 override.
 put(setter+4,registry);put(registry+4,image);put(setter+8,si);put(setter+0x14,si+0xc8)
 mapping={}
 for v in range(5):
  byte(si+0xc8,v);put(image+0x144,0);byte(si+0x71e03,0)
  call(0x535f673c,setter,entry);mapping[v]=struct.unpack('<H',u.mem_read(entry+0xc,2))[0]
 assert list(mapping.values())==[1,8,3,6,1]
 byte(si+0xc8,0);byte(si+0x71e03,1);byte(si+0x71e04,3)
 call(0x535f673c,setter,entry);assert struct.unpack('<H',u.mem_read(entry+0xc,2))[0]==6
 forced=[]
 for mode in (2,3):
  put(image+0x144,mode);call(0x535f673c,setter,entry);forced.append(struct.unpack('<H',u.mem_read(entry+0xc,2))[0])
 assert forced==[1,1]
 # Execute actual recipe SI freeze plus actual native NEON memcpy to postcopy rejoin.
 u.mem_map(0x55100000,0x300000)
 u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
 recipe,source,frozen=0x55100000,0x55200000,0x55300000
 pattern=bytes((i*13+7)&255 for i in range(0x74270));u.mem_write(source,pattern)
 byte(source+0xc8,1);byte(source+0x71e03,1);byte(source+0x71e04,3)
 put(recipe+0x44c8,frozen)
 u.reg_write(UC_ARM_REG_R0,recipe);u.reg_write(UC_ARM_REG_R1,1);u.reg_write(UC_ARM_REG_R2,source)
 u.reg_write(UC_ARM_REG_SP,0x550ff000);u.reg_write(UC_ARM_REG_LR,0x550fff00)
 u.emu_start(0x53510800,0x53510834,count=200000)
 assert u.reg_read(UC_ARM_REG_PC)==0x53510834
 assert bytes(u.mem_read(source,0x74270))==bytes(u.mem_read(frozen,0x74270))
 byte(source+0xc8,2);byte(source+0x71e04,1)
 assert bytes(u.mem_read(frozen+0xc8,1))==b'\x01' and bytes(u.mem_read(frozen+0x71e04,1))==b'\x03'
 put(setter+8,frozen);put(setter+0x14,frozen+0xc8);put(image+0x144,0)
 call(0x535f673c,setter,entry);assert struct.unpack('<H',u.mem_read(entry+0xc,2))[0]==6
 return {'rtos_sha256':SHA,'main_frame_dimensions':dims,'capture_orientation_to_exif':mapping,'checks':{'descriptor_to_main_frame':True,'registry_slot2_and_actual_exif_setters':True,'actual_store_record_registry_to_exif':True,'native_full_si_freeze_and_source_independence':True,'independent_makernote_preview_size':True,'capture_si_orientation':True,'si_orientation_override':True,'metadata_modes_2_3_force_normal':True},'limitations':['Synthetic object state; does not execute file scheduler, container assembly, JPEG hardware or physical camera.','Actual Store record-to-registry and EXIF setters execute; asynchronous filesystem request/container assembly does not.','No claim that a capture-size MakerNote enum has been identified.']}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rtos',required=True,type=Path);p.add_argument('--output',type=Path);a=p.parse_args();r=probe(a.rtos.read_bytes());s=json.dumps(r,indent=2)+'\n'
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(s)
 print(s,end='')
if __name__=='__main__':main()
