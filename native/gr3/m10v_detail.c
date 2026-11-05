/* Stock ImageControlDetailController adapter. No private allocator, shadow
 * settings or stock parameter storage. Callbacks follow stock immediate update
 * semantics; journal failure restores the visible slider to committed state. */
#include "m10v_tone.h"
#include "m10v_library.h"
#include "m10v_debug.h"
#ifndef M10V_ISP_NATIVE_GRAIN_MODE
#define M10V_ISP_NATIVE_GRAIN_MODE 0
#endif
extern const uint32_t m10v_detail_tables, m10v_detail_common_tables, m10v_detail_red_tables, m10v_detail_phoenix_tables, m10v_detail_charmera_tables, m10v_detail_pixel_tables;
typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn2)(uint32_t,uint32_t);
typedef void (*text_fn)(uint32_t,uint32_t,const char *);
static int ram(uint32_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p;}
static int slot(uint32_t ui){

 if(!ram(ui,0x1a0))return -1;
 const uint8_t *m=(const uint8_t *)(uintptr_t)ui;
 if(m[0x199]>2||m[0x19a]>=M10V_TONE_CHOICES||m[0x19b]||m[0x19d])return -1;
 for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)if(m[0x198]==m10v_slot_tone(i))return (int)i;
 return -1;
}
static int load(uint32_t ui,m10v_library_state *s){
 int i=slot(ui);if(i<0)return -1;
 if(m10v_camera_library_load(s)<0)return -1;
 return m10v_library_valid(s)?i:-1;
}
uint32_t m10v_detail_table(uint32_t ui){
 m10v_library_state s;
 int i=load(ui,&s);if(i<0)return 0x53b3488cu;
 uint32_t film=s.slots[i].film;
 return (uint32_t)(uintptr_t)(film==290?&m10v_detail_pixel_tables:film==M10V_CHAR_ID?&m10v_detail_charmera_tables:film==67?&m10v_detail_phoenix_tables:m10v_800t_halation_film(film)?&m10v_detail_tables:film==68?&m10v_detail_red_tables:&m10v_detail_common_tables);
}
static uint32_t value(const m10v_library_state *s,uint32_t target,uint32_t field){
 const m10v_slot *v=&s->slots[target];
#if M10V_PURE_ISP_EFFECTS
 const m10v_film_effects *e=&s->effects[target];
 if(field>=5&&field<=8){
  if(!m10v_film_fx_tagged(e))return 0;
  if(field==5)return e->leak_gain;
  if(field==6)return e->leak_position;
  if(field==7)return e->leak_spread;
  return e->leak_variation&3u;
 }
#endif
 if(field==4)return v->halo_profile==M10V_HALO_SPILL?1:v->halo_profile==M10V_HALO_STREAK?2:0;
 if(field==11)return s->effects[target].reserved[1];
 if(field==0)return v->halo_gain;if(field==1)return v->halo_spread;
 if(field==2)return v->halo_threshold;if(field==3)return v->grain;
 return field==10?s->effects[target].film_exposure:0;
}
static uint32_t limit(uint32_t field){
 static const uint8_t limits[13]={8,8,8,3,2,3,4,2,3,0,2,3,3};return limits[field];
}
uint32_t m10v_detail_control(uint32_t op,uint32_t ui,uint32_t arg){
 /* Native rows already use this rectangle. Only resize when an EI row
  * needs extra room or a recycled view still carries an EI rectangle. */
 if(op==8){
  if(!ram(ui,0x1a0))return 0;
  uint32_t list=*(const uint32_t *)(uintptr_t)(ui+0x194);if(!ram(list,4))return 0;
  uint32_t row=((fn2)0x53394758u)(list,arg&65535);if(!ram(row,0xf8))return 0;
  const uint32_t field=arg>>16;
  for(unsigned i=0;i<2;++i){
   uint32_t view=*(const uint32_t *)(uintptr_t)(row+0xf4-4*i);
   if(!ram(view,0x64))continue;
   uint32_t width=i?(field==29?64u:40u):(field==28?60u:40u);
   const uint32_t *bounds=(const uint32_t *)(uintptr_t)(view+0x20);
   if(bounds[0]==50&&bounds[1]==10&&bounds[2]==width&&bounds[3]==40)continue;
   const uint32_t rect[4]={50,10,width,40};
   ((void (*)(uint32_t,const uint32_t *))0x533ab548u)(view,rect);
  }
  return 1;
 }
 m10v_library_state s;int target=load(ui,&s);if(target<0)return 0;
 uint32_t field=arg,v=arg&255;
 if(op==2)field=arg>>8;
 if(op==3)field=arg>>16;
 if(op==4)field=((fn1)0x531b01d0u)(ui)-18;
 uint32_t film=s.slots[target].film;
 if(op==9)return film==67?1:2;
 uint32_t special=m10v_800t_halation_film(film)||film==67;
 if(op!=7&&(field>11||field==9||(field==11&&film!=M10V_CHAR_ID)||
    (field>=5&&field<=8&&!M10V_PURE_ISP_EFFECTS)||
    (field==4&&(!M10V_UNIVERSAL_HALATION||special))||
    (field==3&&!M10V_PURE_ISP_EFFECTS&&(!M10V_ISP_NATIVE_GRAIN_MODE||film==M10V_CHAR_ID||film==M10V_PIXEL_ID))||
    (field<3&&!M10V_UNIVERSAL_HALATION&&!special)||(field==10&&film!=68&&film!=67)))return 0;
 if(op==4){
  if(field>=10){
   m10v_library_init(&s);
   return s.slots[target].film==film?value(&s,(uint32_t)target,field):0;
  }
  s.slots[target].grain=0;
  m10v_slot_default_halation(&s.slots[target]);
  s.effects[target]=(m10v_film_effects){0};
  return value(&s,(uint32_t)target,field);
 }
 const m10v_slot *old=&s.slots[target];
 if(op==1)return value(&s,(uint32_t)target,field);
 if(op==2||op==7){
  if(op==2&&(v>limit(field)||(field==10&&film==67&&v>1)))return 0;
  uint32_t previous=op==2?value(&s,(uint32_t)target,field):0;
  int result;
  if(op==2&&field==6)M10V_EXIT_LOG(312,ui,previous,v,s.sequence);
  if(op==2&&field==3)M10V_EXIT_LOG(314,ui,previous,v,s.sequence);
  if(op==7)result=m10v_camera_library_reset(&s,(uint32_t)target);
  else if(op==2&&M10V_UNIVERSAL_HALATION&&field==4){
   uint32_t profile=v==1?M10V_HALO_SPILL:v==2?M10V_HALO_STREAK:M10V_HALO_OFF;
   uint32_t gain=old->halo_gain;if(v&&!gain)gain=3;
   result=m10v_camera_library_halation(&s,(uint32_t)target,gain,old->halo_spread,old->halo_threshold,profile);
  }
  else if(M10V_PURE_ISP_EFFECTS&&(field==3||(field>=5&&field<=8)))
   result=m10v_camera_library_effects(&s,(uint32_t)target,field==3?12u:field+3u,v);
  else if(field>=10)result=m10v_camera_library_effects(&s,(uint32_t)target,field==11?7u:6u,v);
  else {
   uint32_t gain=old->halo_gain,spread=old->halo_spread,threshold=old->halo_threshold,grain=M10V_ISP_NATIVE_GRAIN_MODE?old->grain:0,soft=old->soft;
   if(field==0)gain=v;else if(field==1)spread=v;else if(field==2)threshold=v;else if(field==3)grain=v;else soft=v;
   if(m10v_800t_halation_film(film)&&!M10V_UNIVERSAL_HALATION)result=m10v_camera_library_detail(&s,(uint32_t)target,gain,spread,threshold,grain,soft);
   else if(field<3)result=m10v_camera_library_halation(&s,(uint32_t)target,gain,spread,threshold,
       M10V_UNIVERSAL_HALATION&&special?M10V_HALO_SPILL:old->halo_profile);
   else result=m10v_camera_library_texture(&s,(uint32_t)target,grain,soft);
  }
  if(op==2&&field==6)M10V_EXIT_LOG(313,ui,v,(uint32_t)result,s.sequence);
  if(op==2&&field==3)M10V_EXIT_LOG(315,ui,v,(uint32_t)result,s.sequence);
  M10V_LOG(70,18+field,previous,v,((uint32_t)target<<16)|(uint16_t)result);
  if(result){
   uint32_t slider=*(const uint32_t *)(uintptr_t)(ui+0x164),caption=*(const uint32_t *)(uintptr_t)(ui+0x160);
   if(op==2&&ram(slider,4))((fn2)0x5339ee0cu)(slider,previous);
   if(ram(caption,4))((uint32_t (*)(uint32_t,uint32_t,uint32_t))0x53396f80u)(caption,824,0);
   return 0;
  }
  return 1;
 }
 if(op==3){
  /* The official row setter takes 8-bit ASCII and converts it to UTF16.
   * The row owns a LabelView. The CaptionView message setter used for the
   * selected-row caption would overwrite the label's UTF16 pointer here.
   * Keep its original 40px icon + 40px value layout. Full Chinese names are
   * provided by the selected-row caption, never repeated in the FN rail.
   * Each field uses a visually checked, distinct stock 40x40 icon: glow,
   * waves, histogram, grain and exposure compensation. No resource directory is modified.
   * Enum values retain the slider's exact 0-based range; RED uses EI125/64/250.
   * Its three-digit value alone gets 60px, still inside the native 120px rail. */
  static const uint16_t icons[13]={484,473,398,478,484,484,648,473,398,0,648,648,648};
  v=value(&s,(uint32_t)target,field);char text[4]={(char)('0'+v),0,0,0};
  static const char leak_position[5][4]={"L","U","R","D","Rnd"};
  if(field==10){text[0]=v==1?'6':v==2?'2':'1';text[1]=v==1?'4':v==2?'5':'2';text[2]=v==1?0:v==2?'0':'5';}
  if(field==10&&film==67){text[0]=v?'1':'2';text[1]=v?'2':'0';text[2]='0';}
  uint32_t list=*(const uint32_t *)(uintptr_t)(ui+0x194);if(!ram(list,4))return 0;
  uint32_t row=((fn2)0x53394758u)(list,arg&65535);if(!ram(row,4))return 0;
  if(field==11){
   ((uint32_t (*)(uint32_t,uint32_t,uint32_t))0x5339e274u)(row,M10V_SD_LIBRARY?755:749,(M10V_SD_LIBRARY?756:750)+v);return 1;
  }
  ((text_fn)0x5339e2f8u)(row,icons[field],field==6&&v<5?leak_position[v]:text);return 1;
 }
 return 0;
}
