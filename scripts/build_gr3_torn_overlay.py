"""Exact GR III2.10 experimental ISP-only session component; no hooks."""
import hashlib,math,shutil,struct,subprocess,tempfile
from functools import lru_cache
from pathlib import Path
from scripts import build_gr3_border_wait_guard as guard
ROOT=Path(__file__).resolve().parents[1]
EXTERNALS=('m10v_isp_effect_granulation_plane','m10v_torn_eligible','m10v_torn_camera_busy','m10v_save_trace_recipe_raw_status',
           'm10v_isp_effect_transfer_plan_format','m10v_isp_effect_transfer_execute')
TRACE_EXTERNAL='m10v_save_trace_recipe_mark'
SOURCES=('native/gr3/m10v_torn_overlay.c','native/gr3/m10v_torn_overlay.h','scripts/build_gr3_torn_overlay.py','native/gr3/m10v_isp_effect_granulation.h','native/gr3/m10v_isp_effect_memory.h')
def _curves():
 identity=list(range(256))
 edge=[max(0,min(255,((luma-124)*255+4)//8)) for luma in identity]
 profiles=((edge,edge,identity),([255]*256,identity,identity),([128]*256,identity,identity))
 return 'static const int16_t torn_curves[3][3][256]={'+','.join('{'+','.join('{'+','.join(map(str,row))+'}' for row in profile)+'}' for profile in profiles)+'};\n'

MASK_WIDTH,MASK_HEIGHT=64,80
# Jagged paper fragments in normalized frame coordinates. Gaps are painted
# white by the blend; the polygons preserve the underlying scene.
MASK_SHAPES=(
 (((8,19),(14,16),(15,13),(27,10),(29,12),(36,9),(35,21),(38,26),(34,31),(35,38),(28,36),(24,40),(17,37),(14,39),(11,32)),
  ((40,13),(45,15),(53,13),(54,19),(57,21),(55,30),(58,35),(49,39),(44,35),(38,38),(42,29),(39,24)),
  ((13,45),(23,43),(25,46),(35,42),(39,47),(47,43),(55,47),(51,54),(54,60),(46,64),(44,70),(35,67),(31,71),(22,65),(17,67),(15,58),(10,52))),
 (((13,11),(20,14),(23,10),(30,12),(36,10),(41,15),(48,15),(53,20),(48,24),(50,30),(44,30),(39,35),(33,31),(26,35),(22,31),(15,33),(15,27),(9,23)),
  ((9,38),(20,37),(24,40),(29,37),(35,40),(32,47),(35,53),(31,61),(24,64),(23,69),(15,67),(16,59),(11,56),(12,49),(7,46)),
  ((40,40),(46,36),(52,37),(54,43),(59,47),(55,52),(56,58),(51,62),(49,69),(42,67),(39,71),(30,69),(37,61),(36,54),(40,49))),
 (((12,18),(17,15),(19,10),(29,11),(31,15),(39,13),(47,17),(51,16),(52,23),(47,26),(49,31),(41,33),(36,31),(33,36),(25,35),(24,30),(16,31),(12,26)),
  ((10,35),(16,34),(23,38),(31,38),(35,43),(33,47),(38,53),(34,58),(28,58),(24,64),(16,62),(17,55),(10,51),(12,46),(8,41)),
  ((42,37),(50,35),(55,39),(56,46),(53,51),(57,56),(53,61),(49,60),(44,67),(39,65),(34,71),(28,68),(31,63),(38,60),(42,53),(38,47))),
)

@lru_cache(maxsize=1)
def _mask_blob():
 def distance_to_polygon(x,y,edges):
  crossings=0
  distance_squared=math.inf
  for (ax,ay),(bx,by) in edges:
   if (ay>y)!=(by>y) and x<ax+(bx-ax)*(y-ay)/(by-ay):
    crossings+=1
   dx,dy=bx-ax,by-ay
   t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy)))
   distance_squared=min(distance_squared,(x-ax-t*dx)**2+(y-ay-t*dy)**2)
  return math.sqrt(distance_squared)*(-1 if crossings%2 else 1)
 def rasterize(shape):
  fragments=[tuple(zip(polygon,polygon[1:]+polygon[:1])) for polygon in shape]
  # Preserve subpixel geometry during native interpolation. The zero crossing
  # at 127.5 is restored to a narrow alpha edge after the upscale.
  return bytes(max(0,min(255,round(127.5+102*min(
      distance_to_polygon(x+.5,y+.5,edges) for edges in fragments))))
      for y in range(MASK_HEIGHT) for x in range(MASK_WIDTH))
 return b''.join(
  rasterize(shape)+bytes([128])*(MASK_WIDTH*MASK_HEIGHT//2)
  for shape in MASK_SHAPES)
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
  t=Path(td)
  masks=_mask_blob()
  (t/'m10v_torn_curves.h').write_text(_curves()+
      f'#define TORN_MASK_WIDTH {MASK_WIDTH}u\n#define TORN_MASK_HEIGHT {MASK_HEIGHT}u\n#define TORN_MASK_COUNT {len(MASK_SHAPES)}u\n')
  (t/'masks.bin').write_bytes(masks)
  (t/'masks.S').write_text('.section .rodata.torn_masks,"a",%progbits\n.balign 64\n.global torn_masks\n.type torn_masks,%object\ntorn_masks:\n.incbin "masks.bin"\n')
  subprocess.run([clang,*guard.FLAGS,'-c','masks.S','-o','masks.o'],cwd=t,check=True,capture_output=True)
  subprocess.run([clang,*guard.FLAGS,f'-DM10V_DEBUG_MODE={int(debug)}','-I',str(t),'-c',str(ROOT/SOURCES[0]),'-o',str(t/'core.o')],check=True,capture_output=True)
  link=' '.join(f'{n} = {v};' for n,v in externals.items())+f'SECTIONS {{ . = {base}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}'
  (t/'core.ld').write_text(link);subprocess.run([lld,'-T',str(t/'core.ld'),'--entry=m10v_torn_init',str(t/'core.o'),str(t/'masks.o'),'-o',str(t/'core.elf')],check=True,capture_output=True)
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
 mask_offset=image.find(masks)
 if mask_offset<0 or (base+mask_offset)&63:
  raise ValueError('torn mask asset readback differs')
 m.update(capture_mode='single',native_passes=[1,3],
          masks=dict(base=base+mask_offset,bytes=len(masks),count=len(MASK_SHAPES),
                     width=MASK_WIDTH,height=MASK_HEIGHT,sha256=hashlib.sha256(masks).hexdigest()),
          allocation='enable only; NV12 workspace plus alignment slack')
 return bytes(image),m
