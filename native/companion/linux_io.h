#ifndef M10V_COMPANION_LINUX_IO_H
#define M10V_COMPANION_LINUX_IO_H
#include "http_server.h"
int m10v_linux_random(void*,uint8_t*,uint32_t);
uint64_t m10v_linux_now_ms(void*);
int m10v_linux_prepare_wifi(m10v_companion_server_config*);
int m10v_linux_pause_ms(unsigned);
#endif
