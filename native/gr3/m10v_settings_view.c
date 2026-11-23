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
#if M10V_ADJ_EXTRA_CAMERA
#include "m10v_adj_extra_camera.h"
#endif
#ifndef M10V_NATIVE_BASE
#define M10V_NATIVE_BASE 0x540b6000u
#endif
/* The catalog owns ten tiles and the page indicator. Other settings do
 * not allocate bitmap storage. The heap word is outside the widget entries. */
_Static_assert((M10V_SD_DIRECTORY_LIMIT+9)/10<=M10V_CARD_MAX_PAGES,"catalog indicator extent");
static uint32_t *card_descriptors(const m10v_settings_view *v){return (uint32_t *)(uintptr_t)(v->widgets[M10V_VIEW_HEAP]+M10V_CARD_DESCRIPTOR_OFFSET);}
typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn2)(uint32_t,uint32_t);
typedef uint32_t (*fn3)(uint32_t,uint32_t,uint32_t);
typedef uint32_t (*ctor)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
enum { ROOT, BACKGROUND, TITLE, NAME, FOOTER, ERROR_TEXT,
 FRAME=6, INNER=16, ICON=26,
#if M10V_MENU_HUB
 ROW=36, VALUE=40, PAGE=44, SELECTED_COUNT=45, THEME=46, FILM_CANCEL=47, FILM_SAVE=48,
#else
 ROW_FRAME=36, ROW_INNER=40, ROW=44, VALUE=48, PAGE=52, SELECTED_COUNT=53,
#endif
 COUNT=M10V_VIEW_COUNT };
static uint32_t ptr(const void *p){return (uint32_t)(uintptr_t)p;}
static void visible(uint32_t w,uint32_t yes){((fn2)0x533ad3c0u)(w,yes);}
static void color(uint32_t w,uint32_t c){((fn2)0x53393e00u)(w,c);}
static void style_row(m10v_settings_view *v,uint32_t i,uint32_t shown,uint32_t selected){
#if M10V_MENU_HUB
 (void)shown;
 (void)selected;
#else
 uint32_t panel=v->widgets[ROW_FRAME+i],marker=v->widgets[ROW_INNER+i];
 visible(panel,selected);visible(marker,shown);color(panel,6);color(marker,2);
#endif
 uint32_t ink=!M10V_MENU_HUB&&selected?28:31;
 ((fn2)0x5339658cu)(v->widgets[ROW+i],ink);
 ((fn2)0x5339658cu)(v->widgets[VALUE+i],ink);
}
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
#if M10V_MENU_HUB
 uint32_t skin=0;
#endif
 if(make(v,1,0,0,720,480)||make(v,11,0,0,720,480))goto fail;
#if M10V_MENU_HUB
 if(make(v,10,0,0,720,480))goto fail;
 skin=v->widgets[--v->count];
#endif
 if(make(v,17,M10V_MENU_HUB?88:20,M10V_MENU_HUB?16:12,M10V_MENU_HUB?560:580,42)||make(v,0,24,58,672,38)||
    make(v,17,20,432,680,40)||make(v,17,20,378,680,40))goto fail;
 for(uint32_t i=0;i<10;i++)if(make(v,11,M10V_FILM_GRID_X-4+(i%5)*M10V_FILM_GRID_DX,M10V_FILM_GRID_Y-4+(i/5)*M10V_FILM_GRID_DY,136,136))goto fail;
 for(uint32_t i=0;i<10;i++)if(make(v,11,M10V_FILM_GRID_X-2+(i%5)*M10V_FILM_GRID_DX,M10V_FILM_GRID_Y-2+(i/5)*M10V_FILM_GRID_DY,132,132))goto fail;
 for(uint32_t i=0;i<10;i++)if(make(v,10,M10V_FILM_GRID_X+(i%5)*M10V_FILM_GRID_DX,M10V_FILM_GRID_Y+(i/5)*M10V_FILM_GRID_DY,M10V_CARD_WIDTH,M10V_CARD_TILE_HEIGHT))goto fail;
 /* Selection rectangles precede text in the child draw order. */
#if !M10V_MENU_HUB
 for(uint32_t i=0;i<4;i++)if(make(v,11,0,84+i*72,720,64))goto fail;
 for(uint32_t i=0;i<4;i++)if(make(v,11,0,147+i*72,720,1))goto fail;
#endif
 for(uint32_t i=0;i<4;i++)if(make(v,17,M10V_MENU_HUB?60:36,
   (M10V_MENU_HUB?87:90)+i*(M10V_MENU_HUB?53:72),M10V_MENU_HUB?280:300,M10V_MENU_HUB?50:52))goto fail;
 for(uint32_t i=0;i<4;i++)if(make(v,17,350,(M10V_MENU_HUB?87:90)+i*(M10V_MENU_HUB?53:72),M10V_MENU_HUB?310:330,M10V_MENU_HUB?50:52))goto fail;
 if(make(v,10,(720-M10V_CARD_DOTS_WIDTH)/2,M10V_MENU_HUB?448:428,M10V_CARD_DOTS_WIDTH,M10V_CARD_DOTS_HEIGHT)||
    make(v,17,494,10,202,38))goto fail;
#if M10V_MENU_HUB
 v->widgets[v->count++]=skin;
 if(make(v,17,460,419,108,45)||make(v,17,578,419,108,45))goto fail;
 ((fn2)0x53396644u)(v->widgets[FILM_CANCEL],1);
 ((fn2)0x53396644u)(v->widgets[FILM_SAVE],1);
 ((fn2)0x5339aa30u)(skin,1);
 ((fn2)0x5339aa44u)(skin,1);
 /* CaptionView f1=2 right aligns, f2=1 vertically centers. */
 for(uint32_t i=0;i<4;i++){
  ((fn2)0x53396644u)(v->widgets[VALUE+i],2);
  ((fn2)0x53396658u)(v->widgets[VALUE+i],1);
  ((fn2)0x53396658u)(v->widgets[ROW+i],1);
 }
#endif
 color(v->widgets[BACKGROUND],M10V_MENU_HUB?DETAIL_BACKGROUND:1);
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
fail:
#if M10V_MENU_HUB
 if(v->count>=2&&skin&&v->count<COUNT)v->widgets[v->count++]=skin;
#endif
 m10v_settings_view_destroy(v);return -1;
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
static void bitmap(const m10v_settings_view *v,uint32_t slot,uint32_t id,uint32_t *pixels,uint32_t width,uint32_t height){
 uint32_t *d=card_descriptors(v)+slot*2;
 uint32_t *directory=(uint32_t *)(uintptr_t)(v->widgets[M10V_VIEW_HEAP]+M10V_CARD_DIRECTORY_OFFSET);
 d[0]=width|(height<<16);d[1]=ptr(pixels)/4;
 directory[id-M10V_CARD_FIRST]=ptr(d);
}
#if M10V_MENU_HUB
#include "m10v_settings_controller.h"
#include "m10v_menu_hub_view.inc"
#endif
void m10v_settings_view_draw(m10v_settings_view *v,const m10v_settings *s,const m10v_settings_ops *o){
 if(!v||!s||v->count!=COUNT)return;
 uint32_t name_page=s->screen==M10V_SETTINGS_NAME;
 uint32_t ab_page=s->screen==M10V_SETTINGS_AB;
 uint32_t catalog=s->screen==M10V_SETTINGS_CATALOG;
 uint32_t roll_catalog=catalog&&s->slot==M10V_ROLL_CATALOG_MODE;
 uint32_t films=s->screen==M10V_SETTINGS_FILMS||catalog;
#if M10V_MENU_HUB
 uint32_t film_detail=s->screen==M10V_SETTINGS_FILM_DETAIL;
 uint32_t film_editing=film_detail&&(s->value&M10V_FILM_DETAIL_EDIT);
#endif
#if M10V_MENU_HUB
 color(v->widgets[BACKGROUND],DETAIL_BACKGROUND);
#endif
 uint32_t focus=catalog?(s->focus==M10V_CATALOG_TOUCH_FOCUS_HIDDEN?10:s->index%10):s->focus;
 uint32_t error=s->error>=1&&s->error<=4;
 visible(v->widgets[TITLE],M10V_MENU_HUB||!catalog||error);
 visible(v->widgets[FOOTER],!catalog);
 visible(v->widgets[SELECTED_COUNT],catalog&&!roll_catalog);
#if M10V_MENU_HUB
 visible(v->widgets[THEME],m10v_settings_view_theme(v->widgets[THEME],
   films?0:name_page?1:s->screen==M10V_SETTINGS_WATERMARK?2:film_detail?m10v_film_detail_rows(s):4,
   name_page?0:s->focus,film_editing?3:ab_page));
 visible(v->widgets[FILM_CANCEL],film_editing);visible(v->widgets[FILM_SAVE],film_editing);
 const uint32_t title_rect[4]={catalog?70:88,catalog?5:16,catalog?408:560,42};
 ((void (*)(uint32_t,const uint32_t *))0x533ab548u)(v->widgets[TITLE],title_rect);
 if(catalog&&!error)caption(v->widgets[TITLE],M10V_VIEW_FILMS);
#endif
 if(catalog)caption(v->widgets[SELECTED_COUNT],1116+m10v_library_count(&s->saved));
 if(!catalog){
  caption(v->widgets[TITLE],films?M10V_VIEW_FILMS:M10V_VIEW_STAMP);
  caption(v->widgets[FOOTER],films?M10V_VIEW_FILM_HELP:
    s->screen==M10V_SETTINGS_VALUE||name_page?M10V_VIEW_VALUE_HELP:M10V_VIEW_STAMP_HELP);
 }
 visible(v->widgets[NAME],0);
 visible(v->widgets[ERROR_TEXT],!films&&error);
 if(error)caption(v->widgets[films?TITLE:ERROR_TEXT],s->error==4?1127:M10V_VIEW_EMPTY+s->error-1);
 ((fn2)0x5339658cu)(v->widgets[TITLE],films&&error?10:31);
 if(films&&!v->widgets[M10V_VIEW_HEAP])v->widgets[M10V_VIEW_HEAP]=((fn1)0x536af2a8u)(M10V_CARD_HEAP_BYTES);
 for(uint32_t i=0;i<10;i++){
  uint32_t id=films?film(s,o,i):0;
  visible(v->widgets[FRAME+i],films&&id);visible(v->widgets[INNER+i],films&&id);
  visible(v->widgets[ICON+i],films&&id);
  /* Rectangle palette6 is yellow; unselected frames use background1. */
  color(v->widgets[FRAME+i],i==focus?6:1);
  uint32_t enabled=0;for(uint32_t k=0;!roll_catalog&&k<M10V_SLOT_COUNT;k++)if(s->saved.slots[k].film==id&&id)enabled=1;
  if(id){
   uint32_t icon=id==M10V_MARLBORO_ID?M10V_MARLBORO_ICON:M10V_THREE_FILM(id)?M10V_THREE_FILM_ICON(id):M10V_LEICA(id)?M10V_LEICA_ICON(id):M10V_FOUR_LOOKS(id)?M10V_FOUR_LOOKS_ICON(id):M10V_EXTRA_FILM(id)?M10V_EXTRA_FILM_ICON(id):M10V_C41(id)?M10V_C41_ICON(id):M10V_ANIME_E6(id)?M10V_ANIME_E6_ICON_FIRST+id-306:M10V_D76(id)?775+id-M10V_D76_FIRST:id==M10V_5213_ID?774:M10V_STYLE(id)?762+id-M10V_STYLE_FIRST:id==M10V_PIXEL_ID?761:id==M10V_CHAR_ID?755:M10V_CUSTOM(id)?754:670+id;
   if(v->widgets[M10V_VIEW_HEAP]){
    uint32_t *pixels=(uint32_t *)(uintptr_t)(v->widgets[M10V_VIEW_HEAP]+i*M10V_CARD_TILE_PIXELS*4);
    char custom[24];
    const char *name=0;
    int rendered;
    if(M10V_CUSTOM(id)){
     uint32_t index=(s->index/10)*10+i;
     int ok=catalog?m10v_sd_camera_catalog_name(index,id,custom,sizeof(custom)):
      m10v_sd_camera_custom_name(&s->saved,i,custom,sizeof(custom));
     name=ok?custom:"LUT";
     rendered=m10v_film_card_custom(pixels,name,i,enabled);
    }else{
     if(catalog)name=m10v_directory[(s->index/10)*10+i].name;
     rendered=m10v_film_card_render(pixels,id,i,enabled);
    }
    if(!rendered){
     m10v_film_card_label(pixels,catalog?name:0,i==focus);
     icon=M10V_CARD_ID(i);
     bitmap(v,i,icon,pixels,M10V_CARD_WIDTH,M10V_CARD_TILE_HEIGHT);
    }
   }
   ((fn2)0x5339a9a0u)(v->widgets[ICON+i],icon);

  }
 }
 uint32_t heap=v->widgets[M10V_VIEW_HEAP];
 if(catalog&&heap){
  uint32_t total=((s->group>=M10V_DIRECTORY_COUNT&&s->group<=M10V_SD_DIRECTORY_LIMIT?s->group:M10V_DIRECTORY_COUNT)+9)/10;
  uint32_t *dots=(uint32_t *)(uintptr_t)(heap+M10V_CARD_DOTS_OFFSET);
  m10v_film_card_dots(dots,s->index/10,total);
  bitmap(v,M10V_CARD_COUNT,M10V_CARD_DOTS_ID,dots,M10V_CARD_DOTS_WIDTH,M10V_CARD_DOTS_HEIGHT);
  ((fn2)0x5339a9a0u)(v->widgets[PAGE],M10V_CARD_DOTS_ID);
 }
 visible(v->widgets[PAGE],catalog&&heap);

#if M10V_MENU_HUB
 if(film_detail&&s->slot<M10V_SLOT_COUNT){
  uint32_t rows=m10v_film_detail_rows(s);
  const m10v_slot *film=&s->saved.slots[s->slot];
  const m10v_film_effects *fx=&s->saved.effects[s->slot];
  uint32_t values[3]={film->grain,m10v_film_fx_tagged(fx)?fx->grain_size:film->grain?film->grain-1u:0,film->halo_gain};
  if(film_editing&&s->focus<3)values[s->focus]=s->value&255u;
  static const uint16_t names[3]={1164,1250,862};
  static const uint16_t grain[4]={973,1179,1176,1180};
  static const uint16_t sizes[3]={1172,1173,1174};
  caption(v->widgets[TITLE],1249);
  visible(v->widgets[FOOTER],!film_editing);
  caption(v->widgets[FOOTER],M10V_VIEW_STAMP_HELP);
  if(film_editing){
   caption(v->widgets[FILM_CANCEL],1260);caption(v->widgets[FILM_SAVE],1248);
   ((fn2)0x5339658cu)(v->widgets[FILM_SAVE],28);
  }
  const uint32_t name_rect[4]={407,19,278,42};
  char custom[24];
  const char *name=m10v_library_name(film->film);
  if(M10V_CUSTOM(film->film)&&m10v_sd_camera_custom_name(&s->saved,s->slot,custom,sizeof(custom)))name=custom;
  if(name){
   ((void (*)(uint32_t,const uint32_t *))0x533ab548u)(v->widgets[NAME],name_rect);
   ((fn2)0x53390ef8u)(v->widgets[NAME],ptr(name));
   visible(v->widgets[NAME],1);
  }
  for(uint32_t i=0;i<4;i++){
   visible(v->widgets[ROW+i],i<rows);visible(v->widgets[VALUE+i],i<rows);
   if(i>=rows)continue;
   style_row(v,i,1,i==s->focus);
   caption(v->widgets[ROW+i],names[i]);
   caption(v->widgets[VALUE+i],i==2?1251+values[i]:i==1?sizes[values[i]]:grain[values[i]]);
  }
  ((fn1)0x533ad308u)(v->widgets[ROOT]);return;
 }
#endif

 uint32_t values[4]={s->saved.stamp,s->saved.format,s->saved.corner,s->saved.color};
 if(s->screen==M10V_SETTINGS_VALUE&&s->focus<4)values[s->focus]=s->value;
 for(uint32_t i=0;i<4;i++){
  uint32_t w=v->widgets[ROW+i],value=v->widgets[VALUE+i];
  uint32_t selected=!films&&!name_page&&i==s->focus;
  style_row(v,i,!films&&!name_page,selected);
  visible(w,!films&&!name_page);visible(value,!films&&!name_page);
  caption(w,M10V_VIEW_MODE+i);caption(value,valueres(i,values[i]));
 }
 if(!films&&s->focus<5)caption(v->widgets[TITLE],s->screen==M10V_SETTINGS_VALUE?
   (s->focus==4?M10V_VIEW_EDIT_NAME:M10V_VIEW_EDIT_MODE+s->focus):M10V_VIEW_STAMP);
 if(name_page){
  caption(v->widgets[TITLE],M10V_VIEW_EDIT_NAME);
  visible(v->widgets[ROW],1);
  caption(v->widgets[ROW],s->value?M10V_VIEW_NAME_ON:M10V_VIEW_NAME_OFF);
  style_row(v,0,1,1);
 }
 if(ab_page){
  caption(v->widgets[TITLE],M10V_VIEW_AB_TITLE);caption(v->widgets[FOOTER],M10V_VIEW_AB_HELP);
#if !M10V_MENU_HUB
  visible(v->widgets[NAME],1);
  /* Dynamic name uses the established ASCII widget, including SD names. */
  uint32_t choice=s->focus==1?s->index:s->slot,slot=m10v_ab_slot(choice);
  const char *name=slot<M10V_SLOT_COUNT?m10v_library_name(s->saved.slots[slot].film):m10v_ab_stock_name(choice);
  char custom[24];
  if(slot<M10V_SLOT_COUNT&&M10V_CUSTOM(s->saved.slots[slot].film)&&m10v_sd_camera_custom_name(&s->saved,slot,custom,sizeof(custom)))name=custom;
  ((fn2)0x53390ef8u)(v->widgets[NAME],ptr(name?name:""));
#endif
  for(uint32_t i=0;i<4;i++){
   caption(v->widgets[ROW+i],M10V_VIEW_AB_A+i);visible(v->widgets[VALUE+i],i<2);
   if(i<2){uint32_t c=i?s->index:s->slot,k=m10v_ab_slot(c);
    uint32_t film=k<M10V_SLOT_COUNT?s->saved.slots[k].film:0;
    caption(v->widgets[VALUE+i],m10v_ab_caption(c,film));
#if M10V_MENU_HUB
    if(s->focus==i&&M10V_CUSTOM(film)){
     char custom[24];
     if(m10v_sd_camera_custom_name(&s->saved,k,custom,sizeof(custom))){
      const uint32_t rect[4]={350,87+i*53,310,50};
      uint32_t name=v->widgets[NAME];
      ((void (*)(uint32_t,const uint32_t *))0x533ab548u)(name,rect);
      ((fn2)0x53390ef8u)(name,ptr(custom));
      visible(name,1);visible(v->widgets[VALUE+i],0);
     }
    }
#endif
   }
  }
 }
 if(s->screen==M10V_SETTINGS_WATERMARK){
  caption(v->widgets[TITLE],M10V_VIEW_STAMP);
  for(uint32_t i=0;i<4;i++){
   visible(v->widgets[ROW+i],i<2);visible(v->widgets[VALUE+i],0);
   style_row(v,i,i<2,i<2&&i==s->focus);
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
#if M10V_MENU_HUB
 visible(v->widgets[FILM_CANCEL],0);visible(v->widgets[FILM_SAVE],0);
 visible(v->widgets[THEME],m10v_settings_view_theme(v->widgets[THEME],3,s->focus,0));
#endif
 visible(v->widgets[TITLE],1);visible(v->widgets[FOOTER],1);
 uint32_t title=m10v_zoom_title();
 caption(v->widgets[TITLE],title);
 caption(v->widgets[FOOTER],title+(s->editing?4:3));
 visible(v->widgets[NAME],0);visible(v->widgets[PAGE],0);visible(v->widgets[SELECTED_COUNT],0);
 visible(v->widgets[ERROR_TEXT],s->error!=0);
 if(s->error)caption(v->widgets[ERROR_TEXT],title+(s->error==2?6:5));
 for(uint32_t i=0;i<10;i++){
  visible(v->widgets[FRAME+i],0);visible(v->widgets[INNER+i],0);visible(v->widgets[ICON+i],0);
 }
 for(uint32_t i=0;i<4;i++){
  uint32_t selected=i<3&&i==s->focus;
  style_row(v,i,i<3,selected);
  visible(v->widgets[ROW+i],i<3);visible(v->widgets[VALUE+i],i>0&&i<3);
  if(i<3){
   caption(v->widgets[ROW+i],i?title+i:2);
   if(i){unsigned mm=s->editing&&selected?s->editor.value:s->saved.mm[i-1];
    caption(v->widgets[VALUE+i],m10v_zoom_caption(m10v_zoom_bits(mm)));}
  }
 }
}

#if M10V_SHUTDOWN_ALBUM
void m10v_settings_view_shutdown(m10v_settings_view *v,const m10v_settings *s,uint32_t count){
 if(!v||!s||v->count!=COUNT)return;
#if M10V_MENU_HUB
 visible(v->widgets[FILM_CANCEL],0);visible(v->widgets[FILM_SAVE],0);
 visible(v->widgets[THEME],m10v_settings_view_theme(v->widgets[THEME],count+1,s->focus,0));
#endif
 visible(v->widgets[TITLE],1);visible(v->widgets[FOOTER],1);
 caption(v->widgets[TITLE],1230);
 caption(v->widgets[FOOTER],M10V_VIEW_STAMP_HELP);
 visible(v->widgets[NAME],0);visible(v->widgets[PAGE],0);visible(v->widgets[SELECTED_COUNT],0);
 visible(v->widgets[ERROR_TEXT],s->error!=0);
 if(s->error)caption(v->widgets[ERROR_TEXT],M10V_VIEW_FAILED);
 for(uint32_t i=0;i<10;i++){
  visible(v->widgets[FRAME+i],0);visible(v->widgets[INNER+i],0);visible(v->widgets[ICON+i],0);
 }
 for(uint32_t i=0;i<4;i++){
  style_row(v,i,i<=count,i<=count&&i==s->focus);
  visible(v->widgets[ROW+i],i<=count);visible(v->widgets[VALUE+i],i<=count&&i==s->value);
  caption(v->widgets[ROW+i],1231+i);caption(v->widgets[VALUE+i],1235);
 }
}
#endif

#if M10V_ADJ_EXTRA_CAMERA
static uint32_t adj_value_resource(uint32_t id){
 if(id&&id<=M10V_ADJ_EXTRA_STOCK_MAX){
  uint32_t root=((uint32_t (*)(void))0x5320ad88u)();
  uint32_t translator=((fn1)0x5320b67cu)(root);
  return ((fn2)0x53292810u)(translator,id);
 }
 if(id==20)return 1200;
#if M10V_BORDER_ENABLED
 if(id==M10V_ADJ_EXTRA_BORDER)return 1155;
#endif
 return id>=24&&id<=27 ? 1196+id-24 : M10V_VIEW_OFF;
}
void m10v_settings_view_adj(m10v_settings_view *v,const m10v_settings *s){
 if(!v||!s||v->count!=COUNT)return;
#if M10V_MENU_HUB
 visible(v->widgets[FILM_CANCEL],0);visible(v->widgets[FILM_SAVE],0);
 visible(v->widgets[THEME],m10v_settings_view_theme(v->widgets[THEME],4,s->focus,0));
#endif
 visible(v->widgets[TITLE],1);visible(v->widgets[FOOTER],1);
 caption(v->widgets[TITLE],1191);
 caption(v->widgets[FOOTER],1201);
 visible(v->widgets[NAME],0);visible(v->widgets[PAGE],0);visible(v->widgets[SELECTED_COUNT],0);
 visible(v->widgets[ERROR_TEXT],s->error!=0);
 if(s->error)caption(v->widgets[ERROR_TEXT],M10V_VIEW_FAILED);
 for(uint32_t i=0;i<10;i++){
  visible(v->widgets[FRAME+i],0);visible(v->widgets[INNER+i],0);visible(v->widgets[ICON+i],0);
 }
 for(uint32_t i=0;i<4;i++){
  uint32_t selected=i==s->focus;
  style_row(v,i,1,selected);
  visible(v->widgets[ROW+i],1);visible(v->widgets[VALUE+i],1);
  caption(v->widgets[ROW+i],1192+i);
  caption(v->widgets[VALUE+i],adj_value_resource(selected?s->value:(s->expected>>(8*i))&255u));
 }
}
#endif
