#!/usr/bin/env python3
"""ASan/UBSan validation for glyph transforms, odd strides and visible Y/C pairs."""
from pathlib import Path
import shutil
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <stdlib.h>
#include <assert.h>
#include "m10v_library.c"
int main(void){
 const uint32_t sizes[][2]={{6000,4000},{640,420},{320,240},{65,49},{17,19},{3,3},{2,1}};
 m10v_library_date date={2026,10,28,23,59};
 for(unsigned s=0;s<7;s++)for(unsigned d=0;d<5;d++)for(unsigned corner=0;corner<4;corner++){
  unsigned w=sizes[s][0],h=sizes[s][1],stride=w+3,bytes=stride*h;
  uint8_t *y=malloc(bytes+32),*uv=malloc(bytes+32);assert(y&&uv);
  for(unsigned i=0;i<bytes+32;i++){y[i]=73;uv[i]=129;}
  m10v_library_image image={y,uv,bytes,bytes,w,h,stride};
  m10v_library_state state;m10v_library_init(&state);
  state.stamp=2;state.format=corner;state.reserved=1;state.corner=corner;state.color=corner;
  stamp_oriented(&image,&state,&date,"KODAK 5207",d);
  for(unsigned row=0;row<h;row++)for(unsigned x=w;x<stride;x++){assert(y[row*stride+x]==73);assert(uv[row*stride+x]==129);}
  for(unsigned i=bytes;i<bytes+32;i++){assert(y[i]==73);assert(uv[i]==129);}
  free(y);free(uv);
 }
 return 0;
}
'''
def main():
 with tempfile.TemporaryDirectory() as tmp:
  source=Path(tmp)/'probe.c';source.write_text(HARNESS);out=Path(tmp)/'probe'
  files=['halation_core.c','film_5207.c','film_harman.c','film_curated.c','film_newstocks.c','film_style_filters_0.c','film_style_filters_1.c','film_d76_0.c','film_d76_1.c']
  subprocess.run([shutil.which('clang') or 'clang','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(ROOT/'native/gr3'),str(source),*[str(ROOT/'native/gr3'/f) for f in files],'-o',str(out)],check=True)
  subprocess.run([str(out)],check=True)
 print('Oriented production stamp:140 layouts passed ASan/UBSan and row/tail guards.')
if __name__=='__main__':main()
