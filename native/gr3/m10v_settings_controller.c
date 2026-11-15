/* Exact GR III 2.10 BaseController ownership adapter. Not enabled until the
 * separately audited root/factory patches and key mapping are installed. */
#include "m10v_tone.h"
#include "m10v_settings_controller.h"
#if M10V_COMPANION_ENABLED
#include "m10v_companion_owner.h"
#endif
#include "m10v_debug.h"
#include "m10v_sd_library.h"
#include "m10v_film_card.h"
#include "m10v_film_directory.h"
#include "m10v_zoom_camera.h"
#if M10V_ADJ_EXTRA_CAMERA
#include "m10v_adj_extra_camera.h"
#define M10V_SETTINGS_ADJ_EXTRA 10u
static const uint8_t adj_extra_functions[]={
 M10V_ADJ_EXTRA_GUIDES,M10V_ADJ_EXTRA_FILM,M10V_ADJ_EXTRA_EFFECTS,M10V_ADJ_EXTRA_ASPECT,20,
#if M10V_BORDER_ENABLED
 M10V_ADJ_EXTRA_BORDER,
#endif
};
static uint32_t adj_function(uint32_t index){
 const volatile uint8_t *stock=(const volatile uint8_t *)M10V_ADJ_EXTRA_STOCK_LIST;
 if(index<M10V_ADJ_EXTRA_STOCK_CHOICES)return stock[index];
 return adj_extra_functions[index-M10V_ADJ_EXTRA_STOCK_CHOICES];
}
#endif
#if M10V_GUIDES_CAMERA
#include "m10v_guides_camera.h"
#endif
#ifndef M10V_AB_ENABLED
#define M10V_AB_ENABLED 1
#endif
/* Keep one auditable ARM gate without optimizing away the shared lifecycle. */
__attribute__((noinline)) uint32_t m10v_settings_controller_ab_available(void){
 uint32_t value;__asm__ volatile("mov %0, %1":"=r"(value):"I"(M10V_AB_ENABLED));return value;
}
#ifndef M10V_HALF_PAIR_ENABLED
#define M10V_HALF_PAIR_ENABLED 0
#endif
#if M10V_HALF_PAIR_ENABLED
#include "m10v_half_pair_camera.h"
#endif
#if M10V_TORN_ENABLED
#include "m10v_torn_overlay.h"
#endif
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
#if M10V_SHUTDOWN_ALBUM
static void shutdown_restore(m10v_settings_controller *p);
#endif
static m10v_settings_controller *page(uint32_t owner,uint32_t i){
 return (m10v_settings_controller *)(uintptr_t)(owner+M10V_SETTINGS_OWNER_BYTES+i*M10V_SETTINGS_CONTROLLER_BYTES);
}
#if M10V_PHOTO_RECIPE
extern uint32_t m10v_camera_library_box_id(void);
extern int m10v_isp_effects_camera_copy_box(uint32_t,uint32_t);
extern int m10v_isp_effects_camera_reload_box(uint32_t);
#if M10V_BORDER_ENABLED
extern int m10v_border_camera_copy_box(uint32_t,uint32_t);
#endif
#if M10V_HDF_UI_CACHE
extern int m10v_hdf_copy_box(uint32_t);
extern int m10v_hdf_load(uint32_t *);
#endif
int m10v_camera_library_save_box(uint32_t);
int m10v_camera_library_reload_box(void);
void m10v_camera_library_adj_tone_set(uint32_t);
uint32_t m10v_camera_library_adj_tone(void);
#endif
#include "m10v_ab_camera.inc"
#if M10V_SHUTDOWN_ALBUM
#define M10V_SETTINGS_SHUTDOWN 11u
/* A checked resource build changes the count word after the native build. */
const uint32_t m10v_settings_controller_shutdown_config[2]={0x3141534du,0};
typedef struct {uint16_t width,height;const char *path;} shutdown_image;
static const shutdown_image shutdown_images[3]={
 {720,480,"A:\\Resource\\Jpeg\\GB_ING.jpg"},
 {720,480,"A:\\Resource\\Jpeg\\GB_Urban.jpg"},
 {720,480,"A:\\Resource\\Jpeg\\GB_Diary.jpg"},
};
const void *m10v_settings_controller_shutdown_descriptor(uint32_t request){
 return request>=13&&request<=15?&shutdown_images[request-13]:0;
}
static uint32_t shutdown_count(void){
 const volatile uint32_t *config=m10v_settings_controller_shutdown_config;
 uint32_t count=config[1];return count<=3?count:0;
}
typedef struct {uint32_t magic,sequence,choice,crc;} shutdown_record;
static const char shutdown_files[2][12]={"M10VSA0.BIN","M10VSA1.BIN"};
static int shutdown_read(uint32_t fs,uint32_t page,shutdown_record *out){
 return ((uint32_t (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,shutdown_files[page],sizeof(*out),out)&&
  out->magic==0x3141534du&&out->sequence&&(out->sequence&1u)==page&&out->choice<=3&&
  out->crc==m10v_sd_crc((const uint8_t *)out,12);
}
static shutdown_record shutdown_latest(uint32_t fs){
 shutdown_record a={0},b={0};
 if(!shutdown_read(fs,0,&a))a.sequence=0;
 if(!shutdown_read(fs,1,&b))b.sequence=0;
 return b.sequence>a.sequence?b:a;
}
static void shutdown_restore(m10v_settings_controller *p){
 uint32_t fs=ab_fs(),count=shutdown_count();
 if(!fs||!count)return;
 shutdown_record record=shutdown_latest(fs);
 if(p==ab_owner())p->shutdown_album=record.sequence&&record.choice<=count?record.choice:0;
}
static int shutdown_save(uint32_t choice){
 m10v_settings_controller *p=ab_owner();uint32_t fs=ab_fs();
 if(!p||!fs||choice>shutdown_count())return 0;
 shutdown_record record=shutdown_latest(fs),back;
 if(record.sequence==UINT32_MAX)return 0;
 record.magic=0x3141534du;record.sequence++;record.choice=choice;
 record.crc=m10v_sd_crc((const uint8_t *)&record,12);
 uint32_t page=record.sequence&1u;
 if(!((uint32_t (*)(uint32_t,const char *,uint32_t,const void *))0x53825fa8u)(fs,shutdown_files[page],sizeof(record),&record)||
    !shutdown_read(fs,page,&back)||back.sequence!=record.sequence||back.choice!=choice||p!=ab_owner())return 0;
 p->shutdown_album=choice;
 M10V_LOG(140,choice,record.sequence,0,0);
 return 1;
}
uint32_t m10v_settings_controller_shutdown_render(uint32_t display,uint32_t request,uint32_t rect,uint32_t context){
 m10v_settings_controller *p=ab_owner();
 uint32_t choice=p?p->shutdown_album:0;
 if(choice&&choice<=shutdown_count())request=12+choice;
 return ((uint32_t (*)(uint32_t,uint32_t,uint32_t,uint32_t))0x5322e4a8u)(display,request,rect,context);
}
#endif
uint32_t m10v_settings_controller_owner_size(void){
#if M10V_ADJ_EXTRA_CAMERA || M10V_GUIDES_CAMERA
#if M10V_TORN_ENABLED
 return 0x6e00;
#else
 return 0x6d00;
#endif
#elif M10V_COMPANION_ENABLED
 return M10V_COMPANION_DESCRIPTOR_OFFSET+M10V_COMPANION_DESCRIPTOR_BYTES;
#else
 return M10V_SETTINGS_OWNER_BYTES+2*M10V_SETTINGS_CONTROLLER_BYTES+(M10V_LIVE_COLOR?0x4000u:0u);
#endif
}
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
#if M10V_COMPANION_ENABLED
 m10v_companion_ui_init(owner);
#endif
#if M10V_ADJ_EXTRA_CAMERA
 m10v_adj_extra_camera_init(owner);
#endif
#if M10V_GUIDES_CAMERA
 m10v_guides_camera_init(owner);
#endif
 #if M10V_HALF_PAIR_ENABLED
 m10v_half_pair_init(owner);
 #endif
#if M10V_TORN_ENABLED
 m10v_torn_init(owner);
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
#if M10V_TORN_ENABLED
 m10v_torn_destroy(owner);
#endif
#if M10V_ADJ_EXTRA_CAMERA
 m10v_adj_extra_camera_dispose(owner);
#endif
#if M10V_GUIDES_CAMERA
 m10v_guides_camera_dispose(owner);
#endif
#if M10V_COMPANION_ENABLED
 m10v_companion_ui_stop(owner);
#endif
#if M10V_HALF_PAIR_ENABLED
 m10v_half_pair_destroy(owner);
#endif
 ab_clear(&page(owner,0)->ab);
#if M10V_LIVE_COLOR
 m10v_camera_library_preview_clear(owner);
#endif
 for(uint32_t i=0;i<2;i++)m10v_settings_controller_destroy(page(owner,i));
 return m10v_settings_top_dtor_original(owner);
}
uint32_t m10v_settings_controller_factory(uint32_t factory,uint32_t route){
#if M10V_SHUTDOWN_ALBUM
 if(route==M10V_SETTINGS_SHUTDOWN_ROUTE){
  uint32_t owner=m10v_settings_factory_original(factory,0x0200004au);
  return owner&&shutdown_count()?(uint32_t)(uintptr_t)page(owner,1):0;
 }
#endif
#if M10V_ADJ_EXTRA_CAMERA
 if(route==M10V_SETTINGS_ADJ_ROUTE){
  uint32_t owner=m10v_settings_factory_original(factory,0x0200004au);
  return owner?(uint32_t)(uintptr_t)page(owner,1):0;
 }
#endif
 if(route==M10V_SETTINGS_AB_ROUTE&&!m10v_settings_controller_ab_available())return m10v_settings_factory_original(factory,route);
 if(route!=M10V_SETTINGS_FILMS_ROUTE&&route!=M10V_SETTINGS_STAMP_ROUTE&&route!=M10V_SETTINGS_NAME_ROUTE&&route!=M10V_SETTINGS_AB_ROUTE&&route!=M10V_SETTINGS_ZOOM_ROUTE)
  return m10v_settings_factory_original(factory,route);
 uint32_t owner=m10v_settings_factory_original(factory,0x0200004au);
 return owner?(uint32_t)(uintptr_t)page(owner,route==M10V_SETTINGS_STAMP_ROUTE||route==M10V_SETTINGS_NAME_ROUTE):0;
}
uint32_t m10v_settings_controller_ready(m10v_settings_controller *p,uint32_t route){
 p->display_trace=0;
 p->pending_source=0;
 p->film_touch_start=p->film_touch_last=0;
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
#if M10V_SHUTDOWN_ALBUM
 if(route==M10V_SETTINGS_SHUTDOWN_ROUTE){
  m10v_settings_controller *cache=ab_owner();
  if(!cache||!shutdown_count())return 0;
  shutdown_restore(cache);
  if(cache!=ab_owner())return 0;
  p->page=M10V_SETTINGS_SHUTDOWN;
  p->state.screen=M10V_SETTINGS_SHUTDOWN;
  p->state.focus=p->state.value=cache->shutdown_album;
  p->state.error=0;
 }else
#endif
#if M10V_ADJ_EXTRA_CAMERA
 if(route==M10V_SETTINGS_ADJ_ROUTE){
  m10v_adj_extra_assignments a;
  m10v_adj_extra_camera_load(&a);
  p->page=M10V_SETTINGS_ADJ_EXTRA;
  p->state.focus=0;p->state.error=0;p->state.value=a.function[0];
  p->state.expected=(uint32_t)a.function[0]|((uint32_t)a.function[1]<<8)|
      ((uint32_t)a.function[2]<<16)|((uint32_t)a.function[3]<<24);
 }else
#endif
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
#if M10V_SHUTDOWN_ALBUM
 if(p->page==M10V_SETTINGS_SHUTDOWN)m10v_settings_view_shutdown(&p->view,&p->state,shutdown_count());
 else
#endif
#if M10V_ADJ_EXTRA_CAMERA
 if(p->page==M10V_SETTINGS_ADJ_EXTRA)m10v_settings_view_adj(&p->view,&p->state);
 else
#endif
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
#if !M10V_CAMERA_GR3X
static uint32_t catalog_tile(uint32_t x,uint32_t y){
 if(x<M10V_FILM_GRID_X||y<M10V_FILM_GRID_Y)return 10;
 x-=M10V_FILM_GRID_X;y-=M10V_FILM_GRID_Y;
 uint32_t column=x/M10V_FILM_GRID_DX,row=y/M10V_FILM_GRID_DY;
 if(column>=5||row>=2||x%M10V_FILM_GRID_DX>=M10V_CARD_WIDTH||
    y%M10V_FILM_GRID_DY>=M10V_CARD_TILE_HEIGHT)return 10;
 return row*5+column;
}
static uint32_t catalog_touch(m10v_settings_controller *p,uint32_t payload){
 if(p->page!=M10V_SETTINGS_FILMS||p->state.screen!=M10V_SETTINGS_CATALOG)return 0;
 /* Stock GR III 2.10 TouchModel (5323e768) publishes a 0x58-byte packet.
  * Its current point is at +8/+12 and the gesture kind at +0x50.
  * A single finger produces down (1), drag (5), optional fling (7),
  * and release (10). The prior sample copied to +0x28 retains the
  * last contact coordinates when the release sample clears them. */
 if(!ab_ram(payload,0x58)){
  p->film_touch_start=p->film_touch_last=0;
  return 0;
 }
 const uint8_t *packet=(const uint8_t *)(uintptr_t)payload;
 uint32_t kind=packet[0x50],fingers=packet[0];
 if((kind==1||kind==5)&&fingers==1){
  uint32_t x=*(const uint32_t *)(packet+8),y=*(const uint32_t *)(packet+12);
  if(x>720||y>480){p->film_touch_start=p->film_touch_last=0;return 0;}
  uint32_t point=(y<<16)|(x+1);
  if(kind==1){
   p->film_touch_start=p->film_touch_last=point;
   p->film_touch_dragged=0;
   M10V_LOG(76,x,y,p->state.index,0);
  }else if(p->film_touch_start){
   p->film_touch_last=point;
   p->film_touch_dragged=1;
  }
  return 0;
 }
 /* The stock touch model may queue a tap or double tap notification
  * before release. Commit exclusively on release to avoid a double toggle. */
 if((kind==2||kind==4||kind==7)&&fingers==0){
  if(kind==7)p->film_touch_dragged=1;
  return 0;
 }
 uint32_t start=p->film_touch_start,last=p->film_touch_last;
 p->film_touch_start=p->film_touch_last=0;
 if(!start)return 0;
 if(kind!=10||fingers){
  M10V_LOG(78,kind,fingers,p->state.index,0);
  return 0;
 }
 int32_t dx=(int32_t)(last&0xffffu)-(int32_t)(start&0xffffu);
 int32_t dy=(int32_t)(last>>16)-(int32_t)(start>>16);
 uint32_t width=(uint32_t)(dx<0?-dx:dx),height=(uint32_t)(dy<0?-dy:dy);
 uint32_t before=p->state.index,end=p->state.group;
 if(!p->film_touch_dragged&&packet[0x28]==1){
  uint32_t x=(start&0xffffu)-1,y=start>>16,tile=catalog_tile(x,y);
  uint32_t end_x=*(const uint32_t *)(packet+0x30),end_y=*(const uint32_t *)(packet+0x34);
  if(tile<10&&catalog_tile(end_x,end_y)==tile&&end_x+12>=x&&x+12>=end_x&&end_y+12>=y&&y+12>=end_y){
   m10v_settings_ops o;ops(&o);
   uint32_t index=(before/10)*10+tile;
   if(m10v_settings_catalog_tap(&p->state,&o,index)){
    M10V_LOG(79,x,y,index,(m10v_library_count(&p->state.saved)<<16)|p->state.error);
    m10v_settings_view_draw(&p->view,&p->state,&o);
    return 1;
   }
  }
 }else if(width>=60&&width>=2*height&&
    ((dx>0&&before>=10)||(dx<0&&before/10+1<(end+9)/10))){
  m10v_settings_ops o;ops(&o);
  m10v_settings_key(&p->state,&o,dx>0?M10V_KEY_PREVIOUS:M10V_KEY_NEXT);
  m10v_settings_view_draw(&p->view,&p->state,&o);
 }
 M10V_LOG(77,(uint32_t)dx,(uint32_t)dy,before,p->state.index);
 return p->state.index!=before;
}
#endif
uint32_t m10v_settings_controller_key(m10v_settings_controller *p,uint32_t event){
 uint32_t raw=*(const uint16_t *)(uintptr_t)event,key;
#if !M10V_CAMERA_GR3X
 if(raw==0x30)return catalog_touch(p,*(const uint32_t *)(uintptr_t)(event+4));
#endif
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
#if M10V_SHUTDOWN_ALBUM
 if(p->page==M10V_SETTINGS_SHUTDOWN){
  m10v_settings *s=&p->state;uint32_t count=shutdown_count();
  if(key==M10V_KEY_BACK){((fn1)0x5316ca28u)((uint32_t)(uintptr_t)p);return 1;}
  if(key==M10V_KEY_UP)s->focus=s->focus?s->focus-1:count;
  if(key==M10V_KEY_DOWN)s->focus=s->focus<count?s->focus+1:0;
  if(key==M10V_KEY_OK){
   if(shutdown_save(s->focus)){s->value=s->focus;s->error=0;}
   else s->error=M10V_SETTINGS_SAVE_FAILED;
  }
  m10v_settings_view_shutdown(&p->view,s,count);return 1;
 }
#endif
#if M10V_ADJ_EXTRA_CAMERA
 if(p->page==M10V_SETTINGS_ADJ_EXTRA){
  m10v_settings *s=&p->state;
  s->error=0;
  if(key==M10V_KEY_BACK){
   ((fn1)0x5316ca28u)((uint32_t)(uintptr_t)p);
   return 1;
  }
  if(key==M10V_KEY_UP||key==M10V_KEY_DOWN){
   s->focus=(s->focus+(key==M10V_KEY_UP?3u:1u))&3u;
   s->value=(s->expected>>(8*s->focus))&255u;
  }else if(key==M10V_KEY_LEFT||key==M10V_KEY_RIGHT){
   uint32_t index=0,count=M10V_ADJ_EXTRA_STOCK_CHOICES+sizeof(adj_extra_functions);
   for(uint32_t i=1;i<count;i++)if(adj_function(i)==s->value)index=i;
   index=key==M10V_KEY_LEFT?(index?index-1:count-1):(index+1==count?0:index+1);
   s->value=adj_function(index);
  }else if(key==M10V_KEY_OK){
   uint32_t shift=8*s->focus,old=(s->expected>>shift)&255u;
   if(s->value!=old){
    if(m10v_adj_extra_camera_assign(s->focus+6,s->value))
     s->expected=(s->expected&~(255u<<shift))|(s->value<<shift);
    else s->error=M10V_SETTINGS_SAVE_FAILED;
   }
  }
  m10v_settings_view_adj(&p->view,s);
  return 1;
 }
#endif
 if(p->page==M10V_SETTINGS_ZOOM){
  m10v_zoom_menu_ops z;zoom_ops(&z);
  m10v_zoom_menu_key(&p->zoom,&z,key);
  if(p->zoom.closed)((fn1)0x5316ca28u)((uint32_t)(uintptr_t)p);
  else m10v_settings_view_zoom(&p->view,&p->zoom);
  return 1;
 }
 p->film_touch_start=p->film_touch_last=0;
 m10v_settings_ops o;ops(&o);uint32_t before=p->state.screen;
 if(before==M10V_SETTINGS_CATALOG&&key<=M10V_KEY_OK)p->state.focus=0;
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
#if M10V_SHUTDOWN_ALBUM
 if(route==M10V_SETTINGS_SHUTDOWN_ROUTE&&shutdown_count())return 0x0200004au;
#endif
#if M10V_ADJ_EXTRA_CAMERA
 if(route==M10V_SETTINGS_ADJ_ROUTE)return 0x0200004au;
#endif
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
