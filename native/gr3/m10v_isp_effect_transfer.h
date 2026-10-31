#ifndef M10V_ISP_EFFECT_TRANSFER_H
#define M10V_ISP_EFFECT_TRANSFER_H
#include <stdint.h>
/* Immutable build-time NV12 asset in the checked append-RX range. Byte counts
 * include both planes; camera code never initializes/decompresses these pixels. */
typedef struct {
    uint32_t base,bytes,width,height,stride;
} m10v_isp_effect_texture;
typedef struct {
    uint32_t source[8],destination[8],workspace_bytes;
} m10v_isp_effect_transfer;
/* Prepare original public Resize descriptors for two REAL planes. Only metadata
 * is read/written. Workspace must be a separately reserved, exclusively owned
 * native allocation; addresses alone do not prove its lifetime or reservation.
 * out must be ordinary caller-owned RAM, disjoint from texture metadata.
 * 0: zero-sized disabled request, no mutation. -1: rejection, no mutation.
 * 1: metadata prepared, NOT hardware execution/completion or DMA admission. */
int m10v_isp_effect_transfer_plan(const m10v_isp_effect_texture *texture,
    uint32_t workspace,uint32_t capacity,uint32_t width,uint32_t height,
    uint32_t source_width,uint32_t source_height,uint32_t phase,
    m10v_isp_effect_transfer *out);
/* Explicit destination format: 1 is two-plane YUV422 (full-height chroma,
 * 2*stride*height bytes); 2 is NV12 (half-height chroma, 3/2 bytes).
 * Source remains a two-real-plane immutable NV12 asset. Same ownership and
 * no-mutation-on-rejection contract; legacy plan() is exactly format2. */
int m10v_isp_effect_transfer_plan_format(const m10v_isp_effect_texture *texture,
    uint32_t workspace,uint32_t capacity,uint32_t width,uint32_t height,
    uint32_t source_width,uint32_t source_height,uint32_t phase,uint32_t format,
    m10v_isp_effect_transfer *out);
#endif
