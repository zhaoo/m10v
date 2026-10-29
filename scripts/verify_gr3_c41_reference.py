"""Stdlib build-time provenance, inventory and packed profile readback."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def verify(root=ROOT):
 from scripts.verify_gr3_anime_e6_reference import verify_profile
 from scripts.fit_gr3_c41_native import native_header
 root=Path(root);ref=json.loads((root/'native/gr3/c41-reference.json').read_text());web=json.loads((root/'web/gr3/c41-luts.json').read_text())
 if ref['camera_validated'] or ref['default_camera_renderer']!='quantized native ISP; no CPU color LUT':raise ValueError('unsupported fidelity claim')
 if [s['id'] for s in web['stocks']]!=[312,313] or [s['film_id'] for s in ref['native_profiles_full']]!=[312,313]:raise ValueError('C41 inventory')
 for p,h in ref['files'].items():
  if hashlib.sha256((root/p).read_bytes()).hexdigest()!=h:raise ValueError('C41 source changed: '+p)
 for stock,spec,q in zip(web['stocks'],ref['stocks'],ref['native_profiles_full']):
  verify_profile(q)
  for item in [stock,spec]:
   if not item['approximation'] or item['official_lut'] or item['film_calibrated'] or item['camera_calibrated']:raise ValueError('unsupported fidelity claim')
  for key,digest in [('values','table_sha256'),('native_values','native_preview_sha256')]:
   v=stock[key]
   if len(v)!=10125 or any(type(x)is not int or not 0<=x<=255 for x in v) or hashlib.sha256(bytes(v)).hexdigest()!=spec[digest]:raise ValueError('C41 table digest/bounds')
 if web['stocks'][0]['values']==web['stocks'][1]['values']:raise ValueError('aliased C41 targets')
 if (root/'native/gr3/m10v_c41_native_profiles.h').read_text()!=native_header(ref):raise ValueError('C41 native readback')
 return ref
if __name__=='__main__':verify();print('C41 reference verified')
