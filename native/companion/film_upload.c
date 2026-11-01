#include "film_upload.h"
#include "../gr3/m10v_sd_library.h"
_Static_assert(sizeof(m10v_film_upload)<=128,"upload metadata reservation");
static void copy(void*out,const void*in,unsigned n){for(unsigned i=0;i<n;i++)((uint8_t*)out)[i]=((const uint8_t*)in)[i];}
static int matches(const m10v_film_upload_metadata*a,const m10v_film_upload_metadata*b){return a->model==b->model&&a->schema==b->schema&&a->stable_id==b->stable_id&&a->target_slot==b->target_slot&&a->size==b->size&&a->chunk_bytes==b->chunk_bytes&&m10v_constant_equal(a->renderer_hash,b->renderer_hash,32)&&m10v_constant_equal(a->content_hash,b->content_hash,32);}
int m10v_companion_stage_begin(m10v_film_upload*s,const m10v_film_upload_metadata*m,const uint8_t id[16],const uint8_t renderer[32]){
 if(!s||!m||!id||!renderer)return M10V_ERROR_INVALID_RECIPE;
 if(m->model!=239)return M10V_ERROR_UNSUPPORTED_MODEL;
 if(m->schema!=1)return M10V_ERROR_UNSUPPORTED_PROTOCOL;
 if(m->stable_id<79||m->stable_id>288||m->target_slot>4||m->size!=M10V_FILM_BYTES||m->chunk_bytes!=M10V_FILM_CHUNK_BYTES)return M10V_ERROR_INVALID_RECIPE;
 if(!m10v_constant_equal(m->renderer_hash,renderer,32))return M10V_ERROR_INCOMPATIBLE_RENDERER;
 if(s->state&&s->state!=M10V_UPLOAD_FAILED&&matches(&s->metadata,m))return 0;
 if(s->state==M10V_UPLOAD_VERIFYING||s->state==M10V_UPLOAD_UNKNOWN)return M10V_ERROR_BUSY;
 for(unsigned i=0;i<sizeof(*s);i++)((uint8_t*)s)[i]=0;s->metadata=*m;copy(s->id,id,16);s->state=M10V_UPLOAD_RECEIVING;return 0;
}
int m10v_companion_stage_chunk(m10v_film_upload*s,uint8_t*stage,const uint8_t id[16],unsigned index,const uint8_t*bytes,uint32_t n,const uint8_t hash[32]){
 if(!s||!stage||!id||!bytes||!hash||s->state!=M10V_UPLOAD_RECEIVING||!m10v_constant_equal(s->id,id,16)||index>=3||n!=M10V_FILM_CHUNK_BYTES)return M10V_ERROR_INVALID_RECIPE;
 uint8_t actual[32];m10v_sha256(bytes,n,actual);if(!m10v_constant_equal(actual,hash,32))return M10V_ERROR_INVALID_RECIPE;
 uint32_t offset=index*M10V_FILM_CHUNK_BYTES;if(offset>s->received)return M10V_ERROR_INVALID_RECIPE;
 if(offset<s->received)return m10v_constant_equal(stage+offset,bytes,n)?0:M10V_ERROR_INVALID_RECIPE;
 copy(stage+offset,bytes,n);s->received+=n;return 0;
}
int m10v_companion_stage_validate(m10v_film_upload*s,const uint8_t*stage,const uint8_t id[16]){
 if(!s||!stage||!id||!s->state||!m10v_constant_equal(s->id,id,16)||s->received!=M10V_FILM_BYTES)return M10V_ERROR_INVALID_RECIPE;
 if(s->state==M10V_UPLOAD_FAILED)return s->error;
 if(s->state!=M10V_UPLOAD_RECEIVING)return 0;
 uint8_t hash[32];m10v_sha256(stage,M10V_FILM_BYTES,hash);
 if(!m10v_constant_equal(hash,s->metadata.content_hash,32)||!m10v_constant_equal(stage+8448,s->metadata.renderer_hash,32)||!m10v_sd_record(stage,M10V_FILM_BYTES,s->metadata.stable_id))return M10V_ERROR_INVALID_RECIPE;
 return 0;
}
static int readback(m10v_film_upload*s,const m10v_film_bank_services*io){
 uint8_t part[64],hash[32];m10v_sha256_context ctx;m10v_sha256_init(&ctx);
 for(uint32_t offset=0;offset<M10V_FILM_BYTES;offset+=sizeof(part)){if(io->read(io->ctx,s->metadata.target_slot,s->bank,offset,part,sizeof(part))!=(int)sizeof(part))return M10V_ERROR_RESULT_UNKNOWN;m10v_sha256_update(&ctx,part,sizeof(part));}
 m10v_sha256_finish(&ctx,hash);return m10v_constant_equal(hash,s->metadata.content_hash,32)?0:M10V_ERROR_READBACK_MISMATCH;
}
int m10v_companion_stage_verify(m10v_film_upload*s,const uint8_t*stage,const uint8_t id[16],const m10v_film_bank_services*io){
 int code=m10v_companion_stage_validate(s,stage,id);if(code)return code;if(s->state==M10V_UPLOAD_VERIFIED)return 0;
 if(!io||!io->is_current||!io->enter||!io->leave||!io->is_busy||!io->references||!io->store_once||!io->read||!io->is_current(io->ctx))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 if(!io->enter(io->ctx))return M10V_ERROR_BUSY;
 if(io->is_busy(io->ctx)){io->leave(io->ctx);return M10V_ERROR_BUSY;}
 if(s->state==M10V_UPLOAD_RECEIVING){unsigned mask=3;if(!io->references(io->ctx,s->metadata.target_slot,&mask)||mask>3||mask==3){io->leave(io->ctx);return M10V_ERROR_BUSY;}
  s->bank=(uint8_t)((mask&1)?1:0);s->state=M10V_UPLOAD_VERIFYING;
  int stored=io->store_once(io->ctx,s->metadata.target_slot,s->bank,stage,M10V_FILM_BYTES);
  if(stored==M10V_IO_NOT_WRITTEN){s->state=M10V_UPLOAD_FAILED;s->error=M10V_ERROR_STORE_FAILED;io->leave(io->ctx);return s->error;}
 }
 code=readback(s,io);s->state=(uint8_t)(code?M10V_UPLOAD_UNKNOWN:M10V_UPLOAD_VERIFIED);s->error=(uint8_t)code;io->leave(io->ctx);return code;
}

int m10v_companion_upload_parse(const uint8_t*body,uint32_t n,m10v_json_token*t,m10v_film_upload_metadata*out){
 uint16_t count;if(!out||m10v_json_parse(body,n,t,&count)||t[0].type!=M10V_JSON_OBJECT||t[0].count!=8)return M10V_ERROR_INVALID_RECIPE;
 static const char*keys[]={"model","schema","stableId","targetSlot","size","chunkBytes","rendererHash","contentHash"};uint16_t at[8];
 for(unsigned i=0;i<8;i++){at[i]=m10v_json_get(body,t,0,keys[i]);if(at[i]==M10V_JSON_MISSING)return M10V_ERROR_INVALID_RECIPE;}
 char model[16];if(!m10v_json_string(body,&t[at[0]],model,sizeof(model)))return M10V_ERROR_UNSUPPORTED_MODEL;
 static const char expected[]="GR III";for(unsigned i=0;i<sizeof(expected);i++)if(model[i]!=expected[i])return M10V_ERROR_UNSUPPORTED_MODEL;
 uint32_t values[5];for(unsigned i=0;i<5;i++)if(!m10v_json_uint(body,&t[at[i+1]],&values[i]))return M10V_ERROR_INVALID_RECIPE;
 if(values[0]!=1)return M10V_ERROR_UNSUPPORTED_PROTOCOL;if(values[1]<79||values[1]>288||values[2]>4||values[3]!=M10V_FILM_BYTES||values[4]!=M10V_FILM_CHUNK_BYTES)return M10V_ERROR_INVALID_RECIPE;
 for(unsigned i=0;i<sizeof(*out);i++)((uint8_t*)out)[i]=0;out->model=239;out->schema=1;out->stable_id=(uint16_t)values[1];out->target_slot=(uint8_t)values[2];out->size=values[3];out->chunk_bytes=values[4];
 for(unsigned i=0;i<2;i++){const m10v_json_token*v=&t[at[6+i]];if(v->type!=M10V_JSON_STRING||v->end-v->start!=64||!m10v_unhex((const char*)body+v->start,32,i?out->content_hash:out->renderer_hash))return M10V_ERROR_INVALID_RECIPE;}
 return 0;
}
