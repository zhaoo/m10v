"""Compile original computer-rendered RGBA art into immutable ISP inputs.

Each style uses two NV12-shaped weight fields. The ISP receives zero-based
unsigned UV weights and applies positive and negative endpoints separately.
The second field also contains the Y exposure weight.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 512, 304
ASSET_BYTES = 3268608
ASSET_SHA256 = 'adfc792bdf010de0bebde30168b33aed6d228143fbe5f6e8bb8bbf3d1b72936a'

def sha(b):return hashlib.sha256(b).hexdigest()

def pack_imprint(rgba):
    rgba=np.asarray(rgba)
    if rgba.dtype!=np.uint8 or rgba.ndim!=3 or rgba.shape[2]!=4:
        raise ValueError('RGBA8 input required')
    h,w,_=rgba.shape
    if w<2 or h<2 or (w|h)&1 or w>WIDTH or h>HEIGHT:
        raise ValueError('bounded even texture geometry required')
    rgb=rgba[:,:,:3].astype(np.float64)*(rgba[:,:,3:4].astype(np.float64)/255.)
    r,g,b=rgb.transpose(2,0,1)
    y=np.rint(np.clip(.299*r+.587*g+.114*b,0,255)).astype(np.uint8)
    cb=-.168736*r-.331264*g+.5*b
    cr=.5*r-.418688*g-.081312*b
    stride=(w+63)&~63
    yp=np.zeros((h,stride),np.uint8);yp[:,:w]=y
    positive=np.zeros((h//2,stride),np.uint8)
    negative=np.zeros_like(positive)
    for channel,v in enumerate((cb,cr)):
        low=v.reshape(h//2,2,w//2,2).mean(axis=(1,3))
        positive[:,channel:w:2]=np.rint(np.clip(2*low,0,255)).astype(np.uint8)
        negative[:,channel:w:2]=np.rint(np.clip(-2*low,0,255)).astype(np.uint8)
    return bytes(yp.nbytes)+positive.tobytes(),yp.tobytes()+negative.tobytes()

def build(prefix):
    prefix=Path(prefix);blob=bytearray();assets=[]
    sources={}
    for path in (Path(__file__),ROOT/'web/shared/film-imprints.mjs',ROOT/'scripts/render_film_imprint_assets.mjs'):
        sources[str(path.relative_to(ROOT))]=sha(path.read_bytes())
    for id in ('025','001','004','007'):
        path=ROOT/f'native/gr3/film-imprints/pokemon/{id}.png'
        sources[str(path.relative_to(ROOT))]=sha(path.read_bytes())
    for style in range(1,8):
        path=ROOT/f'native/gr3/film-imprints/{style}.png'
        sources[str(path.relative_to(ROOT))]=sha(path.read_bytes())
        with Image.open(path) as image:
            if image.mode!='RGBA' or image.size!=(768,512):raise ValueError('original 768x512 RGBA art required')
            source=np.array(image.resize((WIDTH,HEIGHT),Image.Resampling.LANCZOS))
        # The print is fixed on the physical sensor/film plane. EXIF rotates
        # the photo AND print afterwards. Pre-rotating then stretching a
        # portrait mask into the landscape sensor would distort the motifs.
        for polarity,data in zip(('positive','negative'),pack_imprint(source)):
            assets.append(dict(style=style,polarity=polarity,offset=len(blob),length=len(data),
                width=WIDTH,height=HEIGHT,stride=WIDTH,sha256=sha(data)))
            blob.extend(data)
    if len(blob)!=ASSET_BYTES:raise ValueError('imprint immutable resource budget differs')
    if sha(blob)!=ASSET_SHA256:raise ValueError('imprint resource identity differs; review regenerated artwork before updating the pin')
    manifest=dict(schema='m10v-film-imprints/v2',blob_length=len(blob),blob_sha256=sha(blob),
        sources=sources,assets=assets,format='NV12_IMPRINT_Y_SPLIT_UNSIGNED_CBCR',
        coordinates='sensor-fixed; EXIF rotates photo and print together',
        camera_tested=False,exact_rgb_screen=False,cpu_pixel_access=False,
        model='split unsigned UV weights with native identity weight tables and bounded Y exposure')
    prefix.parent.mkdir(parents=True,exist_ok=True)
    prefix.with_suffix('.raw').write_bytes(blob)
    prefix.with_suffix('.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest,bytes(blob)
