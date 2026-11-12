"""Exact GR III2.10 experimental ISP-only session component; no hooks."""
import hashlib,random,shutil,struct,subprocess,tempfile
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
 # Leave a narrow, opaque white paper lip inside the geometric edge.
 edge=[max(0,min(255,((luma-116)*255+4)//8)) for luma in identity]
 # Keep the white lip, then darken the contact shadow and shade the paper
 # backing. The last part of the field carries subtle variation in the gap.
 shadow=[max(0,min(144,(luma-131)*16,(173-luma)*6),
             min(76,max(0,(luma-148)*3//2),56+max(0,luma-214)//2))
         for luma in identity]
 profiles=((edge,edge,identity),([255]*256,identity,identity),([128]*256,identity,identity),
           (shadow,shadow,identity),([205]*256,identity,identity))
 return 'static const int16_t torn_curves[5][3][256]={'+','.join('{'+','.join('{'+','.join(map(str,row))+'}' for row in profile)+'}' for profile in profiles)+'};\n'

# Preserve the existing ROM budget and the native Resize stride alignment.
MASK_WIDTH, MASK_HEIGHT = 64, 80
# Each layout shares one fracture between the two sides. The first follows
# the larger turns in the approved desktop JPG.
CENTER_TURNS = (
    (0, -17, 14, -11, -26, 27, 44, 18, -31, -44, 7, 31, 11, -18, 0),
    (-20, 21, 35, 13, -30, -42, -16, 30, 49, 12, -28, -20, 24, 33, 10),
    (17, 34, -7, -33, -14, 32, 47, 4, -39, -25, 18, 38, 11, -29, -14),
)


def _interpolate(knots, position):
    index = min(int(position), len(knots) - 2)
    fraction = position - index
    return knots[index] * (1 - fraction) + knots[index + 1] * fraction


@lru_cache(maxsize=1)
def _mask_blob():
    masks = []
    for variant, turns in enumerate(CENTER_TURNS):
        rng = random.Random(801 + variant)
        noise = [
            (spacing, [rng.uniform(-amplitude, amplitude)
                       for _ in range(MASK_HEIGHT // spacing + 2)])
            for spacing, amplitude in ((11, .68), (4, .43), (1, .24))
        ]
        luma = bytearray()
        for y in range(MASK_HEIGHT):
            t = y / (MASK_HEIGHT - 1)
            tear = MASK_WIDTH * .49 + _interpolate(turns, t * (len(turns) - 1)) * .064
            tear += sum(_interpolate(knots, y / spacing) for spacing, knots in noise)
            # Independent fraying on each lip, around the same main fracture.
            left = tear - 2.35 - rng.uniform(-.55, .55)
            right = tear + 2.35 + rng.uniform(-.55, .55)
            left_slope = rng.uniform(43, 57)
            right_slope = rng.uniform(61, 77)
            for x in range(MASK_WIDTH):
                distance = min((x + .5 - left) * left_slope,
                               (right - x - .5) * right_slope)
                backing = rng.randint(214, 255)
                luma.append(round(max(0, min(backing, 127.5 + distance))))
        masks.append(luma + bytes([128]) * (MASK_WIDTH * MASK_HEIGHT // 2))
    return b''.join(masks)


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
      f'#define TORN_MASK_WIDTH {MASK_WIDTH}u\n#define TORN_MASK_HEIGHT {MASK_HEIGHT}u\n#define TORN_MASK_COUNT {len(CENTER_TURNS)}u\n')
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
 m.update(capture_mode='single',layout='center-tear',native_passes=[2,5],
          masks=dict(base=base+mask_offset,bytes=len(masks),count=len(CENTER_TURNS),
                     width=MASK_WIDTH,height=MASK_HEIGHT,sha256=hashlib.sha256(masks).hexdigest()),
          allocation='enable only; NV12 workspace plus alignment slack')
 return bytes(image),m
