#ifndef M10V_COMPANION_MAILBOX_H
#define M10V_COMPANION_MAILBOX_H
#include <stdint.h>
#define M10V_COMPANION_CAPACITY 16384u
#define M10V_COMPANION_MAGIC 0x31434d4du
#define M10V_COMPANION_PROTOCOL 1u

enum {M10V_COMPANION_OK=0,M10V_COMPANION_INVALID=1,M10V_COMPANION_BRIDGE_UNAVAILABLE=2,M10V_COMPANION_BUSY=3,M10V_COMPANION_DISABLED=4};
enum {M10V_PING=1,M10V_READ_CAPABILITIES=2,M10V_READ_STATE=3,M10V_APPLY_PATCH=4};
typedef struct {
 uint32_t magic,protocol,capacity,owner_generation;
 volatile uint32_t request_sequence,response_sequence;
 uint32_t command,request_length,request_crc,response_length,response_crc,response_code,last_consumed;
 uint8_t request_payload[M10V_COMPANION_CAPACITY],response_payload[M10V_COMPANION_CAPACITY];
} m10v_companion_mailbox;
typedef struct {uint32_t generation,sequence,command;const uint8_t *payload;uint32_t length;} m10v_companion_request;
typedef struct {uint32_t sequence,code,length;uint8_t payload[M10V_COMPANION_CAPACITY];} m10v_companion_response;
/* Returns 1 only if the maintenance operation completed on the relevant CPU.
 * Never replace these with fences or one-time install cache flushes on target. */
typedef int (*m10v_companion_cache)(void*,void*,uint32_t);
typedef struct {
 m10v_companion_mailbox *mailbox;void *ctx;uint32_t owner_generation;
 /* Lease callbacks pin resident allocation through generation invalidation. */
 int (*acquire_owner)(void*,uint32_t);void (*release_owner)(void*,uint32_t);
 int (*is_owner_alive)(void*,uint32_t);
 m10v_companion_cache producer_flush,consumer_invalidate,consumer_flush,producer_invalidate;
 int (*wake_owner)(void*);
 unsigned in_flight;
} m10v_companion_channel;
struct m10v_companion_target;
void m10v_companion_mailbox_init(m10v_companion_mailbox*,uint32_t generation);
int m10v_companion_exchange(m10v_companion_channel*,const m10v_companion_request*,m10v_companion_response*);
int m10v_companion_consume(m10v_companion_channel*,const struct m10v_companion_target*);
#endif
