"""Fit the additional film display targets offline. Error is against targets, not film."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def native_header(ref):
 from scripts.fit_gr3_d76_native import native_header as full_header
 return full_header(ref).replace('native_d76','native_extra_films').replace('[7]','[3]').replace('live approximation, never still completion','quantized native ISP; no CPU color LUT')
def generate():
 import numpy as np
 from scripts.fit_gr3_native_film_targets import fit,quantize,render_quantized,fit_gate
 from scripts.build_gr3_harman_reference import sample_tetrahedral
 from scripts.analyze_gr3_film_color_targets import metrics
 from scripts.verify_gr3_anime_e6_reference import verify_profile
 ref=json.loads((ROOT/'native/gr3/extra-films-reference.json').read_text());web=json.loads((ROOT/'web/gr3/extra-films-luts.json').read_text())
 base=np.array(json.loads((ROOT/'native/gr3/native-film-fit-targets.json').read_text())['base_gamma_q14'])/16384
 grey=np.repeat(np.linspace(0,1,256)[:,None],3,axis=1)
 train=np.vstack([np.random.default_rng(314316).uniform(0,1,(4096,3)),grey,grey,grey]);hold=np.random.default_rng(20261028316).uniform(0,1,(32768,3))
 grid=np.stack(np.meshgrid(*[np.linspace(0,1,15)]*3,indexing='ij'),axis=-1).reshape(-1,3);profiles=[]
 for stock,spec in zip(web['stocks'],ref['stocks']):
  table=np.array(stock['values']).reshape(15,15,15,3)/255
  params,opt=fit(train,sample_tetrahedral(table,train),base,iterations=5000 if stock['id']==315 else 1000,constrain_native=True,monochrome=stock['id'] in (314,315));q=quantize(params)
  if stock['id'] in (314,315):
   from scripts.fit_gr3_native_film_targets import STD_CSP
   post=np.repeat(np.rint(np.mean(q['post_q9'],axis=0)).astype(int)[None,:],3,axis=0)
   native=(STD_CSP.astype(int)@post+256)//512
   q.update(post_q9=post.tolist(),native_csp_signed9=native.tolist(),effective_relative_post=(np.linalg.inv(STD_CSP)@native).tolist())
  score=metrics(sample_tetrahedral(table,hold),render_quantized(q,hold,base))
  q.update(film_id=stock['id'],holdout=score,optimization=opt,gate=fit_gate(score,False));verify_profile(q);profiles.append(q)
  stock['native_values']=np.rint(render_quantized(q,grid,base)*255).astype('uint8').reshape(-1).tolist();spec['native_preview_sha256']=hashlib.sha256(bytes(stock['native_values'])).hexdigest();print(stock['id'],json.dumps(score),flush=True)
 ref.update(native_profiles_full=profiles,fitting_validation=dict(train_seed=314316,holdout_seed=20261028316,holdout_count=32768,iterations_limit=1000,double_x_iterations_limit=5000,metric='CIEDE2000, display sRGB, not physical film',camera_validated=False))
 (ROOT/'web/gr3/extra-films-luts.json').write_text(json.dumps(web,separators=(',',':'))+'\n')
 for p in ['scripts/fit_gr3_extra_films_native.py','scripts/fit_gr3_native_film_targets.py','scripts/verify_gr3_extra_films_reference.py','web/gr3/extra-films-luts.json']:ref['files'][p]=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
 (ROOT/'native/gr3/extra-films-reference.json').write_text(json.dumps(ref,indent=2)+'\n');(ROOT/'native/gr3/m10v_extra_films_native_profiles.h').write_text(native_header(ref))
if __name__=='__main__':generate()
