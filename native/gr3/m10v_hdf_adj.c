/* Added ADJ function20; original0..19 retain their exact dispatch records.
 * Only a pending UI value changes while browsing; OK commits the same HDF
 * journal as MENU. Capture consumes its published cache, never this cursor. */
#include "m10v_hdf_state.h"
extern int m10v_hdf_load(uint32_t *);
extern int m10v_hdf_save(uint32_t);
extern uint32_t m10v_hdf_adj_parent_event(uint32_t,uint32_t);
typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn2)(uint32_t,uint32_t);
typedef uint32_t (*fn3)(uint32_t,uint32_t,uint32_t);
static uint32_t word(uint32_t c,uint32_t off){return *(const uint32_t *)(uintptr_t)(c+off);}
static uint32_t selected(uint32_t c){return ((fn2)0x531a2820u)(c,*(const uint8_t *)(uintptr_t)(c+0x1f4));}
void m10v_hdf_adj_enter(uint32_t c){
 m10v_hdf_ui *p=m10v_hdf_ui_owner();if(!p)return;
 uint32_t value;p->controller=c;p->error=0;
 if(m10v_hdf_cached(&value)<0){m10v_hdf_bootstrap();if(m10v_hdf_cached(&value)<0){value=0;p->error=1;}}
 p->pending=value;
}
void m10v_hdf_adj_draw(uint32_t c,uint32_t i){
 uint32_t item=((fn2)0x53394758u)(word(c,0x1f0),(uint8_t)i);
 ((fn2)0x533a1808u)(item,i<4?972+i:0);
}
uint32_t m10v_hdf_adj_current(uint32_t c,uint32_t i){
 m10v_hdf_ui *p=m10v_hdf_ui_owner();return i<4&&p&&p->controller==c&&p->pending==i;
}
void m10v_hdf_adj_set(uint32_t c,uint32_t i){
 m10v_hdf_ui *p=m10v_hdf_ui_owner();if(p&&p->controller==c&&i<4)p->pending=i;
}
uint32_t m10v_hdf_adj_count(uint32_t c){(void)c;return 4;}
/* Despite this legacy export name, stock record +0x3c is an exclusion
 * predicate: the icon loop (531a428c) hides nonzero, and slot navigation
 * (531a475c) skips nonzero. A cold cache is still usable: enter bootstraps
 * it. Only a missing owner must exclude HDF from the native five slots. */
uint32_t m10v_hdf_adj_available(uint32_t c){(void)c;return m10v_hdf_ui_owner()==0;}
uint32_t m10v_hdf_adj_event(uint32_t c,uint32_t event){
 uint32_t key=*(const uint16_t *)(uintptr_t)event;m10v_hdf_ui *p=m10v_hdf_ui_owner();
 /* These keys enter native capture/power/return services. Relinquish only
  * our cursor; never storage, widget rebuild or navigation on this path. */
 if(key==1||key==0x35||key==0x89||key==0xaa){if(p)p->controller=0;return m10v_hdf_adj_parent_event(c,event);}
 if(key==0xd8&&p&&p->controller==c&&selected(c)==20){
  uint32_t value=((fn1)0x53394820u)(word(c,0x1f0));
  if(value>3||m10v_hdf_save(value)){
   /* A failed verification can still leave a valid new journal. Reconcile
    * from disk, keep the error visible, and do not claim the old value won. */
   uint32_t actual;if(m10v_hdf_load(&actual)==0)p->pending=actual;
   p->error=1;((fn3)0x53396f80u)(word(c,0x160),976,0);return 1;
  }
  p->pending=value;p->error=0;p->controller=0;
 }
 return m10v_hdf_adj_parent_event(c,event);
}
