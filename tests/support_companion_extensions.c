#include "extensions.h"
#include "transaction.h"
#include "auth.h"
#include <assert.h>
#include <string.h>
typedef struct {m10v_extension_owner owner;m10v_extension_snapshot state;int writes,busy,blocked,uncertain,failread,mismatch,locked,current;} fixture;
static int current(void*v){return ((fixture*)v)->current;}
static int enter(void*v){fixture*f=v;if(f->locked)return 0;f->locked=1;return 1;}
static void leave(void*v){((fixture*)v)->locked=0;}
static int busy(void*v){return ((fixture*)v)->busy;}
static int blocked(void*v){return ((fixture*)v)->blocked;}
static int read_state(void*v,m10v_extension_snapshot*s){fixture*f=v;if(f->writes>=2&&f->failread)return M10V_ERROR_BRIDGE_UNAVAILABLE;*s=f->state;return 0;}
static int write_state(void*v,uint32_t field,uint32_t value){fixture*f=v;f->writes++;if(!f->mismatch){f->state.values[field]=value;f->state.revision[0]++;}return f->uncertain?M10V_IO_UNCERTAIN:M10V_IO_OK;}
static void torn_actions(void){
 fixture f={0};f.current=1;f.state.available=1u<<24;f.state.revision[0]=1;f.state.values[24]=1;
 m10v_extension_services io={.ctx=&f,.owner=&f.owner,.is_current=current,.enter=enter,.leave=leave,.is_busy=busy,.blocked=blocked,.read=read_state,.write=write_state};
 m10v_extension_patch p={.field=24,.value=1};p.request_id[0]=1;p.base_revision[0]=1;assert(m10v_unhex(M10V_EXTENSIONS_HASH,32,p.contract_hash));m10v_extension_result r;
 assert(m10v_extensions_valid(&f.state));
 assert(!m10v_extensions_apply(&p,&io,&r));assert(f.writes==1&&r.status==M10V_OPERATION_COMMITTED&&r.snapshot.revision[0]==2);
 assert(!m10v_extensions_apply(&p,&io,&r));assert(f.writes==1);
 p.request_id[0]=2;assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_REVISION_CONFLICT&&f.writes==1);
 memcpy(p.base_revision,f.state.revision,32);
 for(unsigned stage=2;stage<=4;stage++){f.state.values[24]=stage;assert(m10v_extensions_valid(&f.state));p.value=stage;assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_INVALID_RECIPE&&f.writes==1);}
 p.value=0;assert(!m10v_extensions_apply(&p,&io,&r));assert(f.writes==2&&r.snapshot.values[24]==0);
 assert(m10v_extension_persistent[24]==0);
}
int main(void){
 torn_actions();
 fixture f={0};f.current=1;f.state.available=7;f.state.revision[0]=1;
 m10v_extension_services io={.ctx=&f,.owner=&f.owner,.is_current=current,.enter=enter,.leave=leave,.is_busy=busy,.blocked=blocked,.read=read_state,.write=write_state};
 m10v_extension_patch p={.field=0,.value=1};p.request_id[0]=1;p.base_revision[0]=1;assert(m10v_unhex(M10V_EXTENSIONS_HASH,32,p.contract_hash));
 m10v_extension_result r;
 assert(!m10v_extensions_apply(&p,&io,&r));assert(r.status==M10V_OPERATION_COMMITTED&&r.has_snapshot&&r.snapshot.values[0]==1&&f.writes==1);
 assert(!m10v_extensions_apply(&p,&io,&r));assert(f.writes==1);
 p.value=0;assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_INVALID_RECIPE&&f.writes==1);
 p.request_id[0]=2;assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_REVISION_CONFLICT&&f.writes==1);
 memcpy(p.base_revision,f.state.revision,32);f.blocked=1;assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_BUSY);f.blocked=0;
 f.busy=1;assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_BUSY);f.busy=0;
 p.field=21;assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_INVALID_RECIPE);p.field=3;assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_INVALID_RECIPE);p.field=0;
 f.uncertain=1;f.failread=1;assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_RESULT_UNKNOWN);assert(r.status==M10V_OPERATION_UNKNOWN&&f.writes==2);
 assert(m10v_extensions_apply(&p,&io,&r)==M10V_ERROR_RESULT_UNKNOWN&&f.writes==2);
 m10v_extension_patch other=p;other.request_id[0]=3;assert(m10v_extensions_apply(&other,&io,&r)==M10V_ERROR_BUSY&&f.writes==2);
 assert(m10v_extensions_poll(p.request_id,&io,&r)==M10V_ERROR_RESULT_UNKNOWN&&f.writes==2);
 f.failread=0;assert(!m10v_extensions_poll(p.request_id,&io,&r));assert(r.status==M10V_OPERATION_COMMITTED&&f.writes==2&&!f.owner.pending.present);
 other=p;other.request_id[0]=4;other.value=1;memcpy(other.base_revision,f.state.revision,32);f.mismatch=1;
 assert(m10v_extensions_apply(&other,&io,&r)==M10V_ERROR_READBACK_MISMATCH);assert(r.status==M10V_OPERATION_UNKNOWN&&f.writes==3);
 assert(m10v_extensions_poll(other.request_id,&io,&r)==M10V_ERROR_RESULT_UNKNOWN&&f.writes==3);
 return 0;
}
