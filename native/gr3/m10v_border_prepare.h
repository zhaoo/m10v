#ifndef M10V_BORDER_PREPARE_H
#define M10V_BORDER_PREPARE_H
#include <stdint.h>
/* INACTIVE adapter; no hook or builder registration.
 * Call only before StillMake's current R2Y submit53501f98, under exclusive
 * current-recipe ownership. The first FROZEN0 call precedes the first output
 * write; only its owning hook publishes PREPARED6 after success. Later stripes
 * can repeat in PREPARED6 after their native helper restores the common output
 * pitch. The plan is idempotent. Phase must equal the entry sample at commit.
 * 1: committed metadata, 0: owned frozen OFF (no image/plan access), -1: reject.
 * Rejection performs no metadata writes. The successful multiword commit needs
 * the caller's ownership; it is not atomic against concurrent native readers.
 * Once PREPARED6 has been published, rejection MUST retain the native worker,
 * stack and owners permanently; the hook must never submit an old-pitch stripe
 * after an earlier stripe used the new layout. This function does not wait or
 * change phase, and cannot itself enforce that external failure policy.
 * Preserve native halo ROI/W/H and validate its complete configured extent
 * against native row capacity and the newly reserved row/plane guards.
 * No CPU pixel access, allocation, filesystem, wait or submission.
 */
int m10v_border_prepare(uint32_t module,uint32_t config);
#endif
