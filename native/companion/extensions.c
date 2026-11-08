#include "extensions.h"
#include "transaction.h"
#include "auth.h"
#include "resident_bridge.h"
_Static_assert(sizeof(m10v_extension_patch)<=M10V_RESIDENT_PAYLOAD,"extension patch fits resident frame");
_Static_assert(sizeof(m10v_extension_result)<=M10V_RESIDENT_PAYLOAD,"extension result fits resident frame");
#if !M10V_COMPANION_RTOS_ONLY
const char *const m10v_extension_names[M10V_EXTENSION_FIELDS]={"quickSwitch","quickSwitchA","quickSwitchB","hdf","border","grainMode","grainSize","leakGain","leakPosition","leakSpread","blurGain","blurRange","stamp","stampFormat","stampCorner","stampColor","filmNameStamp","focalA","focalB","focalSlot","aspect","imprint"};
#endif
const uint8_t m10v_extension_min[M10V_EXTENSION_FIELDS]={0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,28,28,0,0,0};
const uint8_t m10v_extension_max[M10V_EXTENSION_FIELDS]={1,21,21,3,2,4,2,3,2,2,3,2,2,3,3,3,1,50,50,2,6,7};
const uint8_t m10v_extension_persistent[M10V_EXTENSION_FIELDS]={0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,1};
static void zero(void*p,unsigned n){for(unsigned i=0;i<n;i++)((uint8_t*)p)[i]=0;}
static int equal(const void*a,const void*b,unsigned n){return m10v_constant_equal(a,b,n);}
int m10v_extensions_valid(const m10v_extension_snapshot*s){if(!s||s->busy>1||(s->available&~M10V_EXTENSION_MASK))return 0;for(unsigned i=0;i<M10V_EXTENSION_FIELDS;i++)if((s->available&(1u<<i))&&(s->values[i]<m10v_extension_min[i]||s->values[i]>m10v_extension_max[i]))return 0;return 1;}
void m10v_extensions_owner_init(m10v_extension_owner*o){if(o)zero(o,sizeof(*o));}
static int result(m10v_extension_result*r,unsigned status,unsigned code,const m10v_extension_snapshot*s){zero(r,sizeof(*r));r->status=status;r->code=code;if(s){r->has_snapshot=1;r->snapshot=*s;}return (int)code;}
static int reject(m10v_extension_result*r,unsigned code){return result(r,M10V_OPERATION_REJECTED,code,0);}
static int acquire(const m10v_extension_services*s,m10v_extension_result*r){if(!s||!s->owner||!s->is_current||!s->enter||!s->leave||!s->is_busy||!s->blocked||!s->read||!s->write||!s->is_current(s->ctx))return reject(r,M10V_ERROR_BRIDGE_UNAVAILABLE);if(!s->enter(s->ctx))return reject(r,M10V_ERROR_BUSY);if(!s->is_current(s->ctx)){s->leave(s->ctx);return reject(r,M10V_ERROR_BRIDGE_UNAVAILABLE);}return 0;}
static int fresh(const m10v_extension_services*s,m10v_extension_snapshot*out){if(!s->is_current(s->ctx))return M10V_ERROR_BRIDGE_UNAVAILABLE;int code=s->read(s->ctx,out);if(code)return code;return s->is_current(s->ctx)&&m10v_extensions_valid(out)?0:M10V_ERROR_BRIDGE_UNAVAILABLE;}
static int matches(const m10v_extension_snapshot*a,const m10v_extension_snapshot*b){if(a->available!=b->available)return 0;for(unsigned i=0;i<M10V_EXTENSION_FIELDS;i++)if((a->available&(1u<<i))&&a->values[i]!=b->values[i])return 0;return 1;}
static void complete(m10v_extension_owner*o,m10v_extension_record*r,unsigned status,unsigned code,const m10v_extension_snapshot*s){result(&r->result,status,code,s);if(status!=M10V_OPERATION_UNKNOWN){o->cache=*r;o->cache.present=1;r->present=0;}}
int m10v_extensions_apply(const m10v_extension_patch*p,const m10v_extension_services*s,m10v_extension_result*out){
 if(!out)return M10V_ERROR_INVALID_RECIPE;if(!p)return reject(out,M10V_ERROR_INVALID_RECIPE);int code=acquire(s,out);if(code)return code;
 m10v_extension_owner*o=s->owner;uint8_t digest[32];m10v_sha256((const uint8_t*)p,sizeof(*p),digest);
 m10v_extension_record*r=o->pending.present&&equal(o->pending.id,p->request_id,16)?&o->pending:o->cache.present&&equal(o->cache.id,p->request_id,16)?&o->cache:0;
 if(r){if(!equal(r->digest,digest,32))code=reject(out,M10V_ERROR_INVALID_RECIPE);else {*out=r->result;code=(int)out->code;}goto done;}
 if(o->pending.present||s->blocked(s->ctx)||s->is_busy(s->ctx)){code=reject(out,M10V_ERROR_BUSY);goto done;}
 uint8_t hash[32];m10v_unhex(M10V_EXTENSIONS_HASH,32,hash);
 if(!equal(hash,p->contract_hash,32)){code=reject(out,M10V_ERROR_INCOMPATIBLE_RENDERER);goto done;}
 if(!equal(p->boot_id,s->boot_id,16)){code=reject(out,M10V_ERROR_REVISION_CONFLICT);goto done;}
 m10v_extension_snapshot actual;code=fresh(s,&actual);if(code){code=reject(out,(unsigned)code);goto done;}
 if(actual.busy){code=reject(out,M10V_ERROR_BUSY);goto done;}
 if(!equal(actual.revision,p->base_revision,32)){code=reject(out,M10V_ERROR_REVISION_CONFLICT);goto done;}
 if(p->field>=M10V_EXTENSION_FIELDS||!(actual.available&(1u<<p->field))||p->value<m10v_extension_min[p->field]||p->value>m10v_extension_max[p->field]){code=reject(out,M10V_ERROR_INVALID_RECIPE);goto done;}
 if(!s->is_current(s->ctx)||s->is_busy(s->ctx)||s->blocked(s->ctx)){code=reject(out,M10V_ERROR_BUSY);goto done;}
 r=&o->pending;zero(r,sizeof(*r));for(unsigned i=0;i<16;i++)r->id[i]=p->request_id[i];for(unsigned i=0;i<32;i++)r->digest[i]=digest[i];r->present=1;r->expected=actual;r->expected.values[p->field]=p->value;
 if(actual.values[p->field]==p->value){complete(o,r,M10V_OPERATION_COMMITTED,0,&actual);*out=r->result;code=0;goto done;}
 int written=s->write(s->ctx,p->field,p->value);
 if(written==M10V_IO_NOT_WRITTEN){complete(o,r,M10V_OPERATION_REJECTED,M10V_ERROR_STORE_FAILED,0);*out=r->result;code=M10V_ERROR_STORE_FAILED;goto done;}
 code=fresh(s,&actual);
 if(code){complete(o,r,M10V_OPERATION_UNKNOWN,M10V_ERROR_RESULT_UNKNOWN,0);*out=r->result;code=M10V_ERROR_RESULT_UNKNOWN;goto done;}
 if(!matches(&r->expected,&actual)){complete(o,r,M10V_OPERATION_UNKNOWN,M10V_ERROR_READBACK_MISMATCH,&actual);*out=r->result;code=M10V_ERROR_READBACK_MISMATCH;goto done;}
 complete(o,r,M10V_OPERATION_COMMITTED,0,&actual);*out=r->result;code=0;
 done:s->leave(s->ctx);return code;
}
int m10v_extensions_poll(const uint8_t id[16],const m10v_extension_services*s,m10v_extension_result*out){
 if(!out)return M10V_ERROR_INVALID_RECIPE;if(!id)return reject(out,M10V_ERROR_INVALID_RECIPE);int code=acquire(s,out);if(code){out->status=M10V_OPERATION_UNKNOWN;return code;}
 m10v_extension_owner*o=s->owner;m10v_extension_record*r=&o->pending;
 if(r->present&&equal(r->id,id,16)){m10v_extension_snapshot actual;code=fresh(s,&actual);if(!code&&matches(&r->expected,&actual)){complete(o,r,M10V_OPERATION_COMMITTED,0,&actual);*out=r->result;}else code=result(out,M10V_OPERATION_UNKNOWN,M10V_ERROR_RESULT_UNKNOWN,code?0:&actual);}
 else if(o->cache.present&&equal(o->cache.id,id,16)){*out=o->cache.result;code=(int)out->code;}
 else code=result(out,M10V_OPERATION_UNKNOWN,M10V_ERROR_RESULT_UNKNOWN,0);
 s->leave(s->ctx);return code;
}
