"""Official-description-guided display approximations, not measured film LUTs.

All numerical coefficients are authored assumptions. ISO/process and qualitative
colour constraints come from the sources below. No physical fidelity claim.
"""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
SOURCES=[dict(id='opticolour-official',url='https://www.optik-oldschool.com/products/opticolour-200',facts='ISO200, daylight, C41; natural colour, good contrast, greens/reds and skin. No sensitometric curves supplied.'),dict(id='nc500-official',url='https://filmotec.de/originalwolfen-nc500/',facts='ISO400 C41; greens, desaturated shadows, pronounced grain.'),dict(id='nc500-datasheet',url='https://filmotec.de/wp-content/uploads/2023/04/Datenblatt-Wolfen-NC500.pdf',facts='ISO400/27, daylight C41 curves, no remjet. Curves NOT digitized; spectral dye/scan calibration unavailable.')]
SPECS=[dict(id=312,name='OptiColour 200',key='opticolour-200',title='OPTICOLOUR',code='200',color='#73946b',iso=200,source_ids=['opticolour-official']),dict(id=313,name='NC500',key='orwo-nc500',title='WOLFEN',code='NC500',color='#8c7e4f',iso=400,source_ids=['nc500-official','nc500-datasheet'])]
MODELS={312:dict(contrast=.065,saturation=1.075,mix=[[1.012,-.005,-.007],[0,1.005,-.005],[.006,.004,.990]],black=[.006,.006,.004],white=[.998,.995,.987]),313:dict(contrast=.10,saturation=.72,mix=[[.99,.015,-.005],[.012,.998,-.010],[.005,.010,.985]],black=[.011,.020,.009],white=[.974,.989,.958])}
def generate():
 import numpy as np
 from scripts.build_gr3_anime_e6_reference import authored
 grid=np.stack(np.meshgrid(*[np.linspace(0,1,15)]*3,indexing='ij'),axis=-1).reshape(-1,3)
 stocks=[];specs=[]
 for spec in SPECS:
  values=np.rint(authored(grid,MODELS[spec['id']])*255).astype('uint8').reshape(-1).tolist()
  stock={**spec,'ascii_name':spec['name'],'values':values,'approximation':True,'official_lut':False,'film_calibrated':False,'camera_calibrated':False}
  stocks.append(stock);specs.append({k:v for k,v in stock.items() if k!='values'}|dict(table_sha256=hashlib.sha256(bytes(values)).hexdigest(),source_kind='official qualitative constraints; independently authored display model',model_parameters=MODELS[spec['id']],limitations='Numerical parameters are assumptions, not measured film data. Scan/scene/camera spectra uncalibrated. No 100 percent claim.'))
 (ROOT/'web/gr3/c41-luts.json').write_text(json.dumps(dict(size=15,bits=8,order='RGB, blue fastest',stocks=stocks),separators=(',',':'))+'\n')
 files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['scripts/build_gr3_c41_reference.py']}
 (ROOT/'native/gr3/c41-reference.json').write_text(json.dumps(dict(schema='m10v-c41-reference/v1',sources=SOURCES,stocks=specs,files=files,camera_validated=False,default_camera_renderer='quantized native ISP; no CPU color LUT',reference_domain='encoded display sRGB D65'),indent=2)+'\n')
if __name__=='__main__':generate()
