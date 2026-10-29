#ifndef M10V_BORDER_CAMERA_H
#define M10V_BORDER_CAMERA_H
#include <stdint.h>
#include "m10v_border.h"
#ifndef M10V_BORDER_ENABLED
#define M10V_BORDER_ENABLED 0
#endif
/* Embedded in the original TopMenu-owned Effects controller, not append RX.
 * UI-only refresh/save publish this cache; capture only reads snapshot(). */
typedef struct {uint32_t magic,version,style,sequence;} m10v_border_cache;
#define M10V_BORDER_CACHE_PAGE_OFFSET 0x1a8u
#ifndef M10V_BORDER_CACHE_OWNER_OFFSET
#define M10V_BORDER_CACHE_OWNER_OFFSET (0x223cu+M10V_BORDER_CACHE_PAGE_OFFSET)
#endif
int m10v_border_camera_refresh(uint32_t owner);
int m10v_border_camera_save(uint32_t owner,uint32_t style);
/* Bounded singleton lookup and stable cache copy only. Missing/busy/invalid
 * owner returns off. Never constructs UI, reads SD, allocates or waits. */
uint32_t m10v_border_camera_cached(void);
/* Returns1 only for a stable valid cache, including genuine off. Returns0
 * without touching output for unavailable/mutating/invalid cache or output.
 * Capture must use this status-bearing API, never infer validity from off. */
int m10v_border_camera_snapshot(uint32_t *style);
#endif
