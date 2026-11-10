/* GR III2.10 scalar eligibility; no pixel or filesystem operations. */
#include "m10v_torn_overlay.h"
#include "m10v_tone.h"
#include "m10v_library.h"
#include "m10v_isp_recipe_color.h"
#include "m10v_isp_effects_shot.h"
#define U(p) ((uint32_t)(uintptr_t)(p))
typedef uint32_t (*fn1)(uint32_t);
static int ram(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x55000000u&&p<=0x80000000u-n;}
static uint32_t word(uint32_t p){return *(const volatile uint32_t*)(uintptr_t)p;}
extern int m10v_camera_library_read_current(m10v_library_state *);
static int film_safe(const m10v_library_state *s,uint32_t tone){
 uint32_t slot=m10v_tone_slot(tone);
 if(slot>=M10V_SLOT_COUNT)return 1;
 uint32_t film=s->slots[slot].film;
 /* Unknown/custom and special CPU renderers need their own admission proof. */
 return M10V_BUILTIN(film)&&film!=289u&&film!=290u;
}
int m10v_torn_camera_busy(void){
 if(!(word(0x55064398u)&1u)||!(word(0x55063eccu)&1u))return 1;
 const volatile uint8_t *s=(const void*)0x55067958u;
 return s[0x2c]||s[0x2d]||s[0x880]!=3u||*(const volatile uint8_t*)0x55063e03u;
}
int m10v_torn_eligible(uint32_t recipe,uint32_t si){
 m10v_library_state state;uint32_t tone;
 if(recipe){
  if(!ram(recipe,M10V_TORN_RECIPE_BYTES)||word(recipe)!=0x53d0fc90u||
     !ram(si,0x74270u)||word(recipe+0x44c8u)!=si)return 0;
  const volatile uint8_t *p=(const void*)(uintptr_t)si;
  /* Requested Single (fb9) and normalized Single (799) are distinct: some
   * non-single modes normalize to zero. Both must belong to this saved SI. */
  if(p[0xfb9]||p[0x799]||p[0x7b6]==6u)return 0;
  m10v_isp_effects_shot_snapshot effects;
  if(!m10v_isp_effects_shot_read(recipe,&effects))return 0;
  tone=p[0x77c];
  if(!m10v_tone_valid(tone)||tone==14u)return 0;
  if(m10v_tone_slot(tone)>=M10V_SLOT_COUNT)return 1;
  if(!m10v_isp_frame_recipe_state((void*)(uintptr_t)recipe,&state))return 0;
 }else{
  if(!(word(0x55063dccu)&1u))return 0;
  uint32_t root=((uint32_t(*)(void))0x5320ad88u)();
  if(!root)return 0;
  uint32_t settings=((fn1)0x5320b31cu)(root),image=((fn1)0x5320ba9cu)(root);
  if(!settings||!image||((fn1)0x53245190u)(settings)!=0u||
     ((fn1)0x53245260u)(settings)==6u||((fn1)0x532bd6d4u)(image))return 0;
  tone=((fn1)0x532bd6b4u)(image);
  if(!m10v_tone_valid(tone)||tone==14u)return 0;
  if(m10v_tone_slot(tone)>=M10V_SLOT_COUNT)return 1;
  if(m10v_camera_library_read_current(&state))return 0;
 }
 return film_safe(&state,tone);
}
