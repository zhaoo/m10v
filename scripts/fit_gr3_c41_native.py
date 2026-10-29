"""Fit the C41 display targets offline. Error is against targets, not film."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def native_header(ref):
 from scripts.fit_gr3_anime_e6_native import native_header as packed_header
 return packed_header(ref).replace('native_anime_e6','native_c41').replace('[6]','[2]')
def generate():
 import numpy as np
 from scripts.fit_gr3_native_film_targets import fit,quantize,render_quantized,fit_gate
 from scripts.build_gr3_harman_reference import sample_tetrahedral
 from scripts.analyze_gr3_film_color_targets import metrics
 from scripts.verify_gr3_anime_e6_reference import verify_profile
 ref=json.loads((ROOT/'native/gr3/c41-reference.json').read_text());web=json.loads((ROOT/'web/gr3/c41-luts.json').read_text())
 base=np.array(json.loads((ROOT/'native/gr3/native-film-fit-targets.json').read_text())['base_gamma_q14'])/16384
 grey=np.repeat(np.linspace(0,1,256)[:,None],3,axis=1)
 train=np.vstack([np.random.default_rng(312313).uniform(0,1,(4096,3)),grey,grey,grey]);hold=np.random.default_rng(20261028313).uniform(0,1,(32768,3))
 grid=np.stack(np.meshgrid(*[np.linspace(0,1,15)]*3,indexing='ij'),axis=-1).reshape(-1,3);profiles=[]
 for stock,spec in zip(web['stocks'],ref['stocks']):
  table=np.array(stock['values']).reshape(15,15,15,3)/255
  params,opt=fit(train,sample_tetrahedral(table,train),base,iterations=600);q=quantize(params)
  score=metrics(sample_tetrahedral(table,hold),render_quantized(q,hold,base))
  q.update(film_id=stock['id'],holdout=score,optimization=opt,gate=fit_gate(score,False));verify_profile(q);profiles.append(q)
  stock['native_values']=np.rint(render_quantized(q,grid,base)*255).astype('uint8').reshape(-1).tolist();spec['native_preview_sha256']=hashlib.sha256(bytes(stock['native_values'])).hexdigest();print(stock['id'],json.dumps(score),flush=True)
 ref.update(native_profiles_full=profiles,fitting_validation=dict(train_seed=312313,holdout_seed=20261028313,holdout_count=32768,iterations_limit=600,metric='CIEDE2000, display sRGB, not physical film',camera_validated=False))
 (ROOT/'web/gr3/c41-luts.json').write_text(json.dumps(web,separators=(',',':'))+'\n')
 for p in ['scripts/fit_gr3_c41_native.py','scripts/verify_gr3_c41_reference.py','web/gr3/c41-luts.json']:ref['files'][p]=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
 (ROOT/'native/gr3/c41-reference.json').write_text(json.dumps(ref,indent=2)+'\n');(ROOT/'native/gr3/m10v_c41_native_profiles.h').write_text(native_header(ref))
if __name__=='__main__':generate()
