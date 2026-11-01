#include "http_server.h"
/* Includes global request/staging/receipt memory plus a conservative nested
 * scalar call-stack allowance; no heap allocation or raw JSON receipt copies. */
_Static_assert(sizeof(m10v_companion_server)+sizeof(m10v_companion_server_config)+4096<=65536,"companion staging/stack budget exceeds 64 KiB");
static int equal(const char*a,const char*b){unsigned i=0;while(a[i]&&a[i]==b[i])i++;return a[i]==b[i];}
static unsigned text_length(const char*s){unsigned n=0;while(s[n])n++;return n;}
static void copy(void*out,const void*in,unsigned bytes){for(unsigned i=0;i<bytes;i++)((uint8_t*)out)[i]=((const uint8_t*)in)[i];}
typedef struct {uint8_t*out;unsigned size;int failed;} writer;
static void text(writer*w,const char*value){for(unsigned i=0;value[i];i++){if(w->size>=M10V_HTTP_RESPONSE_BYTES){w->failed=1;return;}w->out[w->size++]=(uint8_t)value[i];}}
static void number(writer*w,uint32_t value){char digits[11];unsigned n=0;do{digits[n++]=(char)('0'+value%10);value/=10;}while(value);while(n){char one[2]={digits[--n],0};text(w,one);}}
static void quoted(writer*w,const char*value){text(w,"\"");text(w,value);text(w,"\"");}
static void hex(writer*w,const uint8_t*value,unsigned bytes){char encoded[65];m10v_hex(value,bytes,encoded);quoted(w,encoded);}
static writer begin(m10v_companion_server*s,unsigned status){s->status=status;writer w={s->output.bytes,0,0};return w;}
static int finish(m10v_companion_server*s,writer*w){
 if(w->failed){s->status=500;s->output_bytes=0;return 1;}s->output_bytes=w->size;
 return 0;
}
static int error(m10v_companion_server*s,unsigned status,unsigned code){writer w=begin(s,status);text(&w,"{\"error\":{\"code\":");quoted(&w,m10v_error_name(code));text(&w,"}}");return finish(s,&w);}
static unsigned field(const m10v_library_state*state,unsigned slot,unsigned key){
 const m10v_slot*v=&state->slots[slot];const m10v_film_effects*e=&state->effects[slot];switch(key){
 case M10V_FIELD_FILMID:return v->film;case M10V_FIELD_GRAIN:return v->grain;case M10V_FIELD_GRAINSIZE:return e->grain_size;
 case M10V_FIELD_HALOGAIN:return v->halo_gain;case M10V_FIELD_HALOSPREAD:return v->halo_spread;case M10V_FIELD_HALOTHRESHOLD:return v->halo_threshold;case M10V_FIELD_HALOPROFILE:return v->halo_profile;
 case M10V_FIELD_LEAKGAIN:return e->leak_gain;case M10V_FIELD_LEAKPOSITION:return e->leak_position;case M10V_FIELD_LEAKSPREAD:return e->leak_spread;case M10V_FIELD_LEAKVARIATION:return e->leak_variation;case M10V_FIELD_FILMEXPOSURE:return e->film_exposure;case M10V_FIELD_CHARMERACOLOR:return e->reserved[1];default:return 0;}
}
static void snapshot_json(m10v_companion_server*s,writer*w,const m10v_companion_snapshot*snap){
 text(w,"{\"protocol\":1,\"schemaVersion\":2,\"bootId\":");hex(w,s->auth.boot,16);text(w,",\"instanceId\":");hex(w,s->config->instance_id,16);
 text(w,",\"catalogHash\":");hex(w,s->config->catalog_hash,32);text(w,",\"rendererHash\":");hex(w,s->config->renderer_hash,32);text(w,",\"revision\":");hex(w,snap->revision,32);text(w,",\"configHash\":");hex(w,snap->config_hash,32);text(w,",\"journalSequence\":");number(w,snap->state.sequence);
 text(w,",\"activeSlot\":");if(snap->active_slot<0)text(w,"null");else number(w,(unsigned)snap->active_slot);
 text(w,",\"busy\":");text(w,snap->busy?"true":"false");text(w,",\"fresh\":true,\"config\":{\"slots\":[");
 for(unsigned slot=0;slot<M10V_SLOT_COUNT;slot++){if(slot)text(w,",");unsigned id=snap->state.slots[slot].film;text(w,"{\"filmId\":");number(w,id);text(w,",\"parameters\":{");unsigned count=0;for(unsigned key=1;key<M10V_FIELD_COUNT;key++)if(m10v_field_supported(key,id)||m10v_field_readonly(key)){if(count++)text(w,",");quoted(w,m10v_field_names[key]);text(w,":");number(w,field(&snap->state,slot,key));}text(w,"},\"customHash\":");if(M10V_CUSTOM(id))hex(w,snap->custom_hashes[slot],32);else text(w,"null");text(w,"}");}
 text(w,"],\"globals\":{\"stamp\":");number(w,snap->state.stamp);text(w,",\"format\":");number(w,snap->state.format);text(w,",\"corner\":");number(w,snap->state.corner);text(w,",\"color\":");number(w,snap->state.color);text(w,",\"filmNameStamp\":");number(w,snap->state.reserved&1u);text(w,"}}}");
}
static int receipt_json(m10v_companion_server*s,const m10v_operation_receipt*r){
 writer w=begin(s,r->status==M10V_OPERATION_QUEUED||r->status==M10V_OPERATION_APPLYING?202:200);static const char*states[]={"queued","applying","committed","rejected","unknown"};text(&w,"{\"requestId\":");hex(&w,r->request_id,16);text(&w,",\"bootId\":");hex(&w,s->auth.boot,16);text(&w,",\"status\":");quoted(&w,states[r->status]);
 if(r->error){text(&w,",\"error\":{\"code\":");quoted(&w,m10v_error_name(r->error));text(&w,"}");}
 if(r->status==M10V_OPERATION_COMMITTED&&r->has_snapshot){text(&w,",\"snapshot\":");snapshot_json(s,&w,&r->snapshot);}text(&w,"}");return finish(s,&w);
}
int m10v_companion_server_init(m10v_companion_server*s,const m10v_companion_server_config*cfg,const m10v_companion_backend*backend){
 if(!s||!cfg||!backend||!backend->exchange||!cfg->random||!cfg->now_ms||!cfg->operation_timeout_ms)return 1;for(unsigned i=0;i<sizeof(*s);i++)((uint8_t*)s)[i]=0;s->config=cfg;s->backend=*backend;s->pending_index=-1;uint8_t boot[16];if(!cfg->random(cfg->random_ctx,boot,16))return 1;return m10v_auth_init(&s->auth,cfg->key,cfg->key_id,boot,cfg->random,cfg->random_ctx);
}
void m10v_companion_tick(m10v_companion_server*s){
 if(s->pending_index<0)return;m10v_operation_receipt*r=&s->receipts[s->pending_index];unsigned command=r->status==M10V_OPERATION_QUEUED?M10V_BACKEND_SUBMIT:M10V_BACKEND_POLL;
 m10v_backend_request request={.command=command,.patch=&s->pending_patch};m10v_backend_response response={M10V_OPERATION_UNKNOWN,0,&r->snapshot};int code=s->backend.exchange(s->backend.ctx,&request,&response);
 /* A READ already in flight must finish before SUBMIT. Retain QUEUED:
  * POLL is never a substitute for an unsubmitted APPLY. */
 if(code==M10V_ERROR_BUSY&&command==M10V_BACKEND_SUBMIT){
  m10v_backend_request read={.command=M10V_BACKEND_READ_STATE};m10v_backend_response discard={M10V_OPERATION_UNKNOWN,0,&r->snapshot};
  int drained=s->backend.exchange(s->backend.ctx,&read,&discard);
  uint64_t now=s->config->now_ms(s->config->clock_ctx);
  if(drained==M10V_ERROR_BRIDGE_UNAVAILABLE||now<s->pending_since||now-s->pending_since>=s->config->operation_timeout_ms){r->status=M10V_OPERATION_UNKNOWN;r->error=M10V_ERROR_RESULT_UNKNOWN;}
  return;
 }
 if(code==M10V_ERROR_NONE&&response.status==M10V_OPERATION_COMMITTED&&response.has_snapshot){r->status=M10V_OPERATION_COMMITTED;r->has_snapshot=1;r->error=0;s->pending_index=-1;return;}
 if(response.status==M10V_OPERATION_REJECTED&&code>=M10V_ERROR_UNAUTHORIZED&&code<=M10V_ERROR_RESULT_UNKNOWN){r->status=M10V_OPERATION_REJECTED;r->error=(uint8_t)code;s->pending_index=-1;return;}
 uint64_t now=s->config->now_ms(s->config->clock_ctx);
 if(r->status==M10V_OPERATION_UNKNOWN||response.status==M10V_OPERATION_UNKNOWN||code==M10V_ERROR_BRIDGE_UNAVAILABLE||now<s->pending_since||now-s->pending_since>=s->config->operation_timeout_ms){r->status=M10V_OPERATION_UNKNOWN;r->error=code==M10V_ERROR_READBACK_MISMATCH?M10V_ERROR_READBACK_MISMATCH:M10V_ERROR_RESULT_UNKNOWN;}
 else r->status=M10V_OPERATION_APPLYING;
}
static int seen(m10v_companion_server*s,const uint8_t*id,int insert){uint8_t hash[32];m10v_sha256(id,16,hash);unsigned found=1;for(unsigned i=0;i<4;i++){unsigned bit=((unsigned)hash[i*2]|((unsigned)hash[i*2+1]<<8))%2048;uint8_t mask=(uint8_t)(1u<<(bit%8));if(!(s->seen_operations[bit/8]&mask))found=0;if(insert)s->seen_operations[bit/8]|=mask;}return (int)found;}
void m10v_companion_bad_request(m10v_companion_server*s){s->authenticated=0;s->response_signature[0]=0;error(s,400,M10V_ERROR_INVALID_RECIPE);}
int m10v_companion_process(m10v_companion_server*s,const char*head,uint32_t head_bytes,const uint8_t*body,uint32_t body_bytes){
 if(m10v_http_parse_head(head,head_bytes,&s->request)){m10v_companion_bad_request(s);return 0;}
 return m10v_companion_process_parsed(s,body,body_bytes);
}
static int upload_json(m10v_companion_server*s){
 m10v_film_upload*u=&s->film.upload;writer w=begin(s,u->state==M10V_UPLOAD_VERIFYING?202:200);static const char*states[]={"empty","receiving","verifying","verified","failed","unknown"};
 text(&w,"{\"uploadId\":");hex(&w,u->id,16);text(&w,",\"status\":");quoted(&w,states[u->state]);text(&w,",\"receivedBytes\":");number(&w,u->received);text(&w,",\"targetSlot\":");number(&w,u->metadata.target_slot);text(&w,",\"stableId\":");number(&w,u->metadata.stable_id);text(&w,",\"contentHash\":");hex(&w,u->metadata.content_hash,32);if(u->state==M10V_UPLOAD_VERIFIED){text(&w,",\"bank\":");number(&w,u->bank);}if(u->error){text(&w,",\"error\":{\"code\":");quoted(&w,m10v_error_name(u->error));text(&w,"}");}text(&w,"}");return finish(s,&w);
}
static __attribute__((noinline)) int route_upload(m10v_companion_server*s,const uint8_t*body,uint32_t body_bytes){
 const char*method=s->request.method,*path=s->request.path,*stage="/m10v/v1/films/stage";unsigned stage_bytes=text_length(stage),path_bytes=text_length(path);m10v_film_upload*u=&s->film.upload;
 if(equal(method,"POST")&&equal(path,stage)){
  if(!s->config->upload_film)return error(s,503,M10V_ERROR_BRIDGE_UNAVAILABLE);
  m10v_film_upload_metadata meta;int code=m10v_companion_upload_parse(body,body_bytes,s->output.tokens,&meta);if(code)return error(s,400,(unsigned)code);uint8_t id[16];if(!s->config->random(s->config->random_ctx,id,16))return error(s,503,M10V_ERROR_BRIDGE_UNAVAILABLE);
  code=m10v_companion_stage_begin(u,&meta,id,s->config->renderer_hash);return code?error(s,code==M10V_ERROR_BUSY?409:400,(unsigned)code):upload_json(s);
 }
 if(path_bytes>=stage_bytes+33){unsigned match=1;for(unsigned i=0;i<stage_bytes;i++)if(path[i]!=stage[i])match=0;uint8_t id[16];
  if(match&&path[stage_bytes]=='/'&&m10v_unhex(path+stage_bytes+1,16,id)){
   const char*suffix=path+stage_bytes+33;
   if(equal(method,"GET")&&!*suffix){
    if(!s->config->upload_film)return error(s,503,M10V_ERROR_BRIDGE_UNAVAILABLE);
    if(!u->state||!m10v_constant_equal(id,u->id,16))return error(s,404,M10V_ERROR_RESULT_UNKNOWN);
    if(u->state==M10V_UPLOAD_VERIFYING||u->state==M10V_UPLOAD_UNKNOWN){m10v_film_backend_request film={u,s->staging};m10v_backend_request request={.command=M10V_BACKEND_FILM_POLL,.film=&film};m10v_backend_response response={0};s->backend.exchange(s->backend.ctx,&request,&response);}
    return upload_json(s);
   }
const char*chunks="/chunks/";unsigned n=text_length(chunks);match=text_length(suffix)>n;for(unsigned i=0;i<n&&match;i++)if(suffix[i]!=chunks[i])match=0;
   if(equal(method,"PUT")&&match){unsigned index=0,count=0;for(const char*p=suffix+n;*p;p++){if(*p<'0'||*p>'9'||count++>=5){match=0;break;}index=index*10+(unsigned)(*p-'0');}
    if(match&&index<12288){if(!s->config->upload_film)return error(s,503,M10V_ERROR_BRIDGE_UNAVAILABLE);uint8_t hash[32];if(text_length(s->request.chunk_hash)!=64||!m10v_unhex(s->request.chunk_hash,32,hash))return error(s,400,M10V_ERROR_INVALID_RECIPE);int code=m10v_companion_stage_chunk(u,s->staging,id,index,body,body_bytes,hash);return code?error(s,400,(unsigned)code):upload_json(s);}
   }
   if(equal(method,"POST")&&equal(suffix,"/verify")){
    if(!s->config->upload_film)return error(s,503,M10V_ERROR_BRIDGE_UNAVAILABLE);if(body_bytes)return error(s,400,M10V_ERROR_INVALID_RECIPE);
    int code=m10v_companion_stage_validate(u,s->staging,id);if(code)return error(s,400,(unsigned)code);if(u->state==M10V_UPLOAD_VERIFIED)return upload_json(s);if(s->pending_index>=0)return error(s,409,M10V_ERROR_BUSY);
    m10v_film_backend_request film={u,s->staging};m10v_backend_request request={.command=u->state==M10V_UPLOAD_RECEIVING?M10V_BACKEND_FILM_VERIFY:M10V_BACKEND_FILM_POLL,.film=&film};m10v_backend_response response={0};
    if(u->state==M10V_UPLOAD_RECEIVING)s->pending_since=s->config->now_ms(s->config->clock_ctx);
    code=s->backend.exchange(s->backend.ctx,&request,&response);
    if(code==M10V_ERROR_BUSY)return error(s,409,M10V_ERROR_BUSY);
    if(code&&u->state==M10V_UPLOAD_RECEIVING)return error(s,503,(unsigned)code);
    if(u->state!=M10V_UPLOAD_VERIFIED&&u->state!=M10V_UPLOAD_FAILED&&u->state!=M10V_UPLOAD_UNKNOWN)u->state=M10V_UPLOAD_VERIFYING;
    uint64_t now=s->config->now_ms(s->config->clock_ctx);if(u->state==M10V_UPLOAD_VERIFYING&&(now<s->pending_since||now-s->pending_since>=s->config->operation_timeout_ms)){u->state=M10V_UPLOAD_UNKNOWN;u->error=M10V_ERROR_RESULT_UNKNOWN;}
    return upload_json(s);
   }
  }
 }
 return error(s,404,M10V_ERROR_INVALID_RECIPE);
}

static __attribute__((noinline)) int route_authenticated(m10v_companion_server*s,const uint8_t*body,uint32_t body_bytes){
 const char*method=s->request.method,*path=s->request.path;
 if(equal(method,"GET")&&equal(path,"/m10v/v1/capabilities")){
  writer w=begin(s,200);text(&w,"{\"protocol\":1,\"model\":\"GR III\",\"recipeSchema\":1,\"stateSchema\":2,\"slotCount\":10,\"firmwareIdentity\":\"d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4\",\"bootId\":");hex(&w,s->auth.boot,16);text(&w,",\"sessionId\":");quoted(&w,s->session);text(&w,",\"instanceId\":");hex(&w,s->config->instance_id,16);text(&w,",\"buildId\":");hex(&w,s->config->build_id,32);text(&w,",\"catalogHash\":");hex(&w,s->config->catalog_hash,32);text(&w,",\"rendererHash\":");hex(&w,s->config->renderer_hash,32);
  text(&w,",\"capabilities\":{\"readState\":");text(&w,s->config->read_state?"true":"false");text(&w,",\"writeState\":");text(&w,s->config->write_state?"true":"false");text(&w,",\"uploadFilm\":");text(&w,s->config->upload_film?"true":"false");text(&w,",\"captureEvidence\":");text(&w,s->config->capture_evidence?"true":"false");text(&w,"},\"parameters\":");text(&w,M10V_PARAMETERS_JSON);text(&w,",\"readOnlyParameters\":");text(&w,M10V_READONLY_JSON);text(&w,",\"limits\":");text(&w,M10V_LIMITS_JSON);text(&w,"}");return finish(s,&w);
 }
 if(equal(method,"GET")&&equal(path,"/m10v/v1/state")){
  if(!s->config->read_state)return error(s,503,M10V_ERROR_BRIDGE_UNAVAILABLE);m10v_companion_snapshot snapshot;m10v_backend_request request={.command=M10V_BACKEND_READ_STATE};m10v_backend_response response={M10V_OPERATION_UNKNOWN,0,&snapshot};int code=s->backend.exchange(s->backend.ctx,&request,&response);if(code||!response.has_snapshot)return error(s,503,code?code:response.status==M10V_OPERATION_APPLYING?M10V_ERROR_BUSY:M10V_ERROR_BRIDGE_UNAVAILABLE);writer w=begin(s,200);snapshot_json(s,&w,&snapshot);return finish(s,&w);
 }
 const char *prefix="/m10v/v1/operations/";unsigned prefix_bytes=text_length(prefix),path_bytes=text_length(path);unsigned prefix_match=path_bytes>=prefix_bytes;for(unsigned i=0;i<prefix_bytes&&prefix_match;i++)if(path[i]!=prefix[i])prefix_match=0;
 if(equal(method,"GET")&&prefix_match){uint8_t id[16];if(path_bytes!=prefix_bytes+32||!m10v_unhex(path+prefix_bytes,16,id))return error(s,400,M10V_ERROR_INVALID_RECIPE);for(unsigned i=0;i<32;i++)if(s->receipts[i].occupied&&m10v_constant_equal(id,s->receipts[i].request_id,16))return receipt_json(s,&s->receipts[i]);return error(s,404,M10V_ERROR_RESULT_UNKNOWN);}
 if(equal(method,"POST")&&equal(path,"/m10v/v1/operations")){
  m10v_companion_patch patch;int code=m10v_operation_parse_tokens(body,body_bytes,s->output.tokens,&patch);if(code)return error(s,400,(unsigned)code);
  if(!m10v_constant_equal(patch.boot_id,s->auth.boot,16))return error(s,409,M10V_ERROR_REVISION_CONFLICT);
  if(!m10v_constant_equal(patch.catalog_hash,s->config->catalog_hash,32)||!m10v_constant_equal(patch.renderer_hash,s->config->renderer_hash,32))return error(s,409,M10V_ERROR_INCOMPATIBLE_RENDERER);
  if(!s->config->write_state)return error(s,503,M10V_ERROR_BRIDGE_UNAVAILABLE);uint8_t digest[32];m10v_operation_digest(&patch,digest);
  for(unsigned i=0;i<32;i++)if(s->receipts[i].occupied&&m10v_constant_equal(s->receipts[i].request_id,patch.request_id,16)){if(!m10v_constant_equal(s->receipts[i].digest,digest,32))return error(s,409,M10V_ERROR_INVALID_RECIPE);return receipt_json(s,&s->receipts[i]);}
  if(seen(s,patch.request_id,0))return error(s,409,M10V_ERROR_RESULT_UNKNOWN);
  if(s->pending_index>=0||s->film.upload.state==M10V_UPLOAD_VERIFYING||s->film.upload.state==M10V_UPLOAD_UNKNOWN)return error(s,409,M10V_ERROR_BUSY);
  unsigned index=s->receipt_cursor++%32;m10v_operation_receipt*r=&s->receipts[index];for(unsigned i=0;i<sizeof(*r);i++)((uint8_t*)r)[i]=0;copy(r->request_id,patch.request_id,16);copy(r->digest,digest,32);r->status=M10V_OPERATION_QUEUED;r->occupied=1;s->pending_patch=patch;s->pending_index=(int)index;s->pending_since=s->config->now_ms(s->config->clock_ctx);seen(s,patch.request_id,1);return receipt_json(s,r);
 }
 return route_upload(s,body,body_bytes);
}

int m10v_companion_process_parsed(m10v_companion_server*s,const uint8_t*body,uint32_t body_bytes){
 s->authenticated=0;s->session[0]=0;s->response_signature[0]=0;
 if(m10v_auth_accept(&s->auth,&s->request,body,body_bytes,s->session))return error(s,401,M10V_ERROR_UNAUTHORIZED);
 s->authenticated=1;m10v_companion_tick(s);
 int result=route_authenticated(s,body,body_bytes);
 if(result)return result;
 return m10v_auth_sign_response(&s->auth,&s->request,s->session,s->status,s->output.bytes,s->output_bytes,s->response_signature);
}
