#ifndef M10V_LIVE_CAMERA_H
#define M10V_LIVE_CAMERA_H

#include "m10v_live_ingress.h"

typedef struct {
    m10v_live_ingress *arena;
    uint32_t next_frame, frame_slot, frame_tick, shot_si, shot_generation, nonce[3], consumer_tick;
    uint32_t diagnostic_tick;
    m10v_live_ingress_diagnostic diagnostic;
} m10v_live_camera;

m10v_live_camera *m10v_live_device_camera(void);
int m10v_live_device_mode(void);
int m10v_live_device_configured_mode(void);
int m10v_live_device_set_mode(uint32_t mode);
void m10v_live_camera_display(uint32_t recipe, uint32_t config, uint32_t y, uint32_t uv);
void m10v_live_camera_shutter(uint32_t si, uint32_t generation);
void m10v_live_camera_insert_tag(void *);
int m10v_live_camera_write_tag(const uint32_t *, uint32_t *);

#endif
