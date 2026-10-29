"""Offline full native color fit; never installs firmware or disables CPU effects.

Geometry follows gr3-film-mods FINDINGS 30b/33b camera experiments and the
quadrant-ratio description in gr-custom-tool gr4_editor/numeric/model.py.
This implementation uses independent analytic joint optimization. Its inverse
Standard is an explicit model-domain inverse, not recovered JPEG scene radiance.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,struct,sys
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/m10v-native-fit-mpl')
import numpy as np
from scipy.linalg import null_space
from scipy.optimize import minimize,isotonic_regression
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BOUNDS=np.array([[1298,750,0,0],[1448,843,0,0],[1298,750,0,0],[1205,843,0,0]])
SELECT=np.array([[0,1,2,2,2],[3,4,5,5,5],[6,7,8,8,8],[9,10,11,11,11]])
YCC=np.array([[77,150,29],[-43,-85,128],[128,-107,-21]],float)/256
# Default Standard fixture values from original writer; actual per-frame application
# must validate its own CCA/CSP composition rather than treating these as global.
STD_CCA=np.array([[436,-184,4],[-48,400,-96],[1,-104,359]])
STD_CSP=YCC*256
AXIS=np.linspace(0,1,256);KNOTS=33;KA=np.linspace(0,1,KNOTS)
def groups(rgb):
 c=np.asarray(rgb)@YCC.T;b,r=c[:,1],c[:,2]
 quadrant=(np.floor((np.degrees(np.arctan2(r,b))%360)/90).astype(int))
 a=np.where(quadrant%2==0,np.abs(b),np.abs(r));d=np.abs(b)+np.abs(r)
 ratio=np.divide(2048*a,d,out=np.full_like(a,2048),where=d>1e-14)
 slot=np.sum(ratio[:,None]<BOUNDS[quadrant],axis=1)
 return SELECT[quadrant,slot]
def seam_basis():
 # A neutral-preserving row has two off-diagonal coefficients. Require equal
 # responses on both sides of every actual partition ray, for arbitrary chroma.
 rays=[]
 for q in range(4):
  rays.append(q*90.)
  rays.extend((q*90+np.degrees(np.arctan2(2048-v,v)))%360 for v in BOUNDS[q])
 constraints=[[] for _ in range(3)]
 for angle in sorted(set(rays)):
  theta=np.radians(np.array([angle-1e-7,angle+1e-7]));sample=np.column_stack([np.full(2,.5),.1*np.cos(theta),.1*np.sin(theta)])@np.linalg.inv(YCC).T
  left,right=groups(sample)
  if left==right:continue
  direction=np.array([0,np.cos(np.radians(angle)),np.sin(np.radians(angle))])@np.linalg.inv(YCC).T
  for c in range(3):
   others=[j for j in range(3) if j!=c];row=np.zeros(24);v=direction[others]-direction[c]
   row[left*2:left*2+2]=v;row[right*2:right*2+2]=-v;constraints[c].append(row)
 return [null_space(np.asarray(rows)) for rows in constraints]
BASIS=seam_basis();ND=[b.shape[1] for b in BASIS]
def identity_parameters():return np.r_[np.eye(3).ravel(),np.eye(3).ravel(),np.tile(KA,3),np.zeros(sum(ND))]
def unpack(p):
 m,pst=p[:9].reshape(3,3),p[9:18].reshape(3,3);curves=p[18:18+3*KNOTS].reshape(3,KNOTS);h=np.tile(np.eye(3),(12,1,1));at=18+3*KNOTS
 for c,basis in enumerate(BASIS):
  off=(basis@p[at:at+basis.shape[1]]).reshape(12,2);at+=basis.shape[1];others=[j for j in range(3) if j!=c]
  h[:,c,others]=off;h[:,c,c]=1-off.sum(1)
 return m,pst,curves,h
def inverse_standard(rgb,base):
 values,idx=np.unique(base,return_index=True)
 return np.column_stack([np.interp(rgb[:,c],values,AXIS[idx]) for c in range(3)])
def render(params,rgb,base):
 m,p,curves,h=unpack(params);x=inverse_standard(np.asarray(rgb),base);z=x@m.T;g=groups(z);v=np.einsum('nij,nj->ni',h[g],z)
 b=np.interp(np.clip(v,0,1),AXIS,base);u=np.column_stack([np.interp(b[:,c],KA,curves[c]) for c in range(3)])
 return np.clip(u@p.T,0,1)
def pack_multiaxis(q):
 q=np.asarray(q)
 if q.shape!=(12,3,3) or np.any(q!=np.rint(q)) or q.min()<-2048 or q.max()>2047:raise ValueError('signed12 sector coefficients required')
 ctl=[32,328,328,328,293,800,1600,2400,3200,32,1024,1024,1024,1024,0,0,0,0,0,640,1280]
 b=struct.pack('<16H20B',*BOUNDS.ravel(),*SELECT.ravel())
 b+=struct.pack('<540I',*np.repeat((q&4095)[:,None],5,axis=1).ravel())+bytes(1440)
 b+=struct.pack('<21H9H',*ctl,*((YCC*256).astype(int).ravel()&511))
 return b
def fit_gate(metric,pixel_model_validated=False):
 fidelity=metric['de00_p95']<=2 and metric['de00_max']<=6 and metric['de00_median']<=.7
 return {'eligible':bool(fidelity and pixel_model_validated),'fidelity_pass':bool(fidelity),'pixel_model_validated':pixel_model_validated,'thresholds':{'de00_median':.7,'de00_p95':2,'de00_max':6},'camera_target_validation_required':True}
def fit(rgb,target,base,iterations=600,constrain_native=False,monochrome=False):
 x=inverse_standard(rgb,base);n=len(x);p0=identity_parameters();base_slopes=np.diff(base)*255
 if monochrome and not constrain_native:raise ValueError('Monochrome fitting requires native CSP constraints')
 if constrain_native:p0[9:18]=(STD_CSP/256).ravel()
 if monochrome:p0[9:18]=np.array([[.28,.61,.11],[0,0,0],[0,0,0]]).ravel()
 native_inverse=np.linalg.inv(STD_CSP) if constrain_native else None
 # For neutral targets, train in the local CIEDE2000 lightness metric. RGB
 # squared error otherwise underweights visible errors in dark neutral tones.
 weights=np.ones((n,1))
 if monochrome:
  t=np.mean(target,axis=1);linear=np.where(t<=.04045,t/12.92,((t+.055)/1.055)**2.4)
  dl=np.where(linear<=216/24389,24389/27,116/3*np.maximum(linear,1e-12)**(-2/3))
  ds=np.where(t<=.04045,1/12.92,2.4/1.055*((t+.055)/1.055)**1.4)
  light=np.where(linear<=216/24389,linear*24389/27,116*np.cbrt(linear)-16)
  sl=1+.015*(light-50)**2/np.sqrt(20+(light-50)**2)
  weights=((dl*ds/sl)**2)[:,None];weights/=weights.mean()
 def objective(params):
  m,p,cv,h=unpack(params)
  if constrain_native:p=native_inverse@(p*256)
  z=x@m.T;g=groups(z);v=np.einsum('nij,nj->ni',h[g],z)
  clip=np.clip(v,0,1);b=np.interp(clip,AXIS,base);pos=b*(KNOTS-1);idx=np.minimum(pos.astype(int),KNOTS-2);frac=pos-idx
  u=np.empty_like(x);slope=np.empty_like(x)
  for c in range(3):
   lo,hi=cv[c,idx[:,c]],cv[c,idx[:,c]+1];u[:,c]=lo*(1-frac[:,c])+hi*frac[:,c];slope[:,c]=(hi-lo)*(KNOTS-1)
  out=u@p.T;error=out-target;loss=np.sum(weights*error**2)/n;do=2*weights*error/n;dp=do.T@u;du=do@p
  dcv=np.zeros_like(cv)
  for c in range(3):
   np.add.at(dcv[c],idx[:,c],du[:,c]*(1-frac[:,c]));np.add.at(dcv[c],idx[:,c]+1,du[:,c]*frac[:,c])
  dv=du*slope*base_slopes[np.minimum((clip*255).astype(int),254)]*((v>=0)&(v<=1))
  dz=np.einsum('ni,nij->nj',dv,h[g]);dm=dz.T@x;dh=np.zeros((12,3,3))
  for j in range(12):
   mask=g==j;dh[j]=dv[mask].T@z[mask]
  overflow=np.maximum(h-1.995,0)+np.minimum(h+1.995,0);loss+=np.sum(overflow**2);dh+=2*overflow
  grads=[];at=18+3*KNOTS
  for c,basis in enumerate(BASIS):
   others=[j for j in range(3) if j!=c];gd=dh[:,c,others]-dh[:,c,c,None];par=params[at:at+basis.shape[1]];at+=len(par)
   grads.extend(basis.T@gd.reshape(-1)+2e-6*par);loss+=1e-6*np.sum(par**2)
  backwards=np.minimum(np.diff(cv,axis=1),0);loss+=10*np.sum(backwards**2);dcv[:,:-1]-=20*backwards;dcv[:,1:]+=20*backwards
  # Gentle curvature penalty controls undersampled gamma knots.
  bend=np.diff(cv,n=2,axis=1);loss+=1e-5*np.sum(bend**2);dcv[:,:-2]+=2e-5*bend;dcv[:,1:-1]-=4e-5*bend;dcv[:,2:]+=2e-5*bend
  if constrain_native:dp=256*native_inverse.T@dp
  return loss,np.r_[dm.ravel(),dp.ravel(),dcv.ravel(),grads]
 fitted=minimize(objective,p0,jac=True,method='L-BFGS-B',bounds=[(-1,2)]*9+([(-250/256,250/256)]*3+([(0,0)]*6 if monochrome else [(-250/256,250/256)]*6) if constrain_native else [(-1,2)]*9)+[(0,1)]*(3*KNOTS)+[(-2,2)]*sum(ND),options={'maxiter':iterations,'ftol':1e-14,'gtol':1e-8,'maxls':40})
 result=fitted.x.copy()
 if constrain_native:result[9:18]=(native_inverse@(result[9:18].reshape(3,3)*256)).ravel()
 return result,{'iterations':fitted.nit,'success':bool(fitted.success),'message':str(fitted.message),'objective':float(fitted.fun)}
def quantize(params):
 m,p,cv,h=unpack(params);m=np.rint(m*8192).astype(int);p=np.rint(p*512).astype(int);h=np.rint(h*1024).astype(int)
 for c in range(3):h[:,c,c]=1024-sum(h[:,c,j] for j in range(3) if j!=c)
 curves=np.array([np.rint(np.interp(AXIS,KA,isotonic_regression(row).x)*16383).astype(int) for row in cv])
 native_m=(m@STD_CCA+4096)//8192;native_p=(STD_CSP.astype(int)@p+256)//512
 return {'matrix_q13':m.tolist(),'post_q9':p.tolist(),'curves':curves.tolist(),'hue_q10':h.tolist(),
  'native_cca_signed12':native_m.tolist(),'native_csp_signed9':native_p.tolist(),
  'effective_relative_matrix':(native_m@np.linalg.inv(STD_CCA)).tolist(),
  'effective_relative_post':(np.linalg.inv(STD_CSP)@native_p).tolist()}

def render_quantized(q,rgb,base):
 x=inverse_standard(rgb,base);z=x@np.array(q.get('effective_relative_matrix',np.array(q['matrix_q13'])/8192)).T;h=np.array(q['hue_q10'])/1024;v=np.einsum('nij,nj->ni',h[groups(z)],z);b=np.interp(np.clip(v,0,1),AXIS,base)
 # Exact frame helper curve indexing: correction position=baseQ14/64.
 # The original gamma input points retain their actual 256-entry geometry.
 base_codes=np.rint(base*16384).astype(int);mapped=[]
 for row in np.asarray(q['curves']):
  index=np.minimum(base_codes>>6,255);frac=base_codes&63;next_index=np.minimum(index+1,255)
  mapped.append((row[index]*(64-frac)+row[next_index]*frac+32)//64)
 u=np.column_stack([np.interp(np.clip(v[:,c],0,1),AXIS,np.asarray(mapped)[c]/16384) for c in range(3)])
 return np.clip(u@np.array(q.get('effective_relative_post',np.array(q['post_q9'])/512)).T,0,1)
def load_tables():
 text=(ROOT/'native/gr3/m10v_film_color_candidates.h').read_text();out={}
 for name,body in re.findall(r'm10v_(\w+)_candidate_lut\[3375\]\[3\] = \{(.*?)\n\};',text,re.S):
  out[name]=np.array([list(map(int,v)) for v in re.findall(r'\{(\d+),(\d+),(\d+)\}',body)],np.uint8).reshape(15,15,15,3)
 return out
# Base curves are extracted directly from the original tuning object, not from
# an assumed sRGB transfer function or a JPEG inversion.
def stock_gamma():
 from tests.test_gr3_isp_base import StockISP
 rom=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
 from scripts.build_gr3_isp_multiaxis import FIRMWARE_SHA256
 if hashlib.sha256(rom).hexdigest()!=FIRMWARE_SHA256:raise ValueError('unsupported RTOS hash')
 e=StockISP(rom);e.make(11);g=struct.unpack('<I',e.u.mem_read(0x60000000+0x17c,4))[0]
 return np.array(struct.unpack('<256H',e.u.mem_read(g+0x2a08,512)))/16384
def generate(out,train_count=8192,holdout_count=65536,iterations=800):
 from scripts.analyze_gr3_film_color_targets import native_table_rgb,metrics
 out=Path(out);out.mkdir(parents=True,exist_ok=True);base=stock_gamma();tables=load_tables()
 train_codes=np.random.default_rng(52076731).integers(0,256,(train_count,3),dtype=np.uint8)
 grey=np.repeat(np.arange(256,dtype=np.uint8)[:,None],3,axis=1);train_codes=np.vstack([train_codes,grey,grey,grey]);train=train_codes/255
 hold=np.random.default_rng(67185207).integers(0,256,(holdout_count,3),dtype=np.uint8)
 skin=np.array([[115,82,68],[194,150,130],[98,62,45],[220,172,143],[255,210,180]],np.uint8)
 report={'schema':'gr3-full-native-film-fit/v1','seeds':{'train':52076731,'holdout':67185207},'basis_dof':ND,'base_gamma_q14':np.rint(base*16384).astype(int).tolist(),
  'domain':'explicit model Standard inverse -> relative matrix -> native 12 continuous sectors -> original base gamma -> correction curves -> post matrix',
  'camera_model_evidence':'gr3-film-mods FINDINGS30b/33b; geometry and sector pixel application physically validated there; current target and complete-chain quantization require new camera validation',
  'current_camera_validation':False,'targets':{}}
 for name,table in tables.items():
  target=native_table_rgb(table,train_codes)/255;params,opt=fit(train,target,base,iterations);q=quantize(params)
  sets={'random_holdout':hold,'grey':grey,'skin_reference':skin};scores={}
  for setname,codes in sets.items():
   expected=native_table_rgb(table,codes)/255;actual=render_quantized(q,codes/255,base);scores[setname]=metrics(expected,actual)
  scores['quantization']=metrics(render(params,hold/255,base),render_quantized(q,hold/255,base))
  gate=fit_gate(scores['random_holdout'],False);range_ok=bool(np.min(q['hue_q10'])>=-2048 and np.max(q['hue_q10'])<=2047 and np.min(q['native_cca_signed12'])>=-2048 and np.max(q['native_cca_signed12'])<=2047 and np.min(q['native_csp_signed9'])>=-256 and np.max(q['native_csp_signed9'])<=255)
  if not range_ok:gate['eligible']=False;gate['reason']='native signed12 CCA/hue or signed9 CSP coefficient overflow'
  row={'parameters':q,'float_parameters':params.tolist(),'optimization':opt,'metrics':scores,'gate':gate,'target_sha256':hashlib.sha256(table.tobytes()).hexdigest(),
   'all_five_levels_identical':True,'scope':'CPU reference to original target LUT color only; spatial effects untouched','source_target':'current full15cube candidate, not independently film calibrated'}
  report['targets'][name]=row
  if range_ok:(out/(name+'-multiaxis.bin')).write_bytes(pack_multiaxis(q['hue_q10']))
  (out/'native-film-fit.json').write_text(json.dumps(report,indent=2)+'\n')
  print(name,json.dumps({'metrics':scores['random_holdout'],'gate':gate,'optimization':opt}),flush=True)
 export_header(report,out/'m10v_native_film_fit_targets.h')
 return report
def export_header(report,path):
 header='/* Generated offline native targets. No camera validation or production activation. */\n#ifndef M10V_NATIVE_FILM_FIT_TARGETS_H\n#define M10V_NATIVE_FILM_FIT_TARGETS_H\n#include \"m10v_isp_frame_color.h\"\n#include \"m10v_isp_multiaxis.h\"\n'
 for name,row in report['targets'].items():
  q=row['parameters'];m=q['matrix_q13'];p=q['post_q9'];h=np.array(q['hue_q10'])
  if h.min()<-2048 or h.max()>2047:continue
  raw=pack_multiaxis(h);ctl=raw[3652:3694];final=struct.unpack_from('<9H',raw,3694)
  arr=lambda x:'{'+','.join(map(str,np.asarray(x).ravel()))+'}'
  header+=f'/* {name}: fidelity_pass={int(row["gate"]["fidelity_pass"])}, enabled=0 */\n'
  header+=f'static const m10v_isp_frame_target m10v_native_fit_{name}_frame = '+'{'+arr(m)+','+arr(p)+',{'+','.join(arr(c) for c in q['curves'])+'}};\n'
  mats=np.repeat(h[:,None],5,axis=1).reshape(60,9)&4095
  header+=f'static const m10v_isp_multiaxis_target m10v_native_fit_{name}_multi = '+'{'+arr(BOUNDS)+','+arr(SELECT)+',{'+','.join(arr(v) for v in mats)+'},{0},'+arr(list(ctl))+','+arr(final)+'};\n'
 Path(path).write_text(header+'#endif\n')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--out',default=str(ROOT/'builds/gr3-native-film-fit'));a.add_argument('--train',type=int,default=8192);a.add_argument('--holdout',type=int,default=65536);a.add_argument('--iterations',type=int,default=800);args=a.parse_args();generate(args.out,args.train,args.holdout,args.iterations)
