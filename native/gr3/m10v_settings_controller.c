/* Exact GR III 2.10 BaseController ownership adapter. Not enabled until the
 * separately audited root/factory patches and key mapping are installed. */
#include "m10v_tone.h"
#include "m10v_settings_controller.h"
#include "m10v_debug.h"
#include "m10v_sd_library.h"
#include "m10v_film_card.h"
#include "m10v_film_directory.h"
#include "m10v_zoom_camera.h"
#ifndef M10V_LIVE_COLOR
#define M10V_LIVE_COLOR 0
#endif
typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn2)(uint32_t,uint32_t);
typedef uint32_t (*fn3)(uint32_t,uint32_t,uint32_t);
extern uint32_t m10v_settings_factory_original(uint32_t,uint32_t);
extern uint32_t m10v_settings_top_dtor_original(uint32_t);
extern uint32_t m10v_settings_controller_vtable(void);
static int load(void *ctx,m10v_library_state *s){(void)ctx;return m10v_camera_library_load(s);}
static uint32_t extent(void *ctx){(void)ctx;return m10v_sd_camera_directory_extent();}
static uint32_t item(void *ctx,uint32_t i){(void)ctx;return m10v_sd_camera_directory_item(i);}
static int install(void *ctx,uint32_t i,uint32_t id,uint32_t slot){
 (void)ctx;m10v_library_state state;
 if(m10v_camera_library_load(&state)<0||!m10v_camera_library_mutation_begin())return -1;
 int result=m10v_sd_camera_directory_install(i,id,slot);
 m10v_camera_library_load(&state);m10v_camera_library_mutation_end(&state);return result;
}
static int remove_film(void *ctx,uint32_t slot){
 (void)ctx;m10v_library_state fresh;
 if(m10v_camera_library_load(&fresh)<0)return -1;
 if(!m10v_camera_library_mutation_begin())return -1;
 int r=m10v_camera_library_remove(&fresh,slot);
 if(r){m10v_camera_library_mutation_end(&fresh);return r;}
 uint32_t root=((uint32_t (*)(void))0x5320ad88u)(),model=((fn1)0x5320ba9cu)(root);
 uint8_t *m=(uint8_t *)(uintptr_t)model;uint8_t prior=m[0x1b];m[0x1b]=0;
 uint32_t tone=((fn1)0x532bd6b4u)(model),bank=((fn1)0x532bd6d4u)(model),active=m10v_tone_slot(tone);
 if(!bank&&active<M10V_SLOT_COUNT&&active>=slot){
  if(M10V_APPENDED_SLOTS)((fn2)0x532bd61cu)(model,0);
  ((fn2)0x532c26c0u)(model,active==slot?11:m10v_slot_tone(active-1));
 }
 m[0x1b]=prior;m10v_camera_library_mutation_end(&fresh);return 0;
}
static int stamp(void *ctx,uint32_t enabled,uint32_t format,uint32_t corner,uint32_t color){
 (void)ctx;m10v_library_state fresh;
 if(m10v_camera_library_load(&fresh)<0)return -1;
 return m10v_camera_library_stamp(&fresh,enabled,format,corner,color);
}
static int film_name_stamp(void *ctx,uint32_t enabled){
 (void)ctx;m10v_library_state fresh;
 if(m10v_camera_library_load(&fresh)<0)return -1;
 return m10v_camera_library_film_name_stamp(&fresh,enabled);
}
extern unsigned m10v_zoom_live_slot(void);
extern int m10v_zoom_live_apply(unsigned);
static void zoom_ops(m10v_zoom_menu_ops *o){o->load=m10v_zoom_camera_load;o->save=m10v_zoom_camera_save;o->select=m10v_zoom_live_apply;o->current=m10v_zoom_live_slot;}
static void ops(m10v_settings_ops *o){o->context=0;o->load=load;o->item=item;o->install=install;o->remove=remove_film;o->stamp=stamp;o->film_name_stamp=film_name_stamp;o->extent=extent;}
static m10v_settings_controller *page(uint32_t owner,uint32_t i){
 return (m10v_settings_controller *)(uintptr_t)(owner+M10V_SETTINGS_OWNER_BYTES+i*M10V_SETTINGS_CONTROLLER_BYTES);
}
#include "m10v_ab_camera.inc"
uint32_t m10v_settings_controller_owner_size(void){return M10V_SETTINGS_OWNER_BYTES+2*M10V_SETTINGS_CONTROLLER_BYTES+(M10V_LIVE_COLOR?256u:0u);}
uint32_t m10v_settings_controller_top_ctor(uint32_t owner){
 ((fn1)0x5319aa68u)(owner);
 for(uint32_t i=0;i<2;i++){
  m10v_settings_controller *p=page(owner,i);uint8_t *b=(uint8_t *)p;
  for(uint32_t n=0;n<sizeof(*p);n++)b[n]=0;
  ((fn1)0x5316c8d4u)((uint32_t)(uintptr_t)p);
  *(uint32_t *)p=m10v_settings_controller_vtable();
  p->page=i?M10V_SETTINGS_STAMP:M10V_SETTINGS_FILMS;
  p->ab.a=M10V_APPENDED_SLOTS?12:1;p->ab.b=5;
 }
#if M10V_LIVE_COLOR
 m10v_camera_library_preview_init(owner);
#endif
 return owner;
}
uint32_t m10v_settings_controller_destroy(m10v_settings_controller *p){
 ((fn1)0x5316ce8cu)((uint32_t)(uintptr_t)p);
 m10v_settings_view_destroy(&p->view);
 ((fn1)0x5316c774u)((uint32_t)(uintptr_t)p);
 return (uint32_t)(uintptr_t)p;
}
uint32_t m10v_settings_controller_top_dtor(uint32_t owner){
 ab_clear(&page(owner,0)->ab);
#if M10V_LIVE_COLOR
 m10v_camera_library_preview_clear(owner);
#endif
 for(uint32_t i=0;i<2;i++)m10v_settings_controller_destroy(page(owner,i));
 return m10v_settings_top_dtor_original(owner);
}
uint32_t m10v_settings_controller_factory(uint32_t factory,uint32_t route){
 if(route!=M10V_SETTINGS_FILMS_ROUTE&&route!=M10V_SETTINGS_STAMP_ROUTE&&route!=M10V_SETTINGS_NAME_ROUTE&&route!=M10V_SETTINGS_AB_ROUTE&&route!=M10V_SETTINGS_ZOOM_ROUTE)
  return m10v_settings_factory_original(factory,route);
 uint32_t owner=m10v_settings_factory_original(factory,0x0200004au);
 return owner?(uint32_t)(uintptr_t)page(owner,route==M10V_SETTINGS_STAMP_ROUTE||route==M10V_SETTINGS_NAME_ROUTE):0;
}
uint32_t m10v_settings_controller_ready(m10v_settings_controller *p,uint32_t route){
 p->display_trace=0;
 p->pending_source=0;
 p->page=route==M10V_SETTINGS_ZOOM_ROUTE?M10V_SETTINGS_ZOOM:route==M10V_SETTINGS_AB_ROUTE?M10V_SETTINGS_AB:route==M10V_SETTINGS_NAME_ROUTE?M10V_SETTINGS_NAME:route==M10V_SETTINGS_STAMP_ROUTE?M10V_SETTINGS_WATERMARK:M10V_SETTINGS_FILMS;m10v_settings_ops o;ops(&o);
 /* AB is a shooting ImageControl child, not a generic Setup controller.
  * Match stock 531ab0f8 / 531ab160(route02000012): mode0 waits for the
  * shooting transition before presentation; parameter137=0 keeps the active
  * ImageControl system mode instead of restoring the saved mode (value2).
  * ready runs before BaseController enter/5316dec0 applies these parameters.
  * The same owner is also used by Setup, so restore its original defaults. */
 p->base[0x12b]=p->page==M10V_SETTINGS_AB?0:2;
 p->base[0x137]=p->page==M10V_SETTINGS_AB?0:2;
 int opened=0;
 if(p->page==M10V_SETTINGS_ZOOM){m10v_zoom_menu_ops z;zoom_ops(&z);m10v_zoom_menu_open(&p->zoom,&z);}
 else opened=m10v_settings_open(&p->state,&o,p->page);
 if(route==M10V_SETTINGS_AB_ROUTE)M10V_LOG(92,route,(uint32_t)opened,p->state.screen,p->view.count);
 if(opened)return 0;
 if(p->page==M10V_SETTINGS_AB){p->ab.down=0;ab_pair(&p->ab);p->state.slot=p->ab.a;p->state.index=p->ab.b;}
 uint32_t result=p->view.count==M10V_VIEW_COUNT&&p->view.widgets[0] ? 1 : m10v_settings_view_create(&p->view)==0;
 if(route==M10V_SETTINGS_AB_ROUTE)M10V_LOG(93,route,result,p->view.count,p->view.widgets[0]);
 return result;
}
void m10v_settings_controller_enter(m10v_settings_controller *p,uint32_t route,uint32_t flags){
 if(route==M10V_SETTINGS_AB_ROUTE)M10V_LOG(94,(uint32_t)(uintptr_t)p,route,p->state.screen,flags);
 (void)route;(void)flags;m10v_settings_ops o;ops(&o);
 M10V_LOG(80,p->page,route,p->state.screen,p->state.focus);
 if(p->page==M10V_SETTINGS_ZOOM)m10v_settings_view_zoom(&p->view,&p->zoom);
 else m10v_settings_view_draw(&p->view,&p->state,&o);
 ((fn3)0x5316d354u)((uint32_t)(uintptr_t)p,0,p->view.widgets[0]);
 M10V_LOG(81,p->page,route,p->state.screen,p->state.focus);
}
/* Observe the real UI-loop draw boundary. Keep the stock renderer and its
 * display selection intact; at most two snapshots per A/B entry (first frame
 * and first non-busy frame), never an SD write on every preview frame. */
void m10v_settings_controller_ab_render(m10v_settings_controller *p){
#if M10V_DEBUG_MODE
 uint32_t trace=0,root=0;
 if(p->page==M10V_SETTINGS_AB&&p->display_trace!=3){
  uint32_t model=((fn1)0x5320b13cu)(((fn1)0x5320ad88u)(0));
  uint32_t busy=((fn1)0x53233574u)(model);
  trace=!p->display_trace||(!busy&&!(p->display_trace&2));
  if(trace){
   uint32_t records[25*5],count=0;
#define DISPLAY_RECORD(t,a,b,c) do{uint32_t *r=records+5*count++;r[0]=97;r[1]=(t);r[2]=(a);r[3]=(b);r[4]=(c);}while(0)
   p->display_trace|=1u|(!busy?2u:0u);
   DISPLAY_RECORD(0,(uint32_t)(uintptr_t)p,*(uint32_t *)(p->base+0x124),p->base[0x14e]);
   for(uint32_t i=0;i<6;i++){
    uint8_t *slot=p->base+i*0x30;uint32_t w=*(uint32_t *)(slot+4);
    DISPLAY_RECORD(i+1,w,slot[8]|((uint32_t)slot[9]<<8),w?((uint8_t *)(uintptr_t)w)[0xa0]|((uint32_t)((uint8_t *)(uintptr_t)w)[0xa2]<<8):0);
    if(w){
     root=w;
     uint32_t gate=((fn3)0x532334d0u)(model,slot[8],slot[9]);
     DISPLAY_RECORD(8,busy,gate,model);
     DISPLAY_RECORD(7,w,*(uint32_t *)(uintptr_t)(w+0x28),*(uint32_t *)(uintptr_t)(w+0x2c));
     DISPLAY_RECORD(9,w,*(uint32_t *)(uintptr_t)(w+0xec),(uint32_t)(uintptr_t)(slot+0xc));
    }
   }
   (void)m10v_debug_batch(records,count);
#undef DISPLAY_RECORD
  }
 }
#endif
 ((fn1)0x5316d0f0u)((uint32_t)(uintptr_t)p);
#if M10V_DEBUG_MODE
 if(trace)M10V_LOG(98,(uint32_t)(uintptr_t)p,root,root?((uint8_t *)(uintptr_t)root)[0xa0]|((uint32_t)((uint8_t *)(uintptr_t)root)[0xa2]<<8):0,p->base[0x14e]);
#endif
}
uint32_t m10v_settings_controller_key(m10v_settings_controller *p,uint32_t event){
 uint32_t raw=*(const uint16_t *)(uintptr_t)event,key;
 M10V_LOG(82,raw,p->state.screen,p->state.focus,p->state.value);
 /* Physical MENU/DISP can be filtered before this virtual handler. The
  * dispatch adapter retries only an unhandled first press on this owned page. */
 if(raw==4||raw==5||raw==0x1b){
  if(p->page!=M10V_SETTINGS_FILMS||p->state.screen!=M10V_SETTINGS_CATALOG)return 0;
  uint32_t payload=*(const uint32_t *)(uintptr_t)(event+4);
  if(!ab_ram(payload,8)||*(const uint8_t *)(uintptr_t)payload!=1||
     *(const uint32_t *)(uintptr_t)(payload+4)!=1)return 0;
  if(raw==0x1b){
   uint32_t retired=0;
   for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)if(p->state.saved.slots[i].film&&!M10V_CUSTOM(p->state.saved.slots[i].film)&&!m10v_directory_name(p->state.saved.slots[i].film))retired=1;
   if(!retired)return 0;
  }
  p->pending_source=event;
  if(raw==4){
   p->state.screen=M10V_SETTINGS_CLOSED;
   ((fn3)0x5316c9d8u)((uint32_t)(uintptr_t)p,0x08000000u,0x10000000u);
   return 1;
  }
  key=raw==5?M10V_KEY_BACK:M10V_KEY_CLEAN;
 }else switch(raw){
 case 0xce:key=M10V_KEY_LEFT;break;
 case 0xcf:case 0xd3:key=M10V_KEY_RIGHT;break;
 case 0xd0:case 0xd4:key=M10V_KEY_UP;break;
 case 0xd1:case 0xd5:key=M10V_KEY_DOWN;break;
 case 0xd8:key=M10V_KEY_OK;break;
 case 0x86:case 0x89:case 0xda:key=M10V_KEY_BACK;break;
 default:return 0;
 }
 if(p->page==M10V_SETTINGS_ZOOM){
  m10v_zoom_menu_ops z;zoom_ops(&z);
  m10v_zoom_menu_key(&p->zoom,&z,key);
  if(p->zoom.closed)((fn1)0x5316ca28u)((uint32_t)(uintptr_t)p);
  else m10v_settings_view_zoom(&p->view,&p->zoom);
  return 1;
 }
 m10v_settings_ops o;ops(&o);uint32_t before=p->state.screen;
 m10v_settings_key(&p->state,&o,key);
 if(before==M10V_SETTINGS_CATALOG&&p->state.screen==M10V_SETTINGS_FILMS&&key==M10V_KEY_OK){p->ab.enabled=0;ab_clear(&p->ab);}
 if(p->state.screen==M10V_SETTINGS_AB&&p->state.value){
  if(p->state.value==2){p->ab.enabled=0;ab_clear(&p->ab);p->state.screen=M10V_SETTINGS_CLOSED;}
  else{
   uint32_t a=p->state.slot,b=p->state.index; m10v_library_state fresh;
   if(a==b){p->state.error=M10V_SETTINGS_CHANGED;}
   else if(a>=M10V_TONE_CHOICES||b>=M10V_TONE_CHOICES||m10v_camera_library_load(&fresh)<0||ab_save(a,b))p->state.error=M10V_SETTINGS_SAVE_FAILED;
   else{
    uint32_t current=ab_current(),target=current==b?b:a;
    if(current!=target&&ab_apply(target))p->state.error=M10V_SETTINGS_SAVE_FAILED;
    else{
     for(uint32_t i=0;i<sizeof(fresh);i++)((uint8_t *)&p->state.saved)[i]=((const uint8_t *)&fresh)[i];
     uint32_t sa=m10v_ab_slot(a),sb=m10v_ab_slot(b);
     m10v_ab_start(&p->ab,a,b,target,sa<M10V_SLOT_COUNT?fresh.slots[sa].film:0,sb<M10V_SLOT_COUNT?fresh.slots[sb].film:0);
     p->state.screen=M10V_SETTINGS_CLOSED;
    }
   }
  }
  p->state.value=0;
 }
 M10V_LOG(83,raw,p->state.screen,p->state.focus,(p->state.error<<16)|p->state.value);
 if(p->state.screen==M10V_SETTINGS_CLOSED)((fn1)0x5316ca28u)((uint32_t)(uintptr_t)p);
 else m10v_settings_view_draw(&p->view,&p->state,&o);
 M10V_LOG(84,raw,p->state.screen,p->state.focus,(p->state.error<<16)|p->state.value);
 return 1;
}

/* Scoped to the original key dispatch call site, never the global route getter. */
uint32_t m10v_settings_controller_key_route(uint32_t model){
 uint32_t route=((fn1)0x53228c4cu)(model);
 return route==M10V_SETTINGS_FILMS_ROUTE||route==M10V_SETTINGS_STAMP_ROUTE||route==M10V_SETTINGS_NAME_ROUTE||route==M10V_SETTINGS_AB_ROUTE||route==M10V_SETTINGS_ZOOM_ROUTE?0x0200004au:route;
}

/* Dynamic bitmap metadata belongs to the same heap allocation as its pixels.
 * Only the five private icon IDs call this provider. No ROM writes or retained
 * global heap pointers; original TopMenu/root lifetime owns the lookup. */
uint32_t m10v_settings_controller_card_directory(void){
 if(!(*(const volatile uint32_t *)0x55063910u&1u))return 0;
 uint32_t owner=*(const volatile uint32_t *)0x55063988u;
 if((owner&3)||owner<0x55000000u||owner>0x80000000u-0x213cu)return 0;
 m10v_settings_controller *p=page(owner,0);
 if(*(uint32_t *)p!=m10v_settings_controller_vtable()||p->view.count!=M10V_VIEW_COUNT)return 0;
 uint32_t heap=p->view.widgets[M10V_VIEW_HEAP];
 if((heap&3)||heap<0x55000000u||heap>0x80000000u-M10V_CARD_HEAP_BYTES)return 0;
 return heap+M10V_CARD_DIRECTORY_OFFSET-M10V_CARD_FIRST*4u;
}
