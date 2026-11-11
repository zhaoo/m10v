"""Exact GR III2.10 experimental ISP-only session component; no hooks."""
import hashlib,shutil,struct,subprocess,tempfile
from pathlib import Path
from scripts import build_gr3_border_wait_guard as guard
ROOT=Path(__file__).resolve().parents[1]
EXTERNALS=('m10v_isp_effect_granulation_plane','m10v_torn_eligible','m10v_torn_camera_busy','m10v_save_trace_recipe_raw_status')
TRACE_EXTERNAL='m10v_save_trace_recipe_mark'
SOURCES=('native/gr3/m10v_torn_overlay.c','native/gr3/m10v_torn_overlay.h','scripts/build_gr3_torn_overlay.py','native/gr3/m10v_isp_effect_granulation.h','native/gr3/m10v_isp_effect_memory.h')
def _curves():
 identity=list(range(256))
 # Keep dark paper fully open and light backing fully opaque. A short
 # smoothstep softens edge pixels without turning either region translucent.
 dark_paper,white_backing=112,136
 width=white_backing-dark_paper
 denominator=width**3
 mask=[]
 for luma in identity:
  offset=max(0,min(width,luma-dark_paper))
  numerator=255*offset**2*(3*width-2*offset)
  mask.append((numerator+denominator//2)//denominator)
 profiles=((mask,mask,identity),([255]*256,identity,identity),([128]*256,identity,identity))
 return 'static const int16_t torn_curves[3][3][256]={'+','.join('{'+','.join('{'+','.join(map(str,row))+'}' for row in profile)+'}' for profile in profiles)+'};\n'
def build(base=0x54d00000,rtos=None,externals=None,*,enabled=False,camera_model='gr3',debug=False):
 m=dict(schema='m10v-torn-overlay/v1',enabled=False,experimental=True,code_bytes=0,symbols={},patches=[],camera_tested=False,pixel_math_proven=False,firmware_emitted=False)
 if type(enabled)is not bool or type(debug)is not bool:raise ValueError('explicit boolean required')
 if not enabled:return b'',m
 if camera_model!='gr3' or not isinstance(rtos,bytes) or hashlib.sha256(rtos).hexdigest()!=guard.MODELS['gr3']['rtos_sha256']:raise ValueError('GR III2.10 official input required')
 if type(base)is not int or base&15 or not 0x540b6000<=base<0x54ef0000:raise ValueError('invalid append base')
 names=EXTERNALS+((TRACE_EXTERNAL,) if debug else ())
 if not isinstance(externals,dict) or set(externals)!=set(names) or any(type(v)is not int or v&3 or not 0x53000000<=v<0x55000000 for v in externals.values()):raise ValueError('exact native exports required')
 clang,lld=shutil.which('clang'),shutil.which('ld.lld')
 if not clang or not lld:raise RuntimeError('ARM clang/ld.lld required')
 with tempfile.TemporaryDirectory() as td:
  t=Path(td);(t/'m10v_torn_curves.h').write_text(_curves())
  subprocess.run([clang,*guard.FLAGS,f'-DM10V_DEBUG_MODE={int(debug)}','-I',str(t),'-c',str(ROOT/SOURCES[0]),'-o',str(t/'core.o')],check=True,capture_output=True)
  link=' '.join(f'{n} = {v};' for n,v in externals.items())+f'SECTIONS {{ . = {base}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}'
  (t/'core.ld').write_text(link);subprocess.run([lld,'-T',str(t/'core.ld'),'--entry=m10v_torn_init',str(t/'core.o'),'-o',str(t/'core.elf')],check=True,capture_output=True)
  b=(t/'core.elf').read_bytes();sh=struct.unpack_from('<I',b,32)[0];sz,count,ni=struct.unpack_from('<HHH',b,46);rows=[struct.unpack_from('<10I',b,sh+n*sz) for n in range(count)];names=b[rows[ni][4]:rows[ni][4]+rows[ni][5]];image=bytearray();symbols={}
  from scripts.gr3_target_relocations import relocations
  relocations.linked(b)
  for r in rows:
   name=names[r[0]:].split(b'\0',1)[0].decode()
   if r[2]&2 and r[5]:
    if r[1]!=1 or r[2]&1 or name not in ('.text','.rodata') or not base<=r[3]<r[3]+r[5]<=base+65536:raise ValueError('mutable/unbounded section '+name)
    off=r[3]-base;image.extend(bytes(max(0,off+r[5]-len(image))));image[off:off+r[5]]=b[r[4]:r[4]+r[5]]
   if r[1]==2:
    st=rows[r[6]];strings=b[st[4]:st[4]+st[5]]
    for off in range(r[4],r[4]+r[5],16):
     n,v,_,info,_,section=struct.unpack_from('<IIIBBH',b,off);s=strings[n:].split(b'\0',1)[0].decode()
     if not section and s:raise ValueError('undefined '+s)
     if info&15==2 and s.startswith('m10v_torn_') and s not in EXTERNALS:symbols[s]=v
 if any(base<=v<base+len(image) for v in externals.values()):raise ValueError('external overlaps image')
 m.update(enabled=True,base=base,code_bytes=len(image),symbols=symbols,externals=externals,code_sha256=hashlib.sha256(image).hexdigest(),sources={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},mutable_static_bytes=0,cpu_pixel_access=False,cpu_rng=False,allocation='start only; max6144*4096+63, exact native token',owner_offset=0x6d00,owner_bytes=0x6e00,shot_offset=0x57d8,shot_bytes=32,recipe_bytes=0x57f8,format='YC422 only',native_passes=[1,2],curves_sha256=hashlib.sha256(_curves().encode()).hexdigest(),hardware_output_unverified=True)
 m['diagnostics']=debug
 return bytes(image),m
