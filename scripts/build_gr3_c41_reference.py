"""Official-description-guided display approximations, not measured film LUTs.

All numerical coefficients are authored assumptions. ISO/process and qualitative
colour constraints come from the sources below. No physical fidelity claim.
"""
import hashlib,json,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'third_party/spectral-film-lut/src'))
os.environ.setdefault('NUMBA_NUM_THREADS','1')
SOURCES=[dict(id='opticolour-official',url='https://www.optik-oldschool.com/products/opticolour-200',facts='ISO200, daylight, C41; natural colour, good contrast, greens/reds and skin. No sensitometric curves supplied.'),dict(id='nc500-official',url='https://filmotec.de/originalwolfen-nc500/',facts='ISO400 C41; greens, desaturated shadows, pronounced grain.'),dict(id='nc500-datasheet',url='https://filmotec.de/wp-content/uploads/2023/04/Datenblatt-Wolfen-NC500.pdf',facts='ISO400/27, daylight C41 curves, no remjet. Curves NOT digitized; spectral dye/scan calibration unavailable.')]
SPECS=[dict(id=312,name='OptiColour 200',key='opticolour-200',title='OPTICOLOUR',code='200',color='#73946b',iso=200,source_ids=['opticolour-official']),dict(id=313,name='NC500',key='orwo-nc500',title='WOLFEN',code='NC500',color='#8c7e4f',iso=400,source_ids=['nc500-official','nc500-datasheet'])]
MODELS={312:dict(contrast=.065,saturation=1.075,mix=[[1.012,-.005,-.007],[0,1.005,-.005],[.006,.004,.990]],black=[.006,.006,.004],white=[.998,.995,.987]),313:dict(contrast=.10,saturation=.72,mix=[[.99,.015,-.005],[.012,.998,-.010],[.005,.010,.985]],black=[.011,.020,.009],white=[.974,.989,.958])}
SOURCES += [
 dict(id='phoenix-original-official',url='https://www.harmanphoto.co.uk/amfile/file/download/file/1963/product/2143/',facts='Original Phoenix 200, Sep 2024 technical information: ISO200 daylight, C41, high contrast, no masking dyes and limited antihalation. Not Phoenix II. Characteristic chart is not a calibrated positive RGB LUT; numeric design below is authored.'),
 dict(id='colorplus-source-gap',url=None,facts='No same-stock manufacturer digital LUT or sensitometric publication located in the official Kodak/Alaris indexes on 2026-11-02. This is an independent ColorPlus-inspired design, not Gold 200, VR200 or a renamed Kodacolor substitute. Official colour-data requirement remains unmet for this stock.'),
 dict(id='natura-official',url='https://asset.fujifilm.com/www/jp/files/2024-04/96b634a89ec6a5abda6b70437f4d75a4/datasheet_natura1600_01.pdf',facts='Fujifilm NATURA1600 bulletin 013AR313B: ISO1600 daylight, neutral grey balance, faithful colours and fourth colour-sensitive layer. Vendored MIT Natura1600 digitization; display inversion and spectral reconstruction are model assumptions.'),
 dict(id='redscale-official',url='https://www.lomography.com/magazine/34658-experiment-with-the-new-lomography-redscale-xr-film',facts='Official Redscale XR launch: ISO50-200, C41. ISO200 gives intense red/orange; lower ISO can introduce blue/green. This single look targets the ISO200 direction, not the entire exposure range.'),
 dict(id='vista-original-official',url='https://125px.com/docs/unsorted/agfa/F-AF-E6_en.pdf',facts='Manufacturer Agfa F-AF-E6 standard-film brochure, archived copy: original Vista200, ISO200 daylight5500K, AP70/C41, EYE VISION colour fidelity. No substitution of Vista100 or later AgfaPhoto Vista Plus/Fuji C200. Numerical display model is authored, curves not digitized.'),
]
SPECS += [dict(id=i,name=n,key=k,title=t,code=c,color=col,iso=iso,source_ids=[src],group='C41') for i,n,k,t,c,col,iso,src in [
 (322,'Harman Phoenix 200','harman-phoenix-200','PHOENIX','200','#d7672f',200,'phoenix-original-official'),
 (323,'Kodak ColorPlus 200','kodak-colorplus-200','COLORPLUS','200','#d3a837',200,'colorplus-source-gap'),
 (324,'Fujifilm Natura 1600','fujifilm-natura-1600','NATURA','1600','#66a67e',1600,'natura-official'),
 (325,'Lomo Redscale XR','lomo-redscale-xr','REDSCALE','XR 200','#bb492e',200,'redscale-official'),
 (326,'Agfa Vista 200','agfa-vista-200','VISTA','200','#c34555',200,'vista-original-official')]]
MODELS.update({
 322:dict(contrast=.20,saturation=1.14,mix=[[1.055,-.025,-.030],[-.015,1.025,-.010],[.012,-.035,1.023]],black=[.009,.004,.012],white=[.999,.975,.945]),
 323:dict(contrast=.035,saturation=.94,mix=[[1.025,-.010,-.015],[.006,1.004,-.010],[-.008,.014,.994]],black=[.012,.009,.006],white=[.999,.984,.952]),
 325:dict(contrast=.11,saturation=1.02,mix=[[.74,.23,.03],[.30,.59,.11],[.13,.26,.61]],black=[.035,.008,.003],white=[1,.73,.38]),
 326:dict(contrast=.07,saturation=1.09,mix=[[1.018,-.008,-.010],[-.012,1.030,-.018],[.008,-.015,1.007]],black=[.007,.010,.011],white=[.997,.994,.984]),
})
def render(film,rgb):
 import numpy as np
 if film==324:
  from spectral_film_lut.film_spectral import FilmSpectral
  from spectral_film_lut.negative_film.fuji_natura_1600 import FUJI_NATURA_1600
  from spectral_film_lut.utils import film_conversion
  out=film_conversion(rgb,FilmSpectral(FUJI_NATURA_1600),input_colorspace='sRGB',output_gamut='Rec. 709',gamma_func='sRGB',mode='full',exp_kelvin=5500,projector_kelvin=5500,exp_comp=0,white_clip=False,white_balance=0,color_masking=0,upsampling_method='SFL upsampling')
  if not np.isfinite(out).all():raise ValueError('nonfinite Natura target')
  return np.clip(out,0,1)
 from scripts.build_gr3_anime_e6_reference import authored
 return authored(rgb,MODELS[film])
def generate():
 import numpy as np
 from scripts.build_gr3_anime_e6_reference import authored
 grid=np.stack(np.meshgrid(*[np.linspace(0,1,15)]*3,indexing='ij'),axis=-1).reshape(-1,3)
 stocks=[];specs=[]
 for spec in SPECS:
  values=np.rint(render(spec['id'],grid)*255).astype('uint8').reshape(-1).tolist()
  stock={**spec,'ascii_name':spec['name'],'values':values,'approximation':True,'official_lut':False,'film_calibrated':False,'camera_calibrated':False}
  stocks.append(stock);specs.append({k:v for k,v in stock.items() if k!='values'}|dict(table_sha256=hashlib.sha256(bytes(values)).hexdigest(),source_kind='MIT spectral Natura model with assumed display adaptation' if spec['id']==324 else 'independently authored display model; official qualitative constraints where available',model_parameters=MODELS.get(spec['id'],dict(model='FUJI_NATURA_1600',illuminant=5500,exp_comp=0,color_masking=0,white_balance=0)),limitations='Numerical display parameters are assumptions, not film/camera measurements. ColorPlus official colour source unavailable. Scan/scene/camera spectra uncalibrated. No 100 percent claim.'))
 (ROOT/'web/gr3/c41-luts.json').write_text(json.dumps(dict(size=15,bits=8,order='RGB, blue fastest',stocks=stocks),separators=(',',':'))+'\n')
 paths=['scripts/build_gr3_c41_reference.py','third_party/spectral-film-lut/LICENSE',*map(lambda p:str(p.relative_to(ROOT)),sorted((ROOT/'third_party/spectral-film-lut/src').rglob('*.py')))]
 files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
 (ROOT/'native/gr3/c41-reference.json').write_text(json.dumps(dict(schema='m10v-c41-reference/v1',sources=SOURCES,stocks=specs,files=files,camera_validated=False,default_camera_renderer='quantized native ISP; no CPU color LUT',reference_domain='encoded display sRGB D65'),indent=2)+'\n')
if __name__=='__main__':generate()
