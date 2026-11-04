#ifndef M10V_ZOOM_CAMERA_H
#define M10V_ZOOM_CAMERA_H
#include "m10v_zoom.h"
int m10v_zoom_camera_prime(void);
int m10v_zoom_camera_load(m10v_zoom_state *);
int m10v_zoom_camera_save(m10v_zoom_state *,const m10v_zoom_editor *);
uint32_t m10v_zoom_camera_bits(unsigned);
unsigned m10v_zoom_camera_slot(uint32_t);
int m10v_zoom_camera_select(unsigned);
#endif
