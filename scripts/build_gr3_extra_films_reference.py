"""Three reproducible offline targets; not physical film/camera calibration.

ACROS II uses an authored tonal interpretation guided by Fujifilm's published
identity/gradation descriptions. The restricted PictureFX LUT is not copied.
Double-X uses the vendored MIT spectral model and Polymax grade2 print paper.
Turquoise is an authored colour-swap interpretation of Lomography's 2021 guide.
"""
import hashlib,json,sys,os
from functools import cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'third_party/spectral-film-lut/src')]
os.environ.setdefault('NUMBA_NUM_THREADS','4')
SPECS=[dict(id=314,name='ACROS II 100',ascii_name='ACROS II 100',key='acros-ii-100',title='ACROS II',code='100',color='#777b72',iso=100,group='黑白',source='https://www.fujifilm.com/us/en/business/professional-photography/film/neopan-100-acros-ii/support',reference='independently authored official-description-guided tonal interpretation; not original ACROS I or Fujifilm camera simulation'),dict(id=315,name='Double-X 5222',ascii_name='Double-X 5222',key='double-x-5222',title='DOUBLE-X',code='5222',color='#6a6961',iso=250,group='黑白',source='https://www.kodak.com/content/products-brochures/Film/DOUBLEX-Technical-Data-EN.pdf',reference='MIT spectral_film_lut KODAK_5222 D96 nominal curve6 plus Kodak Polymax grade2; display sRGB adaptation is assumed'),dict(id=316,name='LomoChrome Turquoise',ascii_name='LomoChrome Turquoise',key='lomochrome-turquoise',title='TURQUOISE',code='100-400',color='#397f8c',iso=400,group='创意',source='https://shop.lomography.com/us/2021-lomochrome-turquoise-120-iso-100-400',reference='independent 2021-formula colour-swap model guided by official colour directions; numeric mixing/tone coefficients assumed')]
PARAMETERS=dict(acros=dict(input_knots=[0,.025,.07,.18,.40,.70,1],output_knots=[.003,.015,.049,.172,.427,.760,.992],rgb_weights=[.28,.61,.11],status='authored, not digitized sensitometry'),turquoise=dict(matrix=[[.10,0,.90],[0,.78,.22],[.78,.22,0]],contrast=.065,saturation=1.04,black=[.007,.016,.014],white=[.985,.992,.987],status='authored visible-RGB colour-swap, not measured spectral layers'),double_x=dict(negative='KODAK_5222',paper='KODAK_POLYMAX_GRADE_2',exposure_kelvin=6500,projector_kelvin=6500,input='encoded display sRGB; not recovered scene radiance',colour_masking=0,source_license='MIT Jan Lohse',development='D96 nominal curve6 as digitized upstream; not D76'),spatial='no baked grain, halation, MTF or detail reconstruction; existing native user-controlled grain remains independent')
@cache
def spectral_models():
 from spectral_film_lut.film_spectral import FilmSpectral
 from spectral_film_lut.bw_negative_film.kodak_5222 import KODAK_5222
 from spectral_film_lut.bw_print_film.kodak_polymax_fine_art import KODAK_POLYMAX_GRADE_2
 return FilmSpectral(KODAK_5222),FilmSpectral(KODAK_POLYMAX_GRADE_2)
def render(film,rgb):
 import numpy as np
 x=np.clip(np.asarray(rgb,float),0,1)
 if film==314:
  from scipy.interpolate import PchipInterpolator
  p=PARAMETERS['acros'];y=PchipInterpolator(p['input_knots'],p['output_knots'])(x@np.array(p['rgb_weights']))
  return np.repeat(np.clip(y,0,1)[:,None],3,axis=1)
 if film==315:
  from spectral_film_lut.utils import film_conversion
  n,p=spectral_models();out=film_conversion(x,n,p,input_colorspace='sRGB',output_gamut='Rec. 709',gamma_func='sRGB',mode='full',exp_kelvin=6500,projector_kelvin=6500,exp_comp=0,white_clip=False,white_balance=0,color_masking=0,apd_intermediate=True,reference_negative=n,upsampling_method='SFL upsampling')
  if not np.isfinite(out).all():raise ValueError('nonfinite spectral target')
  return np.repeat(np.clip(np.mean(out,axis=1),0,1)[:,None],3,axis=1)
 if film==316:
  from scripts.build_gr3_anime_e6_reference import authored
  p=PARAMETERS['turquoise'];return authored(x,dict(mix=p['matrix'],**{k:p[k] for k in ['contrast','saturation','black','white']}))
 raise ValueError('unknown extra film')
def generate():
 import numpy as np
 grid=np.stack(np.meshgrid(*[np.linspace(0,1,15)]*3,indexing='ij'),axis=-1).reshape(-1,3);stocks=[];specs=[]
 for spec in SPECS:
  values=np.rint(render(spec['id'],grid)*255).astype('uint8').reshape(-1).tolist()
  stock=spec|dict(values=values,approximation=True,official_lut=False,film_calibrated=False,camera_calibrated=False);stocks.append(stock);specs.append({k:v for k,v in stock.items() if k!='values'}|dict(table_sha256=hashlib.sha256(bytes(values)).hexdigest()))
 (ROOT/'web/gr3/extra-films-luts.json').write_text(json.dumps(dict(size=15,bits=8,order='RGB, blue fastest',stocks=stocks),separators=(',',':'))+'\n')
 paths=['scripts/build_gr3_extra_films_reference.py','third_party/spectral-film-lut/LICENSE',*map(lambda p:str(p.relative_to(ROOT)),sorted((ROOT/'third_party/spectral-film-lut/src').rglob('*.py')))]
 ref=dict(schema='m10v-extra-film-reference/v1',stocks=specs,parameters=PARAMETERS,camera_validated=False,default_camera_renderer='quantized native ISP; no CPU color LUT',files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},limits='Implementation error is against declared display references, never measured physical film fidelity. No 100 percent claim.')
 (ROOT/'native/gr3/extra-films-reference.json').write_text(json.dumps(ref,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':generate()
