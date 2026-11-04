#ifndef M10V_ADJ_EXTRA_CAMERA_H
#define M10V_ADJ_EXTRA_CAMERA_H

#include "m10v_adj_extra.h"

#define M10V_ADJ_EXTRA_STOCK_LIST 0x53b4eba0u
#define M10V_ADJ_EXTRA_STOCK_CHOICES 19u
#define M10V_ADJ_EXTRA_STOCK_MAX 19u
#define M10V_ADJ_EXTRA_GUIDES 24u
#define M10V_ADJ_EXTRA_FILM 25u
#define M10V_ADJ_EXTRA_EFFECTS 26u
#define M10V_ADJ_EXTRA_ASPECT 27u
#define M10V_ADJ_EXTRA_BORDER 28u
#define M10V_ADJ_EXTRA_BORDER_ROUTE 0x0200f108u

void m10v_adj_extra_camera_init(uint32_t owner);
void m10v_adj_extra_camera_dispose(uint32_t owner);
int m10v_adj_extra_camera_load(m10v_adj_extra_assignments *out);
int m10v_adj_extra_camera_assign(unsigned logical_slot, unsigned function);
void m10v_adj_extra_camera_after_route_leave(uint32_t controller);
void m10v_adj_extra_camera_refresh(uint32_t controller);
void m10v_adj_extra_camera_initial_render(uint32_t controller);
void m10v_adj_extra_camera_touch0(uint32_t controller);
void m10v_adj_extra_camera_touch1(uint32_t controller);
void m10v_adj_extra_camera_touch2(uint32_t controller);
void m10v_adj_extra_camera_touch3(uint32_t controller);
void m10v_adj_extra_camera_touch4(uint32_t controller);
enum {
    M10V_ADJ_RETIRE_RESTORE,
    M10V_ADJ_RETIRE_DESTROY,
    M10V_ADJ_RETIRE_DEFER
};
void m10v_adj_extra_camera_retire(uint32_t controller, unsigned mode);
void m10v_adj_extra_camera_suspend(uint32_t controller, unsigned suspended);
uint32_t m10v_adj_extra_camera_event(uint32_t controller, uint32_t event);
uint32_t m10v_adj_extra_camera_lever_pending(uint32_t controller);
uint32_t m10v_adj_extra_camera_slot_type(uint32_t controller, uint32_t slot);
uint32_t m10v_adj_extra_camera_virtual_focus(uint32_t controller);

#endif
