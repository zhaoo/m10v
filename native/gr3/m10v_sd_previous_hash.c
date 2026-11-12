/* Keep the prior authenticated table in its own bounded append-RX object.
 * The main SD validator remains within its existing 64 KiB component budget. */
#include <stdint.h>
#ifndef M10V_SD_PREVIOUS_LINKAGE
#include "m10v_sd_contract.h"
#define M10V_SD_PREVIOUS_LINKAGE
#endif
M10V_SD_PREVIOUS_LINKAGE int m10v_sd_previous_hash(uint32_t id,const uint32_t h[8]){
 if(!h)return 0;
 if((id>=33u&&id<=78u)||(id>=289u&&id<=330u)){
  uint32_t index=id>=289u?id-243u:id-33u;
  uint32_t before_directory=1,before_leica=1;
  for(uint32_t i=0;i<32u;i++){
   uint8_t byte=(uint8_t)(h[i>>2]>>(24u-8u*(i&3u)));
   if(byte!=m10v_sd_pre_directory_count_hashes[index][i])before_directory=0;
   if(byte!=m10v_sd_pre_leica_hashes[index][i])before_leica=0;
  }
  if(before_directory||before_leica)return 1;
 }
 for(uint32_t index=0;index<64u;index++){
  if(id!=m10v_sd_leica_rc1_ids[index])continue;
  for(uint32_t i=0;i<32u;i++)
   if((uint8_t)(h[i>>2]>>(24u-8u*(i&3u)))!=m10v_sd_leica_rc1_hashes[index][i])return 0;
  return 1;
 }
 return 0;
}
