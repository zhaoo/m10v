/* Keep the prior authenticated table in its own bounded append-RX object.
 * The main SD validator remains within its existing 64 KiB component budget. */
#include <stdint.h>
#ifndef M10V_SD_PREVIOUS_LINKAGE
#include "m10v_sd_contract.h"
#define M10V_SD_PREVIOUS_LINKAGE
#endif
M10V_SD_PREVIOUS_LINKAGE int m10v_sd_previous_hash(uint32_t id,const uint32_t h[8]){
 if(!h||!((id>=33u&&id<=78u)||(id>=289u&&id<=330u)))return 0;
 uint32_t index=id>=289u?id-243u:id-33u;
 for(uint32_t i=0;i<32u;i++)
  if((uint8_t)(h[i>>2]>>(24u-8u*(i&3u)))!=m10v_sd_pre_directory_count_hashes[index][i])return 0;
 return 1;
}
