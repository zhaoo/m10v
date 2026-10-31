#ifndef M10V_ISP_EFFECT_TRANSFER_RUNTIME_H
#define M10V_ISP_EFFECT_TRANSFER_RUNTIME_H
#include "m10v_isp_effect_transfer.h"
/* Experimental synchronous native Resize admission; never camera CPU pixels.
 * Caller exclusively owns the destination reservation and must prevent native
 * factory teardown for this entire call. frame_token is nonzero/unique among
 * live frames. Runtime keeps a private descriptor snapshot and client on stack
 * until checked native callback tail completion; no timeout releases owners.
 * After metadata admission and stage ownership, every prepared=1 DMA enqueue
 * first calls original5383c8a8 clean+invalidate over the exact complete workspace
 * (both real planes), including reused Clarity scratch. This is native cache
 * maintenance, not CPU pixel processing; immutable ROM input needs no per-frame
 * source maintenance. Native cache_backend ABI is pinned by the enclosing
 * border runtime component; physical cache coherency still needs camera tests.
 * 1 completed native callback, -1 rejected before enqueue, -3 unsupported host,
 * -4 native status error AFTER callback/guarded release (output is invalid).
 * A post-submit ownership violation fatally retains the frame instead of
 * returning. Readiness does not establish physical DMA acceptance/performance.
 */
int m10v_isp_effect_transfer_execute(const m10v_isp_effect_transfer *plan,
                                   uint32_t frame_token);
#endif
