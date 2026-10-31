/* Generic dispatcher observer. All records are recipe-owned and data-only. */
#include "m10v_save_trace.h"
#if M10V_BORDER_ENABLED && M10V_DEBUG_MODE
#include "m10v_border_shot.h"
#endif
static int ram(uint32_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<=0x80000000u-n;}
void m10v_module_trace_mark(uint32_t module,uint32_t message,uint32_t handler,uint32_t event,uint32_t result){
 if((event!=204&&event!=205)||!ram(module,4)||!ram(message,24)||
    (handler&3)||handler<0x53000000u||handler>=0x55000000u)return;
 uint32_t meta=*(const uint32_t *)(uintptr_t)(message+12);
 if(!ram(meta,32))return;
 uint32_t recipe=*(const uint32_t *)(uintptr_t)(meta+20);
 if(!ram(recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)||*(const uint32_t *)(uintptr_t)recipe!=0x53d0fc90u||
    *(const uint32_t *)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC||
    meta<recipe+0x5f0u||message<recipe+0x3b0u)return;
 uint32_t delta=meta-recipe-0x5f0u,kind=delta>>5;
 if((delta&31)||kind>=24||message!=recipe+0x3b0u+24*kind)return;
 /* Border diagnostics: retain the live main descriptor at the handoff after
  * BackResize and across the following native review/JPEG modules. This is
  * metadata only and stays in the existing bounded recipe trace. */
 uint32_t detail=handler;
#if M10V_BORDER_ENABLED && M10V_DEBUG_MODE
 if((kind==21u||kind==12u||kind==10u||kind==6u)&&
    *(const uint32_t *)(uintptr_t)(recipe+M10V_BORDER_SHOT_OFFSET))
     detail=*(const uint32_t *)(uintptr_t)(recipe+0xc0u);
#endif
 m10v_save_trace_recipe_mark(recipe,event,kind,detail,event==204?module:result);
#if M10V_BORDER_ENABLED && M10V_DEBUG_MODE
 if(event==205&&kind==10u&&
    *(const uint32_t *)(uintptr_t)(recipe+M10V_BORDER_SHOT_OFFSET))
  m10v_save_trace_recipe_mark(recipe,197u,0x4d313030u,
    *(const uint32_t *)(uintptr_t)(recipe+M10V_BORDER_SHOT_OFFSET),detail);
#endif
 if(event==204&&handler==0x5350c764u)m10v_save_trace_recipe_mark(recipe,206,kind,*(const uint32_t *)(uintptr_t)(message+4),module);
}
#if M10V_MODULE_SAFE_STORE_SINK
#include "m10v_debug.h"
#if M10V_PURE_ISP_EFFECTS
#include "m10v_isp_effects_shot.h"
#endif
/* Only the common generic receiver rejoin may call this sink: the actual
 * handler returned, reference-counter mutex is released, and owner callback
 * (which may retire the recipe) has not yet run. A pure-ISP diagnostic build
 * also drains selected returned modules for active effects at this boundary.
 * Original StoreImageProcess may still report
 * asynchronous service results; draining records is NOT media durability. */
void m10v_module_trace_finish(uint32_t meta,uint32_t handler){
 if(!ram(meta,32))return;
#if !M10V_PURE_ISP_EFFECTS
 if(handler!=0x5350c764u)return;
#endif
 uint32_t recipe=*(const uint32_t *)(uintptr_t)(meta+20);
 if(!ram(recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)||*(const uint32_t *)(uintptr_t)recipe!=0x53d0fc90u||
    meta<recipe+0x5f0u)return;
 uint32_t delta=meta-recipe-0x5f0u,kind=delta>>5;
 if((delta&31)||kind>=24)return;
#if M10V_PURE_ISP_EFFECTS
 uint32_t effects=0,flags=0;
 if(handler!=0x5350c764u){
  if(handler<0x53000000u||handler>=0x55000000u||(handler&3u)||
     !((1u<<kind)&((1u<<19)|(1u<<4)|(1u<<12)|(1u<<10)|(1u<<11)|(1u<<5)))||
     *(const uint32_t*)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC)return;
  const m10v_isp_effects_shot_snapshot *s=(const void*)(uintptr_t)(recipe+M10V_ISP_EFFECTS_SHOT_OFFSET);
  if(s->magic!=M10V_ISP_EFFECTS_SHOT_MAGIC||s->owner!=recipe||s->ready!=1u||
     !(s->settings.leak_gain||s->settings.blur_gain||s->settings.grain_mode>=2u))return;
  effects=1;
  uint32_t request=*(const uint32_t*)(uintptr_t)(recipe+0x5cu);
  flags=ram(request,0x40)?*(const uint8_t*)(uintptr_t)(request+0x24u):0xffu;
  flags|=(uint32_t)*(const uint8_t*)(uintptr_t)(recipe+0x4368u)<<8;
  flags|=(uint32_t)*(const uint8_t*)(uintptr_t)(recipe+0x4369u)<<16;
 }
#endif
 uint32_t time[2]={0,0};int error=((int (*)(uint32_t *))0x53050b7cu)(time);
 m10v_save_trace_recipe_mark(recipe,207,kind,time[1],time[0]|(error?0x80000000u:0));
 uint32_t records[M10V_SAVE_TRACE_CAPACITY][5];
 uint32_t count=m10v_save_trace_recipe_take(recipe,&records[0][0],M10V_SAVE_TRACE_CAPACITY);
#if M10V_PURE_ISP_EFFECTS
 if(effects){
  if(count==M10V_SAVE_TRACE_CAPACITY){m10v_debug_batch(&records[0][0],count);count=0;}
  uint32_t *r=records[count++];r[0]=198;r[1]=recipe;r[2]=0x46584d00u;r[3]=kind;r[4]=flags;
 }
#endif
 if(count)m10v_debug_batch(&records[0][0],count);
}
#endif
