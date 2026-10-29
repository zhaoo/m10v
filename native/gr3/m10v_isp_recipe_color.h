#ifndef M10V_ISP_RECIPE_COLOR_H
#define M10V_ISP_RECIPE_COLOR_H
#include "m10v_isp_frame_color.h"
#include "m10v_save_trace.h"
#include "m10v_library.h"
#define M10V_ISP_RECIPE_COLOR_MAGIC 0x31435349u
enum {M10V_ISP_RECIPE_EMPTY=0,M10V_ISP_RECIPE_READY=1,
      M10V_ISP_RECIPE_APPLIED=2,M10V_ISP_RECIPE_REJECTED=3,
      M10V_ISP_RECIPE_MISMATCH=4,M10V_ISP_RECIPE_BUSY=5,M10V_ISP_RECIPE_UNSUPPORTED=6,M10V_ISP_RECIPE_OBSERVED=7,M10V_ISP_RECIPE_MUTATING=8};
typedef struct {
    uint32_t magic,version,bytes,status,sequence;
    uint16_t tone,selected_tone; /* selected carrier frozen at producer ingress */
    uint32_t si,info,tuning,busy;
    union {
      m10v_isp_frame_target target;
      struct {uint32_t magic,si,tone,grain,size,planned,armed,noise_ready,done;} native_grain;
    };
    m10v_library_state state;
} m10v_isp_recipe_color;
/* Producer ingress: selected target and ShootingInfo identity are explicit.
 * Call before queueing the recipe; SD/filesystem services are not called here.
 * This module does NOT claim any approximate target is equivalent to a 3D LUT. */
int m10v_isp_frame_recipe_snapshot(void *recipe,const m10v_library_state *);
int m10v_isp_frame_recipe_state(void *recipe,m10v_library_state *out);
int m10v_isp_frame_recipe_producer(void *recipe);
uint32_t m10v_isp_frame_recipe_direction(void *recipe,uint32_t shooting);
/* Call-site adapter only. context is original DevelopMacroProcess C; C+30
 * points to sourceRecipe+1a8, C+34 is original ShootingInfo. */
int m10v_isp_frame_recipe_begin(const void *context,void *tuning,void *info);
int m10v_isp_frame_recipe_finish(const void *context);
uint32_t m10v_isp_frame_recipe_grain_settings(const void *context,void *params,uint32_t execution);
void m10v_isp_frame_recipe_grain_done(const void *context,const void *params,uint32_t result);
uint32_t m10v_isp_frame_recipe_completed(void *recipe,uint32_t shooting,uint32_t tone,const m10v_library_state *);
#endif
