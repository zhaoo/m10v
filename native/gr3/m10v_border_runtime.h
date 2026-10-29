#ifndef M10V_BORDER_RUNTIME_H
#define M10V_BORDER_RUNTIME_H
#include <stdint.h>
/* Owned border integration entry points. They require the original
 * current-recipe worker ownership.
 * before_submit runs immediately before53501f98's original enqueue. Once
 * PREPARED, a later rejection retains this native frame instead of submitting
 * one stripe with its restored old pitch. It never waits on a normal/OFF path.
 * after_resize runs at534ff458, after original cleanup, before owner callback.
 * No factory stop/join/destroy may run until this synchronous worker returns.
 * Native bank/cache ownership and all18 cold-boot guard patches are required.
 * JPEG handoff runs after the residual library and admits only provenance-
 * checked full or native-cropped views of the existing bank. No pixel pointer
 * is CPU-dereferenced. Only5820B metadata is newly allocated.
 */
void m10v_border_runtime_before_submit(uint32_t module,uint32_t config);
int m10v_border_runtime_after_resize(uint32_t module,uint32_t config);
int m10v_border_runtime_jpeg(uint32_t context);
#endif
