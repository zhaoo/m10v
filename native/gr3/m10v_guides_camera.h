#ifndef M10V_GUIDES_CAMERA_H
#define M10V_GUIDES_CAMERA_H

#include <stdint.h>

/* App-task-only state embedded in the original TopMenu's owned allocation. */
void m10v_guides_camera_init(uint32_t top_owner);
void m10v_guides_camera_dispose(uint32_t top_owner);
void m10v_guides_camera_restore(uint32_t live);
void m10v_guides_camera_leave(uint32_t live);

uint32_t m10v_guides_camera_mode(void);
uint32_t m10v_guides_camera_set_mode(uint32_t mode);

uint32_t m10v_guides_camera_count(void);
void m10v_guides_camera_draw(uint32_t context, uint32_t view, uint32_t row);
uint32_t m10v_guides_camera_apply(uint32_t context, uint32_t row);
uint32_t m10v_guides_camera_checked(uint32_t context, uint32_t row);
void m10v_guides_camera_summary(uint32_t context, uint32_t view);

void m10v_guides_camera_update(uint32_t live);
void m10v_guides_camera_prepare(uint32_t canvas);
void m10v_guides_camera_paint(uint32_t canvas, uint32_t bitmap);
void m10v_guides_camera_finish(uint32_t canvas);
uint32_t m10v_guides_camera_suppress_grid(uint32_t grid, uint32_t bitmap);

#endif
