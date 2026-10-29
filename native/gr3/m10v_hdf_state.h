#ifndef M10V_HDF_STATE_H
#define M10V_HDF_STATE_H
#include <stdint.h>
#ifndef M10V_HDF_OWNER_OFFSET
#define M10V_HDF_OWNER_OFFSET 0x193cu
#endif
#ifndef M10V_HDF_UI_CACHE
#define M10V_HDF_UI_CACHE 0
#endif
/* Existing HDF page fields occupy [0,0x190). Its allocation is0x1c0.
 * These words have one TopMenu owner, are zeroed by its constructor, and
 * invalidated before its destructor. Never reuse stock settings padding. */
#define M10V_HDF_CACHE_OFFSET 0x190u
#define M10V_HDF_CACHE_MAGIC 0x43464448u
typedef struct {
 uint32_t published,magic,controller,pending,error;
} m10v_hdf_ui;
_Static_assert(M10V_HDF_CACHE_OFFSET+sizeof(m10v_hdf_ui)<=0x1c0,"HDF page owned tail");
static inline m10v_hdf_ui *m10v_hdf_ui_owner(void){
 if(!(*(const volatile uint32_t *)0x55063910u&1u))return 0;
 uintptr_t owner=*(const volatile uint32_t *)0x55063988u;
 if((owner&3)||owner<0x55000000u||owner>0x80000000u-M10V_HDF_OWNER_OFFSET-0x1c0u)return 0;
 m10v_hdf_ui *p=(void *)(owner+M10V_HDF_OWNER_OFFSET+M10V_HDF_CACHE_OFFSET);
 return p->magic==M10V_HDF_CACHE_MAGIC?p:0;
}
int m10v_hdf_cached(uint32_t *);
void m10v_hdf_bootstrap(void);
#endif
