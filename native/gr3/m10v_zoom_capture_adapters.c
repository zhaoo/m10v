/* GR III 2.10 firmware boundaries. Uninstalled until preimage-checked linker
 * integration supplies the original trampolines. No shared mutable scratch. */
#include "m10v_zoom_capture.h"
#include "m10v_aspect_config.h"
extern uint32_t m10v_zoom_mm(uint32_t bits);
extern uint32_t m10v_zoom_bits(uint32_t mm);
extern void m10v_zoom_original_marker_write(uint32_t, uint32_t);
extern void m10v_zoom_original_marker_read(uint32_t, uint32_t, uint32_t);
extern void m10v_zoom_original_marker_summary(uint32_t, uint32_t, uint32_t);
extern uint32_t m10v_zoom_original_raw_count(uint32_t);
extern uint32_t m10v_zoom_original_raw_value(uint32_t, uint32_t);
extern uint32_t m10v_zoom_capture_raw_bits(uint32_t);
extern void m10v_zoom_capture_native_resolution(uint32_t, uint32_t, uint32_t,
                                               uint16_t *, uint16_t *);
extern uint32_t m10v_zoom_native_ifd_byte(uint32_t, uint32_t);
extern void m10v_zoom_native_ifd_write_byte(uint32_t, uint32_t, uint32_t);
extern void m10v_zoom_native_summary_write(uint32_t, uint32_t, uint32_t);
static uint32_t word(uint32_t p, uint32_t off) {
    return *(const uint32_t *)(uintptr_t)(p + off);
}
static uint32_t read_marker(uint32_t ifd) {
    uint8_t bytes[3];
    unsigned i;
    if (!ifd || word(ifd,8) < 3) return 0;
    for (i=0;i<3;i++) bytes[i]=(uint8_t)m10v_zoom_native_ifd_byte(ifd,i);
    return m10v_zoom_capture_marker_decode(bytes);
}
void m10v_zoom_capture_marker_write(uint32_t context, uint32_t ifd) {
    uint8_t marker[3];
    uint32_t props=context?word(context,0x1c):0;
    uint32_t mm=props?m10v_zoom_mm(word(props,0x7b8)):0;
    if (!ifd || word(ifd,8)<3 || !m10v_zoom_capture_marker_encode(mm,marker)) {
        m10v_zoom_original_marker_write(context,ifd); return;
    }
    for (unsigned i=0;i<3;i++) m10v_zoom_native_ifd_write_byte(ifd,i,marker[i]);
}
void m10v_zoom_capture_marker_read(uint32_t context, uint32_t ifd, uint32_t state) {
    uint32_t mm=read_marker(ifd);
    if (!mm || !state) {m10v_zoom_original_marker_read(context,ifd,state);return;}
    *(uint32_t *)(uintptr_t)(state+0x7b8)=m10v_zoom_bits(mm);
}
void m10v_zoom_capture_marker_summary(uint32_t context, uint32_t summary, uint32_t ifd) {
    uint32_t mm=read_marker(ifd);
    /* Keep native enum handling. Unknown/custom enum is zero, never fake35/50.
     * Caller-side custom icon/text handling remains required separately. */
    m10v_zoom_original_marker_summary(context,summary,ifd);
    if (mm && summary) m10v_zoom_native_summary_write(summary,0x11,(mm*100)/M10V_ZOOM_MIN_MM);
}
uint32_t m10v_zoom_capture_raw_count(uint32_t model) {
    uint32_t mm=m10v_zoom_mm(m10v_zoom_capture_raw_bits(model));
    uint32_t count=m10v_zoom_capture_quality_count(mm);
    return count?count:m10v_zoom_original_raw_count(model);
}
uint32_t m10v_zoom_capture_raw_value(uint32_t model,uint32_t index) {
    uint32_t mm=m10v_zoom_mm(m10v_zoom_capture_raw_bits(model));
    if (m10v_zoom_capture_quality_count(mm)) {
        int value=m10v_zoom_capture_quality_value(mm,index);
        return value<0?0:(uint32_t)value;
    }
    return m10v_zoom_original_raw_value(model,index);
}
int m10v_zoom_capture_resolution(uint32_t bits,uint32_t quality,uint32_t ratio,
                                uint16_t *width,uint16_t *height) {
    uint32_t mm=m10v_zoom_mm(bits);
    uint16_t sw=0,sh=0,qw=0,qh=0;
    m10v_zoom_capture_rect rect;
    if (!m10v_zoom_capture_quality_count(mm) || quality>3 || ratio>(M10V_HALF_FRAME?6u:5u) ||
        !width || !height) return 0;
    m10v_zoom_capture_native_resolution(0x3f800000,0,ratio,&sw,&sh);
    m10v_zoom_capture_native_resolution(0x3f800000,quality,ratio,&qw,&qh);
    if (!m10v_zoom_capture_geometry(mm,sw,sh,qw,qh,&rect)) return 0;
    *width=(uint16_t)rect.output_width;
    *height=(uint16_t)rect.output_height;
    return 1;
}
/* For custom/invalid metadata, suppress a fixed35/50 glyph rather than mislabel it.
 * Caption uses caller-owned numeric resource IDs, never a RAM string pointer. */
extern uint32_t m10v_zoom_caption(uint32_t bits);
uint32_t m10v_zoom_capture_custom(uint32_t bits) {
    return bits != 0x3f800000u && bits != 0x3fa00000u && bits != M10V_ZOOM_DEFAULT_SECOND_BITS;
}
uint32_t m10v_zoom_capture_caption(uint32_t bits) {
    if (!m10v_zoom_capture_custom(bits)) return UINT32_MAX;
    return m10v_zoom_capture_quality_count(m10v_zoom_mm(bits)) ?
        m10v_zoom_caption(bits) : 0;
}
/* Metadata tag0x040c preparation: native caller subsequently offsets AF boxes
 * using state+6a8/+6ac. This is replay geometry, NOT a proven sensor crop hook. */
extern void m10v_zoom_original_replay_rect(uint32_t context);
void m10v_zoom_capture_replay_rect(uint32_t context) {
    uint32_t state=context?word(context,8):0;
    uint32_t mm=state?m10v_zoom_mm(word(state,0x7b8)):0;
    uint32_t ratio=state?*(const uint8_t *)(uintptr_t)(state+0x7b6):0;
    uint16_t w=0,h=0;
    m10v_zoom_capture_rect rect;
    uint32_t qw,qh;
    if (!m10v_zoom_capture_quality_count(mm) || ratio>(M10V_HALF_FRAME?6u:5u)) {
        m10v_zoom_original_replay_rect(context);return;
    }
    m10v_zoom_capture_native_resolution(0x3f800000,0,ratio,&w,&h);
    if (!m10v_zoom_capture_geometry(mm,w,h,w,h,&rect)) {
        m10v_zoom_original_replay_rect(context);return;
    }
    /* All products bounded below2^32: sensor6000x4000 ->45x30Q16. */
    qw=(rect.width*73728u)/150u;
    qh=(rect.height*73728u)/150u;
    *(uint32_t *)(uintptr_t)(state+0x6a0)=qw;
    *(uint32_t *)(uintptr_t)(state+0x6a4)=qh;
    *(uint32_t *)(uintptr_t)(state+0x6a8)=(2949120u-qw)/2u;
    *(uint32_t *)(uintptr_t)(state+0x6ac)=(1966080u-qh)/2u;
}
