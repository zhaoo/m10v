/* Independent HDF settings controller. Original TopMenu owns this small tail;
 * no film objects, film selection, film detail page or film journal is used. */
#include <stdint.h>
#include <stddef.h>
#include "m10v_debug.h"
#include "m10v_hdf_state.h"
#ifndef M10V_BORDER_ENABLED
#define M10V_BORDER_ENABLED 0
#endif
#if M10V_BORDER_ENABLED
#include "m10v_border_camera.h"
#endif
#ifndef M10V_HDF_ENABLED
#define M10V_HDF_ENABLED 1
#endif
#ifndef M10V_PURE_ISP_EFFECTS
#define M10V_PURE_ISP_EFFECTS 0
#endif
#if M10V_PURE_ISP_EFFECTS
#if !M10V_HDF_ENABLED || !M10V_BORDER_ENABLED
#error "Pure ISP Effects menu requires HDF and border ownership"
#endif
#include "m10v_isp_effects_camera.h"
#include "m10v_isp_effects_resources.h"
#ifndef M10V_ISP_EFFECT_CACHE_OWNER_OFFSET
#error "Pure ISP Effects menu requires explicit cache owner offset"
#endif
#endif
#ifndef M10V_HDF_OWNER_OFFSET
#define M10V_HDF_OWNER_OFFSET 0x193cu
#endif
#ifndef M10V_HDF_GROUPED
#define M10V_HDF_GROUPED 0
#endif
#define ROUTE 0x0200f102u
#define WORDS 9u
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
#if M10V_PURE_ISP_EFFECTS
 m10v_isp_effects_settings editor;uint32_t editor_sequence,parameter_index;
#endif
} page;
#if M10V_PURE_ISP_EFFECTS
_Static_assert(sizeof(page)<=0x200,"Effects controller capacity");
_Static_assert(M10V_ISP_EFFECT_CACHE_OWNER_OFFSET==M10V_HDF_OWNER_OFFSET+0x200u,"Effects cache placement");
_Static_assert(sizeof(m10v_isp_effects_camera_cache)==44,"Effects cache capacity");
#else
_Static_assert(sizeof(page)<=0x1c0,"HDF owned controller capacity");
#endif
_Static_assert(offsetof(page,style)==0x1bc,"HDF style pointer must follow caches");
#if M10V_BORDER_ENABLED
_Static_assert(offsetof(page,hdf_cache_reserved)==M10V_HDF_CACHE_OFFSET,"HDF cache placement");
_Static_assert(offsetof(page,border)==M10V_BORDER_CACHE_PAGE_OFFSET,"border cache placement");
_Static_assert(M10V_HDF_OWNER_OFFSET+offsetof(page,border)==M10V_BORDER_CACHE_OWNER_OFFSET,"border cache owner placement");
#endif
static uint32_t ptr(const void *p){return (uint32_t)(uintptr_t)p;}
static void caption(uint32_t w,uint32_t id){((fn3)0x53396f80u)(w,id,0);}
static int make(page *p,uint32_t type,uint32_t x,uint32_t y,uint32_t width,uint32_t height){
 uint32_t w=((fn1)0x536af2a8u)(type==1?0xf8:type==11?0xf0:0x110);if(!w)return -1;
 uint32_t ctor=type==1?0x5339199c:type==11?0x53393d84:0x53396944;
 ((uint32_t (*)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t))ctor)(w,x,y,width,height);
 p->widgets[p->count++]=w;
 if(type!=1)((fn2)0x533aba64u)(p->widgets[0],w);
 return 0;
}
static void clear(page *p){
 if(p->style){
  uint32_t *w=(uint32_t *)(uintptr_t)p->style,n=0;
  while(n<8&&w[n])n++;
  ((fn3)0x5316cde8u)(0,p->style,n);
  ((fn1)0x536af2e4u)(p->style);p->style=0;
 }
 ((fn3)0x5316cde8u)(0,ptr(p->widgets),p->count);
 for(uint32_t i=0;i<WORDS;i++)p->widgets[i]=0;p->count=0;
}
static int make_style(page *p){
 p->style=((fn1)0x536af2a8u)(8*4);if(!p->style)return -1;
 uint32_t *words=(uint32_t *)(uintptr_t)p->style;
 for(uint32_t i=0;i<8;i++)words[i]=0;
 for(uint32_t i=0;i<8;i++){
  uint32_t w=((fn1)0x536af2a8u)(0xf0);if(!w)return -1;
  ((uint32_t (*)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t))0x53393d84u)(w,0,i<4?84+i*72:147+(i-4)*72,720,i<4?64:1);
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
#if M10V_PURE_ISP_EFFECTS
static uint32_t effect_title(uint32_t child){return M10V_ISP_TEXT_LEAK+child-2u;}
static uint32_t parameter_count(page *p){return p->child==2u?4u:3u;}
static uint32_t parameter_title(page *p){
 if(!p->parameter_index)return M10V_ISP_TEXT_SWITCH;
 if(p->parameter_index==1u)return M10V_ISP_TEXT_GAIN;
 if(p->child==2u)return p->parameter_index==2u?M10V_ISP_TEXT_POSITION:M10V_ISP_TEXT_SPREAD;
 return p->child==3u?M10V_ISP_TEXT_SIZE:M10V_ISP_TEXT_BLUR_RANGE;
}
static uint32_t *parameter(page *p){
 uint32_t index=p->child==2u?p->parameter_index-1u:p->child==3u?2u+p->parameter_index:4u+p->parameter_index;
 return ((uint32_t *)&p->editor)+index;
}
static uint32_t parameter_value(page *p){
 uint32_t kind=p->child-2u;
 if(!p->parameter_index)return m10v_isp_effects_enabled(&p->editor,kind);
 if(p->parameter_index==1u){uint32_t value=m10v_isp_effects_strength(&p->editor,kind);return kind==1u?(value?value-1u:0u):value-1u;}
 return *parameter(p);
}
static int set_parameter(page *p,uint32_t value){
 uint32_t kind=p->child-2u;
 if(!p->parameter_index)return m10v_isp_effects_set_enabled(&p->editor,kind,value);
 if(p->parameter_index==1u)return m10v_isp_effects_set_strength(&p->editor,kind,kind==1u?(value?value+1u:0u):value+1u);
 *parameter(p)=value;return 1;
}
static uint32_t parameter_max(page *p){
 return !p->parameter_index?1u:p->parameter_index==1u&&p->child==3u?3u:2u;
}
static uint32_t choice_title(page *p,uint32_t value){
 if(!p->parameter_index)return value?M10V_ISP_TEXT_ON:972u;
 if(p->parameter_index==1u)return p->child==3u?(value?972u+value:M10V_ISP_TEXT_INHERIT):973u+value;
 if(p->child==2u)return (p->parameter_index==2u?M10V_ISP_TEXT_LEFT:M10V_ISP_TEXT_NARROW)+value;
 return (p->child==3u?M10V_ISP_TEXT_FINE:M10V_ISP_TEXT_SMALL)+value;
}
static int effect_snapshot(page *p){return m10v_isp_effects_camera_snapshot(&p->editor,&p->editor_sequence);}
#endif
static void draw(page *p){
 if(p->count!=WORDS||!p->style)return;
#if M10V_PURE_ISP_EFFECTS
 uint32_t special=p->child>=2u,start=0,count=4,focus=p->value;
 uint32_t title=p->child==1u?1155u:970u;
 if(p->root==1u){title=1140;count=5;focus=p->focus;}
 else if(p->root==2u){title=effect_title(p->child);count=parameter_count(p);focus=p->parameter_index;}
 else if(special){title=parameter_title(p);count=parameter_max(p)+1u;}
 else if(p->child==1u)count=3;
 if(count>4u&&focus>3u)start=focus-3u;
 caption(p->widgets[2],title);caption(p->widgets[3],p->root?941:971);
 for(uint32_t i=0;i<4u;++i){
  uint32_t logical=start+i,visible=logical<count,id=972u;
  if(p->root==1u)id=logical==0u?1141u:logical==1u?1155u:effect_title(logical);
  else if(p->root==2u){uint32_t old=p->parameter_index;p->parameter_index=logical;id=parameter_title(p);p->parameter_index=old;}
  else if(special)id=choice_title(p,logical);
  else id=p->child==1u?(logical==0u?972u:logical==1u?1156u:1157u):972u+logical;
  ((fn2)0x533ad3c0u)(p->widgets[4+i],visible);caption(p->widgets[4+i],id);style_row(p,i,visible,focus==logical);
 }
#elif M10V_BORDER_ENABLED
 uint32_t border=!p->root&&p->child;
 caption(p->widgets[2],p->root?1140:border?1155:970);caption(p->widgets[3],p->root?941:971);
 for(uint32_t i=0;i<4;i++){
  uint32_t visible=p->root?i<(M10V_HDF_ENABLED?2u:1u):i<(border?3u:4u);
  ((fn2)0x533ad3c0u)(p->widgets[4+i],visible);
  uint32_t id=p->root?(M10V_HDF_ENABLED&&i==0?1141:1155):border?(i==0?972:i==1?1156:1157):972+i;
  caption(p->widgets[4+i],id);
  style_row(p,i,visible,p->root?p->focus==i:p->value==i);
 }
#else
 caption(p->widgets[2],p->root?1140:970);caption(p->widgets[3],p->root?941:971);
 for(uint32_t i=0;i<4;i++){
  ((fn2)0x533ad3c0u)(p->widgets[4+i],!p->root||i==0);
  caption(p->widgets[4+i],p->root?1141:972+i);
  style_row(p,i,!p->root||i==0,p->root?i==0:p->value==i);
 }
#endif
 ((fn2)0x533ad3c0u)(p->widgets[8],!p->root&&p->error);
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
#if M10V_PURE_ISP_EFFECTS
 ((m10v_isp_effects_camera_cache *)(uintptr_t)(owner+M10V_ISP_EFFECT_CACHE_OWNER_OFFSET))->magic=0;
#endif
 ((m10v_hdf_ui *)(uintptr_t)(owner+M10V_HDF_OWNER_OFFSET+M10V_HDF_CACHE_OFFSET))->magic=0;
 m10v_hdf_menu_destroy((page *)(uintptr_t)(owner+M10V_HDF_OWNER_OFFSET));return m10v_hdf_menu_parent_dtor(owner);
}
uint32_t m10v_hdf_menu_factory(uint32_t factory,uint32_t route){
 if(route!=ROUTE)return m10v_hdf_menu_parent_factory(factory,route);
 uint32_t owner=m10v_hdf_menu_parent_factory(factory,0x0200004a);
 return owner?owner+M10V_HDF_OWNER_OFFSET:0;
}
uint32_t m10v_hdf_menu_ready(page *p,uint32_t route){
 M10V_LOG(33,ptr(p),route,p->count,p->style);
 (void)route;p->error=0;p->root=M10V_HDF_GROUPED;
#if M10V_BORDER_ENABLED
 p->root=1;p->focus=0;p->child=0;
 M10V_LOG(34,ptr(p),1,0,0);
 int border_refresh=m10v_border_camera_refresh(ptr(p)-M10V_HDF_OWNER_OFFSET);
 M10V_LOG(34,ptr(p),2,(uint32_t)border_refresh,p->border.sequence);
 M10V_LOG(205,0x52454652u,(uint32_t)border_refresh,p->border.style,p->border.sequence);
 if(border_refresh<0)return 0;
#endif
#if M10V_PURE_ISP_EFFECTS
 p->parameter_index=0;
 M10V_LOG(34,ptr(p),3,0,0);
 int effects_refresh=m10v_isp_effects_camera_refresh(ptr(p)-M10V_HDF_OWNER_OFFSET);
 int effects_snapshot=effect_snapshot(p);
 M10V_LOG(34,ptr(p),4,(uint32_t)effects_refresh,(uint32_t)effects_snapshot);
 if(effects_refresh<0||!effects_snapshot)return 0;
#endif
#if M10V_HDF_ENABLED
 M10V_LOG(34,ptr(p),5,0,0);
 int hdf_load=m10v_hdf_load(&p->saved);
 M10V_LOG(34,ptr(p),6,(uint32_t)hdf_load,p->saved);
 if(hdf_load<0)return 0;p->value=p->saved;
#else
 p->value=p->saved=0;
#endif
 if(p->count==WORDS&&p->style){M10V_LOG(34,ptr(p),7,1,p->count);return 1;}
 if(p->count){clear(p);return 0;}
 if(make(p,1,0,0,720,480)||make(p,11,0,0,720,480)||make(p,17,20,20,680,50)||make(p,17,20,414,680,42))goto fail;
 ((fn2)0x53393e00u)(p->widgets[1],1);
 if(make_style(p))goto fail;
 for(uint32_t i=0;i<4;i++)if(make(p,17,36,90+i*72,644,52))goto fail;
 if(make(p,17,20,384,680,30))goto fail;
 uint32_t root=p->widgets[0],*v=(uint32_t *)(uintptr_t)*(uint32_t *)(uintptr_t)root;
 ((fn1)(uintptr_t)v[0x28/4])(root);((fn1)(uintptr_t)v[0x34/4])(root);M10V_LOG(34,ptr(p),7,1,p->count);return 1;
fail:M10V_LOG(34,ptr(p),8,0,p->count);clear(p);return 0;
}
void m10v_hdf_menu_enter(page *p,uint32_t route,uint32_t flags){
 M10V_LOG(35,ptr(p),route,flags,p->count);
 (void)route;(void)flags;draw(p);((fn3)0x5316d354u)(ptr(p),0,p->widgets[0]);
}
#if M10V_DEBUG_MODE
static uint32_t key_impl(page *p,uint32_t event){
#else
uint32_t m10v_hdf_menu_key(page *p,uint32_t event){
#endif
 uint32_t key=*(const uint16_t *)(uintptr_t)event;
#if M10V_PURE_ISP_EFFECTS
 uint32_t back=key==0x86||key==0x89||key==0xda;
 uint32_t up=key==0xce||key==0xd0||key==0xd4;
 uint32_t down=key==0xd1||key==0xd5;
 if(p->root==1u){
  if(up){if(p->focus)p->focus--;}
  else if(down){if(p->focus<4u)p->focus++;}
  else if(key==0xd8||key==0xcf||key==0xd3){
   p->child=p->focus;p->error=0;
   if(p->child>=2u){p->parameter_index=0;p->root=2;}
   else {p->root=0;if(p->child)p->saved=p->value=p->border.style;
    else if(m10v_hdf_load(&p->saved)<0){p->root=1;p->error=1;}else p->value=p->saved;}
  }else if(back){((fn1)0x5316ca28u)(ptr(p));return 1;}else return 0;
  draw(p);return 1;
 }
 if(p->root==2u){
  if(up){if(p->parameter_index)p->parameter_index--;}
  else if(down){if(p->parameter_index+1u<parameter_count(p))p->parameter_index++;}
  else if(key==0xd8||key==0xcf||key==0xd3){p->saved=p->value=parameter_value(p);p->root=0;p->error=0;}
  else if(back){p->root=1;p->error=0;}else return 0;
  draw(p);return 1;
 }
 if(p->child>=2u){
  if(back){p->value=p->saved;p->root=2;p->error=0;}
  else if(up){if(p->value)p->value--;p->error=0;}
  else if(down||key==0xcf||key==0xd3){if(p->value<parameter_max(p))p->value++;p->error=0;}
  else if(key==0xd8){
   m10v_isp_effects_settings previous=p->editor;
   if(!set_parameter(p,p->value)){p->error=1;draw(p);return 1;}
   int result=m10v_isp_effects_camera_save(ptr(p)-M10V_HDF_OWNER_OFFSET,&p->editor);
   if(result){
    /* A failed readback may follow a persisted write: refresh journal winner
     * and reconcile editor without publishing the unverified candidate. */
    p->editor=previous;
    (void)m10v_isp_effects_camera_refresh(ptr(p)-M10V_HDF_OWNER_OFFSET);
    if(effect_snapshot(p))p->saved=p->value=parameter_value(p);
    p->error=1;
   }else {p->saved=p->value;(void)effect_snapshot(p);p->root=2;p->error=0;}
  }else return 0;
  draw(p);return 1;
 }
#endif
 if(p->root){
#if M10V_BORDER_ENABLED
  if(key==0xce||key==0xd0||key==0xd4){p->focus=0;draw(p);return 1;}
  if(key==0xd1||key==0xd5){p->focus=M10V_HDF_ENABLED?1:0;draw(p);return 1;}
  if(key==0xd8||key==0xcf||key==0xd3){
   p->child=M10V_HDF_ENABLED?p->focus:1;
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
 if((M10V_HDF_GROUPED||M10V_BORDER_ENABLED)&&(key==0x86||key==0x89||key==0xda)){
  p->value=p->saved;p->root=1;p->error=0;draw(p);return 1;
 }
 if(key==0xce||key==0xd0||key==0xd4){if(p->value)p->value--;p->error=0;}
 else if(key==0xcf||key==0xd3||key==0xd1||key==0xd5){
  uint32_t max=3;
#if M10V_BORDER_ENABLED
  if(p->child)max=2;
#endif
  if(p->value<max)p->value++;p->error=0;
 }
 else if(key==0xd8){
  int result=-1;
#if M10V_BORDER_ENABLED
  if(p->child)result=m10v_border_camera_save(ptr(p)-M10V_HDF_OWNER_OFFSET,p->value);
  else
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
  else{p->saved=p->value;if(M10V_HDF_GROUPED||M10V_BORDER_ENABLED){p->root=1;draw(p);}else ((fn1)0x5316ca28u)(ptr(p));return 1;}
 }else if(key==0x86||key==0x89||key==0xda){((fn1)0x5316ca28u)(ptr(p));return 1;}
 else return 0;
 draw(p);return 1;
}
#if M10V_DEBUG_MODE
uint32_t m10v_hdf_menu_key(page *p,uint32_t event){
 uint32_t key=*(const uint16_t*)(uintptr_t)event;
 M10V_LOG(36,ptr(p),key,p->root,(p->focus<<16)|p->child);
 uint32_t result=key_impl(p,event);
 M10V_LOG(39,ptr(p),result,p->root,(p->parameter_index<<16)|p->value);
 return result;
}
#endif
uint32_t m10v_hdf_menu_key_route(uint32_t model){
 uint32_t route=m10v_hdf_menu_parent_key_route(model);
 if(route==ROUTE)M10V_LOG(37,model,route,0x0200004a,0);
 return route==ROUTE?0x0200004a:route;
}
