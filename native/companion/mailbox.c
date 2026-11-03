#include "mailbox.h"
#include "target_adapter.h"
_Static_assert(sizeof(m10v_companion_mailbox)<65536,"bounded mailbox");
static uint32_t crc_byte(uint32_t crc,uint8_t byte){crc^=byte;for(unsigned b=0;b<8;b++)crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u);return crc;}
static uint32_t crc(uint32_t generation,uint32_t sequence,uint32_t command,const uint8_t *data,uint32_t length){
 uint32_t value=~0u,words[5]={M10V_COMPANION_PROTOCOL,generation,sequence,command,length};
 for(unsigned i=0;i<5;i++)for(unsigned b=0;b<4;b++)value=crc_byte(value,(uint8_t)(words[i]>>(b*8)));
 for(uint32_t i=0;i<length;i++)value=crc_byte(value,data[i]);return ~value;
}
static int ready(const m10v_companion_channel*c,uint32_t generation){
 return c&&generation&&c->owner_generation==generation&&c->acquire_owner&&c->release_owner&&c->is_owner_alive&&c->is_owner_alive(c->ctx,generation)&&c->mailbox&&c->producer_flush&&c->consumer_invalidate&&c->consumer_flush&&c->producer_invalidate&&c->wake_owner;
}
static int header(const m10v_companion_mailbox*m,uint32_t generation){return m->magic==M10V_COMPANION_MAGIC&&m->protocol==1&&m->capacity==M10V_COMPANION_CAPACITY&&m->owner_generation==generation;}
void m10v_companion_mailbox_init(m10v_companion_mailbox*m,uint32_t generation){if(!m)return;uint8_t*p=(uint8_t*)m;for(unsigned i=0;i<sizeof(*m);i++)p[i]=0;m->magic=M10V_COMPANION_MAGIC;m->protocol=1;m->capacity=M10V_COMPANION_CAPACITY;m->owner_generation=generation;}
int m10v_companion_exchange(m10v_companion_channel*c,const m10v_companion_request*r,m10v_companion_response*out){
 if(!r||!out)return M10V_COMPANION_INVALID;
 if(!ready(c,r->generation))return M10V_COMPANION_BRIDGE_UNAVAILABLE;
 if(c->in_flight)return M10V_COMPANION_BUSY;
 if(!r->sequence||r->length>M10V_COMPANION_CAPACITY||(r->length&&!r->payload))return M10V_COMPANION_INVALID;
 if(r->command<M10V_PING||r->command>M10V_READ_STATE)return M10V_COMPANION_DISABLED;
 if(!c->acquire_owner(c->ctx,r->generation))return M10V_COMPANION_BRIDGE_UNAVAILABLE;
 c->in_flight=1;int result=M10V_COMPANION_BRIDGE_UNAVAILABLE;m10v_companion_mailbox*m=c->mailbox;
 if(!c->producer_invalidate(c->ctx,m,sizeof(*m))||!ready(c,r->generation)||!header(m,r->generation))goto done;
 if(r->sequence<=m->request_sequence){result=M10V_COMPANION_INVALID;goto done;}
 if(m->request_sequence!=m->response_sequence){result=M10V_COMPANION_BUSY;goto done;}
 m->command=r->command;m->request_length=r->length;
 for(uint32_t i=0;i<r->length;i++)m->request_payload[i]=r->payload[i];
 m->request_crc=crc(r->generation,r->sequence,r->command,r->payload,r->length);
 if(!c->producer_flush(c->ctx,m,sizeof(*m)))goto done;
 __atomic_thread_fence(__ATOMIC_RELEASE);m->request_sequence=r->sequence;
 if(!c->producer_flush(c->ctx,(void*)&m->request_sequence,sizeof(m->request_sequence))||!c->wake_owner(c->ctx))goto done;
 /* Read-only exchange: target wake must schedule and complete its bounded
  * owner turn. No unbounded Linux busy-loop, arbitrary RTOS call or write. */
 if(!ready(c,r->generation)||!c->producer_invalidate(c->ctx,m,sizeof(*m))||!ready(c,r->generation))goto done;
 __atomic_thread_fence(__ATOMIC_ACQUIRE);
 if(!header(m,r->generation)||m->response_sequence!=r->sequence||m->response_length>M10V_COMPANION_CAPACITY||m->response_code>M10V_COMPANION_DISABLED)goto done;
 if(m->response_crc!=crc(r->generation,r->sequence,m->response_code,m->response_payload,m->response_length))goto done;
 out->sequence=r->sequence;out->code=m->response_code;out->length=m->response_length;
 for(uint32_t i=0;i<out->length;i++)out->payload[i]=m->response_payload[i];result=(int)out->code;
 done:c->in_flight=0;c->release_owner(c->ctx,r->generation);return result;
}
static int consume_held(m10v_companion_channel*c,const m10v_companion_target*t){
 m10v_companion_mailbox*m=c->mailbox;
 if(!c->consumer_invalidate(c->ctx,m,sizeof(*m)))return M10V_COMPANION_BRIDGE_UNAVAILABLE;
 uint32_t generation=m->owner_generation;
 if(!ready(c,generation)||!t->is_owner_alive(t->ctx,generation)||!header(m,generation))return M10V_COMPANION_BRIDGE_UNAVAILABLE;
 __atomic_thread_fence(__ATOMIC_ACQUIRE);uint32_t sequence=m->request_sequence;
 if(!sequence||sequence<=m->last_consumed)return M10V_COMPANION_INVALID;
 uint32_t code=M10V_COMPANION_OK,length=0;
 if(m->request_length>M10V_COMPANION_CAPACITY||m->request_crc!=crc(generation,sequence,m->command,m->request_payload,m->request_length))code=M10V_COMPANION_INVALID;
 else if(m->command<M10V_PING||m->command>M10V_READ_STATE)code=M10V_COMPANION_DISABLED;
 else if(t->is_busy(t->ctx))code=M10V_COMPANION_BUSY;
 else {length=M10V_COMPANION_CAPACITY;code=(uint32_t)t->snapshot(t->ctx,m->command,m->response_payload,&length);if(length>M10V_COMPANION_CAPACITY){length=0;code=M10V_COMPANION_INVALID;}}
 if(code!=M10V_COMPANION_OK)length=0;
 if(!ready(c,generation)||!t->is_owner_alive(t->ctx,generation))return M10V_COMPANION_BRIDGE_UNAVAILABLE;
 m->last_consumed=sequence;m->response_length=length;m->response_code=code;m->response_crc=crc(generation,sequence,code,m->response_payload,length);
 if(!c->consumer_flush(c->ctx,m,sizeof(*m)))return M10V_COMPANION_BRIDGE_UNAVAILABLE;
 __atomic_thread_fence(__ATOMIC_RELEASE);m->response_sequence=sequence;
 return c->consumer_flush(c->ctx,(void*)&m->response_sequence,sizeof(m->response_sequence))?M10V_COMPANION_OK:M10V_COMPANION_BRIDGE_UNAVAILABLE;
}

int m10v_companion_consume(m10v_companion_channel*c,const m10v_companion_target*t){
 if(!c||!t||!t->is_owner_alive||!t->snapshot||!t->is_busy||!ready(c,c->owner_generation))return M10V_COMPANION_BRIDGE_UNAVAILABLE;
 uint32_t generation=c->owner_generation;
 if(!t->is_owner_alive(t->ctx,generation)||!c->acquire_owner(c->ctx,generation))return M10V_COMPANION_BRIDGE_UNAVAILABLE;
 int result=consume_held(c,t);c->release_owner(c->ctx,generation);return result;
}
