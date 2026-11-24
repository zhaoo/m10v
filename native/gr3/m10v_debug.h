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
#ifndef M10V_CONTROLS_TRACE_ONLY
#define M10V_CONTROLS_TRACE_ONLY 0
#endif
#if M10V_DEBUG_MODE && (M10V_ADJ_EXIT_TRACE || M10V_CONTROLS_TRACE_ONLY)
/* Match the focused SD logger's existing event filter at compile time, so
 * rejected capture diagnostics do not consume immutable runtime space. */
#if M10V_CONTROLS_TRACE_ONLY
#define M10V_CONTROL_EVENT(e) (((e)>=360u&&(e)<=383u)||((e)>=400u&&(e)<=417u))
#else
#define M10V_CONTROL_EVENT(e) ((e)==198u||(e)==212u||((e)>=230u&&(e)<=315u)||((e)>=360u&&(e)<=383u)||((e)>=400u&&(e)<=417u))
#endif
#define M10V_LOG(e,a,b,c,d) do { const uint32_t m10v_event_=(e); if(M10V_CONTROL_EVENT(m10v_event_)) (void)m10v_debug_log(m10v_event_,(a),(b),(c),(d)); } while(0)
#elif M10V_DEBUG_MODE
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
