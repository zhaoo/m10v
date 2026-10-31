#include "m10v_save_trace.h"
#include "m10v_debug.h"
#if M10V_PURE_ISP_EFFECTS
#include "m10v_isp_effects_shot.h"
#endif
#if M10V_BORDER_ENABLED
#include "m10v_border_shot.h"
#include "m10v_border_camera.h"
#endif
#include <stdint.h>
#if M10V_RECIPE_SNAPSHOT
#include "m10v_isp_recipe_color.h"
#endif
void m10v_lifecycle_file_flush(m10v_save_trace *trace){
 /* The synchronous file caller exclusively owns this optional heap block;
  * its callback has returned and all native inner cleanup has completed. */
 uintptr_t at=(uintptr_t)trace;
 if((at&3)||at<0x55000000u||at>0x80000000u-sizeof(*trace)||trace->magic!=M10V_SAVE_TRACE_MAGIC||trace->busy||trace->count>=M10V_SAVE_TRACE_CAPACITY)return;
 uint32_t records[M10V_SAVE_TRACE_CAPACITY][5],count=trace->count;
 for(uint32_t i=0;i<count;i++)for(uint32_t j=0;j<5;j++)records[i][j]=trace->events[i][j];
 if(trace->dropped){uint32_t *r=records[count++];r[0]=199;r[1]=(uint32_t)at;r[2]=trace->dropped;r[3]=trace->count;r[4]=0;}
 if(count)m10v_debug_batch(&records[0][0],count);

}
/* Invoked only by the locked JPEG worker, outside a filesystem callback.
 * r4 is the native context owned by recipe+0x9b8. No image is retained and
 * neither the allocator/setter hooks nor the event callback writes to SD. */
void m10v_lifecycle_phase(uint32_t context,uint32_t event,uint32_t result){
 if(context<0x550009b8u||context>=0x80000000u||(context&3)||event<190||event>194)return;
 uint32_t recipe=context-0x9b8u,time[2]={0,0};
#if M10V_RECIPE_SNAPSHOT
 if(event==193&&recipe<=0x80000000u-M10V_SAVE_RECIPE_EXTENDED_BYTES){
  const m10v_isp_recipe_color *s=(const m10v_isp_recipe_color *)(uintptr_t)(recipe+M10V_SAVE_COLOR_OFFSET);
  if(s->magic==M10V_ISP_RECIPE_COLOR_MAGIC)m10v_save_trace_recipe_mark(recipe,198,0x49535001u,(s->status<<16)|s->tone,s->sequence);
#if M10V_HDF_SHARED_RECIPE
  /* All three words belong to the same sole extended recipe allocation.
   * Read diagnostics only; the trace never controls processing or ownership. */
  if(*(const uint32_t *)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)==M10V_SAVE_TRACE_MAGIC){
   const uint32_t *h=(const uint32_t *)(uintptr_t)(recipe+M10V_CAPTURE_RAW_TOKEN_OFFSET+36u);
   m10v_save_trace_recipe_mark(recipe,198,0x48444601u,(h[0]<<8)|(h[1]&255u),h[2]);
  }
#endif
 }
#endif
 int status=((int (*)(uint32_t *))0x53050b7cu)(time);
 m10v_save_trace_recipe_mark(recipe,event,time[1],time[0]|(status?0x80000000u:0),result);
 /* Submit-return must not delay reaching the original encode wait. Flush
  * only on this existing capture worker's pre-submit and post-wait borders. */
 if(event==191||event==194)return;
 uint32_t records[M10V_SAVE_TRACE_CAPACITY][5];
 uint32_t count=m10v_save_trace_recipe_take(recipe,&records[0][0],M10V_SAVE_TRACE_CAPACITY);
 if(count)m10v_debug_batch(&records[0][0],count);
#if M10V_PURE_ISP_EFFECTS && M10V_DEBUG_MODE
 /* One bounded batch at the existing filesystem-safe JPEG boundary. Never
  * log from ISP wait loops or publish completion from diagnostics. Keep this
  * independent of the earlier trace ring, which can already be full. */
 if(event==193&&recipe<=0x80000000u-M10V_SAVE_RECIPE_EXTENDED_BYTES&&
    *(const uint32_t*)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)==M10V_SAVE_TRACE_MAGIC){
  const m10v_isp_effects_shot_snapshot *s=(const void*)(uintptr_t)(recipe+M10V_ISP_EFFECTS_SHOT_OFFSET);
  uint32_t si=*(const uint32_t*)(uintptr_t)(recipe+0x44c8u),native=0xffffffffu;
  if(si>=0x55000000u&&si<=0x80000000u-0x94cu&&!(si&3u)){
   const uint8_t *p=(const void*)(uintptr_t)si;native=p[0x77c]|((uint32_t)p[0x795]<<16);
  }
  const uint32_t facts[8][5]={
   {198,recipe,0x46583030u,s->magic,s->owner},
   {198,recipe,0x46583031u,s->ready,s->sequence},
   {198,recipe,0x46583032u,s->settings.leak_gain,s->settings.blur_gain},
   {198,recipe,0x46583033u,s->planned,s->native_completed},
   {198,recipe,0x46583034u,s->failed,s->source_si},
   {198,recipe,0x46583035u,s->stock_workspace_bytes,s->stock_query_valid},
   {198,recipe,0x46583036u,s->effective_grain_strength,s->settings.grain_mode},
   {198,recipe,0x46583037u,si,native}};
  m10v_debug_batch(&facts[0][0],8);
 }
#endif
#if M10V_BORDER_ENABLED && M10V_DEBUG_MODE
 /* Capture both sides of the border JPEG handoff, including previews. These
  * are descriptor words only; never dereference a photo plane. One batch per
  * boundary avoids a separate SD transaction for each metadata pair. */
 if((event==193||event==190)&&recipe<=0x80000000u-M10V_SAVE_RECIPE_EXTENDED_BYTES&&
    *(const uint32_t *)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)==M10V_SAVE_TRACE_MAGIC){
  uint32_t shot=*(const uint32_t *)(uintptr_t)(recipe+M10V_BORDER_SHOT_OFFSET);
  if((shot&~255u)==0x42524400u&&(shot&3u)>0u&&(shot&3u)<=2u){
   static const uint32_t offsets[5]={0x70u,0xb0u,0xd0u,0xf0u,0x110u};
   uint32_t n=0;
   for(uint32_t i=0;i<5u;i++){
    const uint32_t *d=(const uint32_t *)(uintptr_t)(recipe+offsets[i]);
    uint32_t tag=0x4a000000u|((event==190?1u:0u)<<20)|(offsets[i]<<8);
    uint32_t *r=records[n++];r[0]=197;r[1]=recipe;r[2]=tag;r[3]=d[1];r[4]=d[2];
    r=records[n++];r[0]=197;r[1]=recipe;r[2]=tag|1u;r[3]=d[4];r[4]=d[5];
   }
   uint32_t *r=records[n++];r[0]=197;r[1]=recipe;r[2]=0x4a000002u|((event==190?1u:0u)<<20);
   r[3]=shot;r[4]=*(const uint16_t *)(uintptr_t)(recipe+0x256u)|
       ((uint32_t)*(const uint16_t *)(uintptr_t)(recipe+0x258u)<<16);
   r=records[n++];r[0]=197;r[1]=recipe;r[2]=0x4a000003u|((event==190?1u:0u)<<20);
   r[3]=*(const uint32_t *)(uintptr_t)(recipe+0x304u);r[4]=*(const uint32_t *)(uintptr_t)(recipe+0x364u);
   m10v_debug_batch(&records[0][0],n);
  }
 }
 /* The bounded capture trace can fill before phase 193. Emit this one
  * diagnostic after the existing safe flush so a full trace cannot hide it. */
 if(event==193&&recipe<=0x80000000u-M10V_SAVE_RECIPE_EXTENDED_BYTES&&
    *(const uint32_t *)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)==M10V_SAVE_TRACE_MAGIC){
  uint32_t style=0,available=m10v_border_camera_snapshot(&style);
  M10V_LOG(205,0x53484f54u,
           *(const uint32_t *)(uintptr_t)(recipe+M10V_BORDER_SHOT_OFFSET),
           available?style:0xffffffffu,
           *(const uint32_t *)(uintptr_t)(recipe+0xc0u));
  M10V_LOG(197,recipe,0x53524353u,
           *(const uint32_t *)(uintptr_t)(recipe+0x80u),
           *(const uint32_t *)(uintptr_t)(recipe+0x120u));
  M10V_LOG(197,recipe,0x504c414eu,
           *(const uint32_t *)(uintptr_t)(recipe+0x74u),
           *(const uint32_t *)(uintptr_t)(recipe+0xb4u));
  const m10v_save_trace *trace=(const m10v_save_trace *)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES);
  if(trace->events[31][0]==197u&&
     (trace->events[31][2]==0x424f5244u||trace->events[31][2]==0x4d313030u))
   M10V_LOG(197,recipe,trace->events[31][2],trace->events[31][3],trace->events[31][4]);
 }
#endif
}
