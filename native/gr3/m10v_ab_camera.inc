/* Included in the settings adapter: uses its explicit owner and stock ABI.
 * Only UI code accesses this state. No capture worker, mutable global or new
 * parameter bank. The separately journalled pair contains no active flag. */
#if M10V_BORDER_ENABLED
#include "m10v_border_camera.h"
#endif
extern uint32_t m10v_ab_adj_event_original(uint32_t,uint32_t);
extern uint32_t m10v_ab_mapper_original(uint32_t,uint32_t);
extern uint32_t m10v_ab_selector_original(uint32_t,uint32_t);
extern uint32_t m10v_ab_live_enter_original(uint32_t,uint32_t,uint32_t);
extern uint32_t m10v_ab_live_leave_original(uint32_t);
extern uint32_t m10v_ab_live_destroy_original(uint32_t);
extern uint32_t m10v_ab_live_event_original(uint32_t,uint32_t);
static int ab_ram(uint32_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<=0x80000000u-n;}
static m10v_settings_controller *ab_owner(void){
 if(!(*(const volatile uint32_t *)0x55063910u&1u))return 0;
 uint32_t owner=*(const volatile uint32_t *)0x55063988u;
 if(!ab_ram(owner,M10V_SETTINGS_OWNER_BYTES+M10V_SETTINGS_CONTROLLER_BYTES))return 0;
 m10v_settings_controller *p=page(owner,0);
 return *(const uint32_t *)p==m10v_settings_controller_vtable()?p:0;
}
static uint32_t ab_current(void){
 uint32_t tone=((uint32_t (*)(void))0x532bd6b4u)();
 for(uint32_t i=0;i<M10V_TONE_CHOICES;i++)if(tone==m10v_ab_tone(i))return i;return M10V_TONE_CHOICES;
}
static uint32_t ab_route(void){
 uint32_t root=((uint32_t (*)(void))0x5320ad88u)();
 return ((fn1)0x53228c4cu)(((fn1)0x5320aefcu)(root));
}
static int ab_apply(uint32_t slot){
 if(slot>=m10v_camera_library_shooting_count())return -1;
 uint32_t root=((uint32_t (*)(void))0x5320ad88u)();
 uint32_t model=((fn1)0x5320ba9cu)(root);
 uint8_t *m=(uint8_t *)(uintptr_t)model;uint8_t prior=m[0x1b];m[0x1b]=0;
 if(M10V_APPENDED_SLOTS)((fn2)0x532bd61cu)(model,0);
 ((fn2)0x532c26c0u)(model,m10v_ab_tone(slot));m[0x1b]=prior;
 return ab_current()==slot?0:-1;
}
typedef struct {uint32_t magic,version,sequence,pair,reserved,crc;} ab_record;
static const char ab_files[2][12]={"M10VAB0.BIN","M10VAB1.BIN"};
static uint32_t ab_crc(const ab_record *r){
 uint32_t c=0xffffffffu;for(uint32_t i=0;i<20;i++){c^=((const uint8_t *)r)[i];for(uint32_t b=0;b<8;b++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return ~c;
}
static __attribute__((always_inline)) inline int ab_valid(const ab_record *r){return r->magic==0x3142414du&&(r->version==1||r->version==2||(M10V_APPENDED_SLOTS&&(r->version==3||r->version==4)))&&!r->reserved&&(r->pair&255)<(r->version==1?5u:r->version==2?12u:r->version==3?17u:22u)&&(r->pair>>8)<(r->version==1?5u:r->version==2?12u:r->version==3?17u:22u)&&(r->pair&255)!=(r->pair>>8)&&r->crc==ab_crc(r);}
static uint32_t ab_fs(void){
 uint32_t m=((uint32_t (*)(void))0x53828014u)();if(!ab_ram(m,12))return 0;
 uint32_t a=*(const uint32_t *)(uintptr_t)(m+8);if(!ab_ram(a,4))return 0;
 uint32_t fs=*(const uint32_t *)(uintptr_t)a;
 return ab_ram(fs,0x24)&&*(const uint8_t *)(uintptr_t)(fs+0x20)?fs:0;
}
static int ab_latest(uint32_t fs,ab_record *out){
 ab_record r[2];int good[2];
 for(uint32_t i=0;i<sizeof(r);i++)((volatile uint8_t *)r)[i]=0;
 for(uint32_t i=0;i<2;i++)good[i]=((uint32_t (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,ab_files[i],24,&r[i])&&ab_valid(&r[i]);
 if(!good[0]&&!good[1])return 0;
 uint32_t i=!good[0]||(good[1]&&r[1].sequence>r[0].sequence);
 for(uint32_t n=0;n<6;n++)((uint32_t *)out)[n]=((const uint32_t *)&r[i])[n];return 1;
}
static int ab_save(uint32_t a,uint32_t b){
 uint32_t fs=ab_fs();if(!fs||a>=M10V_TONE_CHOICES||b>=M10V_TONE_CHOICES||a==b)return -1;
 ab_record old,r,back;for(uint32_t i=0;i<sizeof(back);i++)((volatile uint8_t *)&back)[i]=0;uint32_t seq=ab_latest(fs,&old)?old.sequence:0;if(seq==0xffffffffu)return -1;
 r.magic=0x3142414du;r.version=M10V_APPENDED_SLOTS?4:2;r.sequence=seq+1;r.pair=a|(b<<8);r.reserved=0;r.crc=ab_crc(&r);
 if(!((uint32_t (*)(uint32_t,const char *,uint32_t,const void *))0x53825fa8u)(fs,ab_files[r.sequence&1],24,&r)||
    !((uint32_t (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,ab_files[r.sequence&1],24,&back)||!ab_valid(&back))return -1;
 for(uint32_t i=0;i<6;i++)if(((const uint32_t *)&r)[i]!=((const uint32_t *)&back)[i])return -1;return 0;
}
static void ab_pair(m10v_ab *s){
 uint32_t fs=ab_fs();ab_record r;
 if(fs&&ab_latest(fs,&r)){s->a=r.pair&255;s->b=r.pair>>8;
  if(r.version==1){s->a=s->a?s->a+7:1;s->b=s->b?s->b+7:1;}
  if(M10V_APPENDED_SLOTS&&r.version<3){s->a=s->a==1?12:s->a>=8?s->a+5:s->a;s->b=s->b==1?12:s->b>=8?s->b+5:s->b;}
 }
}
/* No A/B views are added to the native LiveView tree. These legacy words
 * remain reserved solely to preserve the controller ABI. Navigation, capture
 * and power may clear debounce state without touching any UI object. */
static void ab_clear(m10v_ab *s){
 s->down=0;for(uint32_t i=0;i<4;i++)s->reserved[i]=0;
}
static void ab_stop(m10v_ab *s){s->enabled=0;ab_clear(s);}
/* UI controllers receive both raw switch packets and logical key events.
 * The global mapper is not on every device dispatch path. */
static uint32_t ab_event_key(uint32_t event){
 uint32_t key=*(const uint16_t *)(uintptr_t)event;
 if(key!=4)return key;
 uint32_t payload=*(const uint32_t *)(uintptr_t)(event+4);
 if(!ab_ram(payload,8))return key;
 const uint8_t *p=(const uint8_t *)(uintptr_t)payload;
 M10V_LOG(95,event,payload,p[0],*(const uint32_t *)(uintptr_t)(payload+4));
 if(p[0]==1&&p[4]==1)return 0x37;
 if(p[0]==2)return p[4]==1?0x38:p[4]==0?0x36:key;
 return key;
}
#include "m10v_ab_host.inc"
uint32_t m10v_settings_controller_ab_setup(uint32_t controller,uint32_t event,uint32_t parent){
 uint32_t key=ab_event_key(event);
#if M10V_AB_NATIVE_HOST
 if(ab_host_followup(ab_owner(),controller,key,parent))return 1;
#endif
 /* Native A1 queues route 1. A DISP action can already have left this event
  * ahead of our queued 193 navigation. Consume it only for the exact source
  * while that navigation is pending; ready (including failure) clears it. */
 if(key==0xa1){
  m10v_settings_controller *p=ab_owner();
  if(!p||!p->pending_source||p->pending_source!=controller||ab_route()!=parent)return 0;
  p->pending_source=0;M10V_LOG(89,key,9,controller,parent);return 1;
 }
 if(key<0x36||key>0x38)return 0;
 uint32_t root=((uint32_t (*)(void))0x5320ad88u)();uint32_t model=((fn1)0x5320ba9cu)(root);
 if(!ab_ram(model,0x20)){M10V_LOG(89,key,1,model,parent);return 0;}
 M10V_LOG(88,key,parent,*(const uint8_t *)(uintptr_t)(model+0x1b)|((uint32_t)*(const uint8_t *)(uintptr_t)(model+0x1d)<<8),ab_route());
 if(*(const uint8_t *)(uintptr_t)(model+0x1b)){M10V_LOG(89,key,2,model,parent);return 0;}
 if(parent==0x02000012u&&*(const uint8_t *)(uintptr_t)(model+0x1d)){M10V_LOG(89,key,3,model,parent);return 0;}
 m10v_settings_controller *p=ab_owner();
 if(!p){m10v_settings_factory_original(0x55063914u,0x0200004au);p=ab_owner();}
#if M10V_DEBUG_MODE
 uint32_t owner=*(const volatile uint32_t *)0x55063988u;
 uint32_t actual=ab_ram(owner,M10V_SETTINGS_OWNER_BYTES+4)?*(const uint32_t *)(uintptr_t)(owner+M10V_SETTINGS_OWNER_BYTES):0;
 M10V_LOG(90,*(const volatile uint32_t *)0x55063910u,owner,actual,m10v_settings_controller_vtable());
#endif
 if(!p){M10V_LOG(89,key,4,0,parent);return 0;}
 if(key==0x36){p->ab.down=0;M10V_LOG(89,key,5,(uint32_t)(uintptr_t)p,0);return 1;}
 if(key==0x38||p->ab.down){M10V_LOG(89,key,key==0x38?6:7,(uint32_t)(uintptr_t)p,p->ab.down);return 1;}
 p->ab.down=1;M10V_LOG(89,key,8,(uint32_t)(uintptr_t)p,1);
#if M10V_DEBUG_MODE
 uint32_t gate=((fn1)0x5320afbcU)(root);
 M10V_LOG(99,gate,ab_ram(gate,0x14)?*(const uint8_t *)(uintptr_t)(gate+0x10):0xffffffffu,
  ab_ram(controller,0x128)?*(const uint32_t *)(uintptr_t)(controller+0x124):0,
  ab_ram(controller,0x150)?*(const uint8_t *)(uintptr_t)(controller+0x14c):0xffffffffu);
#endif
 M10V_LOG(86,controller,model,0,parent);
#if M10V_AB_NATIVE_HOST
 ab_host_open(p,controller,parent);
#else
 p->pending_source=controller;
 ((fn3)0x5316c9d8u)(controller,M10V_SETTINGS_AB_ROUTE,parent);M10V_LOG(96,controller,parent,key,ab_route());return 1;
#endif
 return 1;
}
uint32_t m10v_settings_controller_ab_adj_event(uint32_t controller,uint32_t event){
 uint32_t key=ab_event_key(event);
 if(key==0xa1&&m10v_settings_controller_ab_setup(controller,event,0x02000000u))return 1;
#if M10V_AB_NATIVE_HOST
 if(ab_host_followup(ab_owner(),controller,key,0x02000000u))return 1;
 if(ab_host_event(ab_owner(),controller,event))return 1;
#endif
 /* A normal ImageControl confirmation is an explicit exit from A/B, even
  * when the same look is confirmed. Do this before native OK queues 0x86;
  * the transition must not carry stale session state into LiveView. No
  * widget cleanup or synchronous diagnostics belong on this exit path. */
 m10v_settings_controller *p=ab_owner();
 if(key==0xd8&&p&&p->ab.enabled&&ab_route()==0x02000000u&&
    ab_ram(controller,0x274)&&ab_host_word(controller,0)==0x53b394e0u&&
    *(const uint8_t *)(uintptr_t)(controller+0x270)!=1&&
    ((fn2)0x531a2820u)(controller,*(const uint8_t *)(uintptr_t)(controller+0x1f4))==12){
  ab_stop(&p->ab);
 }
 if(key>=0x36&&key<=0x38)M10V_LOG(91,key,ab_route(),*(const uint32_t *)(uintptr_t)controller,*(const uint8_t *)(uintptr_t)(controller+0x270));
 if(key>=0x36&&key<=0x38&&ab_route()==0x02000000u&&
    *(const uint32_t *)(uintptr_t)controller==0x53b394e0u&&
    *(const uint8_t *)(uintptr_t)(controller+0x270)!=1&&
    ((fn2)0x531a2820u)(controller,*(const uint8_t *)(uintptr_t)(controller+0x1f4))==12&&
    m10v_settings_controller_ab_setup(controller,event,0x02000000u))return 1;
 return m10v_ab_adj_event_original(controller,event);
}
static uint32_t ab_live_key(m10v_settings_controller *,uint32_t);
uint32_t m10v_settings_controller_ab_selector(uint32_t mapper,uint32_t key){
 if(ab_live_key(ab_owner(),key))return 1;
 /* ImageControl ignores stock DISP. Use its real controller as the navigation
  * owner, preserving the native parent/return route and all detail controls. */
 if(key==0x37)M10V_LOG(85,key,ab_route(),*(const volatile uint32_t *)0x55063910u,0);
 if(key>=0x36&&key<=0x38&&ab_route()==0x02000012u&&(*(const volatile uint32_t *)0x55063910u&1u)){
  uint32_t source=m10v_settings_factory_original(0x55063914u,0x02000012u);
  uint32_t event[2]={key,0};
  if(source&&m10v_settings_controller_ab_setup(source,(uint32_t)(uintptr_t)event,0x02000012u))return 1;
 }
 return m10v_ab_selector_original(mapper,key);
}
static int ab_films_match(m10v_ab *s){
 uint32_t a=m10v_ab_slot(s->a),b=m10v_ab_slot(s->b);if(a>=M10V_SLOT_COUNT&&b>=M10V_SLOT_COUNT)return 1;
 m10v_library_state fresh;if(m10v_camera_library_load(&fresh)<0)return 0;
 return (a>=M10V_SLOT_COUNT||fresh.slots[a].film==s->film_a)&&(b>=M10V_SLOT_COUNT||fresh.slots[b].film==s->film_b);
}
static uint32_t ab_live_key(m10v_settings_controller *p,uint32_t key){
 if(!p||!p->ab.enabled||key<0x36||key>0x38)return 0;
 if(ab_route()!=0x08000000u){p->ab.down=0;return 0;}
 m10v_ab *s=&p->ab;
 if(key==0x37&&!s->down&&!ab_films_match(s)){ab_stop(s);return 0;}
 uint32_t current=ab_current();
 uint32_t dest=m10v_ab_key(s,key,current);
 if(!s->enabled){ab_stop(s);return 0;}
 if(dest){int result=ab_apply(dest-1);M10V_LOG(87,key,current,dest-1,(uint32_t)result);
  if(!result)m10v_ab_commit(s,dest-1);
 }
 return 1;
}
uint32_t m10v_settings_controller_ab_mapper(uint32_t mapper,uint32_t key){
 return ab_live_key(ab_owner(),key)?1:m10v_ab_mapper_original(mapper,key);
}
uint32_t m10v_settings_controller_ab_live_enter(uint32_t live,uint32_t route,uint32_t flags){
 uint32_t r=m10v_ab_live_enter_original(live,route,flags);
 if(route==0x08000000u){
  /* Reconcile legacy positional selections only from the UI lifecycle. */
  m10v_settings_factory_original(0x55063914u,0x0200004au);
#if M10V_BORDER_ENABLED
  /* Normal UI lifecycle after the retained TopMenu factory is published.
   * Never load SD from the constructor or processing-task producer. */
  uint32_t border_style;
  if(!m10v_border_camera_snapshot(&border_style)){
   m10v_settings_controller *border_page=ab_owner();
   if(border_page)m10v_border_camera_refresh((uint32_t)(uintptr_t)border_page-M10V_SETTINGS_OWNER_BYTES);
  }
#endif
  uint32_t model=((fn1)0x5320ba9cu)(((fn1)0x5320ad88u)(0));
  uint8_t *m=(uint8_t *)(uintptr_t)model;uint8_t prior=m[0x1b];m[0x1b]=0;
  m10v_camera_library_reconcile_legacy_selection(model);m[0x1b]=prior;
#if M10V_LIVE_COLOR
  m10v_library_state preview;m10v_camera_library_load(&preview);
#endif
 }
 m10v_settings_controller *p=ab_owner();
 if(p&&route==0x08000000u){
  if(p->ab.enabled&&(ab_current()!=p->ab.selected||!ab_films_match(&p->ab)))ab_stop(&p->ab);
 }return r;
}
uint32_t m10v_settings_controller_ab_live_leave(uint32_t live){
 m10v_settings_controller *p=ab_owner();if(p)ab_clear(&p->ab);
 /* No A/B widgets or synchronous SD diagnostics on native transitions. */
 return m10v_ab_live_leave_original(live);
}
uint32_t m10v_settings_controller_ab_live_destroy(uint32_t live){
 m10v_settings_controller *p=ab_owner();if(p)ab_clear(&p->ab);
 return m10v_ab_live_destroy_original(live);
}
uint32_t m10v_settings_controller_ab_live_event(uint32_t live,uint32_t event){
 m10v_settings_controller *p=ab_owner();
 uint32_t key=ab_event_key(event);
 if(ab_live_key(p,key))return 1;
 uint32_t r=m10v_ab_live_event_original(live,event);
 /* Native dispatch can change controller ownership. Never retain the old
  * settings pointer across it. */
 p=ab_owner();if(!p)return r;
 m10v_ab *s=&p->ab;
 if(s->enabled&&ab_current()!=s->selected)ab_stop(s);
 return r;
}

/* BaseController may discard physical phase-1 DISP before the ADJ virtual key
 * handler. Let the original dispatcher update all input/UI services first,
 * then supply the reserved action only to the unchanged native IC owner.
 * Release/hold, other ADJ slots, capture and power use the original result. */
extern uint32_t m10v_ab_dispatch_original(uint32_t,uint32_t);
uint32_t m10v_settings_controller_ab_dispatch(uint32_t c,uint32_t event){
 /* The film selector owns no native list that can consume MENU/DISP.
  * Preserve original service updates, then recover only a filtered first
  * press. Reacquire ownership after native dispatch; it can destroy the page. */
 uint32_t raw=*(const uint16_t *)(uintptr_t)event;
 if(raw==4||raw==5||raw==0x1b){
  m10v_settings_controller *p=ab_owner();
  if((uint32_t)(uintptr_t)p==c&&p&&p->page==M10V_SETTINGS_FILMS&&
     p->state.screen==M10V_SETTINGS_CATALOG&&p->view.count==M10V_VIEW_COUNT&&
     ab_host_word(c,0x124)==M10V_SETTINGS_FILMS_ROUTE&&ab_route()==M10V_SETTINGS_FILMS_ROUTE){
   uint32_t payload=*(const uint32_t *)(uintptr_t)(event+4);
   if(ab_ram(payload,8)&&*(const uint8_t *)(uintptr_t)payload==1&&
      *(const uint32_t *)(uintptr_t)(payload+4)==1){
    p->pending_source=0;
    uint32_t r=m10v_ab_dispatch_original(c,event);
    if(ab_route()!=M10V_SETTINGS_FILMS_ROUTE)return r;
    p=ab_owner();
    if(!p||(uint32_t)(uintptr_t)p!=c||p->page!=M10V_SETTINGS_FILMS||
       p->view.count!=M10V_VIEW_COUNT||ab_host_word(c,0x124)!=M10V_SETTINGS_FILMS_ROUTE)return r;
    if(p->pending_source==event){p->pending_source=0;return 1;}
    if(p->state.screen!=M10V_SETTINGS_CATALOG)return r;
    return m10v_settings_controller_key(p,event)?1:r;
   }
  }
 }
 if(*(const uint16_t *)(uintptr_t)event!=4||!ab_ram(c,0x274))return m10v_ab_dispatch_original(c,event);
 uint32_t payload=*(const uint32_t *)(uintptr_t)(event+4);
 if(!ab_ram(payload,8)||*(const uint8_t *)(uintptr_t)payload!=1||
    *(const uint32_t *)(uintptr_t)(payload+4)!=1)return m10v_ab_dispatch_original(c,event);
 uint32_t route=ab_route(),vt=*(const uint32_t *)(uintptr_t)c,type=0xffffffffu;
 int scope=ab_host_word(c,0x124)==route;
 if(route==0x02000000u&&vt==0x53b394e0u&&*(const uint8_t *)(uintptr_t)(c+0x270)!=1){
  type=((fn2)0x531a2820u)(c,*(const uint8_t *)(uintptr_t)(c+0x1f4));scope=scope&&type==12;
 }else scope=scope&&route==0x02000012u&&vt==0x53b3b618u;
 if(!scope)return m10v_ab_dispatch_original(c,event);
#if M10V_DEBUG_MODE
 uint32_t keyboard=((fn1)0x5320b1fcu)(((uint32_t (*)(void))0x5320ad88u)());
 M10V_LOG(208,c,route,type,ab_ram(keyboard,0x524)?*(const uint8_t *)(uintptr_t)(keyboard+0x520):0xffffffffu);
#endif
 /* An owned picker may close during native dispatch while the queued route
  * still names ADJ. Its closing DISP is already handled; never reinterpret
  * the same physical press as a request to open another picker. */
 int was_host=ab_host_owned(ab_host(ab_owner()),c);
 uint32_t r=m10v_ab_dispatch_original(c,event);
 if(was_host)return r;
 if(ab_route()!=route)return r;
 m10v_settings_controller *p=ab_owner();
 if(ab_host_owned(ab_host(p),c))return r;
 uint32_t logical[2]={0x37,0};
 uint32_t handled=m10v_settings_controller_ab_setup(c,(uint32_t)(uintptr_t)logical,route);
 M10V_LOG(209,c,route,handled,ab_host(p)?p->host.mode:0);
 return handled?1:r;
}
