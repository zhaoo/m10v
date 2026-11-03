#include "../native/companion/resident_bridge.h"
#include <string.h>
static m10v_resident_wire wire;
static m10v_resident_consumer consumer;
static unsigned mode,calls,cleans,invalidations;
static int cache_in(void*ctx,void*p,uint32_t n){(void)ctx;if(p!=(void*)&wire.request||n!=sizeof(wire.request))return 0;invalidations++;if(mode==4)return 0;if(mode==5&&invalidations==2)wire.request.sequence+=2;return 1;}
static int cache_out(void*ctx,void*p,uint32_t n){(void)ctx;cleans++;if(mode==6)return 0;return p==(void*)&wire.response&&n<=sizeof(wire.response);}
static int execute(void*ctx,uint32_t command,const uint8_t*in,uint32_t bytes,uint8_t*out,uint32_t*length){(void)ctx;if(command!=2||bytes!=3||memcmp(in,"abc",3))return 99;calls++;if(mode==8){*length=M10V_RESIDENT_PAYLOAD+1;return 0;}memcpy(out,"done",4);*length=4;return mode==9?6:0;}
int test_resident_case(unsigned value){
 mode=value;calls=cleans=invalidations=0;memset(&wire,0,sizeof(wire));memset(&consumer,0,sizeof(consumer));
 wire.magic=M10V_RESIDENT_MAGIC;wire.version=2;wire.bytes=sizeof(wire);wire.alive=1;
 wire.request.sequence=2;wire.request.command=2;wire.request.bytes=3;memcpy(wire.request.payload,"abc",3);wire.request.crc=m10v_resident_crc(&wire.request,2);
 if(mode==1)wire.request.sequence=1;if(mode==2)wire.request.crc^=1;if(mode==3)wire.alive=0;if(mode==7)wire.request.bytes=M10V_RESIDENT_PAYLOAD+1;
 m10v_resident_message before=wire.request;
 m10v_resident_ops io={0,cache_in,cache_out,execute};int result=m10v_resident_consume(&wire,&consumer,&io);
 if(mode>=1&&mode<=7){if(calls)return 10+mode;if(!result)return 20+mode;return 0;}
 if(calls!=1||!cleans)return 30;
 if(memcmp(&before,&wire.request,sizeof(before)))return 31;
 if(mode==8)return !result||wire.response.sequence==2;
 if(result||wire.response.sequence!=2||wire.response.correlation!=before.crc||wire.response.code!=(mode==9?6u:0u)||wire.response.bytes!=4||memcmp(wire.response.payload,"done",4)||wire.response.crc!=m10v_resident_crc(&wire.response,2))return 32;
 if(m10v_resident_consume(&wire,&consumer,&io)||calls!=1)return 33;
 return 0;
}
