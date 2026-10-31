"""Optional, exact-ROM-bound prepared-plane Granulation component. No firmware output."""
import hashlib,re,shutil,struct,subprocess,tempfile
from pathlib import Path
from scripts import build_gr3_border_wait_guard as guard
ROOT=Path(__file__).resolve().parents[1]
SOURCES=('native/gr3/m10v_isp_effect_granulation.c','native/gr3/m10v_isp_effect_granulation.h','scripts/build_gr3_isp_effect_granulation.py','native/gr3/m10v_isp_effect_memory.h')
# Complete original entry/body and the native submit, wait, release, lock and
# driver control paths reached by this component. Same hashes on both models.
EXTRA_SPANS=(
 ('granulation_stock_curves',0x538f19d4,0x538f1fd4,'e84b5ea8685293dedad24ed1ccc39587cf7745355284cff55c8c37fdefc81293'),
 ('granulation_original',0x5367ad3c,0x5367b540,'f7bfeb75864fb7935844eb749d3e51f90332d50ef0afb8ba0fb56717541560c3'),
 ('granulation_wait_rng',0x5368a510,0x5368aa24,'8868793c20c1caa93ec5bef8ead59601fe18359a66cf7599c52369e1dfe0d4a9'),
 ('granulation_graph_submit_release',0x5376bba0,0x5376cd48,'1c1aad1a95209c289c1f5f0378f0cf396d719093b25765ed21d3241134d3ffa5'),
)
HOOKS=((0x5367adac,0xe50be650,'granulation_setup_hook'),(0x5367ae14,0xeb003ec4,'granulation_rng_hook'),(0x5367b404,0xeb03c641,'granulation_submit_hook'),(0x5367b410,0xeb003c3e,'granulation_wait_hook'),(0x5367b41c,0xeb03c308,'granulation_release_hook'))
SAVE='push {r0-r12,lr};mrs ip,cpsr;.word 0xeef1ea10;push {ip,lr};.word 0xed2d0b20;.word 0xed6d0b20;'
RESTORE='.word 0xecfd0b20;.word 0xecbd0b20;pop {ip,lr};.word 0xeee1ea10;msr cpsr_f,ip;pop {r0-r12,lr};'
def _asm():
 out=['.syntax unified','.arm','.text','.align 2','.global m10v_isp_effect_granulation_call','.type m10v_isp_effect_granulation_call,%function','m10v_isp_effect_granulation_call:',
 'push {r4,lr};sub sp,sp,#8;ldr r4,[sp,#16];str r4,[sp];ldr r4,[sp,#20];str r4,[sp,#4];bl original_granulation;',
 '.global m10v_isp_effect_granulation_return','.type m10v_isp_effect_granulation_return,%function','m10v_isp_effect_granulation_return:','add sp,sp,#8;pop {r4,pc};', '']
 out += ['.global granulation_setup_hook','.type granulation_setup_hook,%function','granulation_setup_hook:',
  'str lr,[fp,#-0x650];',SAVE,'mov r0,fp;add r1,sp,#264;bl m10v_isp_effect_granulation_setup;',RESTORE,'b original_setup_continue;']
 for name,args,helper,target in [('rng','mov r0,fp;','rng',0x5368a92c),('submit','mov r0,fp;mov r1,r5;','submit',0x5376cd10),('wait','mov r2,fp;','wait',None),('release','mov r1,fp;','release',None)]:
  sym='granulation_'+name+'_hook';out += ['.global '+sym,'.type '+sym+',%function',sym+':',SAVE]
  if name in ('wait','release'):
   out += ['mov r0,fp;bl m10v_isp_effect_granulation_is_owned;cmp r0,#0;bne 2f;',RESTORE+'b original_'+name+';','2:','ldr r0,[sp,#264];ldr r1,[sp,#268];']
  out += [args+'bl m10v_isp_effect_granulation_'+helper+';']
  if name=='rng':out += ['cmp r0,#0;beq 1f;',RESTORE+'bx lr;','1:',RESTORE+'b original_rng;','']
  elif name=='submit':out += [RESTORE+'b original_submit;','']
  else:out += ['str r0,[sp,#264];',RESTORE+'bx lr;']
 return '\n'.join(out)+'\n'
def _compile(base):
 clang,lld=shutil.which('clang'),shutil.which('ld.lld')
 if not clang or not lld:raise RuntimeError('clang and ld.lld required')
 with tempfile.TemporaryDirectory() as td:
  t=Path(td);(t/'hook.S').write_text(_asm());objs=[]
  for n,src in enumerate((ROOT/SOURCES[0],t/'hook.S')):
   obj=t/f'{n}.o';subprocess.run([clang,*guard.FLAGS,'-c',str(src),'-o',str(obj)],check=True,capture_output=True);objs.append(str(obj))
  (t/'link.ld').write_text(f'original_setup_continue = 0x5367adb0; original_granulation = 0x5367ad3c; original_rng = 0x5368a92c; original_submit = 0x5376cd10; original_wait = 0x5368a510; original_release = 0x5376c044; SECTIONS {{ . = {base}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}')
  subprocess.run([lld,'-T',str(t/'link.ld'),'--entry=m10v_isp_effect_granulation_owned',*objs,'-o',str(t/'out')],check=True,capture_output=True)
  b=(t/'out').read_bytes();sh=struct.unpack_from('<I',b,32)[0];size,count,ni=struct.unpack_from('<HHH',b,46);rows=[struct.unpack_from('<10I',b,sh+n*size) for n in range(count)];names=b[rows[ni][4]:rows[ni][4]+rows[ni][5]];image=bytearray();symbols={}
  for r in rows:
   name=names[r[0]:].split(b'\0',1)[0].decode()
   if r[2]&2 and r[5]:
    if r[1]!=1 or r[2]&1 or name not in ('.text','.rodata') or not base<=r[3]<=r[3]+r[5]<=base+65536:raise ValueError('unexpected mutable/unbounded section '+name)
    off=r[3]-base;image.extend(bytes(max(0,off+r[5]-len(image))));image[off:off+r[5]]=b[r[4]:r[4]+r[5]]
   if r[1]==2:
    sr=rows[r[6]];strings=b[sr[4]:sr[4]+sr[5]]
    for off in range(r[4],r[4]+r[5],16):
     n,v,_,info,_,section=struct.unpack_from('<IIIBBH',b,off);s=strings[n:].split(b'\0',1)[0].decode()
     if not section and s:raise ValueError('undefined symbol '+s)
     if info&15==2 and (s.startswith('m10v_isp_effect_granulation_') or s.startswith('granulation_')):symbols[s]=v
 return bytes(image),symbols
def build(base=0x54190000,stock=None,*,enabled=False,camera_model='gr3'):
 if type(enabled)is not bool:raise ValueError('explicit boolean required')
 manifest=dict(schema='m10v-isp-effect-granulation/v1',enabled=False,patches=[],symbols={},code_bytes=0,firmware_emitted=False,camera_tested=False,hardware_completion_proven=False,failure_quiescence_proven=False)
 if not enabled:return b'',manifest
 if camera_model not in guard.MODELS or not isinstance(stock,bytes) or hashlib.sha256(stock).hexdigest()!=guard.MODELS[camera_model]['rtos_sha256']:raise ValueError('exact model-pinned official RTOS required')
 if type(base)is not int or base&15 or not 0x540b6000<=base<=0x54ef0000:raise ValueError('invalid Granulation base')
 spans=[]
 for name,start,end,digest in (*EXTRA_SPANS,*(s for s in guard.ABI_SPANS if s[0] in ('iip_service_control','iip_driver_conditions','native_mutex_wrappers','native_lock_wrappers','native_event_wrappers','native_yield'))):
  if hashlib.sha256(stock[start-guard.RTOS_BASE:end-guard.RTOS_BASE]).hexdigest()!=digest:raise ValueError('native ABI differs: '+name)
  spans.append(dict(name=name,start=start,end=end,sha256=digest))
 for at,expected,_ in HOOKS:
  if struct.unpack_from('<I',stock,at-guard.RTOS_BASE)[0]!=expected:raise ValueError('Granulation hook preimage differs '+hex(at))
 code,symbols=_compile(base)
 patches=[dict(address=a,expected=e,replacement=guard.arm_bl(a,symbols[s]) & (0xfeffffff if s=='granulation_setup_hook' else 0xffffffff),target=symbols[s],symbol=s,role=s) for a,e,s in HOOKS]
 manifest.update(enabled=True,base=base,code_bytes=len(code),code_sha256=hashlib.sha256(code).hexdigest(),symbols=symbols,patches=patches,camera_model=camera_model,original_rtos_sha256=guard.MODELS[camera_model]['rtos_sha256'],verified_abi_spans=spans,mutable_static_bytes=0,pixel_access=False,cpu_rng=False,allocator_calls=0,filesystem_calls=0,preserves=['stock/default: r0-r12 except native result r0, sp/lr/NZCV/VFP','owned luma setup: original frame noise plane/pitch and r7/ip/lr only; all other state preserved'],sources={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},ownership_prerequisite='Caller pins descriptors, context, prepared plane, constant curves and native cache ownership until actual original return; invalid owned operation retains all resources indefinitely.',integration='Merge all five exact-preimage hooks atomically with the call adapter; no stock entry patch.')
 return code,manifest
