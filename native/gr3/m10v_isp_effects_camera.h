#ifndef M10V_ISP_EFFECTS_CAMERA_H
#define M10V_ISP_EFFECTS_CAMERA_H
#include <stdint.h>
#include "m10v_isp_effects_state.h"

/* Builder must reserve this entire independently owned tail before the UI
 * controller constructor, and define M10V_ISP_EFFECT_CACHE_OWNER_OFFSET for
 * the selected layout. No legacy HDF/film-state padding is reused. */
#define M10V_ISP_EFFECT_CACHE_MAGIC 0x31434649u
typedef struct {
    uint32_t magic;
    uint32_t version; /* nonzero even: stable; odd: writer owns publication */
    uint32_t sequence;
    m10v_isp_effects_settings settings;
} m10v_isp_effects_camera_cache;

/* Constructor/UI lifecycle only; zero exactly the owned cache then refresh.
 * UI is the sole writer; live owner storage must outlive any capture read. */
void m10v_isp_effects_camera_init(uint32_t owner);
/* 0 success; negative failure. Only UI refresh/save access the filesystem.
 * The native exact-length read API reports missing/error as the same zero.
 * Cold cache + no valid records therefore publishes safe defaults. A warm
 * cache is retained on missing/error/invalid records; ambiguous valid record
 * generations always reject. Filesystem unavailable leaves cold cache invalid.
 * Save requires an authenticated stable cache floor and proves both exact
 * written readback and journal winner before publishing new settings. */
int m10v_isp_effects_camera_refresh(uint32_t owner);
int m10v_isp_effects_camera_save(uint32_t owner,
    const m10v_isp_effects_settings *settings);
/* Capture path: bounded singleton/cache copy only; no FS, allocation or wait.
 * Return 1 only for a stable valid snapshot; otherwise return 0 with both
 * outputs unchanged. Outputs must be distinct and outside the owner cache. */
int m10v_isp_effects_camera_snapshot(m10v_isp_effects_settings *out,
    uint32_t *sequence);
#endif
