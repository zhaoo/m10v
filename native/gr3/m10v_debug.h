#ifndef M10V_DEBUG_H
#define M10V_DEBUG_H
#include <stdint.h>
#ifndef M10V_DEBUG_MODE
#define M10V_DEBUG_MODE 0
#endif
#ifndef M10V_ADJ_EXIT_TRACE
#define M10V_ADJ_EXIT_TRACE 0
#endif
int m10v_debug_batch(const uint32_t *events, uint32_t count);
int m10v_debug_log(uint32_t event, uint32_t a, uint32_t b, uint32_t c, uint32_t d);
#if M10V_DEBUG_MODE
#define M10V_LOG(e,a,b,c,d) ((void)m10v_debug_log((e),(a),(b),(c),(d)))
#else
#define M10V_LOG(e,a,b,c,d) ((void)0)
#endif
#if M10V_DEBUG_MODE && M10V_ADJ_EXIT_TRACE
#define M10V_EXIT_LOG(e,a,b,c,d) ((void)m10v_debug_log((e),(a),(b),(c),(d)))
#else
#define M10V_EXIT_LOG(e,a,b,c,d) ((void)0)
#endif
#endif
