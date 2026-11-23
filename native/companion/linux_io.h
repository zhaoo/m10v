#ifndef M10V_COMPANION_LINUX_IO_H
#define M10V_COMPANION_LINUX_IO_H
#include "http_server.h"
int m10v_linux_random(void*,uint8_t*,uint32_t);
uint64_t m10v_linux_now_ms(void*);
int m10v_linux_prepare_wifi(m10v_companion_server_config*);
int m10v_linux_pause_ms(unsigned);
#ifndef M10V_COMPANION_DIAGNOSTICS
#define M10V_COMPANION_DIAGNOSTICS 0
#endif
#if M10V_COMPANION_LIVE_SOURCE && M10V_COMPANION_DIAGNOSTICS
void m10v_linux_diagnostics_start(void);
void m10v_linux_trace(const char *, const uint32_t *, unsigned);
#else
#define m10v_linux_trace(...) ((void)0)
#define m10v_linux_diagnostics_start() ((void)0)
#endif
#if M10V_ROLL_LINUX_SERVICE
void m10v_linux_roll_idle(void);
#endif
#endif
