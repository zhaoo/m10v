#ifndef M10V_SETTINGS_CONTROLLER_H
#define M10V_SETTINGS_CONTROLLER_H
#include "m10v_settings_view.h"
#include "m10v_ab.h"
#include "m10v_zoom_menu.h"
#ifndef M10V_AB_NATIVE_HOST
#define M10V_AB_NATIVE_HOST 1
#endif
/* Valid only while page==7. The native controller owns all referenced views;
 * this stores cursor/lifetime state, never a second canvas or controller. */
typedef struct {
 uint32_t controller,mode,origin,source,position,offset,rebuilding,back_pending;
 uint32_t level,focus,a,b,error,films[M10V_SLOT_COUNT];
} m10v_native_ab_host;
/* Two instances are embedded after the original TopMenu object, never placed
 * in undocumented RAM or freed independently from their owner. */
typedef struct {
 uint8_t base[0x158];
 m10v_settings_view view;
 union {m10v_settings state;m10v_native_ab_host host;m10v_zoom_menu zoom;};
 uint32_t page;
 m10v_ab ab;
 uint32_t display_trace;
 uint32_t pending_source;
 uint16_t zoom_mm[2];
 uint32_t zoom_flags;
 uint32_t power_off_pending; /* UI MAIN switch latch; never persisted. */
 uint32_t library_initialized; /* Successful boot migration/cache load, owner lifetime only. */
 uint32_t ab_exit_source; /* Queued return to LiveView still owns this ADJ source. */
 uint32_t half_pair[4]; /* Owner-lifetime pending-pair control; no pixel pointers. */
} m10v_settings_controller;
_Static_assert(sizeof(m10v_native_ab_host)<=sizeof(m10v_settings),"exclusive host state capacity");
#define M10V_SETTINGS_OWNER_BYTES 0x13bcu
#define M10V_SETTINGS_CONTROLLER_BYTES 0x6c0u
_Static_assert(sizeof(m10v_settings_controller)<=M10V_SETTINGS_CONTROLLER_BYTES,"controller tail capacity");
#define M10V_SETTINGS_FILMS_ROUTE 0x0200f100u
#define M10V_SETTINGS_STAMP_ROUTE 0x0200f101u
#define M10V_SETTINGS_NAME_ROUTE 0x0200f103u
#define M10V_SETTINGS_AB_ROUTE 0x0200f104u
#define M10V_SETTINGS_ZOOM_ROUTE 0x0200f105u
_Static_assert(sizeof(m10v_zoom_menu)<=sizeof(m10v_settings),"zoom state capacity");
uint32_t m10v_settings_controller_owner_size(void);
uint32_t m10v_settings_controller_top_ctor(uint32_t owner);
uint32_t m10v_settings_controller_top_dtor(uint32_t owner);
uint32_t m10v_settings_controller_factory(uint32_t factory,uint32_t route);
uint32_t m10v_settings_controller_ready(m10v_settings_controller *,uint32_t route);
void m10v_settings_controller_enter(m10v_settings_controller *,uint32_t route,uint32_t flags);
uint32_t m10v_settings_controller_key(m10v_settings_controller *,uint32_t event);
#endif
