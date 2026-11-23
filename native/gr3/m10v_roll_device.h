#ifndef M10V_ROLL_DEVICE_H
#define M10V_ROLL_DEVICE_H

#include "m10v_roll.h"

/* Settings runs on AppMain. Enable only with verified save receipts and
 * restart recovery bound to the live storage owner. */
#if M10V_ROLL_NATIVE_DEVICE
#include "m10v_library.h"
int m10v_camera_library_roll_preview(m10v_library_state *,uint32_t tone);
uint32_t m10v_camera_library_roll_prepare(uint32_t film,int apply);
void m10v_roll_device_prepare(void);
int m10v_roll_device_snapshot(m10v_roll_record *out);
int m10v_roll_device_open(uint32_t film, uint32_t aspect, uint32_t target);
int m10v_roll_device_change(uint32_t status);
int m10v_roll_device_film_available(uint32_t film);
int m10v_roll_device_locked(void);
#else
static inline int m10v_roll_device_locked(void) { return 0; }
static inline void m10v_roll_device_prepare(void) {}
static inline int m10v_roll_device_snapshot(m10v_roll_record *out) {
    (void)out;
    return -1;
}
static inline int m10v_roll_device_open(uint32_t film, uint32_t aspect, uint32_t target) {
    (void)film;
    (void)aspect;
    (void)target;
    return 0;
}
static inline int m10v_roll_device_change(uint32_t status) {
    (void)status;
    return 0;
}
static inline int m10v_roll_device_film_available(uint32_t film) {
    (void)film;
    return 0;
}
#endif

#endif
