#if !defined(M10V_COMPANION_HOST_TEST)
#error Host fixture backend must never enter a production package
#endif
#include "linux_io.h"
#include "transaction.h"
#include "../native/gr3/m10v_sd_library.h"
#include "../native/gr3/m10v_sd_contract.h"
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
static unsigned ext_writes;
static m10v_extension_owner ext_owner;
static m10v_extension_services ext_io;
static m10v_extension_snapshot ext_state;
static m10v_library_state current;
static m10v_companion_owner owner;
static m10v_companion_owner_services io;
static uint8_t banks[M10V_SLOT_COUNT][2][12288],bank_hashes[M10V_SLOT_COUNT][2][32];
static uint8_t bank_present[M10V_SLOT_COUNT][2];
static unsigned polls,random_calls,locked,read_turn,submit_attempted,submitted;
static int8_t active;
static int random_bytes(void*c,uint8_t*out,uint32_t bytes){int ok=m10v_linux_random(c,out,bytes);if(ok&&random_calls++==0&&bytes==16){memcpy(io.metadata.boot_id,out,16);memcpy(ext_io.boot_id,out,16);}return ok;}
static int is_current(void*c){(void)c;return 1;}
static int enter(void*c){(void)c;if(locked)return 0;locked=1;return 1;}
static void leave(void*c){(void)c;locked=0;}
static int busy(void*c){(void)c;return 0;}
static int references(void*c,unsigned slot,unsigned*out){(void)c;*out=current.effects[slot].reserved[0]?1u<<(current.effects[slot].reserved[0]-1):0;return 1;}
static int store_bank(void*c,unsigned slot,unsigned bank,const uint8_t*data,uint32_t n){(void)c;memcpy(banks[slot][bank],data,n);m10v_sha256(data,n,bank_hashes[slot][bank]);bank_present[slot][bank]=1;return M10V_IO_OK;}
static int read_bank(void*c,unsigned slot,unsigned bank,uint32_t offset,uint8_t*out,uint32_t n){(void)c;if(!bank_present[slot][bank])return -1;memcpy(out,banks[slot][bank]+offset,n);return (int)n;}
static int resolve(void*c,unsigned slot,unsigned id,const uint8_t hash[32],unsigned*bank){(void)c;for(unsigned i=0;i<2;i++)if(bank_present[slot][i]&&m10v_sd_u32(banks[slot][i]+8)==id&&m10v_constant_equal(hash,bank_hashes[slot][i],32)){*bank=i;return 0;}return M10V_ERROR_INVALID_RECIPE;}
static int snapshot(void*c,m10v_companion_snapshot*out){(void)c;memset(out,0,sizeof(*out));out->state=current;out->active_slot=active;for(unsigned slot=0;slot<M10V_SLOT_COUNT;slot++)if(M10V_CUSTOM(current.slots[slot].film)&&current.effects[slot].reserved[0])memcpy(out->custom_hashes[slot],bank_hashes[slot][current.effects[slot].reserved[0]-1],32);return m10v_companion_snapshot_identity(&io.metadata,out);}
static int persist(void*c,const m10v_library_state*next){(void)c;if(getenv("M10V_TEST_MISMATCH"))return M10V_IO_UNCERTAIN;current=*next;return M10V_IO_OK;}
static int tone(void*c,unsigned slot){(void)c;active=(int8_t)slot;return 0;}
static int settled(void*c){(void)c;return 0;}
static int ext_blocked(void*c){(void)c;return owner.pending.present;}
static int ext_read(void*c,m10v_extension_snapshot*out){(void)c;if(ext_writes&&getenv("M10V_TEST_EXT_UNKNOWN"))return M10V_ERROR_BRIDGE_UNAVAILABLE;*out=ext_state;return 0;}
static int ext_write(void*c,uint32_t field,uint32_t value){(void)c;ext_writes++;ext_state.values[field]=value;ext_state.revision[0]++;return M10V_IO_OK;}
static int exchange(void*ctx,const m10v_backend_request*r,m10v_backend_response*out){(void)ctx;
 if(r->command==M10V_BACKEND_READ_EXTENSIONS){int code=ext_read(0,(void*)out->snapshot);out->has_snapshot=!code;return code;}
 if(r->command==M10V_BACKEND_SUBMIT_EXTENSIONS||r->command==M10V_BACKEND_POLL_EXTENSIONS){m10v_extension_result result;const m10v_extension_patch*p=(const void*)r->patch;int code=r->command==M10V_BACKEND_SUBMIT_EXTENSIONS?m10v_extensions_apply(p,&ext_io,&result):m10v_extensions_poll(p->request_id,&ext_io,&result);out->status=result.status;out->has_snapshot=result.has_snapshot;if(result.has_snapshot)*(m10v_extension_snapshot*)(void*)out->snapshot=result.snapshot;return code;}
 if(r->command==M10V_BACKEND_FILM_VERIFY||r->command==M10V_BACKEND_FILM_POLL){m10v_film_bank_services storage={0,is_current,enter,leave,busy,references,store_bank,read_bank};return m10v_companion_stage_verify(r->film->upload,r->film->data,r->film->upload->id,&storage);}
 if(r->command==M10V_BACKEND_READ_STATE){if(getenv("M10V_TEST_ASYNC_READ")&&read_turn++==0){out->status=M10V_OPERATION_APPLYING;return 0;}int code=snapshot(0,out->snapshot);out->has_snapshot=code==0;return code;}
 if(r->command==M10V_BACKEND_SUBMIT){if(getenv("M10V_TEST_ASYNC_READ")&&!submit_attempted++){out->status=M10V_OPERATION_UNKNOWN;return M10V_ERROR_BUSY;}submitted=1;polls=0;out->status=M10V_OPERATION_APPLYING;return 0;}
 if(getenv("M10V_TEST_ASYNC_READ")&&!submitted){out->status=M10V_OPERATION_UNKNOWN;return M10V_ERROR_RESULT_UNKNOWN;}
 if(getenv("M10V_TEST_STALL")||++polls<3){out->status=M10V_OPERATION_APPLYING;return 0;}
 m10v_companion_result result;int code;
 if(owner.pending.present)code=m10v_companion_owner_poll(&io,r->patch->request_id,&result);
 else {m10v_companion_snapshot base;code=snapshot(0,&base);if(code)return code;code=m10v_companion_apply(&base,r->patch,&io,&result);}
 out->status=result.status;out->has_snapshot=result.has_snapshot;if(result.has_snapshot)*out->snapshot=result.snapshot;return code;
}
int main(void){
 m10v_companion_server_config cfg={0};ext_io=(m10v_extension_services){.owner=&ext_owner,.is_current=is_current,.enter=enter,.leave=leave,.is_busy=busy,.blocked=ext_blocked,.read=ext_read,.write=ext_write};ext_state.available=M10V_EXTENSION_MASK;ext_state.values[17]=28;ext_state.values[18]=28;ext_state.revision[0]=1;for(unsigned i=0;i<32;i++){cfg.key[i]=(uint8_t)i;cfg.build_id[i]=2;cfg.catalog_hash[i]=3;cfg.renderer_hash[i]=4;}for(unsigned i=0;i<16;i++)cfg.instance_id[i]=1;strcpy(cfg.key_id,"fixture-key");cfg.random=random_bytes;cfg.now_ms=m10v_linux_now_ms;cfg.operation_timeout_ms=getenv("M10V_TEST_MISMATCH")?10000:100;cfg.read_state=1;cfg.write_state=1;if(getenv("M10V_TEST_CURRENT")){const char *catalog=getenv("M10V_TEST_CATALOG_HASH"),*renderer=getenv("M10V_TEST_RENDERER_HASH");if(!catalog)catalog="653acf3c1b04db0ea2dd10114a1306b78bb4b584534945be8f9de9da25ebab4a";if(!renderer)renderer="80a4d357be06ff0e9510a20bef1035dc3e848ec585bd5d5cdee466c3980506a4";if(strlen(catalog)!=64||strlen(renderer)!=64||!m10v_unhex(catalog,32,cfg.catalog_hash)||!m10v_unhex(renderer,32,cfg.renderer_hash))return 2;}
 if(getenv("M10V_TEST_UPLOAD")){cfg.upload_film=1;memcpy(cfg.renderer_hash,m10v_sd_renderer_hash,32);}
 m10v_library_init(&current);if(getenv("M10V_TEST_FULL_TEN")){for(unsigned i=0;i<10;i++){current.slots[i].film=(uint16_t)(34+i);current.slots[i].grain=3;current.slots[i].halo_profile=6;current.slots[i].halo_spread=3;current.slots[i].halo_threshold=5;}m10v_companion_state_seal(&current,7);}
 m10v_companion_owner_init(&owner);io.owner=&owner;io.is_current=is_current;io.enter=enter;io.leave=leave;io.is_busy=busy;io.snapshot=snapshot;io.persist_once=persist;io.set_tone=tone;io.commit_settled=settled;io.resolve_custom=resolve;memcpy(io.metadata.build_id,cfg.build_id,32);memcpy(io.metadata.catalog_hash,cfg.catalog_hash,32);memcpy(io.metadata.renderer_hash,cfg.renderer_hash,32);m10v_companion_backend backend={0,exchange};int code=m10v_companion_serve(&cfg,&backend);fprintf(stderr,"Host fixture service exited: code=%d errno=%d\n",code,errno);return code;
}
