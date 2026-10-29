#ifndef M10V_CUSTOM_ISP_H
#define M10V_CUSTOM_ISP_H
#include "m10v_isp_frame_color.h"
#include "m10v_sd_library.h"
#define M10V_CUSTOM_ISP_OFFSET 6688u
#define M10V_CUSTOM_ISP_BYTES 1572u
#define M10V_CUSTOM_ISP_END 8276u
_Static_assert(sizeof(m10v_isp_frame_target)==M10V_CUSTOM_ISP_BYTES,"custom ISP payload");
/* Optional versioned extension in formerly zero reserved bytes. Old firmware
 * rejects it; old zero-extension records remain valid on this firmware. */
static inline int m10v_custom_isp_valid(const uint8_t *record){
 const uint8_t *p=record+M10V_CUSTOM_ISP_OFFSET;
 if(!m10v_sd_u32(p)){
  for(uint32_t i=M10V_CUSTOM_ISP_OFFSET;i<8448;i++)if(record[i])return 0;
  return 1;
 }
 if(m10v_sd_u32(p)!=0x5053494du||m10v_sd_u32(p+4)!=1||m10v_sd_u32(p+8)!=M10V_CUSTOM_ISP_BYTES||
    m10v_sd_crc(p+16,M10V_CUSTOM_ISP_BYTES)!=m10v_sd_u32(p+12))return 0;
 for(uint32_t bank=0;bank<2;bank++)for(uint32_t row=0;row<3;row++){
  int sum=0;
  for(uint32_t col=0;col<3;col++){
   uint32_t at=16+(bank*9+row*3+col)*2;
   sum+=(int16_t)((uint32_t)p[at]|((uint32_t)p[at+1]<<8));
  }
  if(sum!=(bank?512:8192))return 0;
 }
 for(uint32_t c=0;c<3;c++)for(uint32_t i=0,previous=0;i<256;i++){
  uint32_t at=16+36+(c*256+i)*2,value=(uint32_t)p[at]|((uint32_t)p[at+1]<<8);
  if(value>16383||value<previous)return 0;previous=value;
 }
 for(uint32_t i=M10V_CUSTOM_ISP_END;i<8448;i++)if(record[i])return 0;
 return 1;
}
/* UI validates a complete record before publishing. Capture never reads SD. */
int m10v_camera_library_custom_profile(const m10v_library_state *,uint32_t,m10v_isp_frame_target *);
#endif
