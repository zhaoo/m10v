"""Actual C renderer, journal ABI and independent integer LUT interpolation."""
import ctypes as C,json,random,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Slot(C.Structure):
 _fields_=[('film',C.c_uint16)]+[(n,C.c_uint8) for n in ('grain','soft','gain','spread','threshold','profile')]
class State(C.Structure):
 _fields_=[('magic',C.c_uint32),('version',C.c_uint16),('size',C.c_uint16),('sequence',C.c_uint32),('slots',Slot*10),('stamp',C.c_uint8),('format',C.c_uint8),('corner',C.c_uint8),('color',C.c_uint8),('effects',(C.c_uint8*8)*10),('reserved',C.c_uint32),('crc',C.c_uint32)]
class Image(C.Structure):
 _fields_=[('y',C.POINTER(C.c_uint8)),('chroma',C.POINTER(C.c_uint8))]+[(n,C.c_uint32) for n in ('y_bytes','chroma_bytes','width','height','stride')]
STORE=C.CFUNCTYPE(C.c_int,C.c_void_p,C.POINTER(State))
class D76Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  out=Path(cls.tmp.name)/'d76.so';sources=['m10v_library.c','halation_core.c','film_5207.c','film_harman.c','film_curated.c','film_newstocks.c','film_style_filters_0.c','film_style_filters_1.c','film_d76_0.c','film_d76_1.c']
  subprocess.run(['clang','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror','-DM10V_APPENDED_SLOTS=1',*[str(ROOT/'native/gr3'/p) for p in sources],'-o',str(out)],check=True,capture_output=True)
  cls.lib=C.CDLL(str(out));cls.rgb=cls.lib.m10v_harman_rgb;cls.rgb.argtypes=[C.c_uint32,C.POINTER(C.c_uint8),C.POINTER(C.c_uint8)]
  cls.lib.m10v_library_select.argtypes=[C.POINTER(State),C.c_uint32,C.c_uint32,STORE,C.c_void_p]
  cls.lib.m10v_library_render_native.argtypes=[C.POINTER(Image),C.POINTER(State),C.c_uint32,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32,C.c_uint32]
 def test_all_seven_c_tables_match_independent_tetrahedra_at_endpoints_neutrals_and_random_rgb(self):
  stocks=json.loads((ROOT/'web/gr3/d76-luts.json').read_text())['stocks'];rng=random.Random(305299)
  cases=[(r,g,b) for r in [0,255] for g in [0,255] for b in [0,255]]+[(i,i,i) for i in range(256)]+[tuple(rng.randrange(256) for _ in range(3)) for _ in range(1024)]
  for variant,stock in enumerate(stocks,23):
   table=stock['values']
   for rgb in cases:
    q=[v*14 for v in rgb];base=[min(v//255,13) for v in q];f=[q[i]-base[i]*255 for i in range(3)];axes=sorted(range(3),key=lambda i:-f[i]);w=[255-f[axes[0]],f[axes[0]]-f[axes[1]],f[axes[1]]-f[axes[2]],f[axes[2]]]
    at=(base[0]*225+base[1]*15+base[2])*3;corners=[at]
    for axis in axes:corners.append(corners[-1]+[675,45,3][axis])
    expected=[(sum(w[j]*table[corners[j]+c] for j in range(4))+127)//255 for c in range(3)]
    out=(C.c_uint8*3)();self.rgb(variant,(C.c_uint8*3)(*rgb),out);self.assertEqual(list(out),expected)
 def test_new_id_journals_are_atomic_and_native_completion_preserves_color_and_padding(self):
  self.assertEqual(C.sizeof(State),184);state=State();self.lib.m10v_library_init(C.byref(state));good=STORE(lambda c,s:0);bad=STORE(lambda c,s:-1)
  for film in range(299,306):
   before=bytes(state);self.assertEqual(self.lib.m10v_library_select(C.byref(state),0,film,bad,None),-2);self.assertEqual(bytes(state),before)
   other=bytes(state.slots)[8:];self.assertEqual(self.lib.m10v_library_select(C.byref(state),0,film,good,None),0);self.assertEqual(bytes(state.slots)[8:],other)
   self.assertEqual(self.lib.m10v_library_valid(C.byref(state)),1);outputs=[]
   for mask in (0,31):
    y=(C.c_uint8*6)(70,110,150,190,91,92);uv=(C.c_uint8*6)(80,180,145,90,93,94);image=Image(y,uv,6,6,4,1,6)
    self.assertEqual(self.lib.m10v_library_render_native(C.byref(image),C.byref(state),0,None,1,None,0,mask),0)
    self.assertEqual(list(y)[4:],[91,92]);self.assertEqual(list(uv)[4:],[93,94]);outputs.append((list(y),list(uv)))
   self.assertEqual(outputs[0][1],[128,128,128,128,93,94])
   self.assertEqual(outputs[1],([70,110,150,190,91,92],[80,180,145,90,93,94]))
 def test_fitted_color_completion_does_not_repeat_the_cpu_lut(self):
  for film in (77,298,*range(291,298),*range(299,306)):
   state=State();self.lib.m10v_library_init(C.byref(state));good=STORE(lambda c,s:0)
   self.assertEqual(self.lib.m10v_library_select(C.byref(state),0,film,good,None),0)
   y=(C.c_uint8*6)(70,110,150,190,91,92);uv=(C.c_uint8*6)(80,180,145,90,93,94);image=Image(y,uv,6,6,4,1,6)
   before=(bytes(y),bytes(uv),bytes(state))
   self.assertEqual(self.lib.m10v_library_render_native(C.byref(image),C.byref(state),0,None,1,None,0,1),0)
   self.assertEqual((bytes(y),bytes(uv),bytes(state)),before,film)
 def test_stdlib_provenance_and_neutral_interpolation_targets(self):
  from scripts.verify_gr3_d76_reference import verify
  self.assertEqual(len(verify(ROOT)),7)
  ref=json.loads((ROOT/'native/gr3/d76-reference.json').read_text())
  for s in ref['stocks']:
   self.assertLess(s['interpolation']['delta_e00_p95'],.6)
   self.assertLess(s['interpolation']['delta_e00_max'],2)
  self.assertEqual(ref['stocks'][-1]['formulation'],'MKII')
if __name__=='__main__':unittest.main()
