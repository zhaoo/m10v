"""C41-only solver: existing ISP objective plus bounded relative-post penalty.

Both packed relative Q9 and final signed9 hardware CSP must be representable.
The shared fitter and previously released targets keep their original behavior.
"""
from scripts.fit_gr3_native_film_targets import *

def fit_c41(rgb,target,base,iterations=1200,constrain_native=True,monochrome=False,warm_start=None):
 x=inverse_standard(rgb,base);n=len(x);p0=identity_parameters();base_slopes=np.diff(base)*255
 if monochrome and not constrain_native:raise ValueError('Monochrome fitting requires native CSP constraints')
 if constrain_native:p0[9:18]=(STD_CSP/256).ravel()
 if monochrome:p0[9:18]=np.array([[.28,.61,.11],[0,0,0],[0,0,0]]).ravel()
 native_inverse=np.linalg.inv(STD_CSP) if constrain_native else None
 if warm_start:
  p0[:9]=np.asarray(warm_start['matrix_q13']).ravel()/8192
  relative_post=np.asarray(warm_start['post_q9'])/512
  p0[9:18]=(STD_CSP@relative_post/256).ravel() if constrain_native else relative_post.ravel()
  p0[18:18+3*KNOTS]=np.concatenate([np.interp(KA,AXIS,np.asarray(c)/16383) for c in warm_start['curves']])
  at=18+3*KNOTS
  sectors=np.asarray(warm_start['hue_q10'])/1024
  for c,basis in enumerate(BASIS):
   others=[j for j in range(3) if j!=c]
   p0[at:at+basis.shape[1]]=basis.T@sectors[:,c,others].reshape(-1);at+=basis.shape[1]
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
  excess=np.maximum(p-1.98,0)+np.minimum(p+.98,0)
  loss+=100*np.sum(excess**2);dp+=200*excess
  if constrain_native:dp=256*native_inverse.T@dp
  return loss,np.r_[dm.ravel(),dp.ravel(),dcv.ravel(),grads]
 fitted=minimize(objective,p0,jac=True,method='L-BFGS-B',bounds=[(-1,2)]*9+([(-250/256,250/256)]*3+([(0,0)]*6 if monochrome else [(-250/256,250/256)]*6) if constrain_native else [(-1,2)]*9)+[(0,1)]*(3*KNOTS)+[(-2,2)]*sum(ND),options={'maxiter':iterations,'ftol':1e-14,'gtol':1e-8,'maxls':40})
 result=fitted.x.copy()
 if constrain_native:result[9:18]=(native_inverse@(result[9:18].reshape(3,3)*256)).ravel()
 return result,{'iterations':fitted.nit,'success':bool(fitted.success),'message':str(fitted.message),'objective':float(fitted.fun)}
