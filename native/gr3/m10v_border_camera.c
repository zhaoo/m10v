/* Independent global border journal. No M10V film-state/schema/SD changes.
 * This module contains no composition or pixel access. */
#include "m10v_border_camera.h"
#define BORDER_MAGIC 0x31524442u
#define CACHE_MAGIC 0x3143424du
typedef struct {uint32_t magic,version,sequence,style,reserved,crc;} border_record;
static const char names[2][12]={"BORDERA.BIN","BORDERB.BIN"};
_Static_assert(sizeof(border_record)==24,"border journal ABI");
_Static_assert(sizeof(m10v_border_cache)==16,"border owner cache ABI");
static int ram(uintptr_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<=0x80000000u-n;}
static __attribute__((always_inline)) inline uint32_t crc(const border_record *r){
 uint32_t c=0xffffffffu;for(uint32_t i=0;i<20;i++){c^=((const uint8_t *)r)[i];for(uint32_t b=0;b<8;b++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return ~c;
}
static __attribute__((always_inline)) inline int valid(const border_record *r){return r->magic==BORDER_MAGIC&&r->version==1&&r->style<=M10V_BORDER_FILM&&!r->reserved&&r->crc==crc(r);}
static uint32_t filesystem(void){
 uint32_t m=((uint32_t (*)(void))0x53828014u)();if(!ram(m,12))return 0;
 uint32_t a=*(const uint32_t *)(uintptr_t)(m+8);if(!ram(a,4))return 0;
 uint32_t fs=*(const uint32_t *)(uintptr_t)a;return ram(fs,0x24)&&*(const uint8_t *)(uintptr_t)(fs+0x20)?fs:0;
}
static int latest(uint32_t fs,border_record *out){
 border_record r[2];int good[2];for(uint32_t i=0;i<sizeof(r);i++)((uint8_t *)r)[i]=0;
 for(uint32_t i=0;i<2;i++)good[i]=((int (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,names[i],24,&r[i])&&valid(&r[i]);
 if(!good[0]&&!good[1])return 0;
 uint32_t i=!good[0]||(good[1]&&r[1].sequence>r[0].sequence);
 for(uint32_t n=0;n<6;n++)((uint32_t *)out)[n]=((const uint32_t *)&r[i])[n];return 1;
}
static m10v_border_cache *cache(uint32_t owner){
 if(!ram(owner,M10V_BORDER_CACHE_OWNER_OFFSET+sizeof(m10v_border_cache)))return 0;
 return (m10v_border_cache *)(uintptr_t)(owner+M10V_BORDER_CACHE_OWNER_OFFSET);
}
static int publish(m10v_border_cache *c,uint32_t style,uint32_t sequence){
 uint32_t v=__atomic_load_n(&c->version,__ATOMIC_ACQUIRE);
 if((v&1u)||!__atomic_compare_exchange_n(&c->version,&v,v+1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return -1;
 c->style=style;c->sequence=sequence;c->magic=CACHE_MAGIC;
 __atomic_store_n(&c->version,v+2?v+2:2,__ATOMIC_RELEASE);return 0;
}
int m10v_border_camera_refresh(uint32_t owner){
 m10v_border_cache *c=cache(owner);if(!c)return -1;
 uint32_t fs=filesystem();if(!fs)return -1;
 border_record r;int found=latest(fs,&r);return publish(c,found?r.style:M10V_BORDER_OFF,found?r.sequence:0);
}
int m10v_border_camera_save(uint32_t owner,uint32_t style){
 m10v_border_cache *c=cache(owner);if(!c||style>M10V_BORDER_FILM)return -1;
 uint32_t fs=filesystem();if(!fs)return -2;
 border_record old,r,back;uint32_t sequence=latest(fs,&old)?old.sequence:0;
 /* UI is the sole journal writer. A stable authenticated cache supplies a
  * lower sequence bound when card reads fail transiently; never rewind it. */
 uint32_t version=__atomic_load_n(&c->version,__ATOMIC_ACQUIRE);
 if(version&&!(version&1u)&&c->magic==CACHE_MAGIC&&c->style<=M10V_BORDER_FILM){
  uint32_t floor=c->sequence;__atomic_thread_fence(__ATOMIC_ACQUIRE);
  if(version==__atomic_load_n(&c->version,__ATOMIC_RELAXED)&&floor>sequence)sequence=floor;
 }
 if(sequence==0xffffffffu)return -3;
 r.magic=BORDER_MAGIC;r.version=1;r.sequence=sequence+1;r.style=style;r.reserved=0;r.crc=crc(&r);
 for(uint32_t i=0;i<sizeof(back);i++)((uint8_t *)&back)[i]=0;
 if(!((int (*)(uint32_t,const char *,uint32_t,const void *))0x53825fa8u)(fs,names[r.sequence&1],24,&r))return -4;
 if(!((int (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,names[r.sequence&1],24,&back))return -5;
 if(!valid(&back))return -6;
 for(uint32_t i=0;i<6;i++)if(((const uint32_t *)&r)[i]!=((const uint32_t *)&back)[i])return -7;
 /* Readback of one slot does not prove that it wins the journal. In
  * particular an unpublished cache plus failed initial reads can hide an
  * older higher-sequence slot. Report failure instead of false success. */
 if(!latest(fs,&old))return -8;
 for(uint32_t i=0;i<6;i++)if(((const uint32_t *)&r)[i]!=((const uint32_t *)&old)[i])return -9;
 return publish(c,style,r.sequence)?-10:0;
}
int m10v_border_camera_snapshot(uint32_t *out){
 if(!ram((uintptr_t)out,4)||!(*(const volatile uint32_t *)0x55063910u&1u))return 0;
 uint32_t owner=__atomic_load_n((const uint32_t *)0x55063988u,__ATOMIC_ACQUIRE);
 m10v_border_cache *c=cache(owner);if(!c)return 0;
 uint32_t before=__atomic_load_n(&c->version,__ATOMIC_ACQUIRE);
 if(!before||(before&1u)||c->magic!=CACHE_MAGIC)return 0;
 uint32_t style=c->style;__atomic_thread_fence(__ATOMIC_ACQUIRE);
 if(c->magic!=CACHE_MAGIC||before!=__atomic_load_n(&c->version,__ATOMIC_RELAXED)||style>M10V_BORDER_FILM)return 0;
 *out=style;return 1;
}
uint32_t m10v_border_camera_cached(void){
 uint32_t style=M10V_BORDER_OFF;(void)m10v_border_camera_snapshot(&style);return style;
}
