/* Independent24-byte AppData journal, owned cache in existing TopMenu tail. */
#include "m10v_zoom_camera.h"
#include "m10v_settings_controller.h"
extern uint32_t m10v_zoom_bits(unsigned);
extern int m10v_zoom_live_apply(unsigned);
extern uint32_t m10v_zoom_native_back_bits(uint32_t);
#ifndef M10V_ZOOM_SEED_LO
#define M10V_ZOOM_SEED_LO 0u
#define M10V_ZOOM_SEED_HI 0u
#define M10V_ZOOM_SEED_FIRST M10V_ZOOM_DEFAULT_FIRST
#define M10V_ZOOM_SEED_SECOND M10V_ZOOM_DEFAULT_SECOND
#endif
#define MAGIC 0x5a4d1000u
#define PENDING 4u
static const char names[2][12]={"M10VZA.bin","M10VZB.bin"};
static int ram(uint32_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p;}
static m10v_settings_controller *cache(void){
 if(!(*(volatile const uint32_t *)0x55063910u&1u))return 0;
 uint32_t owner=*(volatile const uint32_t *)0x55063988u;
 if(!ram(owner,M10V_SETTINGS_OWNER_BYTES+M10V_SETTINGS_CONTROLLER_BYTES))return 0;
 return (m10v_settings_controller *)(uintptr_t)(owner+M10V_SETTINGS_OWNER_BYTES);
}
static uint32_t filesystem(void){
 uint32_t m=((uint32_t (*)(void))0x53828014u)();
 if(!ram(m,12))return 0;
 uint32_t a=((uint32_t *)(uintptr_t)m)[2];if(!ram(a,4))return 0;
 uint32_t fs=*(uint32_t *)(uintptr_t)a;
 return ram(fs,0x24)&&((uint8_t *)(uintptr_t)fs)[0x20]?fs:0;
}
static int read_page(void *ctx,unsigned page,void *out,unsigned n){
 if(page>1||n!=M10V_ZOOM_BYTES)return -1;
 /* Native boolean cannot distinguish missing records from read failure. */
 return !!((int (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)((uint32_t)(uintptr_t)ctx,names[page],n,out);
}
static int write_page(void *ctx,unsigned page,const void *in,unsigned n){
 if(page>1||n!=M10V_ZOOM_BYTES)return -1;
 return !!((int (*)(uint32_t,const char *,uint32_t,const void *))0x53825fa8u)((uint32_t)(uintptr_t)ctx,names[page],n,in);
}
static void publish(m10v_settings_controller *p,const m10v_zoom_state *s){
 if(!p)return;
 unsigned slot=(p->zoom_flags&~7u)==MAGIC?p->zoom_flags&7u:2;
 p->zoom_mm[0]=s->mm[0];p->zoom_mm[1]=s->mm[1];p->zoom_flags=MAGIC|slot;
}
const uint32_t m10v_zoom_seed_parameters[6]={0x31575a4du,M10V_ZOOM_SEED_LO,M10V_ZOOM_SEED_HI,
 ~(0x31575a4du^M10V_ZOOM_SEED_LO^M10V_ZOOM_SEED_HI),M10V_ZOOM_SEED_FIRST,M10V_ZOOM_SEED_SECOND};
static int apply_seed(m10v_zoom_state *s,uint32_t fs,const m10v_zoom_io *io){
 if(!(M10V_ZOOM_SEED_LO|M10V_ZOOM_SEED_HI))return 0;
 const uint32_t *wanted=m10v_zoom_seed_parameters;
 uint32_t back[4];unsigned equal=1;
 int read=((int (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,"M10VZW.bin",sizeof(back),back);
 for(unsigned i=0;i<4;i++)if(!read||back[i]!=wanted[i])equal=0;
 if(equal)return 0;
 if(m10v_zoom_replace(s,M10V_ZOOM_SEED_FIRST,M10V_ZOOM_SEED_SECOND,io))return -1;
 if(!((int (*)(uint32_t,const char *,uint32_t,const void *))0x53825fa8u)(fs,"M10VZW.bin",16,wanted))return -1;
 if(!((int (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,"M10VZW.bin",sizeof(back),back))return -1;
 for(unsigned i=0;i<4;i++)if(back[i]!=wanted[i])return -1;
 return 0;
}
int m10v_zoom_camera_load(m10v_zoom_state *s){
 uint32_t fs=filesystem();if(!s||!fs)return -1;
 m10v_zoom_io io={(void *)(uintptr_t)fs,read_page,write_page};
 int result=m10v_zoom_load(s,&io);if(result>=0&&apply_seed(s,fs,&io))return -1;
 if(result>=0)publish(cache(),s);return result;
}
static m10v_settings_controller *ready(void){
 m10v_settings_controller *p=cache();
 if(p&&(p->zoom_flags&~7u)!=MAGIC){m10v_zoom_state s;if(m10v_zoom_camera_load(&s)<0)return 0;}
 return p;
}
uint32_t m10v_zoom_camera_bits(unsigned slot){
 if(slot>=2)return 0x3f800000u;
 m10v_settings_controller *p=ready();return m10v_zoom_bits(p?p->zoom_mm[slot]:slot?M10V_ZOOM_DEFAULT_SECOND:M10V_ZOOM_DEFAULT_FIRST);
}
unsigned m10v_zoom_camera_slot(uint32_t bits){
 m10v_settings_controller *p=ready();unsigned preferred=p?p->zoom_flags&3u:2;
 if(preferred<=2&&m10v_zoom_camera_bits(preferred)==bits)return preferred;
 if(bits==0x3f800000u)return 2;
 for(unsigned i=0;i<2;i++)if(m10v_zoom_camera_bits(i)==bits)return i;
 return 2;
}
int m10v_zoom_camera_select(unsigned slot){
 m10v_settings_controller *p=ready();if(!p||slot>2)return -1;
 p->zoom_flags=MAGIC|slot;return 0;
}
int m10v_zoom_camera_save(m10v_zoom_state *s,const m10v_zoom_editor *e){
 if(!s||!e)return -1;
 uint32_t fs=filesystem();if(!fs)return -1;
 m10v_zoom_io io={(void *)(uintptr_t)fs,read_page,write_page};m10v_zoom_state fresh;
 if(m10v_zoom_load(&fresh,&io)<0)return -1;
 int result=m10v_zoom_save(&fresh,e,&io);if(result)return result;
 m10v_settings_controller *p=ready();
 uint32_t root=((uint32_t (*)(void))0x53525d5cu)();
 /* A failed apply leaves the backend at the old multiplier, which may no
  * longer identify any slot in the newly committed configuration. Preserve
  * the intended slot until successful native selection resolves it. */
 unsigned pending=p?(p->zoom_flags&PENDING):0;
 unsigned current=p&&pending?p->zoom_flags&3u:2;
 if(!pending&&ram(root,4)){uint32_t back=*(uint32_t *)(uintptr_t)root;if(ram(back,4))current=m10v_zoom_camera_slot(m10v_zoom_native_back_bits(back));}
 *s=fresh;publish(p,&fresh);
 if(p)p->zoom_flags=MAGIC|current|pending;
 if(current!=e->slot)return 0;
 if(p)p->zoom_flags=MAGIC|current|PENDING;
 int applied=m10v_zoom_live_apply(current);
 /* live_apply normally clears pending through camera_select. Also clear it
  * here on confirmed success so this contract does not depend on callbacks. */
 if(!applied&&p)p->zoom_flags=MAGIC|current;
 return applied;
}
#if M10V_COMPANION_ENABLED
static int native_crop_matches(const m10v_zoom_state *durable){
 uint32_t root=((uint32_t(*)(void))0x53525d5cu)();
 if(!ram(root,4)||!ram(*(uint32_t*)(uintptr_t)root,4))return 0;
 uint32_t expected=m10v_zoom_native_back_bits(*(uint32_t*)(uintptr_t)root);
 if(expected!=0x3f800000u&&expected!=m10v_zoom_bits(durable->mm[0])&&expected!=m10v_zoom_bits(durable->mm[1]))return 0;
 extern uint32_t m10v_zoom_native_front_bits(uint32_t);
 root=((uint32_t(*)(void))0x5320ad88u)();
 uint32_t front=root?((uint32_t(*)(uint32_t))0x5320b31cu)(root):0;
 if(!ram(front,4)||m10v_zoom_native_front_bits(front)!=expected)return 0;
 return 1;
}
int m10v_zoom_camera_prime(void){
 m10v_settings_controller *p=cache();
 if(!p)return -1;
 if((p->zoom_flags&~7u)==MAGIC)return 0;
 uint32_t fs=filesystem();if(!fs)return -1;
 /* An unapplied build seed belongs to the native installation path. */
 if(M10V_ZOOM_SEED_LO|M10V_ZOOM_SEED_HI){
  uint32_t marker[4];
  if(!((int (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,"M10VZW.bin",sizeof(marker),marker))return -1;
  for(unsigned i=0;i<4;i++)if(marker[i]!=m10v_zoom_seed_parameters[i])return -1;
 }
 m10v_zoom_io io={(void*)(uintptr_t)fs,read_page,0};m10v_zoom_state durable;
 if(m10v_zoom_load(&durable,&io)<0||cache()!=p||!native_crop_matches(&durable))return -1;
 publish(p,&durable);
 return 0;
}
int m10v_zoom_camera_snapshot(m10v_zoom_state *s){
 uint32_t fs=filesystem();if(!s||!fs)return -1;
 m10v_settings_controller *p=cache();
 if(!p||(p->zoom_flags&~7u)!=MAGIC||(p->zoom_flags&PENDING)||(p->zoom_flags&3u)>2u)return -1;
 m10v_zoom_io io={(void*)(uintptr_t)fs,read_page,write_page};m10v_zoom_state durable;
 if(m10v_zoom_load(&durable,&io)<0||durable.mm[0]!=p->zoom_mm[0]||durable.mm[1]!=p->zoom_mm[1])return -1;
 if(!native_crop_matches(&durable))return -1;
 /* No lazy cache load, seed application, setters or cache publication. */
 *s=durable;return 0;
}
#endif
