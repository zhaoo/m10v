#include "../native/companion/transaction.h"
#include <string.h>
typedef struct {m10v_companion_snapshot snapshot;m10v_companion_owner owner;m10v_companion_owner_services services;unsigned saves,locked,busy;} fixture;
static int current(void*ctx){(void)ctx;return 1;}
static int enter(void*ctx){fixture*f=ctx;if(f->locked)return 0;f->locked=1;return 1;}
static void leave(void*ctx){((fixture*)ctx)->locked=0;}
static int busy(void*ctx){return (int)((fixture*)ctx)->busy;}
static int snapshot(void*ctx,m10v_companion_snapshot*out){*out=((fixture*)ctx)->snapshot;return 0;}
static int persist(void*ctx,const m10v_library_state*s){fixture*f=ctx;f->saves++;f->snapshot.state=*s;return 0;}
static void init(fixture*f){
 memset(f,0,sizeof(*f));m10v_library_init(&f->snapshot.state);
 for(unsigned i=0;i<M10V_SLOT_COUNT;i++){
  m10v_slot*s=&f->snapshot.state.slots[i];memset(s,0,sizeof(*s));s->film=(uint16_t)(34+i);s->halo_spread=3;s->halo_threshold=5;s->halo_profile=6;
  memset(&f->snapshot.state.effects[i],0,sizeof(f->snapshot.state.effects[i]));
 }
 f->snapshot.active_slot=9;f->snapshot.state.stamp=2;f->snapshot.state.format=3;f->snapshot.state.corner=2;f->snapshot.state.color=1;f->snapshot.state.reserved=1;
 m10v_companion_state_seal(&f->snapshot.state,17);
 f->services.ctx=f;f->services.owner=&f->owner;f->services.is_current=current;f->services.enter=enter;f->services.leave=leave;f->services.is_busy=busy;f->services.snapshot=snapshot;f->services.persist_once=persist;
 memset(&f->services.metadata,0x22,sizeof(f->services.metadata));m10v_companion_snapshot_identity(&f->services.metadata,&f->snapshot);
}
int parse_ten(const uint8_t*text,unsigned bytes){m10v_companion_patch p;int c=m10v_operation_parse(text,bytes,&p);if(c)return c;return p.slots_mask!=(1u<<9)||p.values[9][M10V_FIELD_FILMID]!=321;}
int test_ten_case(unsigned mode){
 fixture f;init(&f);if(!m10v_library_valid(&f.snapshot.state))return 100;
 if(mode==0){m10v_companion_snapshot b=f.snapshot;b.state.slots[9].grain=1;m10v_companion_state_seal(&b.state,b.state.sequence);if(m10v_companion_snapshot_identity(&f.services.metadata,&b))return 101;return !memcmp(f.snapshot.config_hash,b.config_hash,32)||!memcmp(f.snapshot.revision,b.revision,32);}
 m10v_companion_snapshot before=f.snapshot;m10v_companion_patch p;memset(&p,0,sizeof(p));memcpy(p.boot_id,f.services.metadata.boot_id,16);memcpy(p.catalog_hash,f.services.metadata.catalog_hash,32);memcpy(p.renderer_hash,f.services.metadata.renderer_hash,32);memcpy(p.base_revision,before.revision,32);memset(p.request_id,0x77,16);p.activate_slot=-1;p.slots_mask=1u<<9;p.fields[9]=1u<<M10V_FIELD_GRAIN;p.values[9][M10V_FIELD_GRAIN]=2;
 if(mode==2)f.busy=1;
 if(mode==3){p.fields[9]=1u<<M10V_FIELD_FILMID;p.values[9][M10V_FIELD_FILMID]=321;}
 if(mode==4){p.fields[9]=1u<<M10V_FIELD_GRAIN;p.values[9][M10V_FIELD_GRAIN]=99;}
 m10v_companion_result result;int code=m10v_companion_apply(&before,&p,&f.services,&result);
 if(mode==2||mode==4)return !code||f.saves||memcmp(&before.state,&f.snapshot.state,sizeof(before.state));
 if(code||f.saves!=1||result.status!=M10V_OPERATION_COMMITTED||!result.has_snapshot)return 102;
 for(unsigned i=0;i<9;i++)if(memcmp(&before.state.slots[i],&f.snapshot.state.slots[i],sizeof(m10v_slot))||memcmp(&before.state.effects[i],&f.snapshot.state.effects[i],sizeof(m10v_film_effects)))return 103;
 if(before.state.stamp!=f.snapshot.state.stamp||before.state.reserved!=f.snapshot.state.reserved)return 104;
 if(m10v_companion_apply(&before,&p,&f.services,&result)||f.saves!=1)return 105;
 return mode==3?f.snapshot.state.slots[9].film!=321:f.snapshot.state.slots[9].grain!=2;
}

int parse_ten_full(const uint8_t*text,unsigned bytes){m10v_companion_patch p;int c=m10v_operation_parse(text,bytes,&p);if(c)return c;return p.slots_mask!=1023;}
