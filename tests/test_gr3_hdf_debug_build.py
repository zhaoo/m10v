"""Debug candidates must compile with and without the optional border menu."""
import shutil,subprocess,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class HdfDebugBuildTests(unittest.TestCase):
 def test_debug_hdf_without_border_compiles_for_grouped_and_standalone_menus(self):
  compiler=shutil.which('clang')
  for grouped in (0,1):
   with self.subTest(grouped=grouped):
    subprocess.run([compiler,'--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-DM10V_DEBUG_MODE=1','-DM10V_HDF_ENABLED=1','-DM10V_BORDER_ENABLED=0',f'-DM10V_HDF_GROUPED={grouped}','-fsyntax-only',str(ROOT/'native/gr3/m10v_hdf_menu.c')],check=True,capture_output=True)
