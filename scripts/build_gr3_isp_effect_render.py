"""Compile metadata-only experimental native ISP renderer; never emit firmware.

bindings={'grain': {base,bytes,width,height,stride}, 'leaks': [[cb,cr], ...9], 'leaks_vertical': [[cb,cr], ...9]}.
Nine leak pairs follow position(left/right/both), then spread(narrow/medium/wide).
externals binds transfer_plan_format, transfer_execute and granulation_owned.
"""
import hashlib,shutil,struct,subprocess,tempfile
from pathlib import Path
from scripts import build_gr3_border_wait_guard as guard
ROOT=Path(__file__).resolve().parents[1]
SOURCES=('native/gr3/m10v_isp_effects_render.c','native/gr3/m10v_isp_effects_render.h','scripts/build_gr3_isp_effect_render.py','native/gr3/m10v_isp_effect_transfer.h','native/gr3/m10v_isp_effect_transfer_runtime.h','native/gr3/m10v_isp_effects_shot.h','native/gr3/m10v_isp_effects_state.h','native/gr3/m10v_isp_effect_granulation.h','native/gr3/m10v_isp_effect_memory.h')
EXTERNALS=('m10v_isp_effect_transfer_plan_format','m10v_isp_effect_transfer_execute','m10v_isp_effect_granulation_owned','m10v_isp_effect_granulation_luma')
FIELDS=('base','bytes','width','height','stride')
def _texture(t):
 if not isinstance(t,dict) or set(t)!=set(FIELDS) or any(type(t[k])is not int for k in FIELDS):raise ValueError('exact five-field texture descriptor required')
 a,n,w,h,s=(t[k] for k in FIELDS)
 if a<0x540b6000 or a&63 or a>=0x55000000 or n>0x55000000-a or w<2 or h<2 or w>3072 or h>2048 or (w|h)&1 or s<w or s>3072 or s&63 or n!=s*h*3//2:raise ValueError('invalid bounded immutable NV12 binding')
 return dict(t)
def _validated(base,bindings,externals):
 if type(base)is not int or base&15 or not 0x540b6000<=base<=0x54ef0000:raise ValueError('invalid renderer code base')
 if not isinstance(bindings,dict) or set(bindings)!=set(('grain','leaks','leaks_vertical')) or not isinstance(bindings['leaks'],(list,tuple)) or len(bindings['leaks'])!=9 or not isinstance(bindings['leaks_vertical'],(list,tuple)) or len(bindings['leaks_vertical'])!=9:raise ValueError('one grain and nine leak pairs required')
 g=_texture(bindings['grain']);pairs=[]
 if g['width']<3000 or g['height']<2000:raise ValueError('grain binding must cover largest crop')
 for pair in bindings['leaks']:
  if not isinstance(pair,(list,tuple)) or len(pair)!=2:raise ValueError('Cb/Cr field pair required')
  p=[_texture(t) for t in pair]
  if [(t['width'],t['height'],t['stride']) for t in p][0]!=[(t['width'],t['height'],t['stride']) for t in p][1]:raise ValueError('paired field geometry differs')
  pairs.append(p)
 vertical=[]
 for pair in bindings['leaks_vertical']:
  if not isinstance(pair,(list,tuple)) or len(pair)!=2:raise ValueError('vertical Cb/Cr field pair required')
  vertical.append([_texture(t) for t in pair])
 if len(vertical)!=9:raise ValueError('nine vertical field pairs required')
 for horizontal,v in zip(pairs,vertical):
  for h,t in zip(horizontal,v):
   if (t['width'],t['height'])!=(h['height'],h['width']):raise ValueError('vertical field geometry must transpose horizontal dimensions')
 all_t=[g]+[t for p in pairs+vertical for t in p]
 for i,t in enumerate(all_t):
  for q in all_t[:i]:
   if t['base']<q['base']+q['bytes'] and q['base']<t['base']+t['bytes']:raise ValueError('overlapping immutable texture bindings')
 if not isinstance(externals,dict) or set(externals)!=set(EXTERNALS) or any(type(v)is not int or v&3 or not 0x540b6000<=v<0x55000000 for v in externals.values()) or len(set(externals.values()))!=4:raise ValueError('four distinct bound native exports required')
 if any(t['base']<=a<t['base']+t['bytes'] for a in externals.values() for t in all_t):raise ValueError('native export points into immutable texture bytes')
 return {'grain':g,'leaks':pairs,'leaks_vertical':vertical},dict(externals)
def leak_curves():
 """A/C = upper endpoint, E/F = lower endpoint, B/D = weight curve.
 Under the polarity hypothesis below, r14 selects the effect at zero spatial
 weight, predicting global lift and modification of the unselected UV byte.
 Zero spatial weight must instead select identity. Polarity follows stock
 upper/lower ordering and the r14
 device symptom; exact native scalar math still needs camera acceptance.
 No camera CPU evaluates these immutable tables.
 """
 profiles=[];a=list(range(256))
 for gain in (2,5,8):
  for channel in range(3):
   if channel==0:
    b=[min(255,n+round((255-n)*(.299*256+.587*112+.114*36)*255/65536*gain/8)) for n in a]
   else:
    delta=round((-62 if channel==1 else 78)*gain/8)
    b=[max(0,min(255,n+delta)) for n in a]
   profiles.append((b,a,a))
 # Source is the spatial mask, noise input is original photo luma.
 # Select between mask and zero to obtain mask*(1-luma), on the ISP.
 profiles.append(([0]*256,a,a))
 return profiles
def _header(bindings):
 def row(t):return '{'+','.join(str(t[k])+'u' for k in FIELDS)+'}'
 out=['static const m10v_isp_effect_texture m10v_render_grain='+row(bindings['grain'])+';', 'static const m10v_isp_effect_texture m10v_render_leaks[9][2]={'+','.join('{'+','.join(row(t) for t in p)+'}' for p in bindings['leaks'])+'};']
 profiles=[]
 for curve in leak_curves():
  profiles.append('{'+','.join('{'+','.join(map(str,v))+'}' for v in curve)+'}')
 out.append('static const m10v_isp_effect_texture m10v_render_leaks_vertical[9][2]={'+','.join('{'+','.join(row(t) for t in p)+'}' for p in bindings['leaks_vertical'])+'};')
 out.append('static const int16_t m10v_render_curves[10][3][256]={'+','.join(profiles)+'};')
 return '\n'.join(out)+'\n'
def _compile(base,bindings,externals):
 bindings,externals=_validated(base,bindings,externals)
 clang,lld=shutil.which('clang'),shutil.which('ld.lld')
 if not clang or not lld:raise RuntimeError('clang and ld.lld required')
 with tempfile.TemporaryDirectory() as td:
  t=Path(td);(t/'m10v_isp_effect_render_bindings.h').write_text(_header(bindings))
  subprocess.run([clang,*guard.FLAGS,'-I',str(t),'-c',str(ROOT/SOURCES[0]),'-o',str(t/'render.o')],check=True,capture_output=True)
  link=' '.join(f'{n} = {a};' for n,a in externals.items())+f'SECTIONS {{ . = {base}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}'
  (t/'render.ld').write_text(link)
  subprocess.run([lld,'-T',str(t/'render.ld'),'--entry=m10v_isp_effects_render',str(t/'render.o'),'-o',str(t/'render.elf')],check=True,capture_output=True)
  b=(t/'render.elf').read_bytes();sh=struct.unpack_from('<I',b,32)[0];size,count,ni=struct.unpack_from('<HHH',b,46);rows=[struct.unpack_from('<10I',b,sh+n*size) for n in range(count)];names=b[rows[ni][4]:rows[ni][4]+rows[ni][5]];image=bytearray();symbols={}
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
     if (info&15==2 and s=='m10v_isp_effects_render') or s in ('m10v_render_grain','m10v_render_leaks','m10v_render_leaks_vertical','m10v_render_curves'):symbols[s]=v
  for d in [bindings['grain']]+[v for pair in bindings['leaks']+bindings['leaks_vertical'] for v in pair]:
   if base<d['base']+d['bytes'] and d['base']<base+len(image):raise ValueError('renderer overlaps immutable texture bytes')
  if any(base<=a<base+len(image) for a in externals.values()):raise ValueError('renderer overlaps bound native export')
  if set(symbols)!=set(('m10v_isp_effects_render','m10v_render_grain','m10v_render_leaks','m10v_render_leaks_vertical','m10v_render_curves')):raise ValueError('renderer symbols differ')
 return bytes(image),symbols
def build(base=0x54e00000,bindings=None,externals=None,*,enabled=False):
 if type(enabled)is not bool:raise ValueError('explicit renderer boolean required')
 m=dict(schema='m10v-isp-effect-render/v1',enabled=False,code_bytes=0,symbols={},patches=[],firmware_emitted=False,camera_tested=False,pixel_math_proven=False)
 if not enabled:return b'',m
 bindings,externals=_validated(base,bindings,externals);code,symbols=_compile(base,bindings,externals)
 m.update(enabled=True,base=base,code_bytes=len(code),code_sha256=hashlib.sha256(code).hexdigest(),symbols=symbols,bindings=bindings,externals=externals,generated_header_sha256=hashlib.sha256(_header(bindings).encode()).hexdigest(),sources={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},mutable_static_bytes=0,allocator_calls=0,cpu_pixel_access=False,cpu_rng=False,required_cache_maintenance={'entry':0x5383c8a8,'operation':'clean_invalidate','span':'complete destination workspace before every prepared=1 ISP enqueue','abi_pin':'enclosing border runtime cache_backend span','physical_cache_proven':False},grain_strength_arguments={'weak':3,'medium':2,'strong':1},execution_order=['native Clarity by caller','original luma gates Cb mask','leak Cb','original luma gates Cr mask','leak Cr','leak Y','stock grain'],saved_orientation={'1':'horizontal selected edge','3':'horizontal opposite edge','8':'vertical selected edge (top=left)','6':'vertical opposite edge'},cpu_frame_rotation=False,roi_views='owned descriptor snapshot shifts Y by top*stride+left and UV by format-correct top; complete stride*height cache spans must fit original allocations; pixels and input descriptors untouched',curve_profiles=10,curve_coefficients=10*3*256,leak_fit='pinned historical spatial field; source-dependent luma exposure and luma-gated chroma; separable BT.601 approximation, native scalar arithmetic pending camera acceptance',workspace='align16(width)*height*2 for 422 leak; *3/2 for NV12 leak or grain',acceptance_required='Real camera output, native scalar arithmetic and visual appearance remain unproven; strict native failures return output invalid with no CPU fallback.')
 m['curve_endpoint_bindings']={'effect':'A/C: graph+5c/+64','identity':'E/F: graph+6c/+70','weight':'B/D: graph+60/+68'}
 m['polarity_evidence']='stock bound ordering and r14 whole-frame whitening; native endpoint output remains unmeasured'
 return code,m
