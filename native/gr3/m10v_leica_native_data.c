/* Link the immutable ISP profiles separately from the bounded Still module. */
#include "m10v_isp_frame_color.h"
typedef struct { int16_t matrix[9],post[9]; uint16_t first[3],offset[3]; } native_frame_packed;
_Static_assert(sizeof(native_frame_packed)==48,"lossless profile storage");
#include "m10v_leica_native_profiles.h"

const void *m10v_leica_native_data(uint32_t index, uint32_t part) {
    if (index >= sizeof(native_leica_frame) / sizeof(native_leica_frame[0])) return 0;
    if (part==0) return &native_leica_frame[index];
    if (part==1) return native_leica_hue[index];
    return native_leica_curve_stream;
}
