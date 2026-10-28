/* Independent HDF settings controller. Original TopMenu owns this small tail;
 * no film objects, film selection, film detail page or film journal is used. */
#include <stdint.h>
#include <stddef.h>
#include "m10v_debug.h"
#ifndef M10V_BORDER_ENABLED
#define M10V_BORDER_ENABLED 0
#endif
#if M10V_BORDER_ENABLED
#include "m10v_border_camera.h"
#endif
#ifndef M10V_HDF_ENABLED
#define M10V_HDF_ENABLED 1
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
 uint32_t focus;m10v_border_cache border;uint32_t child;
#endif
} page;
_Static_assert(sizeof(page)<=0x1c0,"HDF owned controller capacity");
#if M10V_BORDER_ENABLED
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
 ((fn3)0x5316cde8u)(0,ptr(p->widgets),p->count);
 for(uint32_t i=0;i<WORDS;i++)p->widgets[i]=0;p->count=0;
}
static void draw(page *p){
#if M10V_BORDER_ENABLED
 uint32_t border=!p->root&&p->child;
 caption(p->widgets[2],p->root?1140:border?1150:970);caption(p->widgets[3],p->root?941:971);
 for(uint32_t i=0;i<4;i++){
  uint32_t visible=p->root?i<(M10V_HDF_ENABLED?2u:1u):i<(border?3u:4u);
  ((fn2)0x533ad3c0u)(p->widgets[4+i],visible);
  uint32_t id=p->root?(M10V_HDF_ENABLED&&i==0?1141:1150):border?(i==0?972:i==1?1151:1152):972+i;
  caption(p->widgets[4+i],id);
  ((fn2)0x5339658cu)(p->widgets[4+i],(p->root?p->focus==i:p->value==i)?10:31);
 }
#else
 caption(p->widgets[2],p->root?1140:970);caption(p->widgets[3],p->root?941:971);
 for(uint32_t i=0;i<4;i++){
  ((fn2)0x533ad3c0u)(p->widgets[4+i],!p->root||i==0);
  caption(p->widgets[4+i],p->root?1141:972+i);
  ((fn2)0x5339658cu)(p->widgets[4+i],p->root||p->value==i?10:31);
 }
#endif
 ((fn2)0x533ad3c0u)(p->widgets[8],!p->root);
 caption(p->widgets[8],p->error?976:977);
 ((fn1)0x533ad308u)(p->widgets[0]);
}
uint32_t m10v_hdf_menu_top_ctor(uint32_t owner){
 m10v_hdf_menu_parent_ctor(owner);page *p=(page *)(uintptr_t)(owner+M10V_HDF_OWNER_OFFSET);
 for(uint32_t i=0;i<sizeof(*p);i++)((uint8_t *)p)[i]=0;
 ((fn1)0x5316c8d4u)(ptr(p));*(uint32_t *)p=m10v_hdf_menu_vtable();return owner;
}
uint32_t m10v_hdf_menu_destroy(page *p){
 ((fn1)0x5316ce8cu)(ptr(p));clear(p);((fn1)0x5316c774u)(ptr(p));return ptr(p);
}
uint32_t m10v_hdf_menu_top_dtor(uint32_t owner){
 m10v_hdf_menu_destroy((page *)(uintptr_t)(owner+M10V_HDF_OWNER_OFFSET));return m10v_hdf_menu_parent_dtor(owner);
}
uint32_t m10v_hdf_menu_factory(uint32_t factory,uint32_t route){
 if(route!=ROUTE)return m10v_hdf_menu_parent_factory(factory,route);
 uint32_t owner=m10v_hdf_menu_parent_factory(factory,0x0200004a);
 return owner?owner+M10V_HDF_OWNER_OFFSET:0;
}
uint32_t m10v_hdf_menu_ready(page *p,uint32_t route){
 (void)route;p->error=0;p->root=M10V_HDF_GROUPED;
#if M10V_BORDER_ENABLED
 p->root=1;p->focus=0;p->child=0;
 int border_refresh=m10v_border_camera_refresh(ptr(p)-M10V_HDF_OWNER_OFFSET);
 M10V_LOG(205,0x52454652u,(uint32_t)border_refresh,p->border.style,p->border.sequence);
 if(border_refresh<0)return 0;
#endif
#if M10V_HDF_ENABLED
 if(m10v_hdf_load(&p->saved)<0)return 0;p->value=p->saved;
#else
 p->value=p->saved=0;
#endif
 if(p->count==WORDS)return 1;
 if(p->count){clear(p);return 0;}
 if(make(p,1,0,0,720,480)||make(p,11,0,0,720,480)||make(p,17,20,20,680,50)||make(p,17,20,414,680,42))goto fail;
 ((fn2)0x53393e00u)(p->widgets[1],1);
 for(uint32_t i=0;i<4;i++)if(make(p,17,40+i*170,188,160,64))goto fail;
 if(make(p,17,20,320,680,50))goto fail;
 uint32_t root=p->widgets[0],*v=(uint32_t *)(uintptr_t)*(uint32_t *)(uintptr_t)root;
 ((fn1)(uintptr_t)v[0x28/4])(root);((fn1)(uintptr_t)v[0x34/4])(root);return 1;
fail:clear(p);return 0;
}
void m10v_hdf_menu_enter(page *p,uint32_t route,uint32_t flags){
 (void)route;(void)flags;draw(p);((fn3)0x5316d354u)(ptr(p),0,p->widgets[0]);
}
uint32_t m10v_hdf_menu_key(page *p,uint32_t event){
 uint32_t key=*(const uint16_t *)(uintptr_t)event;
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
  M10V_LOG(205,0x53415645u,p->child?p->value:0,(uint32_t)result,p->border.sequence);
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
uint32_t m10v_hdf_menu_key_route(uint32_t model){
 uint32_t route=m10v_hdf_menu_parent_key_route(model);return route==ROUTE?0x0200004a:route;
}
