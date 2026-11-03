#include "resident_bridge.h"
#include <stddef.h>
_Static_assert(offsetof(m10v_resident_wire,request)==128,"request cacheline ownership");
_Static_assert(offsetof(m10v_resident_wire,response)%128==0,"response cacheline ownership");
_Static_assert(sizeof(m10v_resident_message)%128==0,"direction cacheline boundary");
static uint32_t byte_crc(uint32_t c,uint8_t b){c^=b;for(unsigned j=0;j<8;j++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));return c;}
uint32_t m10v_resident_crc(const m10v_resident_message*m,uint32_t sequence){
 if(!m||m->bytes>M10V_RESIDENT_PAYLOAD)return 0;
 uint32_t crc=~0u,words[]={sequence,m->command,m->bytes,m->correlation,m->code};
 for(unsigned i=0;i<5;i++)for(unsigned j=0;j<4;j++)crc=byte_crc(crc,(uint8_t)(words[i]>>(8*j)));
 for(uint32_t i=0;i<m->bytes;i++)crc=byte_crc(crc,m->payload[i]);return ~crc;
}
int m10v_resident_consume(m10v_resident_wire*w,m10v_resident_consumer*c,const m10v_resident_ops*io){
 if(!w||!c||!io||!io->invalidate_request||!io->clean_response||!io->execute||w->magic!=M10V_RESIDENT_MAGIC||w->version!=2||w->bytes!=sizeof(*w)||w->alive!=1)return 1;
 if(!io->invalidate_request(io->ctx,&w->request,sizeof(w->request)))return 2;
 uint32_t seq=w->request.sequence;if(!seq||(seq&1u))return 3;
 volatile const uint8_t*in=(volatile const uint8_t*)&w->request;uint8_t*out=(uint8_t*)&c->scratch;
 for(uint32_t i=0;i<sizeof(c->scratch);i++)out[i]=in[i];
 if(!io->invalidate_request(io->ctx,&w->request,sizeof(w->request)))return 2;
 if(w->request.sequence!=seq||c->scratch.sequence!=seq||w->alive!=1)return 4;
 if(c->scratch.bytes>M10V_RESIDENT_PAYLOAD||c->scratch.correlation||c->scratch.code||m10v_resident_crc(&c->scratch,seq)!=c->scratch.crc)return 5;
 if(seq==c->last_sequence)return c->last_crc==c->scratch.crc?0:5;
 if(c->last_sequence>0xfffffffcu||seq!=c->last_sequence+2)return 5;
 w->response.sequence=seq|1u;
 if(!io->clean_response(io->ctx,&w->response,128))return 2;
 uint32_t length=M10V_RESIDENT_PAYLOAD;
 int code=io->execute(io->ctx,c->scratch.command,c->scratch.payload,c->scratch.bytes,w->response.payload,&length);
 /* Execution may have committed even if publication fails; retain consumed
  * identity so retrying this sequence cannot execute a second time. */
 c->last_sequence=seq;c->last_crc=c->scratch.crc;
 if(length>M10V_RESIDENT_PAYLOAD)return 6;
 w->response.command=c->scratch.command;w->response.bytes=length;w->response.code=(uint32_t)code;w->response.correlation=c->scratch.crc;
 w->response.crc=m10v_resident_crc(&w->response,seq);
 if(!io->clean_response(io->ctx,&w->response,sizeof(w->response)))return 2;
 w->response.sequence=seq;
 if(!io->clean_response(io->ctx,&w->response,128))return 2;
 return 0;
}
