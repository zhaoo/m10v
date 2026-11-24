"""Compile the real diagnostic macro to verify focused argument/call removal."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE='''#include "m10v_debug.h"
static unsigned calls,args,events,mask;
static unsigned side(void){args++;return args;}
static unsigned next_event(void){events++;return 360;}
int m10v_debug_log(uint32_t e,uint32_t a,uint32_t b,uint32_t c,uint32_t d){mask|=e==218?1u:e==270?2u:e==360?4u:e==400?8u:0u;(void)a;(void)b;(void)c;(void)d;calls++;return 0;}
unsigned probe(void){
 calls=args=events=mask=0;
 M10V_LOG(218,side(),0,0,0);
 M10V_LOG(270,side(),0,0,0);
 M10V_EXIT_LOG(270,side(),0,0,0);
 M10V_LOG(360,side(),0,0,0);
 M10V_LOG(400,side(),0,0,0);
 M10V_LOG(next_event(),side(),0,0,0);
 return calls*100+args*10+events;
}
unsigned event_mask(void){return mask;}
'''
class ControlTraceCompileTests(unittest.TestCase):
    def test_focused_macro_removes_rejected_arguments_and_preserves_single_event_evaluation(self):
        compiler=shutil.which('clang')
        if not compiler:self.skipTest('clang required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'probe.c';source.write_text(SOURCE)
            for debug,focused,controls,expected,mask in [(0,0,0,0,0),(1,0,0,551,15),(1,1,0,551,14),(1,0,1,331,12)]:
                with self.subTest(debug=debug,focused=focused,controls=controls):
                    output=root/f'probe-{debug}-{focused}-{controls}.so'
                    subprocess.run([compiler,'-shared','-fPIC','-O2','-I',str(ROOT/'native/gr3'),
                                    f'-DM10V_DEBUG_MODE={debug}',f'-DM10V_ADJ_EXIT_TRACE={focused}',f'-DM10V_CONTROLS_TRACE_ONLY={controls}',
                                    str(source),'-o',str(output)],check=True,capture_output=True)
                    library=ctypes.CDLL(str(output))
                    self.assertEqual(library.probe(),expected)
                    self.assertEqual(library.event_mask(),mask)
