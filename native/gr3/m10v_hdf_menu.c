/* Independent HDF settings controller. Original TopMenu owns this small tail;
 * no film objects, film selection, film detail page or film journal is used. */
#include <stdint.h>
#include <stddef.h>
#include "m10v_debug.h"
#include "m10v_hdf_state.h"
#include "m10v_settings_view.h"
#ifndef M10V_BORDER_ENABLED
#define M10V_BORDER_ENABLED 0
#endif
#if M10V_BORDER_ENABLED
#include "m10v_border_camera.h"
#if M10V_ADJ_EXTRA_CAMERA
#include "m10v_adj_extra_camera.h"
#endif
#define BORDER_DIRECT 2u
#endif
#ifndef M10V_HDF_ENABLED
#define M10V_HDF_ENABLED 1
#endif
#ifndef M10V_PURE_ISP_EFFECTS
#define M10V_PURE_ISP_EFFECTS 0
#endif
#ifndef M10V_TORN_ENABLED
#define M10V_TORN_ENABLED 0
#endif
#if M10V_TORN_ENABLED
#include "m10v_torn_overlay.h"
#if M10V_COMPANION_ENABLED
#include "m10v_companion_owner.h"
#endif
#endif
#if M10V_PURE_ISP_EFFECTS
#include "m10v_isp_effects_camera.h"
#include "m10v_isp_effects_resources.h"
#define IMPRINT_CHILD 3u
#define VIGNETTE_CHILD 4u
#define VIGNETTE_SWITCH 5u
#define VIGNETTE_STRENGTH 6u
#define TORN_SWITCH 7u
#endif
#ifndef M10V_HDF_OWNER_OFFSET
#define M10V_HDF_OWNER_OFFSET 0x193cu
#endif
#ifndef M10V_HDF_GROUPED
#define M10V_HDF_GROUPED 0
#endif
#define ROUTE 0x0200f102u
#define WORDS 9u
#define STYLE_WORDS 8u
#if M10V_HDF_ENABLED
extern int m10v_hdf_load(uint32_t *);
extern int m10v_hdf_save(uint32_t);
#endif
extern uint32_t m10v_hdf_menu_parent_ctor(uint32_t);
extern uint32_t m10v_hdf_menu_parent_dtor(uint32_t);
extern uint32_t m10v_hdf_menu_parent_factory(uint32_t,uint32_t);
extern uint32_t m10v_hdf_menu_parent_key_route(uint32_t);
extern uint32_t m10v_hdf_menu_vtable(void);
typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn2)(uint32_t,uint32_t);
typedef uint32_t (*fn3)(uint32_t,uint32_t,uint32_t);
typedef struct {uint8_t base[0x158];uint32_t widgets[WORDS],count,value,saved,error,root;
#if M10V_BORDER_ENABLED
 uint8_t hdf_cache_reserved[sizeof(m10v_hdf_ui)];
 uint32_t focus;m10v_border_cache border;uint32_t child;
#else
 uint8_t reserved_cache_tail[0x2c];
#endif
 uint32_t style;
#if M10V_MENU_HUB
 uint32_t touch, touch_last, from_hub;
#endif
} page;
_Static_assert(offsetof(page,style)==0x1bc,"HDF style pointer must follow caches");
#if M10V_BORDER_ENABLED
_Static_assert(offsetof(page,hdf_cache_reserved)==M10V_HDF_CACHE_OFFSET,"HDF cache placement");
_Static_assert(offsetof(page,border)==M10V_BORDER_CACHE_PAGE_OFFSET,"border cache placement");
_Static_assert(M10V_HDF_OWNER_OFFSET+offsetof(page,border)==M10V_BORDER_CACHE_OWNER_OFFSET,"border cache owner placement");
#endif
static int direct_border_route(uint32_t route){
#if M10V_BORDER_ENABLED && M10V_ADJ_EXTRA_CAMERA
 return route==M10V_ADJ_EXTRA_BORDER_ROUTE;
#else
 (void)route;return 0;
#endif
}
static int hub_effect_route(uint32_t route){
#if M10V_MENU_HUB
 return route>=0x0200f110u&&route<=0x0200f114u;
#else
 (void)route;return 0;
#endif
}
static int menu_route(uint32_t route){return route==ROUTE||direct_border_route(route)||hub_effect_route(route);}
static uint32_t ptr(const void *p){return (uint32_t)(uintptr_t)p;}
static void caption(uint32_t w,uint32_t id){((fn3)0x53396f80u)(w,id,0);}
static uint32_t widget(page *p,uint32_t type,uint32_t x,uint32_t y,uint32_t width,uint32_t height){
 uint32_t w=((fn1)0x536af2a8u)(type==1||type==10?0xf8:type==11?0xf0:0x110);if(!w)return 0;
 uint32_t ctor=type==1?0x5339199c:type==10?0x5339a908:type==11?0x53393d84:0x53396944;
 ((uint32_t (*)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t))ctor)(w,x,y,width,height);
 if(type!=1)((fn2)0x533aba64u)(p->widgets[0],w);
 return w;
}
static int make(page *p,uint32_t type,uint32_t x,uint32_t y,uint32_t width,uint32_t height){
 uint32_t w=widget(p,type,x,y,width,height);
 if(!w)return -1;
 p->widgets[p->count++]=w;return 0;
}
static void clear(page *p){
 if(p->style){
  uint32_t *w=(uint32_t *)(uintptr_t)p->style,n=0;
  while(n<STYLE_WORDS&&w[n])n++;
  ((fn3)0x5316cde8u)(0,p->style,n);
  ((fn1)0x536af2e4u)(p->style);p->style=0;
 }
 ((fn3)0x5316cde8u)(0,ptr(p->widgets),p->count);
 for(uint32_t i=0;i<WORDS;i++)p->widgets[i]=0;p->count=0;
}
#if !M10V_MENU_HUB
static int make_style(page *p){
 p->style=((fn1)0x536af2a8u)(STYLE_WORDS*4);if(!p->style)return -1;
 uint32_t *words=(uint32_t *)(uintptr_t)p->style;
 for(uint32_t i=0;i<STYLE_WORDS;i++)words[i]=0;
 for(uint32_t i=0;i<8;i++){
  uint32_t w=((fn1)0x536af2a8u)(0xf0);if(!w)return -1;
  ((uint32_t (*)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t))0x53393d84u)(
    w,0,i<4?84+i*72:147+(i-4)*72,720,i<4?64:1);
  words[i]=w;((fn2)0x533aba64u)(p->widgets[0],w);
  ((fn2)0x53393e00u)(w,i<4?6:2);
 }
 return 0;
}
static void style_row(page *p,uint32_t i,uint32_t visible,uint32_t selected){
 uint32_t *words=(uint32_t *)(uintptr_t)p->style;
 ((fn2)0x533ad3c0u)(words[i],visible&&selected);
 ((fn2)0x533ad3c0u)(words[4+i],visible);
 /* Official glyph palette28 is dark; palette10 is yellow text. */
 ((fn2)0x5339658cu)(p->widgets[4+i],visible&&selected?28:31);
}
#endif
#if M10V_PURE_ISP_EFFECTS
static int vignette_load(page *p){
 m10v_isp_effects_settings settings;uint32_t sequence;
 if(m10v_isp_effects_camera_refresh(ptr(p)-M10V_HDF_OWNER_OFFSET)||
    !m10v_isp_effects_camera_snapshot(&settings,&sequence))return -1;
 p->value=p->saved=p->child==VIGNETTE_SWITCH?m10v_isp_vignette_enabled(settings.reserved):
     m10v_isp_vignette_strength(settings.reserved)-1u;return 0;
}
static int vignette_save(page *p){
 m10v_isp_effects_settings settings;uint32_t sequence;
 if(!m10v_isp_effects_camera_snapshot(&settings,&sequence))return -1;
 uint32_t mask=p->child==VIGNETTE_SWITCH?0x400u:0x1800u;
 settings.reserved=M10V_ISP_EFFECT_PREF_TAG|(settings.reserved&~mask)|
     (p->child==VIGNETTE_SWITCH?p->value<<10:p->value<<11);
 if(!m10v_isp_effects_validate(&settings))return -1;
 return m10v_isp_effects_camera_save(ptr(p)-M10V_HDF_OWNER_OFFSET,&settings);
}
static int imprint_load(page *p){
 m10v_isp_effects_settings settings;uint32_t sequence;
 if(m10v_isp_effects_camera_refresh(ptr(p)-M10V_HDF_OWNER_OFFSET)||
    !m10v_isp_effects_camera_snapshot(&settings,&sequence)||!m10v_isp_effects_validate(&settings))return -1;
 p->value=p->saved=m10v_isp_effects_imprint(&settings);return 0;
}
static int imprint_save(page *p){
 m10v_isp_effects_settings settings;uint32_t sequence;
 if(!m10v_isp_effects_camera_snapshot(&settings,&sequence)||
    !m10v_isp_effects_validate(&settings)||!m10v_isp_effects_set_imprint(&settings,p->value))return -1;
 return m10v_isp_effects_camera_save(ptr(p)-M10V_HDF_OWNER_OFFSET,&settings);
}
#if M10V_MENU_HUB
static void make_imprint_rows(page *p){
 uint32_t storage=((fn1)0x536af2a8u)(STYLE_WORDS*4);if(!storage)return;
 uint32_t *rows=(uint32_t *)(uintptr_t)storage;
 for(uint32_t i=0;i<STYLE_WORDS;i++){
  rows[i]=widget(p,17,77,M10V_HUB_ROW_Y+1+i*M10V_HUB_IMPRINT_HEIGHT,620,M10V_HUB_IMPRINT_HEIGHT-3);
  if(!rows[i]){
   ((fn3)0x5316cde8u)(0,storage,i);((fn1)0x536af2e4u)(storage);return;
  }
  ((fn2)0x53396658u)(rows[i],1);
 }
 p->style=storage;
}
#endif
static uint32_t root_rows(void){return (M10V_HDF_ENABLED?4u:3u)+M10V_TORN_ENABLED;}
#if M10V_TORN_ENABLED
static int torn_action(page *p,uint32_t action){
 uint32_t stage=0,generation=0;
 if(!m10v_torn_state(&stage,&generation)||m10v_torn_busy()){M10V_LOG(38,2,stage,generation,0);return -1;}
#if M10V_COMPANION_ENABLED
 uint32_t token=m10v_companion_ui_storage_enter(0);if(!token){M10V_LOG(38,3,stage,generation,action);return -1;}
#endif
 int result=m10v_torn_set(ptr(p)-M10V_HDF_OWNER_OFFSET,action);
#if M10V_COMPANION_ENABLED
 if(!m10v_companion_ui_storage_leave(token))result=-1;
#endif
 M10V_LOG(38,action,stage,generation,(uint32_t)result);
 return result;
}
#endif
#endif
static void draw(page *p){
 if(p->count!=WORDS||(!M10V_MENU_HUB&&!p->style))return;
#if M10V_BORDER_ENABLED
 uint32_t border=!p->root&&p->child;
#if M10V_PURE_ISP_EFFECTS
 uint32_t imprint=!p->root&&p->child==IMPRINT_CHILD;
#if !M10V_MENU_HUB
 uint32_t first=imprint?(p->value/4u)*4u:0u;
#endif
 uint32_t root_first=p->root&&p->focus>=4u?p->focus-3u:0u;
 if(imprint)border=0;
#if M10V_TORN_ENABLED
 uint32_t torn=!p->root&&p->child==TORN_SWITCH;
 if(torn)border=0;
#endif
#endif
 caption(p->widgets[2],p->root?1140:border?1155:970);
#if M10V_MENU_HUB
 uint32_t rows=0,active=4;
 uint32_t confirm=!p->root&&p->child!=VIGNETTE_CHILD;
 caption(p->widgets[3],1248);
 ((fn2)0x533ad3c0u)(p->widgets[3],confirm);
#else
 caption(p->widgets[3],p->root?941:971);
#endif
#if M10V_PURE_ISP_EFFECTS
 if(imprint)caption(p->widgets[2],M10V_ISP_TEXT_IMPRINT);
 if(!p->root&&p->child>=VIGNETTE_CHILD&&p->child<=VIGNETTE_STRENGTH)caption(p->widgets[2],1214);
#if M10V_TORN_ENABLED
 if(torn)caption(p->widgets[2],1218);
#endif
#endif
 for(uint32_t i=0;i<4;i++){
  uint32_t visible=p->root?i<(M10V_HDF_ENABLED?2u:1u):i<(border?3u:4u);
#if M10V_PURE_ISP_EFFECTS
  uint32_t row=p->root?root_first+i:i;
  if(p->root)visible=row<root_rows();
  if(!p->root&&p->child>=VIGNETTE_CHILD)visible=i<(p->child==VIGNETTE_STRENGTH?3u:2u);
#if M10V_MENU_HUB
  if(imprint)visible=0;
#else
  if(imprint)visible=first+i<8u;
#endif
#endif
  ((fn2)0x533ad3c0u)(p->widgets[4+i],visible);
  uint32_t id=p->root?(M10V_HDF_ENABLED&&i==0?1141:1155):border?(i==0?972:i==1?1156:1157):972+i;
#if M10V_PURE_ISP_EFFECTS
  if(p->root){id=M10V_HDF_ENABLED&&row==0u?1141:1155;}
  if(p->root&&row==(M10V_HDF_ENABLED?2u:1u))id=M10V_ISP_TEXT_IMPRINT;
  if(p->root&&row==(M10V_HDF_ENABLED?3u:2u))id=1214;
#if M10V_TORN_ENABLED
  if(p->root&&row==root_rows()-1u)id=1218;
  if(torn)id=i?1219u:1220u;
#endif
  if(!p->root&&p->child==VIGNETTE_CHILD)id=1215+i;
  if(!p->root&&p->child==VIGNETTE_SWITCH)id=i?1217:M10V_ISP_TEXT_OFF;
  if(!p->root&&p->child==VIGNETTE_STRENGTH)id=973+i;
#if !M10V_MENU_HUB
  if(imprint)id=first+i?M10V_ISP_TEXT_IMPRINT_CATS+first+i-1u:M10V_ISP_TEXT_OFF;
#endif
#endif
  caption(p->widgets[4+i],id);
  uint32_t selected=p->root?p->focus==i:p->value==i;
#if M10V_PURE_ISP_EFFECTS
#if !M10V_MENU_HUB
  if(imprint)selected=p->value==first+i;
#endif
  if(p->root)selected=p->focus==row;
#endif
#if M10V_MENU_HUB
  rows+=visible;
  if(visible&&selected)active=i;
#else
  style_row(p,i,visible,selected);
#endif
 }
#if M10V_MENU_HUB
 uint32_t theme=confirm?2:1;
#if M10V_PURE_ISP_EFFECTS
 uint32_t *options=(uint32_t *)(uintptr_t)p->style;
 if(options)for(uint32_t i=0;i<STYLE_WORDS;i++){
  ((fn2)0x533ad3c0u)(options[i],imprint);
  if(imprint)caption(options[i],i?M10V_ISP_TEXT_IMPRINT_CATS+i-1u:M10V_ISP_TEXT_OFF);
 }
 if(imprint){
  if(options){rows=STYLE_WORDS;active=p->value;theme=M10V_HUB_IMPRINT_THEME;}
  else p->error=1;
 }
#endif
 (void)m10v_settings_view_theme(p->widgets[1],rows,active,theme);
#endif
#else
 caption(p->widgets[2],p->root?1140:970);caption(p->widgets[3],p->root?941:971);
 for(uint32_t i=0;i<4;i++){
  ((fn2)0x533ad3c0u)(p->widgets[4+i],!p->root||i==0);
  caption(p->widgets[4+i],p->root?1141:972+i);
  style_row(p,i,!p->root||i==0,p->root?i==0:p->value==i);
 }
#endif
#if M10V_TORN_ENABLED
 ((fn2)0x533ad3c0u)(p->widgets[8],p->error&&(!p->root||p->focus==root_rows()-1u));
#else
 ((fn2)0x533ad3c0u)(p->widgets[8],!p->root&&p->error);
#endif
 caption(p->widgets[8],976);
 ((fn1)0x533ad308u)(p->widgets[0]);
}
void m10v_hdf_menu_cache_init(uint32_t owner){
 m10v_hdf_ui *p=(m10v_hdf_ui *)(uintptr_t)(owner+M10V_HDF_OWNER_OFFSET+M10V_HDF_CACHE_OFFSET);
 for(uint32_t i=0;i<sizeof(*p)/4;i++)((uint32_t *)p)[i]=0;
 p->magic=M10V_HDF_CACHE_MAGIC;
}
uint32_t m10v_hdf_menu_top_ctor(uint32_t owner){
 M10V_LOG(32,0,owner,M10V_HDF_OWNER_OFFSET,0);
 m10v_hdf_menu_parent_ctor(owner);page *p=(page *)(uintptr_t)(owner+M10V_HDF_OWNER_OFFSET);
 for(uint32_t i=0;i<(M10V_PURE_ISP_EFFECTS?0x200u:0x1c0u);i++)((uint8_t *)p)[i]=0;
 m10v_hdf_menu_cache_init(owner);
#if M10V_PURE_ISP_EFFECTS
 m10v_isp_effects_camera_init(owner);
#endif
 ((fn1)0x5316c8d4u)(ptr(p));*(uint32_t *)p=m10v_hdf_menu_vtable();M10V_LOG(32,1,owner,ptr(p),*(uint32_t*)p);return owner;
}
uint32_t m10v_hdf_menu_destroy(page *p){
 ((fn1)0x5316ce8cu)(ptr(p));clear(p);((fn1)0x5316c774u)(ptr(p));return ptr(p);
}
uint32_t m10v_hdf_menu_top_dtor(uint32_t owner){
 ((m10v_hdf_ui *)(uintptr_t)(owner+M10V_HDF_OWNER_OFFSET+M10V_HDF_CACHE_OFFSET))->magic=0;
 m10v_hdf_menu_destroy((page *)(uintptr_t)(owner+M10V_HDF_OWNER_OFFSET));return m10v_hdf_menu_parent_dtor(owner);
}
uint32_t m10v_hdf_menu_factory(uint32_t factory,uint32_t route){
 if(!menu_route(route))return m10v_hdf_menu_parent_factory(factory,route);
 uint32_t owner=m10v_hdf_menu_parent_factory(factory,0x0200004a);
 return owner?owner+M10V_HDF_OWNER_OFFSET:0;
}
uint32_t m10v_hdf_menu_ready(page *p,uint32_t route){
 M10V_LOG(33,ptr(p),route,p->count,p->style);
 (void)route;p->error=0;p->root=M10V_HDF_GROUPED;
#if M10V_MENU_HUB
 p->touch=0;p->from_hub=hub_effect_route(route);
#endif
#if M10V_BORDER_ENABLED
 p->root=1;p->focus=0;p->child=0;
 M10V_LOG(34,ptr(p),1,0,0);
 int border_refresh=m10v_border_camera_refresh(ptr(p)-M10V_HDF_OWNER_OFFSET);
 M10V_LOG(34,ptr(p),2,(uint32_t)border_refresh,p->border.sequence);
 M10V_LOG(205,0x52454652u,(uint32_t)border_refresh,p->border.style,p->border.sequence);
 if(border_refresh<0)return 0;
 if(direct_border_route(route)){
  p->root=0;p->child=BORDER_DIRECT;p->value=p->saved=p->border.style;
  goto build_view;
 }
#endif
#if M10V_HDF_ENABLED
 M10V_LOG(34,ptr(p),5,0,0);
 int hdf_load=m10v_hdf_load(&p->saved);
 M10V_LOG(34,ptr(p),6,(uint32_t)hdf_load,p->saved);
 if(hdf_load<0)return 0;p->value=p->saved;
#else
 p->value=p->saved=0;
#endif
#if M10V_BORDER_ENABLED
build_view:
#endif
 if(p->count==WORDS&&(M10V_MENU_HUB||p->style)){M10V_LOG(34,ptr(p),7,1,p->count);return 1;}
 if(p->count){clear(p);return 0;}
 if(make(p,1,0,0,720,480)||make(p,M10V_MENU_HUB?10:11,0,0,720,480)||
    make(p,17,M10V_MENU_HUB?88:20,M10V_MENU_HUB?16:20,M10V_MENU_HUB?584:680,50)||
    make(p,17,M10V_MENU_HUB?584:20,M10V_MENU_HUB?418:414,M10V_MENU_HUB?90:680,42))goto fail;
#if M10V_MENU_HUB
 ((fn2)0x5339aa30u)(p->widgets[1],1);
 ((fn2)0x5339aa44u)(p->widgets[1],1);
#else
 ((fn2)0x53393e00u)(p->widgets[1],1);
 if(make_style(p))goto fail;
#endif
 for(uint32_t i=0;i<4;i++)if(make(p,17,M10V_MENU_HUB?77:36,
   (M10V_MENU_HUB?87:90)+i*(M10V_MENU_HUB?53:72),M10V_MENU_HUB?620:644,M10V_MENU_HUB?50:52))goto fail;
#if M10V_MENU_HUB
 for(uint32_t i=0;i<4;i++)((fn2)0x53396658u)(p->widgets[4+i],1);
#endif
 if(make(p,17,20,M10V_MENU_HUB?420:384,M10V_MENU_HUB?520:680,30))goto fail;
#if M10V_MENU_HUB && M10V_PURE_ISP_EFFECTS
 make_imprint_rows(p);
#endif
 uint32_t root=p->widgets[0],*v=(uint32_t *)(uintptr_t)*(uint32_t *)(uintptr_t)root;
 ((fn1)(uintptr_t)v[0x28/4])(root);((fn1)(uintptr_t)v[0x34/4])(root);M10V_LOG(34,ptr(p),7,1,p->count);return 1;
fail:M10V_LOG(34,ptr(p),8,0,p->count);clear(p);return 0;
}
uint32_t m10v_hdf_menu_key(page *,uint32_t);
void m10v_hdf_menu_enter(page *p,uint32_t route,uint32_t flags){
 M10V_LOG(35,ptr(p),route,flags,p->count);
 (void)route;(void)flags;
#if M10V_MENU_HUB
 if(p->from_hub&&route-0x0200f110u<root_rows()){
  p->focus=route-0x0200f110u;
  uint32_t event=0xd8;
  m10v_hdf_menu_key(p,ptr(&event));
 }else
#endif
 draw(p);
 ((fn3)0x5316d354u)(ptr(p),0,p->widgets[0]);
}
#if M10V_DEBUG_MODE
static uint32_t key_impl(page *p,uint32_t event){
#else
uint32_t m10v_hdf_menu_key(page *p,uint32_t event){
#endif
 uint32_t key=*(const uint16_t *)(uintptr_t)event;
#if M10V_MENU_HUB
 if(key==4u){
  uint32_t payload=*(const uint32_t *)(uintptr_t)(event+4u);
  if((payload&3u)||payload<0x55000000u||payload>0x80000000u-8u||
     *(const uint8_t *)(uintptr_t)payload!=1u||
     *(const uint32_t *)(uintptr_t)(payload+4u)!=1u)return 0;
  key=0x89u;
 }
 if(key==0x30){
  uint32_t address=*(const uint32_t *)(uintptr_t)(event+4);
  if((address&3)||address<0x55000000u||address>0x80000000u-0x58u){p->touch=0;return 0;}
  const uint8_t *packet=(const uint8_t *)(uintptr_t)address;
  uint32_t kind=packet[0x50];
  if((kind==1||kind==5)&&packet[0]==1){
   uint32_t x=*(const uint32_t *)(packet+8),y=*(const uint32_t *)(packet+12);
   if(x>=720||y>=480){p->touch=0;return 0;}
   uint32_t point=(y<<16)|(x+1);
   if(kind==1)p->touch=point;
   p->touch_last=point;
   return 1;
  }
  if((kind==2||kind==4||kind==7)&&!packet[0])return 1;
  uint32_t point=p->touch;p->touch=0;
  if(kind!=10||packet[0]||!point)return 0;
  uint32_t x=(point&65535)-1,y=point>>16;
  uint32_t ex=(p->touch_last&65535)-1,ey=p->touch_last>>16;
  if(packet[0x28]==1){
   ex=*(const uint32_t *)(packet+0x30);ey=*(const uint32_t *)(packet+0x34);
  }
  if(ex>=720||ey>=480)return 1;
  if(ex+12<x||x+12<ex||ey+12<y||y+12<ey)return 1;
  uint32_t imprint=!p->root&&p->child==IMPRINT_CHILD;
  if(x>=32&&x<77&&y>=18&&y<62)key=0x89;
  else if(x>=33&&x<687&&y>=M10V_HUB_ROW_Y&&y<(imprint?M10V_HUB_ROW_Y+STYLE_WORDS*M10V_HUB_IMPRINT_HEIGHT:298)){
   if(imprint&&!p->style)return 1;
   uint32_t row=(y-M10V_HUB_ROW_Y)/(imprint?M10V_HUB_IMPRINT_HEIGHT:M10V_HUB_ROW_HEIGHT);
   if(p->root){
    row+=p->focus>=4?p->focus-3:0;
    if(row>=root_rows())return 1;
    p->focus=row;
   }else{
    uint32_t limit=p->child==IMPRINT_CHILD?8:p->child==VIGNETTE_STRENGTH?3:p->child>=VIGNETTE_CHILD?2:p->child?3:4;
    if(row>=limit)return 1;
    p->value=row;
    if(p->child!=VIGNETTE_CHILD){draw(p);return 1;}
   }
   key=0xd8;
  }else if(!p->root&&y>=418&&y<466&&x>=558&&x<687)key=0xd8;
  else return 1;
 }
#endif
 if(p->root){
#if M10V_BORDER_ENABLED
#if M10V_PURE_ISP_EFFECTS
  if(key==0xce||key==0xd0||key==0xd4){if(p->focus)p->focus--;p->error=0;draw(p);return 1;}
  if(key==0xd1||key==0xd5){if(p->focus+1u<root_rows())p->focus++;p->error=0;draw(p);return 1;}
#else
  if(key==0xce||key==0xd0||key==0xd4){p->focus=0;draw(p);return 1;}
  if(key==0xd1||key==0xd5){p->focus=M10V_HDF_ENABLED?1:0;draw(p);return 1;}
#endif
  if(key==0xd8||key==0xcf||key==0xd3){
   p->child=M10V_HDF_ENABLED?p->focus:1;
#if M10V_PURE_ISP_EFFECTS
#if M10V_TORN_ENABLED
   if(p->focus==root_rows()-1u){
    uint32_t stage=0,generation=0;
    p->child=TORN_SWITCH;p->root=0;
    p->error=!m10v_torn_state(&stage,&generation);
    p->value=p->saved=stage==1u||stage==2u;
    draw(p);
    return 1;
   }
#endif
   if(p->focus==(M10V_HDF_ENABLED?3u:2u)){
    p->child=VIGNETTE_CHILD;p->value=p->saved=0;p->root=0;p->error=0;draw(p);return 1;
   }else if(p->focus==(M10V_HDF_ENABLED?2u:1u)){
    p->child=IMPRINT_CHILD;
    if(imprint_load(p)){
#if M10V_MENU_HUB
     if(p->from_hub){p->root=0;p->value=p->saved=0;}
#endif
     p->error=1;draw(p);return 1;
    }
   }else
#endif
   if(p->child)p->value=p->saved=p->border.style;
#if M10V_HDF_ENABLED
   else {if(m10v_hdf_load(&p->saved)<0){p->error=1;draw(p);return 1;}p->value=p->saved;}
#endif
   p->root=0;p->error=0;draw(p);return 1;
  }
#else
  if(key==0xd8||key==0xcf||key==0xd3){p->root=0;draw(p);return 1;}
#endif
  if(key==0x86||key==0x89||key==0xda){((fn1)0x5316ca28u)(ptr(p));return 1;}
  return key==0xce||key==0xd0||key==0xd1||key==0xd4||key==0xd5;
 }
 #if M10V_PURE_ISP_EFFECTS
#if M10V_TORN_ENABLED
 if(p->child==TORN_SWITCH){
  if(key==0x86||key==0x89||key==0xda){
#if M10V_MENU_HUB
   if(p->from_hub){((fn1)0x5316ca28u)(ptr(p));return 1;}
#endif
   p->root=1;p->error=0;
  }
  else if(key==0xce||key==0xd0||key==0xd4){p->value=0;p->error=0;}
  else if(key==0xcf||key==0xd3||key==0xd1||key==0xd5){p->value=1;p->error=0;}
  else if(key==0xd8){
   p->error=torn_action(p,p->value)!=0;
   if(!p->error){
#if M10V_MENU_HUB
    if(p->from_hub){((fn1)0x5316ca28u)(ptr(p));return 1;}
#endif
    p->root=1;
   }
  }else return 0;
  draw(p);return 1;
 }
#endif
 if(p->child==VIGNETTE_CHILD&&(key==0xd8||key==0xcf||key==0xd3)){
  p->child=p->value?VIGNETTE_STRENGTH:VIGNETTE_SWITCH;
  p->error=vignette_load(p)!=0;draw(p);return 1;
 }
 if(p->child>=VIGNETTE_SWITCH&&(key==0x86||key==0x89||key==0xda)){
  p->child=VIGNETTE_CHILD;p->value=p->saved=0;p->error=0;draw(p);return 1;
 }
#endif
 if((M10V_HDF_GROUPED||M10V_BORDER_ENABLED)&&(key==0x86||key==0x89||key==0xda)){
#if M10V_BORDER_ENABLED
  if(p->child==BORDER_DIRECT){((fn1)0x5316ca28u)(ptr(p));return 1;}
#endif
#if M10V_MENU_HUB
  if(p->from_hub){((fn1)0x5316ca28u)(ptr(p));return 1;}
#endif
  p->value=p->saved;p->root=1;p->error=0;draw(p);return 1;
 }
 if(key==0xce||key==0xd0||key==0xd4){if(p->value)p->value--;p->error=0;}
 else if(key==0xcf||key==0xd3||key==0xd1||key==0xd5){
  uint32_t max=3;
#if M10V_BORDER_ENABLED
  if(p->child)max=2;
#if M10V_PURE_ISP_EFFECTS
  if(p->child==IMPRINT_CHILD)max=7;
  if(p->child==VIGNETTE_CHILD||p->child==VIGNETTE_SWITCH)max=1;
#endif
#endif
  if(p->value<max)p->value++;p->error=0;
 }
 else if(key==0xd8){
  int result=-1;
#if M10V_BORDER_ENABLED
#if M10V_PURE_ISP_EFFECTS
  if(p->child>=VIGNETTE_SWITCH)result=vignette_save(p);
  else if(p->child==IMPRINT_CHILD){
#if M10V_MENU_HUB
   if(p->style)
#endif
   result=imprint_save(p);
  }
  else
#endif
  if(p->child){
   if(p->child==BORDER_DIRECT)M10V_EXIT_LOG(296,ptr(p),p->value,p->border.style,p->border.sequence);
   result=m10v_border_camera_save(ptr(p)-M10V_HDF_OWNER_OFFSET,p->value);
   if(p->child==BORDER_DIRECT)M10V_EXIT_LOG(297,ptr(p),p->value,(uint32_t)result,p->border.sequence);
  }else
#endif
  {
#if M10V_HDF_ENABLED
   result=m10v_hdf_save(p->value);
#endif
  }
#if M10V_BORDER_ENABLED
  M10V_LOG(205,0x53415645u,p->child?p->value:0,(uint32_t)result,p->border.sequence);
#else
  M10V_LOG(205,0x53415645u,0,(uint32_t)result,0);
#endif
  if(result){
   /* A successful write followed by failed verification may already persist.
    * Reconcile with the same journal reader used by capture, rather than
    * falsely showing the previous value. Stay open with the error visible. */
#if M10V_BORDER_ENABLED
#if M10V_PURE_ISP_EFFECTS
   if(p->child>=VIGNETTE_SWITCH){(void)vignette_load(p);}
   else if(p->child==IMPRINT_CHILD){(void)imprint_load(p);}
   else
#endif
   if(p->child){if(m10v_border_camera_refresh(ptr(p)-M10V_HDF_OWNER_OFFSET)==0)p->saved=p->value=p->border.style;}
   else
#endif
   {
#if M10V_HDF_ENABLED
    uint32_t actual;if(m10v_hdf_load(&actual)==0)p->saved=p->value=actual;
#endif
   }
   p->error=1;
  }
  else{
   p->saved=p->value;
#if M10V_BORDER_ENABLED
   if(p->child==BORDER_DIRECT){((fn1)0x5316ca28u)(ptr(p));return 1;}
#endif
#if M10V_MENU_HUB
   if(p->from_hub){
    if(p->child>=VIGNETTE_SWITCH){p->child=VIGNETTE_CHILD;p->value=p->saved=0;draw(p);}
    else ((fn1)0x5316ca28u)(ptr(p));
    return 1;
   }
#endif
   if(M10V_HDF_GROUPED||M10V_BORDER_ENABLED){p->root=1;draw(p);}
   else ((fn1)0x5316ca28u)(ptr(p));
   return 1;
  }
 }else if(key==0x86||key==0x89||key==0xda){((fn1)0x5316ca28u)(ptr(p));return 1;}
 else return 0;
 draw(p);return 1;
}
#if M10V_DEBUG_MODE
uint32_t m10v_hdf_menu_key(page *p,uint32_t event){
 uint32_t key=*(const uint16_t*)(uintptr_t)event;
 uint32_t navigation=0;
#if M10V_BORDER_ENABLED
 navigation=(p->focus<<16)|p->child;
#endif
 M10V_LOG(36,ptr(p),key,p->root,navigation);
 uint32_t result=key_impl(p,event);
 uint32_t parameter=0;
 M10V_LOG(39,ptr(p),result,p->root,(parameter<<16)|p->value);
 return result;
}
#endif
uint32_t m10v_hdf_menu_key_route(uint32_t model){
 uint32_t route=m10v_hdf_menu_parent_key_route(model);
 if(!menu_route(route))return route;
 M10V_LOG(37,model,route,0x0200004a,0);
 return 0x0200004a;
}
