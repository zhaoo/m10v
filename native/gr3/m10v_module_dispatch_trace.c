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
/* Only the common generic receiver rejoin may call this sink: the actual
 * handler returned, reference-counter mutex is released, and owner callback
 * (which may retire the recipe) has not yet run. No file write is performed
 * for any other kind of module. Original StoreImageProcess may still report
 * asynchronous service results; draining records is NOT media durability. */
void m10v_module_trace_finish(uint32_t meta,uint32_t handler){
 if(handler!=0x5350c764u||!ram(meta,32))return;
 uint32_t recipe=*(const uint32_t *)(uintptr_t)(meta+20);
 if(!ram(recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)||*(const uint32_t *)(uintptr_t)recipe!=0x53d0fc90u||
    meta<recipe+0x5f0u)return;
 uint32_t delta=meta-recipe-0x5f0u,kind=delta>>5;
 if((delta&31)||kind>=24)return;
 uint32_t time[2]={0,0};int error=((int (*)(uint32_t *))0x53050b7cu)(time);
 m10v_save_trace_recipe_mark(recipe,207,kind,time[1],time[0]|(error?0x80000000u:0));
 uint32_t records[M10V_SAVE_TRACE_CAPACITY][5];
 uint32_t count=m10v_save_trace_recipe_take(recipe,&records[0][0],M10V_SAVE_TRACE_CAPACITY);
 if(count)m10v_debug_batch(&records[0][0],count);
}
#endif
