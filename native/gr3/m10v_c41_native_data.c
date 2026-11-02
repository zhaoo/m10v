/* Read-only ISP profiles linked separately to preserve each module's 64KiB
 * relocation bound. No image access, allocation, file IO or runtime fitting. */
#include <stdint.h>
typedef struct { int16_t matrix[9],post[9]; uint16_t first[3],offset[3]; } native_frame_packed;
_Static_assert(sizeof(native_frame_packed)==48,"lossless profile storage");
#include "m10v_c41_native_profiles.h"
const void *m10v_c41_native_data(uint32_t part,uint32_t index){
 if(index>=sizeof(native_c41_frame)/sizeof(native_c41_frame[0]))return 0;
 if(part==0)return &native_c41_frame[index];
 if(part==1)return native_c41_curve_stream;
 if(part==2)return native_c41_hue[index];
 return 0;
}
