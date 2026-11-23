#ifndef M10V_LIVE_INGRESS_H
#define M10V_LIVE_INGRESS_H

#include <stdint.h>

enum {
    M10V_LIVE_DESCRIBE_COMMAND = 11,
    M10V_LIVE_HEARTBEAT_COMMAND = 12,
    M10V_LIVE_INGRESS_MAGIC = 0x31494c4du, /* MLI1 */
    M10V_LIVE_INGRESS_VERSION = 1,
    M10V_LIVE_INGRESS_MONO_NV12 = 1,
    M10V_LIVE_INGRESS_WIDTH = 192,
    M10V_LIVE_INGRESS_HEIGHT = 128,
    M10V_LIVE_INGRESS_Y_BYTES = 192 * 128,
    M10V_LIVE_INGRESS_FRAME_BYTES = 192 * 128 * 3 / 2,
    M10V_LIVE_INGRESS_SLOTS = 3,
    M10V_LIVE_INGRESS_ALIGNMENT = 128,
    M10V_LIVE_INGRESS_STEP_MS = 90,
    M10V_LIVE_INGRESS_LEASE_MS = 5000,
    M10V_LIVE_EXIF_TAG = 0xc7f3,
    M10V_LIVE_EXIF_MAGIC = 0x4c30314du, /* M10L */
    M10V_LIVE_EXIF_WORDS = 6
};

typedef struct {
    uint32_t version, address, bytes, epoch, slot_count, slot_stride, frame_bytes, format;
} m10v_live_ingress_offer;

/* AppMain owns request; the display task owns the diagnostic subrecord.
 * Exposure and frame headers each retain their original single writer.
 * request low two bits select the mode; high bits change on each mode
 * transition. Frame and exposure consumers require the same request value. */
/* Optional producer diagnostics occupy the original reserved control words.
 * Version zero means this producer does not publish diagnostics. Read seq
 * before and after the snapshot; accept only equal, nonzero, even values.
 * A display task publishes at most once per second, without filesystem work.
 * Diagnostic v2 retains the most recently inspected source across mode-off,
 * lease and pacing failures: reason0=source accepted,1..15=source rejection.
 * Profile failures7..11 share reason7; backing/address failures13..15 share
 * reason13. Every underlying guard remains enforced; descriptor words retain
 * the rejected profile, without spending native code on redundant branches.
 * Separate counters/timestamps expose lease,pacing and post-window rejection.
 * v1 overwrote source fields with each attempt and used reason16..22 for
 * non-source rejection. A descriptor_index of0xffffffff invalidates its words.
 * Pointer/descriptor words are observations, never authority to read pixels. */
typedef struct {
    uint32_t seq, version, entries, mode_off, lease_rejected, pace_rejected;
    uint32_t source_rejected, window_rejected, published;
    uint32_t tick, consumer_tick, request, reason, recipe, config, y, uv;
    uint32_t recipe_kind, descriptor_index, descriptor[8];
} m10v_live_ingress_diagnostic;
typedef struct {
    uint32_t magic, version, bytes, epoch, request;
    m10v_live_ingress_diagnostic diagnostic;
} m10v_live_ingress_control;
typedef struct {
    uint32_t seq, tick, request, reserved0, token[4], reserved[24];
} m10v_live_ingress_shutter;
typedef struct {
    uint32_t seq, tick, request, reserved[29];
    uint8_t data[M10V_LIVE_INGRESS_FRAME_BYTES];
} m10v_live_ingress_frame;
typedef struct {
    m10v_live_ingress_control control;
    m10v_live_ingress_shutter shutter;
    m10v_live_ingress_frame frames[M10V_LIVE_INGRESS_SLOTS];
} m10v_live_ingress;

_Static_assert(sizeof(m10v_live_ingress_offer) == 32, "Live offer ABI");
_Static_assert(sizeof(m10v_live_ingress_diagnostic) == 108, "Live diagnostic reserved ABI");
_Static_assert(sizeof(m10v_live_ingress_control) == 128, "Live control ABI");
_Static_assert(sizeof(m10v_live_ingress_shutter) == 128, "Live exposure ABI");
_Static_assert(sizeof(m10v_live_ingress_frame) == 36992, "Live frame ABI");
_Static_assert(sizeof(m10v_live_ingress) == 111232, "Live arena ABI");

#endif
