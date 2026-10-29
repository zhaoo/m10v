"""Offline fit of six display targets to quantized camera ISP parameters.

Never applies a CPU LUT on camera. Holdout errors measure this mathematical
model against authored/community targets, not physical stock fidelity.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def packed_frames(manifest):
 """Lossless original 256 knots, existing native_frame_packed wire shape."""
 from scripts.build_gr3_isp_native_look import encode_curve_deltas,decode_curve_deltas
 stream=bytearray();frames=[]
 for q in [q for q in manifest['native_profiles_full'] if q['film_id']>=309]:
  offsets=[]
  for curve in q['curves']:
   if len(curve)!=256 or any(type(v)is not int or not 0<=v<=16383 for v in curve):raise ValueError('curve shape/range')
   delta=[b-a for a,b in zip(curve,curve[1:])]
   if any(not 0<=v<=255 for v in delta):raise ValueError('lossless curve delta overflow')
   packed=encode_curve_deltas(delta)
   if decode_curve_deltas(packed)!=delta:raise ValueError('lossless delta roundtrip')
   offsets.append(len(stream));stream.extend(packed)
  frames.append(dict(matrix=[v for row in q['matrix_q13'] for v in row],post=[v for row in q['post_q9'] for v in row],first=[c[0] for c in q['curves']],offset=offsets))
 if len(stream)>65535:raise ValueError('curve stream offset overflow')
 return frames,bytes(stream)

def native_header(manifest):
 arr=lambda x:'{'+','.join(map(str,x))+'}'
 packed,stream=packed_frames(manifest)
 frames=['{'+','.join(arr(q[key]) for key in ['matrix','post','first','offset'])+'}' for q in packed]
 hues=[arr([v for sector in q['hue_q10'] for row in sector for v in row]) for q in manifest['native_profiles_full'] if q['film_id']>=309]
 return '/* Generated LOSSLESS native_frame_packed profiles; camera validation pending. Uses existing native_frame_packed typedef. */\nstatic const native_frame_packed native_anime_e6_frame['+str(len(packed))+']={'+','.join(frames)+'};\nstatic const uint8_t native_anime_e6_curve_stream['+str(len(stream))+']='+arr(stream)+';\nstatic const int16_t native_anime_e6_hue['+str(len(packed))+'][108]={'+','.join(hues)+'};\n'
def polish_quantization(q,train,target,base):
 """Train-only deterministic integer coordinate search; never uses holdout."""
 import copy
 import numpy as np
 from scripts.fit_gr3_native_film_targets import STD_CCA,STD_CSP,render_quantized
 from scripts.analyze_gr3_film_color_targets import delta_e
 from scripts.verify_gr3_anime_e6_reference import verify_profile
 def update(v):
  m=np.array(v['matrix_q13']);p=np.array(v['post_q9']);nm=(m@STD_CCA+4096)//8192;npst=(STD_CSP.astype(int)@p+256)//512
  v.update(native_cca_signed12=nm.tolist(),native_csp_signed9=npst.tolist(),effective_relative_matrix=(nm@np.linalg.inv(STD_CCA)).tolist(),effective_relative_post=(np.linalg.inv(STD_CSP)@npst).tolist())
 def score(v):
  de=delta_e(target,render_quantized(v,train,base));return float(np.median(de)*.8+np.mean(de)*.2)
 best=score(q);initial=best
 for sweep in range(8):
  changed=False
  for key,steps in [('post_q9',[-3,-2,-1,1,2,3]),('matrix_q13',[-32,-16,-1,1,16,32])]:
   for r in range(3):
    for c in range(3):
     candidates=[]
     for step in steps:
      v=copy.deepcopy(q);v[key][r][c]+=step;update(v)
      try:verify_profile(v)
      except ValueError:continue
      candidates.append((score(v),v))
     if not candidates:continue
     value,chosen=min(candidates,key=lambda x:x[0])
     if value<best-1e-8:best,q=value,chosen;changed=True
  if not changed:break
 return q,dict(objective='0.8 train median + 0.2 train mean CIEDE2000',initial=initial,final=best,sweeps=sweep+1,maximum_sweeps=8,uses_holdout=False)

def write_native_preview(manifest,web,base):
 import numpy as np
 from scripts.fit_gr3_native_film_targets import render_quantized
 grid=np.stack(np.meshgrid(*[np.linspace(0,1,15)]*3,indexing='ij'),axis=-1).reshape(-1,3)
 for stock,q,spec in zip(web['stocks'],manifest['native_profiles_full'],manifest['stocks']):
  values=np.rint(render_quantized(q,grid,base)*255).astype('uint8').reshape(-1).tolist()
  stock['native_values']=values
  stock['default_preview']='native_values; quantized ISP model approximation'
  spec['native_preview_sha256']=hashlib.sha256(bytes(values)).hexdigest()
 (ROOT/'web/gr3/anime-e6-luts.json').write_text(json.dumps(web,separators=(',',':'))+'\n')

def generate(iterations=600):
 import numpy as np
 from scripts.fit_gr3_native_film_targets import fit,quantize,render_quantized,fit_gate
 from scripts.analyze_gr3_film_color_targets import metrics
 from scripts.build_gr3_harman_reference import sample_tetrahedral
 from scripts.verify_gr3_anime_e6_reference import verify_profile
 manifest=json.loads((ROOT/'native/gr3/anime-e6-reference.json').read_text());web=json.loads((ROOT/'web/gr3/anime-e6-luts.json').read_text())
 base=np.array(json.loads((ROOT/'native/gr3/native-film-fit-targets.json').read_text())['base_gamma_q14'])/16384
 grey=np.repeat(np.linspace(0,1,256)[:,None],3,axis=1)
 train=np.vstack([np.random.default_rng(306311).uniform(0,1,(4096,3)),grey,grey,grey]);hold=np.random.default_rng(20261027311).uniform(0,1,(32768,3))
 extremes=np.array([[r,g,b] for r in [0,1] for g in [0,1] for b in [0,1]])
 profiles=[]
 for stock in web['stocks']:
  table=np.array(stock['values']).reshape(15,15,15,3)/255
  params,opt=fit(train,sample_tetrahedral(table,train),base,iterations=max(iterations,1400) if stock['id']==309 else iterations);q=quantize(params)
  if stock['id']==309:
   q,polish=polish_quantization(q,train[:4096],sample_tetrahedral(table,train[:4096]),base);opt['quantization_polish']=polish
  score=metrics(sample_tetrahedral(table,hold),render_quantized(q,hold,base))
  q.update(film_id=stock['id'],holdout=score,optimization=opt,grey=metrics(sample_tetrahedral(table,grey),render_quantized(q,grey,base)),extremes=metrics(sample_tetrahedral(table,extremes),render_quantized(q,extremes,base)),role='default still and preview native ISP approximation; no CPU color LUT',gate=fit_gate(score,False))
  verify_profile(q);profiles.append(q);print(stock['id'],json.dumps(score),flush=True)
 manifest.update(native_profiles_full=profiles,fitting_validation=dict(train_random=4096,train_seed=306311,grey_repetitions=3,holdout_count=32768,holdout_seed=20261027311,iterations_limit=iterations,provia_iterations_limit=max(iterations,1400),metric='CIEDE2000 in display sRGB D65; against 15cube target, not film',base_gamma_source='native/gr3/native-film-fit-targets.json',camera_validated=False))
 write_native_preview(manifest,web,base)
 for path in ['scripts/fit_gr3_anime_e6_native.py','scripts/verify_gr3_anime_e6_reference.py','scripts/fit_gr3_native_film_targets.py','native/gr3/native-film-fit-targets.json','web/gr3/anime-e6-luts.json']:
  manifest['files'][path]=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
 (ROOT/'native/gr3/anime-e6-reference.json').write_text(json.dumps(manifest,indent=2)+'\n');(ROOT/'native/gr3/m10v_anime_e6_native_profiles.h').write_text(native_header(manifest))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--iterations',type=int,default=600);args=parser.parse_args();generate(args.iterations)
