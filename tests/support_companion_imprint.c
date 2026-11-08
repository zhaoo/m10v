#include "../native/companion/extensions.h"
#include "../native/companion/transaction.h"
#include "../native/companion/auth.h"
#include "../native/gr3/m10v_isp_effects_camera.h"
#include <assert.h>
#include <string.h>
#define M10V_COMPANION_EXT_ISP 1
typedef struct {
 uint32_t ui_owner,store_depth,locked;
 m10v_companion_owner transaction;
 m10v_extension_owner extensions;
 m10v_companion_owner_services services;
} ui_context;
static m10v_isp_effects_settings settings;
static uint32_t sequence,writes,fail_read;
static int current(void*v){(void)v;return 1;}
static int busy(void*v){(void)v;return 0;}
static int enter(void*v){((ui_context*)v)->locked=1;return 1;}
static void leave(void*v){((ui_context*)v)->locked=0;}
static void zero(void*p,unsigned n){memset(p,0,n);}
static void copy(void*d,const void*s,unsigned n){memcpy(d,s,n);}
static int snapshot(ui_context*c,m10v_companion_snapshot*out){(void)c;memset(out,0,sizeof(*out));return 0;}
uint32_t m10v_settings_controller_remote_busy(void){return 0;}
int m10v_camera_library_read_current(m10v_library_state*s){(void)s;assert(0);return -1;}
int m10v_camera_library_commit_snapshot(const m10v_library_state*s){(void)s;assert(0);return -1;}
void m10v_companion_state_seal(m10v_library_state*s,uint32_t n){(void)s;(void)n;assert(0);}
int m10v_isp_effects_camera_snapshot(m10v_isp_effects_settings*out,uint32_t*seq){if(fail_read)return 0;*out=settings;*seq=sequence;return 1;}
int m10v_isp_effects_camera_save(uint32_t owner,const m10v_isp_effects_settings*next){assert(owner==123);writes++;settings=*next;sequence++;if(writes==8)fail_read=1;return 0;}
#include "../native/gr3/m10v_companion_extensions.inc"
int m10v_test_remote_imprint(void){
 ui_context owner={0};owner.ui_owner=123;
 m10v_isp_effects_defaults(&settings);settings.leak_gain=2;settings.blur_gain=1;settings.grain_size=2;
 m10v_extension_services io=extension_services(&owner);
 m10v_extension_snapshot state;
 assert(!extension_read(&owner,&state));assert(state.available&(1u<<21));
 m10v_extension_patch p={.field=21};assert(m10v_unhex(M10V_EXTENSIONS_HASH,32,p.contract_hash));
 m10v_extension_result result;
 for(unsigned style=0;style<=7;style++){
  p.request_id[0]=(uint8_t)(style+1);p.value=style;memcpy(p.base_revision,state.revision,32);
  assert(!m10v_extensions_apply(&p,&io,&result));assert(result.status==M10V_OPERATION_COMMITTED);
  assert(result.snapshot.values[21]==style);assert(m10v_isp_effects_imprint(&settings)==style);
  assert(settings.leak_gain==2&&settings.blur_gain==1&&settings.grain_size==2);
  state=result.snapshot;assert(writes==style);
 }
 p.request_id[0]=10;p.value=8;memcpy(p.base_revision,state.revision,32);
 assert(m10v_extensions_apply(&p,&io,&result)==M10V_ERROR_INVALID_RECIPE);assert(writes==7);
 p.request_id[0]=11;p.value=0;
 assert(m10v_extensions_apply(&p,&io,&result)==M10V_ERROR_RESULT_UNKNOWN);assert(writes==8);
 assert(m10v_extensions_apply(&p,&io,&result)==M10V_ERROR_RESULT_UNKNOWN);assert(writes==8);
 fail_read=0;assert(!m10v_extensions_poll(p.request_id,&io,&result));
 assert(result.status==M10V_OPERATION_COMMITTED&&result.snapshot.values[21]==0&&writes==8);
 return 0;
}
