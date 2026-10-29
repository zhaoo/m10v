"""Custom SD films remain reachable through the curated camera catalog."""
import subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include "m10v_settings.h"
#include "m10v_film_directory.h"
#include <assert.h>
static m10v_library_state saved;
static unsigned writes, changed, fail_extent;
static unsigned extent(void *c){(void)c;return fail_extent?0:M10V_DIRECTORY_COUNT+2;}
static int store(void *c,const m10v_library_state *s){(void)c;(void)s;writes++;return 0;}
static int load(void *c,m10v_library_state *s){(void)c;*s=saved;return 0;}
static unsigned item(void *c,unsigned i){(void)c;
 if(i<M10V_DIRECTORY_COUNT)return i==0?33:0;
 if(i==M10V_DIRECTORY_COUNT)return changed?80:79;
 return i==M10V_DIRECTORY_COUNT+1?288:0;
}
static int install(void *c,unsigned i,unsigned id,unsigned slot){(void)c;
 assert(i>=M10V_DIRECTORY_COUNT&&item(c,i)==id);
 return m10v_library_select_custom(&saved,slot,id,20,store,0);
}
static int remove_film(void *c,unsigned slot){(void)c;return m10v_library_remove(&saved,slot,store,0);}
static int stamp(void *c,unsigned a,unsigned b,unsigned d,unsigned e){(void)c;return m10v_library_stamp(&saved,a,b,d,e,store,0);}
static int name(void *c,unsigned v){(void)c;return m10v_library_film_name_stamp(&saved,v,store,0);}
int main(void){
 m10v_settings_ops o={0,load,item,install,remove_film,stamp,name};m10v_settings p;
 o.extent=extent;
 m10v_library_init(&saved);
 while(m10v_library_count(&saved))assert(remove_film(0,0)==0);
 unsigned before=writes;
 fail_extent=1;assert(m10v_settings_open(&p,&o,M10V_SETTINGS_FILMS)==0);
 assert(p.error==M10V_SETTINGS_SAVE_FAILED);
 fail_extent=0;m10v_settings_key(&p,&o,M10V_KEY_OK);
 assert(p.group==M10V_DIRECTORY_COUNT+2&&p.expected==33&&!p.error&&writes==before);
 p.index=M10V_DIRECTORY_COUNT+9;p.error=M10V_SETTINGS_SAVE_FAILED;
 m10v_settings_key(&p,&o,M10V_KEY_LEFT);
 assert(p.index==0&&p.expected==33&&!p.error);
 p.index=M10V_DIRECTORY_COUNT+9;m10v_settings_key(&p,&o,M10V_KEY_BACK);
 assert(p.screen==M10V_SETTINGS_CLOSED);
 assert(m10v_settings_open(&p,&o,M10V_SETTINGS_FILMS)==0);
 m10v_settings_key(&p,&o,M10V_KEY_RIGHT);
 assert(p.index==M10V_DIRECTORY_COUNT&&p.expected==79&&writes==before);
 changed=1;m10v_settings_key(&p,&o,M10V_KEY_OK);
 assert(p.error==M10V_SETTINGS_CHANGED&&writes==before);
 changed=0;m10v_settings_key(&p,&o,M10V_KEY_OK);
 assert(!p.error&&saved.slots[0].film==79&&writes==before+1);
 m10v_settings_key(&p,&o,M10V_KEY_CLEAN);
 assert(saved.slots[0].film==79&&writes==before+1);
 m10v_settings_key(&p,&o,M10V_KEY_RIGHT);
 assert(p.expected==288);m10v_settings_key(&p,&o,M10V_KEY_RIGHT);assert(p.expected==288);
 m10v_settings_key(&p,&o,M10V_KEY_OK);assert(saved.slots[1].film==288);
 m10v_settings_key(&p,&o,M10V_KEY_LEFT);m10v_settings_key(&p,&o,M10V_KEY_OK);
 assert(m10v_library_count(&saved)==1&&saved.slots[0].film==288);
 return 0;
}
'''
class CustomCatalogTests(unittest.TestCase):
 def test_custom_navigation_install_stale_identity_and_cleanup(self):
  with tempfile.TemporaryDirectory() as tmp:
   t=Path(tmp);(t/'test.c').write_text(HARNESS)
   sources=['m10v_settings.c','m10v_library.c','halation_core.c','film_5207.c','film_harman.c','film_curated.c','film_newstocks.c','film_style_filters_0.c','film_style_filters_1.c','film_d76_0.c','film_d76_1.c']
   subprocess.run(['clang','-O1','-g','-DM10V_APPENDED_SLOTS=1','-fsanitize=address,undefined','-I',str(ROOT/'native/gr3'),str(t/'test.c'),*[str(ROOT/'native/gr3'/s) for s in sources],'-o',str(t/'test')],check=True,capture_output=True)
   r=subprocess.run([str(t/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
