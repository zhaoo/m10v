/* GR III target adapter: visible order is the twelve factory looks, Custom1,
 * Custom2, then up to ten enabled films. Model APIs keep their separate dynamic-tone
 * domain; Custom1/2 are bank selectors, never tone IDs written to a frame. */
#include "m10v_tone.h"
#include "m10v_debug.h"
#include "m10v_library.h"
#include "m10v_roll_device.h"
#ifndef M10V_NATIVE_BASE
#define M10V_NATIVE_BASE 0x540b6000u
#endif
typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn2)(uint32_t,uint32_t);
typedef uint32_t (*fn4)(uint32_t,uint32_t,uint32_t,uint32_t);
extern uint32_t m10v_menu_name(uint32_t,uint32_t);
extern uint32_t m10v_menu_icon(uint32_t,uint32_t);
extern uint32_t m10v_menu_value_name(uint32_t,uint32_t);
extern uint32_t m10v_menu_value_icon(uint32_t,uint32_t);
static uint8_t *model(void){return (uint8_t *)(uintptr_t)((fn1)0x5320ba9cu)(((fn1)0x5320ad88u)(0));}
static int shooting(const uint8_t *m){return (uintptr_t)m==0x55068200u&&m[0x1b]==0;}
static uint32_t row_tone(uint32_t row){return row<12?0:row<14?23+row-12:row<m10v_camera_library_menu_index()?25+row-14:128;}
uint32_t m10v_tone_menu_index(uint32_t address,uint32_t row){
 if(shooting((const uint8_t *)(uintptr_t)address)&&row>=12&&row<m10v_camera_library_menu_index())return row_tone(row);
 return ((fn2)0x532c2c80u)(address,row);
}
uint32_t m10v_tone_menu_menu_name(uint32_t translator,uint32_t value){
 uint8_t *m=model();
 return shooting(m)&&!m[0x1d]?m10v_menu_name(translator,row_tone(m10v_camera_library_shooting_count()+(value==23?1:2))):m10v_menu_value_name(translator,value);
}
uint32_t m10v_tone_menu_menu_icon(uint32_t translator,uint32_t value){
 uint8_t *m=model();
 return shooting(m)&&!m[0x1d]?m10v_menu_icon(translator,row_tone(m10v_camera_library_shooting_count()+(value==23?1:2))):m10v_menu_value_icon(translator,value);
}
uint32_t m10v_tone_menu_adj_name(uint32_t translator,uint32_t value){
 return shooting(model())?m10v_menu_name(translator,row_tone(m10v_camera_library_shooting_count()+(value==23?0:1))):m10v_menu_value_name(translator,value);
}
uint32_t m10v_tone_menu_adj_icon(uint32_t translator,uint32_t value){
 return shooting(model())?m10v_menu_icon(translator,row_tone(m10v_camera_library_shooting_count()+(value==23?0:1))):m10v_menu_value_icon(translator,value);
}
static uint32_t matches(uint32_t address,uint32_t tone,uint32_t row,uint32_t bank){
 if(bank)return (bank==1&&row==12)||(bank==2&&row==13);
 if(row==12||row==13||row>=m10v_camera_library_menu_index())return 0;
 return row<12?((fn2)0x532c2c80u)(address,row)==tone:row_tone(row)==tone;
}
uint32_t m10v_tone_menu_menu_matches(uint32_t controller,uint32_t tone,uint32_t row,uint32_t bank){
 uint8_t *m=model();
 if(shooting(m)&&!m[0x1d])return matches((uint32_t)(uintptr_t)m,tone,row,bank);
 return ((fn4)(M10V_NATIVE_BASE+0xc0u))(controller,tone,row,bank);
}
uint32_t m10v_tone_menu_adj_matches(uint32_t controller,uint32_t row){
 uint8_t *m=model();
 if(!shooting(m))return ((fn2)(M10V_NATIVE_BASE+0xd0u))(controller,row);
 uint32_t address=(uint32_t)(uintptr_t)m;
 return matches(address,((fn1)0x532bd6b4u)(address),row,((fn1)0x532bd6d4u)(address));
}
#if M10V_PHOTO_RECIPE
extern void m10v_camera_library_adj_tone_set(uint32_t);
extern uint32_t m10v_camera_library_adj_tone(void);
/* ADJ's +0x28 callback runs on highlight, including initial selection.
 * Keep its candidate in the UI owner. The real OK callback commits below. */
static int adj_scope(uint32_t c){
    return c>=0x55000000u&&c<=0x80000000u-0x274u&&!(c&3u)&&
        *(const uint32_t *)(uintptr_t)c==0x53b394e0u&&
        *(const uint32_t *)(uintptr_t)(c+0x124)==0x02000000u&&
        *(const uint8_t *)(uintptr_t)(c+0x270)==0;
}
#endif
static uint32_t adj_commit_row(uint32_t controller,uint32_t row,uint8_t *m){
 if(shooting(m)&&m10v_roll_device_locked())return 0;
 if(shooting(m)){
  if(row==12||row==13)row=m10v_camera_library_shooting_count()+row-12;
  else if(row>=14&&row<m10v_camera_library_menu_index())row-=2;
 }
 return ((fn2)(M10V_NATIVE_BASE+0xe0u))(controller,row);
}
uint32_t m10v_tone_menu_adj_select(uint32_t controller,uint32_t row){
 uint8_t *m=model();
 if(shooting(m)&&m10v_roll_device_locked()){
#if M10V_PHOTO_RECIPE
  m10v_camera_library_adj_tone_set(0);
#endif
  return 0;
 }
#if M10V_PHOTO_RECIPE
 M10V_LOG(380,controller,row,(uint32_t)(uintptr_t)m,adj_scope(controller));
 if(adj_scope(controller)&&shooting(m)){
  uint32_t tone=m10v_tone_menu_index((uint32_t)(uintptr_t)m,row);
  if(row!=12&&row!=13&&row<m10v_camera_library_menu_index()&&m10v_tone_valid(tone)){
   m10v_camera_library_adj_tone_set(tone);
   M10V_LOG(381,controller,row,tone,1);return 0;
  }
  m10v_camera_library_adj_tone_set(0);
  M10V_LOG(381,controller,row,tone,0);
  /* Factory Custom1/2 select a backing bank. Leave their native handling
   * to confirmation rather than showing an unrelated virtual look. */
  return 0;
 }
#endif
 return adj_commit_row(controller,row,m);
}
#if M10V_PHOTO_RECIPE
extern int m10v_debug_log(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
uint32_t m10v_tone_menu_adj_confirm(uint32_t controller){
 if(adj_scope(controller)&&((fn2)0x531a2820u)(controller,
      *(const uint8_t *)(uintptr_t)(controller+0x1f4))==12){
  uint32_t list=*(const uint32_t *)(uintptr_t)(controller+0x1f0);
  uint8_t *m=model();
  if(list>=0x55000000u&&list<=0x80000000u-0x80u&&!(list&3u)&&shooting(m)){
   uint32_t row=((fn1)0x53394820u)(list);
   uint32_t previous=m10v_camera_library_adj_tone();
   if(row<m10v_camera_library_menu_index()){
    adj_commit_row(controller,row,m);
    m10v_debug_log(144,row,previous,1,0);
   }
  }
 }
 m10v_camera_library_adj_tone_set(0);
 return ((fn1)0x531a1998u)(controller);
}
#endif
