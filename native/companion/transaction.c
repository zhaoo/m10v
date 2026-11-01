#include "transaction.h"
#include "auth.h"
#include <stddef.h>
_Static_assert(sizeof(m10v_library_state)==184&&offsetof(m10v_library_state,crc)==180,"retain M10V v5 journal ABI");
static void zero(void*p,unsigned size){for(unsigned i=0;i<size;i++)((uint8_t*)p)[i]=0;}
static void copy(void*d,const void*s,unsigned size){for(unsigned i=0;i<size;i++)((uint8_t*)d)[i]=((const uint8_t*)s)[i];}
static int equal(const void*a,const void*b,unsigned size){return m10v_constant_equal(a,b,size);}
void m10v_companion_owner_init(m10v_companion_owner*owner){if(owner)zero(owner,sizeof(*owner));}
void m10v_companion_state_seal(m10v_library_state*state,uint32_t sequence){
 state->sequence=sequence;uint32_t crc=~0u;const uint8_t*bytes=(const uint8_t*)state;
 for(unsigned i=0;i<offsetof(m10v_library_state,crc);i++){crc^=bytes[i];for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u);}state->crc=~crc;
}
int m10v_companion_snapshot_identity(const m10v_companion_metadata*meta,m10v_companion_snapshot*s){
 if(!meta||!s||!m10v_library_valid(&s->state)||s->active_slot < -1||s->active_slot>=(int)M10V_SLOT_COUNT||s->busy>1)return M10V_ERROR_BRIDGE_UNAVAILABLE;
 uint8_t bytes[512];unsigned n=0;const char *prefix="m10v-config/v2";for(unsigned i=0;prefix[i];i++)bytes[n++]=(uint8_t)prefix[i];
 for(unsigned i=12;i<offsetof(m10v_library_state,crc);i++)bytes[n++]=((const uint8_t*)&s->state)[i];
 for(unsigned slot=0;slot<M10V_SLOT_COUNT;slot++){if(M10V_BUILTIN(s->state.slots[slot].film))zero(s->custom_hashes[slot],32);for(unsigned i=0;i<32;i++)bytes[n++]=s->custom_hashes[slot][i];}bytes[n++]=(uint8_t)s->active_slot;m10v_sha256(bytes,n,s->config_hash);
 n=0;prefix="m10v-revision/v2";for(unsigned i=0;prefix[i];i++)bytes[n++]=(uint8_t)prefix[i];const uint8_t*parts[]={meta->boot_id,meta->build_id,meta->catalog_hash,meta->renderer_hash,s->config_hash};const unsigned sizes[]={16,32,32,32,32};for(unsigned p=0;p<5;p++)for(unsigned i=0;i<sizes[p];i++)bytes[n++]=parts[p][i];for(unsigned i=0;i<4;i++)bytes[n++]=(uint8_t)(s->state.sequence>>(8*i));for(unsigned i=0;i<4;i++)bytes[n++]=(uint8_t)(meta->owner_generation>>(8*i));m10v_sha256(bytes,n,s->revision);return 0;
}
static int rejected(m10v_companion_result*out,unsigned code){zero(out,sizeof(*out));out->status=M10V_OPERATION_REJECTED;out->code=code;return (int)code;}
static int acquire(const m10v_companion_owner_services*io,m10v_companion_result*out){
 if(!io||!io->owner||!io->is_current||!io->enter||!io->leave||!io->is_busy||!io->snapshot||!io->is_current(io->ctx))return rejected(out,M10V_ERROR_BRIDGE_UNAVAILABLE);
 if(!io->enter(io->ctx))return rejected(out,M10V_ERROR_BUSY);
 if(!io->is_current(io->ctx)){io->leave(io->ctx);return rejected(out,M10V_ERROR_BRIDGE_UNAVAILABLE);}return 0;
}
static int fresh(const m10v_companion_owner_services*io,m10v_companion_snapshot*out){if(!io->is_current(io->ctx))return M10V_ERROR_BRIDGE_UNAVAILABLE;int code=io->snapshot(io->ctx,out);if(code)return code;if(!io->is_current(io->ctx))return M10V_ERROR_BRIDGE_UNAVAILABLE;return m10v_companion_snapshot_identity(&io->metadata,out);}
static int matches(const m10v_companion_snapshot*a,const m10v_companion_snapshot*b){return a->active_slot==b->active_slot&&equal(&a->state,&b->state,sizeof(a->state))&&equal(a->custom_hashes,b->custom_hashes,sizeof(a->custom_hashes));}
static void complete_record(m10v_companion_owner*owner,m10v_companion_owner_record*r,unsigned status,unsigned code,const m10v_companion_snapshot*actual){
 zero(&r->result,sizeof(r->result));r->result.status=status;r->result.code=code;if(actual){r->result.has_snapshot=1;r->result.snapshot=*actual;}
 if(status!=M10V_OPERATION_UNKNOWN){if(r->remote){owner->remote_cache=*r;owner->remote_cache.present=1;}r->present=0;}
}
static int set_field(m10v_companion_snapshot*next,unsigned slot,unsigned key,unsigned value){
 unsigned film=next->state.slots[slot].film;if(!m10v_field_supported(key,film)||value>m10v_field_max(key,film))return M10V_ERROR_INVALID_RECIPE;
 m10v_slot*v=&next->state.slots[slot];m10v_film_effects*e=&next->state.effects[slot];switch(key){
 case M10V_FIELD_GRAIN:v->grain=(uint8_t)value;break;case M10V_FIELD_GRAINSIZE:e->grain_size=(uint8_t)value;break;case M10V_FIELD_HALOGAIN:v->halo_gain=(uint8_t)value;break;case M10V_FIELD_HALOSPREAD:v->halo_spread=(uint8_t)value;break;case M10V_FIELD_HALOTHRESHOLD:v->halo_threshold=(uint8_t)value;break;case M10V_FIELD_HALOPROFILE:v->halo_profile=(uint8_t)value;break;
 case M10V_FIELD_LEAKGAIN:e->leak_gain=(uint8_t)value;break;case M10V_FIELD_LEAKPOSITION:e->leak_position=(uint8_t)value;break;case M10V_FIELD_LEAKSPREAD:e->leak_spread=(uint8_t)value;break;case M10V_FIELD_LEAKVARIATION:e->leak_variation=(uint8_t)value;break;case M10V_FIELD_FILMEXPOSURE:e->film_exposure=(uint8_t)value;break;case M10V_FIELD_CHARMERACOLOR:e->reserved[1]=(uint8_t)value;break;default:return M10V_ERROR_INVALID_RECIPE;}return 0;
}
static int prepare(const m10v_companion_patch*p,const m10v_companion_owner_services*io,m10v_companion_snapshot*next){
 if(p->slots_mask&~((1u<<M10V_SLOT_COUNT)-1u)||p->activate_slot < -1||p->activate_slot>=(int)M10V_SLOT_COUNT||(p->slots_mask&&p->activate_slot>=0)||(!p->slots_mask&&p->activate_slot<0))return M10V_ERROR_INVALID_RECIPE;
 for(unsigned slot=0;slot<M10V_SLOT_COUNT;slot++){
  unsigned mask=p->fields[slot];if((mask&~((1u<<(M10V_FIELD_COUNT+1))-1))||(!(p->slots_mask&(1u<<slot))&&mask)||((p->slots_mask&(1u<<slot))&&!mask))return M10V_ERROR_INVALID_RECIPE;if(!mask)continue;if(mask&M10V_READONLY_MASK)return M10V_ERROR_INVALID_RECIPE;
  m10v_slot*v=&next->state.slots[slot];m10v_film_effects*e=&next->state.effects[slot];unsigned previous=v->film;
  if(mask&(1u<<M10V_FIELD_FILMID)){unsigned id=p->values[slot][M10V_FIELD_FILMID];if(!id||(!M10V_BUILTIN(id)&&!M10V_CUSTOM(id)))return M10V_ERROR_INVALID_RECIPE;v->film=(uint16_t)id;}
  if(M10V_CUSTOM(v->film)){
   if(mask&M10V_CUSTOM_HASH_FIELD){unsigned bank=2;if(!io->resolve_custom)return M10V_ERROR_BRIDGE_UNAVAILABLE;int code=io->resolve_custom(io->ctx,slot,v->film,p->custom_hashes[slot],&bank);if(code)return code;if(bank>1)return M10V_ERROR_INVALID_RECIPE;e->reserved[0]=(uint8_t)(bank+1);copy(next->custom_hashes[slot],p->custom_hashes[slot],32);}
   else if(v->film!=previous)return M10V_ERROR_INVALID_RECIPE;
  }else {if(mask&M10V_CUSTOM_HASH_FIELD)return M10V_ERROR_INVALID_RECIPE;if(v->film!=previous){e->reserved[0]=0;zero(next->custom_hashes[slot],32);}}
  if(v->film!=previous){
   /* Keep applicable omitted fields. Clear only incompatible legacy state:
    * EI/bank/Charmera bits and the removed soft control cannot cross looks. */
   v->soft=0;if(v->film!=289)e->reserved[1]=0;if((v->film!=67&&v->film!=68)||(v->film==67&&e->film_exposure>1))e->film_exposure=0;
   if(v->film==289){v->grain=0;e->leak_gain=0;}
  }
  for(unsigned key=1;key<M10V_FIELD_COUNT;key++)if(mask&(1u<<key)){int code=set_field(next,slot,key,p->values[slot][key]);if(code)return code;}
 }
 if(p->activate_slot>=0){if(!next->state.slots[(unsigned)p->activate_slot].film)return M10V_ERROR_INVALID_RECIPE;next->active_slot=p->activate_slot;}
 return 0;
}
static int apply(const m10v_companion_snapshot*base,const m10v_companion_patch*p,const m10v_companion_owner_services*io,m10v_companion_result*out,unsigned remote){
 if(!out)return M10V_ERROR_INVALID_RECIPE;if(!base||!p)return rejected(out,M10V_ERROR_INVALID_RECIPE);int code=acquire(io,out);if(code)return code;
 m10v_companion_owner*owner=io->owner;uint8_t digest[32];m10v_operation_digest(p,digest);
 if(remote&&owner->pending.present&&owner->pending.remote&&equal(owner->pending.id,p->request_id,16)){
  if(!equal(owner->pending.digest,digest,32))code=rejected(out,M10V_ERROR_INVALID_RECIPE);else {*out=owner->pending.result;code=(int)out->code;}goto done;
 }
 if(remote&&owner->remote_cache.present&&equal(owner->remote_cache.id,p->request_id,16)){
  if(!equal(owner->remote_cache.digest,digest,32))code=rejected(out,M10V_ERROR_INVALID_RECIPE);else {*out=owner->remote_cache.result;code=(int)out->code;}goto done;
 }
 if(owner->pending.present){code=rejected(out,M10V_ERROR_BUSY);goto done;}
 if(!equal(p->boot_id,io->metadata.boot_id,16)||!equal(base->revision,p->base_revision,32)){code=rejected(out,M10V_ERROR_REVISION_CONFLICT);goto done;}
 if(!equal(p->catalog_hash,io->metadata.catalog_hash,32)||!equal(p->renderer_hash,io->metadata.renderer_hash,32)){code=rejected(out,M10V_ERROR_INCOMPATIBLE_RENDERER);goto done;}
 if(io->is_busy(io->ctx)){code=rejected(out,M10V_ERROR_BUSY);goto done;}
 m10v_companion_snapshot current;code=fresh(io,&current);if(code){code=rejected(out,(unsigned)code);goto done;}
 if(current.busy){code=rejected(out,M10V_ERROR_BUSY);goto done;}
 if(!equal(current.revision,p->base_revision,32)){code=rejected(out,M10V_ERROR_REVISION_CONFLICT);goto done;}
 m10v_companion_snapshot expected=current;code=prepare(p,io,&expected);if(code){code=rejected(out,(unsigned)code);goto done;}
 m10v_companion_state_seal(&expected.state,current.state.sequence);code=m10v_companion_snapshot_identity(&io->metadata,&expected);if(code){code=rejected(out,M10V_ERROR_INVALID_RECIPE);goto done;}
 unsigned changed=!equal(expected.config_hash,current.config_hash,32);
 if(changed&&p->slots_mask){if(current.state.sequence==UINT32_MAX){code=rejected(out,M10V_ERROR_STORE_FAILED);goto done;}m10v_companion_state_seal(&expected.state,current.state.sequence+1);m10v_companion_snapshot_identity(&io->metadata,&expected);}
 if((changed&&p->slots_mask&&!io->persist_once)||(changed&&p->activate_slot>=0&&!io->set_tone)){code=rejected(out,M10V_ERROR_BRIDGE_UNAVAILABLE);goto done;}
 if(!io->is_current(io->ctx)||io->is_busy(io->ctx)){code=rejected(out,M10V_ERROR_BUSY);goto done;}
 m10v_companion_owner_record*r=&owner->pending;zero(r,sizeof(*r));copy(r->id,p->request_id,16);copy(r->digest,digest,32);r->present=1;r->remote=remote;r->expected=expected;
 if(!changed){complete_record(owner,r,M10V_OPERATION_COMMITTED,0,&current);*out=remote?owner->remote_cache.result:r->result;code=0;goto done;}
 int stored=p->slots_mask?io->persist_once(io->ctx,&expected.state):io->set_tone(io->ctx,(unsigned)p->activate_slot);
 if(stored==M10V_IO_NOT_WRITTEN){complete_record(owner,r,M10V_OPERATION_REJECTED,M10V_ERROR_STORE_FAILED,0);*out=r->result;code=M10V_ERROR_STORE_FAILED;goto done;}
 code=fresh(io,&current);
 if(code){complete_record(owner,r,M10V_OPERATION_UNKNOWN,M10V_ERROR_RESULT_UNKNOWN,0);*out=r->result;code=M10V_ERROR_RESULT_UNKNOWN;goto done;}
 if(!matches(&expected,&current)){complete_record(owner,r,M10V_OPERATION_UNKNOWN,M10V_ERROR_READBACK_MISMATCH,&current);*out=r->result;code=M10V_ERROR_READBACK_MISMATCH;goto done;}
 complete_record(owner,r,M10V_OPERATION_COMMITTED,0,&current);*out=r->result;code=0;
 done:io->leave(io->ctx);return code;
}
int m10v_companion_apply(const m10v_companion_snapshot*b,const m10v_companion_patch*p,const m10v_companion_owner_services*i,m10v_companion_result*r){return apply(b,p,i,r,1);}
int m10v_companion_apply_local(const m10v_companion_snapshot*b,const m10v_companion_patch*p,const m10v_companion_owner_services*i,m10v_companion_result*r){return apply(b,p,i,r,0);}
int m10v_companion_owner_poll(const m10v_companion_owner_services*io,const uint8_t id[16],m10v_companion_result*out){
 if(!out)return M10V_ERROR_INVALID_RECIPE;if(!id)return rejected(out,M10V_ERROR_INVALID_RECIPE);int code=acquire(io,out);if(code){out->status=M10V_OPERATION_UNKNOWN;return code;}m10v_companion_owner*owner=io->owner;m10v_companion_owner_record*r=&owner->pending;
 if(r->present&&equal(r->id,id,16)){
  m10v_companion_snapshot actual;code=fresh(io,&actual);
  if(!code&&matches(&r->expected,&actual)){complete_record(owner,r,M10V_OPERATION_COMMITTED,0,&actual);*out=r->result;code=0;}
  else if(!code&&io->commit_settled&&io->commit_settled(io->ctx)){complete_record(owner,r,M10V_OPERATION_REJECTED,M10V_ERROR_READBACK_MISMATCH,&actual);*out=r->result;code=M10V_ERROR_READBACK_MISMATCH;}
  else {r->result.status=M10V_OPERATION_UNKNOWN;r->result.code=M10V_ERROR_RESULT_UNKNOWN;*out=r->result;code=M10V_ERROR_RESULT_UNKNOWN;}
 }else if(owner->remote_cache.present&&equal(owner->remote_cache.id,id,16)){*out=owner->remote_cache.result;code=(int)out->code;}
 else {code=rejected(out,M10V_ERROR_RESULT_UNKNOWN);out->status=M10V_OPERATION_UNKNOWN;}
 io->leave(io->ctx);return code;
}
