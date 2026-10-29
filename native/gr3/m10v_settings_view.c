/* Standalone primitive view. No ImageControl objects, model padding or hooks.
 * ABI evidence: original GR III 2.10 factory 533ad7f0 and constructors below.
 * Every top-level allocation is checked BEFORE invoking its constructor.
 * Remaining stock limitation: child-vector growth and text setters allocate
 * internally without a recoverable OOM contract. This is NOT a hardware proof.
 */
#include "m10v_settings_view.h"
#include "m10v_film_card.h"
#include "m10v_ab.h"
#include "m10v_sd_library.h"
#include "m10v_film_directory.h"
#ifndef M10V_NATIVE_BASE
#define M10V_NATIVE_BASE 0x540b6000u
#endif
/* Ten live bitmaps own portrait artwork; timestamp views allocate none.
 * The reserved heap word is outside the child-widget entries. */
static uint32_t *card_descriptors(const m10v_settings_view *v){return (uint32_t *)(uintptr_t)(v->widgets[M10V_VIEW_HEAP]+M10V_CARD_DESCRIPTOR_OFFSET);}
typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn2)(uint32_t,uint32_t);
typedef uint32_t (*fn3)(uint32_t,uint32_t,uint32_t);
typedef uint32_t (*ctor)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
enum { ROOT, BACKGROUND, TITLE, NAME, FOOTER, ERROR_TEXT,
 FRAME=6, INNER=16, ICON=26, ROW_FRAME=36, ROW_INNER=40, ROW=44, VALUE=48, PAGE=52, COUNT=M10V_VIEW_COUNT };
static uint32_t ptr(const void *p){return (uint32_t)(uintptr_t)p;}
static void visible(uint32_t w,uint32_t yes){((fn2)0x533ad3c0u)(w,yes);}
static void color(uint32_t w,uint32_t c){((fn2)0x53393e00u)(w,c);}
static void caption(uint32_t w,uint32_t id){((fn3)0x53396f80u)(w,id,0);}
static int make(m10v_settings_view *v,uint32_t type,uint32_t x,uint32_t y,uint32_t width,uint32_t height){
 uint32_t size=type==1||type==10?0xf8:type==11?0xf0:0x110;
 uint32_t address=type==1?0x5339199cu:type==10?0x5339a908u:type==11?0x53393d84u:type==17?0x53396944u:0x53390ca0u;
 uint32_t w=((fn1)0x536af2a8u)(size);if(!w)return -1;
 ((ctor)(uintptr_t)address)(w,x,y,width,height);
 v->widgets[v->count++]=w;
 if(type!=1)((fn2)0x533aba64u)(v->widgets[ROOT],w);
 return 0;
}
void m10v_settings_view_destroy(m10v_settings_view *v){
 if(!v||v->count>M10V_VIEW_CAPACITY)return;
 ((fn3)0x5316cde8u)(0,ptr(v->widgets),v->count);
 if(v->widgets[M10V_VIEW_HEAP]){
  uint32_t heap=v->widgets[M10V_VIEW_HEAP];v->widgets[M10V_VIEW_HEAP]=0;
  ((fn1)0x536af2e4u)(heap);
 }
 for(uint32_t i=0;i<M10V_VIEW_CAPACITY;i++)v->widgets[i]=0;
 v->count=0;
}
int m10v_settings_view_create(m10v_settings_view *v){
 if(!v||v->count)return -1;
 for(uint32_t i=0;i<M10V_VIEW_CAPACITY;i++)v->widgets[i]=0;
 if(make(v,1,0,0,720,480)||make(v,11,0,0,720,480)||
    make(v,17,20,12,580,42)||make(v,0,24,58,672,38)||
    make(v,17,20,432,680,40)||make(v,17,20,378,680,40))goto fail;
 for(uint32_t i=0;i<10;i++)if(make(v,11,24+(i%5)*136,96+(i/5)*160,128,156))goto fail;
 for(uint32_t i=0;i<10;i++)if(make(v,11,26+(i%5)*136,98+(i/5)*160,124,152))goto fail;
 for(uint32_t i=0;i<10;i++)if(make(v,10,28+(i%5)*136,100+(i/5)*160,120,M10V_CARD_HEIGHT))goto fail;
 /* Selection rectangles precede text in the child draw order. */
 for(uint32_t i=0;i<4;i++)if(make(v,11,24,84+i*72,672,64))goto fail;
 for(uint32_t i=0;i<4;i++)if(make(v,11,30,90+i*72,660,52))goto fail;
 for(uint32_t i=0;i<4;i++)if(make(v,17,36,90+i*72,300,52))goto fail;
 for(uint32_t i=0;i<4;i++)if(make(v,17,350,90+i*72,330,52))goto fail;
 if(make(v,0,610,18,86,32))goto fail;
 color(v->widgets[BACKGROUND],1);
 for(uint32_t i=0;i<10;i++){
  color(v->widgets[INNER+i],1);
  ((fn2)0x5339aa30u)(v->widgets[ICON+i],1);
  ((fn2)0x5339aa44u)(v->widgets[ICON+i],1);
 }
 /* Same root finalization order as stock5316cd28. */
 uint32_t root=v->widgets[ROOT],*table=(uint32_t *)(uintptr_t)*(uint32_t *)(uintptr_t)root;
 ((fn1)(uintptr_t)table[0x28/4])(root);
 ((fn1)(uintptr_t)table[0x34/4])(root);
 return 0;
fail:m10v_settings_view_destroy(v);return -1;
}
static uint32_t film(const m10v_settings *s,const m10v_settings_ops *o,uint32_t i){
 uint32_t id;
 if(s->screen==M10V_SETTINGS_CATALOG){
  uint32_t index=(s->index/10)*10+i;
  id=index<M10V_SD_DIRECTORY_LIMIT&&o&&o->item?o->item(o->context,index):0;
  if(index<M10V_DIRECTORY_COUNT?id!=m10v_directory[index].id:!M10V_CUSTOM(id))id=0;
  if(id<33)id=0;
 }else id=s->saved.slots[i].film;
 return id&&(id<=M10V_CUSTOM_MAX_ID||M10V_BUILTIN(id))?id:0;
}
static uint32_t valueres(uint32_t row,uint32_t value){
 static const uint16_t first[4]={M10V_VIEW_OFF,M10V_VIEW_YMD,M10V_VIEW_TOP_LEFT,M10V_VIEW_WHITE};
 return row<4&&value<(row?4u:3u)?first[row]+value:M10V_VIEW_OFF;
}
void m10v_settings_view_draw(m10v_settings_view *v,const m10v_settings *s,const m10v_settings_ops *o){
 if(!v||!s||v->count!=COUNT)return;
 uint32_t name_page=s->screen==M10V_SETTINGS_NAME;
 uint32_t ab_page=s->screen==M10V_SETTINGS_AB;
 uint32_t films=s->screen==M10V_SETTINGS_FILMS||s->screen==M10V_SETTINGS_CATALOG;
 uint32_t first=0;
 uint32_t focus=s->screen==M10V_SETTINGS_CATALOG?(s->index-first)%10:s->focus;
 caption(v->widgets[TITLE],films?(M10V_APPENDED_SLOTS?1116+m10v_library_count(&s->saved):M10V_VIEW_FILMS):M10V_VIEW_STAMP);
 caption(v->widgets[FOOTER],s->screen==M10V_SETTINGS_CATALOG?M10V_VIEW_CATALOG_HELP:
   s->screen==M10V_SETTINGS_FILMS?M10V_VIEW_FILM_HELP:
   s->screen==M10V_SETTINGS_VALUE||name_page?M10V_VIEW_VALUE_HELP:M10V_VIEW_STAMP_HELP);
 visible(v->widgets[NAME],0);
 uint32_t error=s->error>=1&&s->error<=4;
 visible(v->widgets[ERROR_TEXT],!films&&error);
 if(error)caption(v->widgets[films?TITLE:ERROR_TEXT],s->error==4?1127:M10V_VIEW_EMPTY+s->error-1);
 ((fn2)0x5339658cu)(v->widgets[TITLE],films&&error?10:31);
 if(s->screen==M10V_SETTINGS_CATALOG){
  for(uint32_t k=0;k<M10V_SLOT_COUNT;k++)if(s->saved.slots[k].film&&!M10V_CUSTOM(s->saved.slots[k].film)&&!m10v_directory_name(s->saved.slots[k].film)){
   caption(v->widgets[FOOTER],1129);break;
  }
 }
 if(films&&!v->widgets[M10V_VIEW_HEAP])v->widgets[M10V_VIEW_HEAP]=((fn1)0x536af2a8u)(M10V_CARD_HEAP_BYTES);
 for(uint32_t i=0;i<10;i++){
  uint32_t id=films?film(s,o,i):0;
  visible(v->widgets[FRAME+i],films&&id);visible(v->widgets[INNER+i],films&&id);
  visible(v->widgets[ICON+i],films&&id);
  /* Rectangle palette6 is yellow; unselected frames use background1. */
  color(v->widgets[FRAME+i],i==focus?6:1);
  uint32_t enabled=0;for(uint32_t k=0;k<M10V_SLOT_COUNT;k++)if(s->saved.slots[k].film==id&&id)enabled=1;
  if(id){
   uint32_t icon=M10V_EXTRA_FILM(id)?M10V_EXTRA_FILM_ICON_FIRST+id-314:M10V_C41(id)?M10V_C41_ICON_FIRST+id-312:M10V_ANIME_E6(id)?M10V_ANIME_E6_ICON_FIRST+id-306:M10V_D76(id)?775+id-M10V_D76_FIRST:id==M10V_5213_ID?774:M10V_STYLE(id)?762+id-M10V_STYLE_FIRST:id==M10V_PIXEL_ID?761:id==M10V_CHAR_ID?755:M10V_CUSTOM(id)?754:670+id;
   if(v->widgets[M10V_VIEW_HEAP]){
    uint32_t *pixels=(uint32_t *)(uintptr_t)(v->widgets[M10V_VIEW_HEAP]+i*M10V_CARD_PIXELS*4);
    if(M10V_CUSTOM(id)){
     char name[24];uint32_t index=first+((s->index-first)/10)*10+i;
     int ok=s->screen==M10V_SETTINGS_CATALOG?
      m10v_sd_camera_catalog_name(index,id,name,sizeof(name)):
      m10v_sd_camera_custom_name(&s->saved,i,name,sizeof(name));
     m10v_film_card_custom(pixels,ok?name:"LUT",i,enabled);
    }else m10v_film_card_render(pixels,id,i,enabled);
    uint32_t *d=card_descriptors(v)+i*2;
    uint32_t *directory=(uint32_t *)(uintptr_t)(v->widgets[M10V_VIEW_HEAP]+M10V_CARD_DIRECTORY_OFFSET);
    d[0]=M10V_CARD_WIDTH|(M10V_CARD_HEIGHT<<16);d[1]=ptr(pixels)/4;
    directory[M10V_CARD_ID(i)-M10V_CARD_FIRST]=ptr(d);
    icon=M10V_CARD_ID(i);
   }
   ((fn2)0x5339a9a0u)(v->widgets[ICON+i],icon);

  }
 }
 visible(v->widgets[PAGE],films);
 if(films){
  uint32_t current=s->index/10+1,total=((s->group>=M10V_DIRECTORY_COUNT&&s->group<=M10V_SD_DIRECTORY_LIMIT?s->group:M10V_DIRECTORY_COUNT)+9)/10,n=0;
  char page[6];
  if(current>=10)page[n++]=(char)('0'+current/10);
  page[n++]=(char)('0'+current%10);page[n++]='/';
  if(total>=10)page[n++]=(char)('0'+total/10);
  page[n++]=(char)('0'+total%10);page[n]=0;
  ((fn2)0x53390ef8u)(v->widgets[PAGE],ptr(page));
 }

 uint32_t values[4]={s->saved.stamp,s->saved.format,s->saved.corner,s->saved.color};
 if(s->screen==M10V_SETTINGS_VALUE&&s->focus<4)values[s->focus]=s->value;
 for(uint32_t i=0;i<4;i++){
  uint32_t w=v->widgets[ROW+i],value=v->widgets[VALUE+i];
  uint32_t selected=!films&&!name_page&&i==s->focus;
  visible(v->widgets[ROW_FRAME+i],selected);visible(v->widgets[ROW_INNER+i],selected);
  color(v->widgets[ROW_FRAME+i],6);color(v->widgets[ROW_INNER+i],1);
  visible(w,!films&&!name_page);visible(value,!films&&!name_page);
  caption(w,M10V_VIEW_MODE+i);caption(value,valueres(i,values[i]));
  /* Text enum10 selects the yellow glyph table; enum6 falls back to WHITE. */
  ((fn2)0x5339658cu)(w,selected&&s->screen!=M10V_SETTINGS_VALUE?10:31);
  ((fn2)0x5339658cu)(value,selected?10:31);
 }
 if(!films&&s->focus<5)caption(v->widgets[TITLE],s->screen==M10V_SETTINGS_VALUE?
   (s->focus==4?M10V_VIEW_EDIT_NAME:M10V_VIEW_EDIT_MODE+s->focus):M10V_VIEW_STAMP);
 if(name_page){
  caption(v->widgets[TITLE],M10V_VIEW_EDIT_NAME);
  visible(v->widgets[ROW],1);
  caption(v->widgets[ROW],s->value?M10V_VIEW_NAME_ON:M10V_VIEW_NAME_OFF);
  ((fn2)0x5339658cu)(v->widgets[ROW],10);
 }
 if(ab_page){
  caption(v->widgets[TITLE],M10V_VIEW_AB_TITLE);caption(v->widgets[FOOTER],M10V_VIEW_AB_HELP);
  visible(v->widgets[NAME],1);
  /* Dynamic name uses the established ASCII widget, including SD names. */
  uint32_t choice=s->focus==1?s->index:s->slot,slot=m10v_ab_slot(choice);
  const char *name=slot<M10V_SLOT_COUNT?m10v_library_name(s->saved.slots[slot].film):m10v_ab_stock_name(choice);
  char custom[24];
  if(slot<M10V_SLOT_COUNT&&M10V_CUSTOM(s->saved.slots[slot].film)&&m10v_sd_camera_custom_name(&s->saved,slot,custom,sizeof(custom)))name=custom;
  ((fn2)0x53390ef8u)(v->widgets[NAME],ptr(name?name:""));
  for(uint32_t i=0;i<4;i++){
   caption(v->widgets[ROW+i],M10V_VIEW_AB_A+i);visible(v->widgets[VALUE+i],i<2);
   if(i<2){uint32_t c=i?s->index:s->slot,k=m10v_ab_slot(c);
    caption(v->widgets[VALUE+i],m10v_ab_caption(c,k<M10V_SLOT_COUNT?s->saved.slots[k].film:0));
   }
  }
 }
 if(s->screen==M10V_SETTINGS_WATERMARK){
  caption(v->widgets[TITLE],M10V_VIEW_STAMP);
  for(uint32_t i=0;i<4;i++){
   visible(v->widgets[ROW+i],i<2);visible(v->widgets[VALUE+i],0);
   visible(v->widgets[ROW_FRAME+i],i<2&&i==s->focus);
   visible(v->widgets[ROW_INNER+i],i<2&&i==s->focus);
   if(i<2)caption(v->widgets[ROW+i],1138+i);
  }
 }else if(s->screen==M10V_SETTINGS_STAMP){caption(v->widgets[TITLE],1138);}
 ((fn1)0x533ad308u)(v->widgets[ROOT]);
}

/* Reuse the existing owned37 widgets; no film allocation on this page. */
extern uint32_t m10v_zoom_title(void);
extern uint32_t m10v_zoom_bits(unsigned);
extern uint32_t m10v_zoom_caption(uint32_t);
void m10v_settings_view_zoom(m10v_settings_view *v,const m10v_zoom_menu *s){
 if(!v||!s||v->count!=COUNT)return;
 uint32_t title=m10v_zoom_title();
 caption(v->widgets[TITLE],title);
 caption(v->widgets[FOOTER],title+(s->editing?4:3));
 visible(v->widgets[NAME],0);visible(v->widgets[PAGE],0);
 visible(v->widgets[ERROR_TEXT],s->error!=0);
 if(s->error)caption(v->widgets[ERROR_TEXT],title+(s->error==2?6:5));
 for(uint32_t i=0;i<10;i++){
  visible(v->widgets[FRAME+i],0);visible(v->widgets[INNER+i],0);visible(v->widgets[ICON+i],0);
 }
 for(uint32_t i=0;i<4;i++){
  uint32_t selected=i<3&&i==s->focus;
  visible(v->widgets[ROW_FRAME+i],selected);visible(v->widgets[ROW_INNER+i],selected);
  color(v->widgets[ROW_FRAME+i],6);color(v->widgets[ROW_INNER+i],1);
  visible(v->widgets[ROW+i],i<3);visible(v->widgets[VALUE+i],i>0&&i<3);
  if(i<3){
   caption(v->widgets[ROW+i],i?title+i:2);
   if(i){unsigned mm=s->editing&&selected?s->editor.value:s->saved.mm[i-1];
    caption(v->widgets[VALUE+i],m10v_zoom_caption(m10v_zoom_bits(mm)));}

   ((fn2)0x5339658cu)(v->widgets[ROW+i],selected&&!s->editing?10:31);
   ((fn2)0x5339658cu)(v->widgets[VALUE+i],selected?10:31);
  }
 }
}
