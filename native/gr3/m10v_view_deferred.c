#include "m10v_view_deferred.h"
#include "m10v_view_recovery.h"
void m10v_view_deferred_enter(m10v_view_deferred *t){
 uint32_t g=t->magic==M10V_VIEW_DEFERRED_MAGIC?t->generation+1u:1u;
 if(!g)g=1;t->magic=M10V_VIEW_DEFERRED_MAGIC;t->generation=g;t->pending_generation=0;t->reserved=0;
}
void m10v_view_deferred_invalidate(m10v_view_deferred *t){
 if(t->magic==M10V_VIEW_DEFERRED_MAGIC)m10v_view_deferred_enter(t);
}
uint32_t m10v_view_deferred_mark(m10v_view_deferred *t,uint32_t state,uint32_t busy){
 if(t->magic!=M10V_VIEW_DEFERRED_MAGIC||!t->generation||t->reserved!=t->generation||state!=2||!busy)return 0;
 t->pending_generation=t->generation;return 1;
}
uint32_t m10v_view_deferred_take(m10v_view_deferred *t,uint32_t state,uint32_t busy){
 if(t->magic!=M10V_VIEW_DEFERRED_MAGIC||!t->generation||t->pending_generation!=t->generation)return 0;
 if(state!=2){t->pending_generation=0;return 0;}if(busy)return 0;
 t->pending_generation=0;return 1;
}
static uint32_t word(uint32_t a){return *(volatile const uint32_t *)(uintptr_t)a;}
static uint32_t byte(uint32_t a){return *(volatile const uint8_t *)(uintptr_t)a;}
static uint32_t quick(void){
 uint32_t q;if(!(word(0x55063910u)&1u))return 0;q=word(M10V_VIEW_FACTORY+0xd8u);
 return q>=0x55000000u&&q<=0x60000000u-M10V_VIEW_DEFERRED_BYTES&&!(q&3u)&&word(q)==M10V_VIEW_QUICK_VPTR?q:0;
}
static uint32_t validmodel(uint32_t m){return m==M10V_VIEW_MODEL&&(word(0x55064398u)&1u)&&word(m)==M10V_VIEW_MODEL_VPTR;}
static uint32_t busy(uint32_t m){return byte(m+0x2f)|byte(m+0x30);}
static m10v_view_deferred *token(uint32_t q){return (m10v_view_deferred *)(uintptr_t)(q+M10V_VIEW_DEFERRED_OFFSET);}
void m10v_view_deferred_on_enter(uint32_t q){
 if(q==quick())m10v_view_deferred_enter(token(q));
}
void m10v_view_deferred_on_producer(uint32_t m){
 uint32_t q;if(!validmodel(m))return;q=quick();
 if(q&&token(q)->magic==M10V_VIEW_DEFERRED_MAGIC)token(q)->reserved=token(q)->generation;
}
void m10v_view_deferred_on_169(uint32_t q){
 typedef void (*complete_fn)(uint32_t);
 ((complete_fn)(uintptr_t)0x531cbe78u)(q);
 /* The genuine producer sends169 before its native stores clear31/2f.
  * A dispatcher scheduled there must retain this generation's completion.
  * Stop-reply still requires every native busy flag clear before retrying;
  * capture-start/re-entry invalidate the generation, as before. */
 if(q==quick()&&validmodel(M10V_VIEW_MODEL))m10v_view_deferred_mark(token(q),byte(q+0x16cu),busy(M10V_VIEW_MODEL));
}
void m10v_view_deferred_on_capture_start(uint32_t m){
 uint32_t q;if(!validmodel(m))return;q=quick();if(q)m10v_view_deferred_invalidate(token(q));
}
void m10v_view_deferred_on_stop_reply(uint32_t m){
 typedef void (*complete_fn)(uint32_t);uint32_t q;
 if(!validmodel(m)||byte(m+0x31))return;q=quick();
 if(q&&m10v_view_deferred_take(token(q),byte(q+0x16cu),busy(m)))((complete_fn)(uintptr_t)0x531cbe78u)(q);
}
