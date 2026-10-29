#ifndef M10V_BORDER_FILL_BUNDLE_H
#define M10V_BORDER_FILL_BUNDLE_H
#include <stdint.h>
/* INACTIVE research ABI. Descriptor/control metadata only; no pixel loop.
 * Caller retains this immutable allocation AND all descriptors/canvas owners
 * through final private callback. All descriptor addresses must denote valid
 * readable native 32-byte descriptors; these checks are not memory protection.
 * The public prepared=1 call skips its normal cache pre/post methods. Caller
 * MUST acquire/release real whole-canvas native cache ownership once externally;
 * NEVER pass this header to native image/cache code as an image descriptor.
 * Complete-chain stage gate, native worker readiness and teardown exclusion
 * are prerequisites. None of these are established merely by this API. */
#define M10V_BORDER_FILL_BUNDLE_TAG 0x42464231u
#define M10V_BORDER_FILL_BUNDLE_MAX 132u
typedef struct {
 uint32_t destination;
 uint16_t y,cb,cr,reserved;
} m10v_border_fill_rectangle;
typedef struct {
 uint32_t tag,count,bytes;
 m10v_border_fill_rectangle rectangles[];
} m10v_border_fill_bundle;
#endif
