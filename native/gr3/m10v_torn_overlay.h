#ifndef M10V_TORN_OVERLAY_H
#define M10V_TORN_OVERLAY_H
#include <stdint.h>
#define M10V_TORN_OWNER_OFFSET 0x6d00u
#define M10V_TORN_OWNER_BYTES 0x6e00u
#define M10V_TORN_SHOT_OFFSET 0x57d8u
#define M10V_TORN_RECIPE_BYTES 0x57f8u
#define M10V_TORN_SHOT_MAGIC 0x31524f54u
typedef struct {uint32_t magic,recipe,si,generation,phase,owner;int32_t result;uint32_t completion;} m10v_torn_snapshot;
void m10v_torn_init(uint32_t owner);
void m10v_torn_destroy(uint32_t owner);
int m10v_torn_state(uint32_t *stage,uint32_t *generation);
int m10v_torn_busy(void);
int m10v_torn_set(uint32_t owner,uint32_t action);
void m10v_torn_reserve(uint32_t recipe);
int m10v_torn_freeze(uint32_t recipe);
/* 1 off/success; -1 rejected before pixel submission, original untouched.
 * A submitted native operation must drain; never returns on uncertain DMA. */
int m10v_torn_execute(uint32_t recipe,uint32_t context,const uint32_t photo[8]);
int m10v_torn_encoder_admit(uint32_t recipe,uint32_t si);
/* Bound by integration. Eligibility for recipe!=0 consults frozen SI/color,
 * never current UI; recipe=0 is the live start check. */
int m10v_torn_eligible(uint32_t recipe,uint32_t si);
int m10v_torn_camera_busy(void);
#endif
