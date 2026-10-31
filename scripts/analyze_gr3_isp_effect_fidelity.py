"""Host-only visual/fit audit. Never imported by camera code or firmware build.

The Granulation scalar blend model and octave frequencies are hypotheses to
check on camera. These previews must never be described as actual ISP output.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scripts.build_gr3_isp_effect_textures import leak_mask, LEGACY_LEAK_COMMIT
from scripts.build_gr3_isp_effect_render import leak_curves
from scripts.build_gr3_isp_effect_blur import CORE_SIGMAS, SCATTER_SIGMAS, SCATTER_WEIGHTS, REFERENCES


RGB_TO_YUV = np.array([[.299,.587,.114],[-.168736,-.331264,.5],[.5,-.418688,-.081312]])


def legacy_screen(rgb,mask,gain=8):
    light=np.floor(mask.astype(float)*gain/8)
    r=rgb.astype(np.int64)
    return np.clip(r+((light[...,None].astype(np.int64)*np.array([256,112,36])*(255-r))>>16),0,255).astype(np.uint8)


def native_pass_model(src,noise,curve):
    """Polarity hypothesis: lower(src)*(1-weight)+upper(src)*weight.
    Anchored to stock table ordering and r14 hardware symptom, NOT measured
    silicon arithmetic. Keep this separate from the fitted profile builder.
    """
    upper,lower,weight=(np.asarray(row,dtype=float) for row in curve)
    alpha=weight[np.asarray(noise,dtype=np.uint8)]/255
    src=np.asarray(src,dtype=np.uint8)
    return np.rint(upper[src]*alpha+lower[src]*(1-alpha)).astype(np.uint8)


def candidate_model(rgb,mask,strength=3,*,r14_endpoints=False):
    """Host hypothesis including BOTH bytes of each actual UV pass.

    r14's preview incorrectly updated only the selected UV component. On
    camera both components pass through the SAME curve: an inactive weight
    MUST be identity, or the other component is changed too.
    """
    yuv=rgb.astype(float)@RGB_TO_YUV.T+np.array([0,128,128])
    yuv=np.rint(np.clip(yuv,0,255)).astype(np.uint8)
    profiles=leak_curves()
    if r14_endpoints:profiles=[(lower,upper,weight) for upper,lower,weight in profiles]
    curves=profiles[(strength-1)*3:strength*3]
    uv=yuv[...,1:3].copy()
    for channel in (0,1):
        field=np.zeros_like(uv);field[...,channel]=mask
        gate=native_pass_model(field,np.broadcast_to(yuv[...,0,None],field.shape),profiles[9])
        uv=native_pass_model(uv,gate,curves[channel+1])
    yy=native_pass_model(yuv[...,0],mask,curves[0])
    out=(np.concatenate((yy[...,None],uv),axis=-1)-np.array([0,128,128]))@np.linalg.inv(RGB_TO_YUV).T
    return np.rint(np.clip(out,0,255)).astype(np.uint8)


def blur_model(rgb,core,scatter=0,weight=0):
    h,w=rgb.shape[:2];fy=np.fft.fftfreq(h)[:,None];fx=np.fft.rfftfreq(w)[None,:]
    f2=fx*fx+fy*fy
    response=(1-weight)*np.exp(-2*np.pi**2*core*core*f2)+weight*np.exp(-2*np.pi**2*scatter*scatter*f2)
    return np.rint(np.clip(np.fft.irfft2(np.fft.rfft2(rgb.astype(float),axes=(0,1))*response[...,None],s=(h,w),axes=(0,1)),0,255)).astype(np.uint8)


def chart(w=768,h=384):
    x=np.arange(w)[None,:];y=np.arange(h)[:,None]
    a=np.empty((h,w,3),np.uint8);a[:]=np.rint(np.broadcast_to(x*255/(w-1),(h,w)))[...,None]
    colors=((255,255,255),(128,128,128),(24,24,24),(194,137,107),(28,87,123),(75,111,57))
    for i,color in enumerate(colors):a[h//4:h//2,i*w//6:(i+1)*w//6]=color
    for i,period in enumerate((2,4,8,16,32,64)):
        z=np.where((x//(period//2))%2,210,45).astype(np.uint8)
        a[h//2:3*h//4,i*w//6:(i+1)*w//6]=z[:,i*w//6:(i+1)*w//6,None]
    for channel in range(3):a[3*h//4:,channel*w//3:(channel+1)*w//3,channel]=210
    return a


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    image=chart();h,w=image.shape[:2];mask=leak_mask(w,h,'left','medium')
    old=legacy_screen(image,mask);new=candidate_model(image,mask)
    oldblur=blur_model(image,2.5)
    newblur=blur_model(image,CORE_SIGMAS[1],SCATTER_SIGMAS[1],SCATTER_WEIGHTS[1])
    panels=(image,old,new,image,candidate_model(image,mask,r14_endpoints=True),newblur)
    canvas=Image.new('RGB',(w*3,(h+32)*2),(24,24,24));draw=ImageDraw.Draw(canvas)
    labels=('SOURCE - host chart','OLD RGB LEAK - historical reference','R15 LEAK - POLARITY HYPOTHESIS',
            'SOURCE - spatial frequency bars','R14 endpoints - symptom reproduction MODEL','R14 blur unchanged - host model')
    for index,(panel,label) in enumerate(zip(panels,labels)):
        xx=(index%3)*w;yy=(index//3)*(h+32)
        canvas.paste(Image.fromarray(panel),(xx,yy+32));draw.text((xx+8,yy+8),label,fill='white')
    canvas.save(args.output/'host-comparison.png')
    # Full 8-bit neutral ramp across all masks, all strength settings.
    ramp=np.broadcast_to(np.arange(256,dtype=np.uint8)[None,:,None],(256,256,3))
    weights=np.broadcast_to(np.arange(256,dtype=np.uint8)[:,None],(256,256));metrics=[]
    for strength,gain in enumerate((2,5,8),1):
        ref=legacy_screen(ramp,weights,gain);fit=candidate_model(ramp,weights,strength)
        error=np.abs(ref.astype(float)-fit)
        metrics.append(dict(strength=strength,legacy_gain=gain,neutral_rgb_mae=float(error.mean()),
                            neutral_rgb_p99=float(np.percentile(error,99)),neutral_rgb_max=float(error.max()),
                            white_max_delta=int(np.abs(fit[:,255].astype(int)-255).max())))
    chart_error=np.abs(old.astype(float)-new)
    active_error=chart_error[mask>0]
    report=dict(scope='HOST MODEL ONLY - not actual ISP output, camera acceptance required',
        polarity_assumption='lower*(1-weight)+upper*weight',hardware_endpoint_observed=False,
        uv_execution='both interleaved bytes traverse both chroma passes',
        legacy_commit=LEGACY_LEAK_COMMIT,neutral_ramp_fit=metrics,
        color_chart_rgb_mae=float(chart_error.mean()),
        color_chart_active_rgb_mae=float(active_error.mean()),
        color_chart_active_rgb_max=float(active_error.max()),
        limitations=['separable YUV fit cannot reproduce all RGB cross-channel screen terms',
                     '4:2:0 luma gating samples every second source row; not a calibrated optical model',
                     'native scalar arithmetic and actual Clarity band response need camera comparison'],
        references=REFERENCES)
    (args.output/'host-fit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
