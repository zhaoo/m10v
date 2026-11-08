"""Production remote adapter and owner transaction; only native cache IO is doubled."""
import ctypes,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RemoteImprint(unittest.TestCase):
 def test_all_styles_preserve_other_settings_and_uncertainty_never_replays(self):
  with tempfile.TemporaryDirectory() as tmp:
   exe=Path(tmp)/'imprint.dylib'
   names=['tests/support_companion_imprint.c','native/companion/extensions.c','native/companion/auth.c','native/gr3/m10v_isp_effects_state.c']
   result=subprocess.run(['clang','-O2','-dynamiclib','-std=c11','-Wall','-Wextra','-Werror',*[str(ROOT/name) for name in names],'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   library=ctypes.CDLL(str(exe))
   self.assertEqual(library.m10v_test_remote_imprint(),0)
