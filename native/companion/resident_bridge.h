#ifndef M10V_RESIDENT_BRIDGE_H
#define M10V_RESIDENT_BRIDGE_H
#include <stdint.h>
#define M10V_RESIDENT_MAGIC 0x32434d4du
#define M10V_RESIDENT_PAYLOAD 1024u
/* Linux owns every request line; RTOS owns header and response lines.
 * Allocation is retained until poweroff, independent of script/UI lifetime. */
typedef struct {
 volatile uint32_t sequence;
 uint32_t command,bytes,crc,correlation,code;
 uint8_t padding[104],payload[M10V_RESIDENT_PAYLOAD];
} m10v_resident_message;
typedef struct {
 uint32_t magic,version,bytes,alive,owner,epoch;
 uint8_t build[32],padding[72];
 _Alignas(128) m10v_resident_message request;
 _Alignas(128) m10v_resident_message response;
} m10v_resident_wire;
typedef struct {uint32_t last_sequence,last_crc; m10v_resident_message scratch;} m10v_resident_consumer;
typedef struct {
 void*ctx;
 int (*invalidate_request)(void*,void*,uint32_t);
 int (*clean_response)(void*,void*,uint32_t);
 int (*execute)(void*,uint32_t,const uint8_t*,uint32_t,uint8_t*,uint32_t*);
} m10v_resident_ops;
uint32_t m10v_resident_crc(const m10v_resident_message*,uint32_t sequence);
int m10v_resident_consume(m10v_resident_wire*,m10v_resident_consumer*,const m10v_resident_ops*);
#endif
