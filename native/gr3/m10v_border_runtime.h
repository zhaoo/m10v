#ifndef M10V_BORDER_RUNTIME_H
#define M10V_BORDER_RUNTIME_H
#include <stdint.h>
/* INACTIVE integration entry points; the firmware builder does not install
 * these yet. Both require the original current-recipe worker ownership.
 * before_submit runs immediately before53501f98's original enqueue. Once
 * PREPARED, a later rejection retains this native frame instead of submitting
 * one stripe with its restored old pitch. It never waits on a normal/OFF path.
 * after_resize runs at534ff458, after original cleanup, before owner callback.
 * No factory stop/join/destroy may run until this synchronous worker returns.
 * Native bank/cache ownership and all18 cold-boot guard patches are required.
 * No pixel pointer is CPU-dereferenced. Only5820B metadata is newly allocated.
 */
void m10v_border_runtime_before_submit(uint32_t module,uint32_t config);
int m10v_border_runtime_after_resize(uint32_t module,uint32_t config);
#endif
