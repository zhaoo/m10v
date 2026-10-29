#ifndef M10V_SAVE_TRACE_H
#define M10V_SAVE_TRACE_H
#include <stdint.h>
#include "m10v_capture_raw_lifetime.h"
/* No hidden owner. Caller keeps this storage alive through its synchronous
 * bridge call and consumes it only after return. Never put it in appendRX.
 * No pointer in a record is retained for later dereference. */
#define M10V_SAVE_TRACE_CAPACITY 32u
#define M10V_SAVE_RECIPE_BYTES 0x4778u
#define M10V_SAVE_TRACE_BYTES 656u
#define M10V_SAVE_COLOR_OFFSET 0x4a08u
#define M10V_SAVE_COLOR_BYTES 1796u
/* Appended stamp owner is independent of color, HDF and RAW lifetime. */
#define M10V_SAVE_STAMP_OFFSET M10V_CAPTURE_RAW_RECIPE_BYTES
#define M10V_SAVE_STAMP_BYTES 16u
#define M10V_SAVE_RECIPE_EXTENDED_BYTES (M10V_SAVE_STAMP_OFFSET+M10V_SAVE_STAMP_BYTES)
#define M10V_SAVE_STAMP_MAGIC 0x3154534du
typedef struct {uint32_t magic,owner,shooting,direction;} m10v_stamp_recipe;
#define M10V_SAVE_EVENT_RAW_BEFORE 187u
#define M10V_SAVE_EVENT_ALLOC_RESULT 188u
#define M10V_SAVE_EVENT_RELEASE_RETURN 189u
#define M10V_SAVE_TRACE_MAGIC 0x31545653u
#define M10V_SAVE_EVENT_BEGIN 180u
#define M10V_SAVE_EVENT_PAYLOAD 181u
#define M10V_SAVE_EVENT_RETURN 182u
#define M10V_SAVE_EVENT_RAW_SET 183u
#define M10V_SAVE_EVENT_ALLOC 184u
#define M10V_SAVE_EVENT_TRANSFER 185u
#define M10V_SAVE_EVENT_RELEASE 186u
typedef struct {
 uint32_t magic,count,dropped,busy;
 uint32_t events[M10V_SAVE_TRACE_CAPACITY][5];
} m10v_save_trace;
void m10v_save_trace_init(m10v_save_trace *);
uint32_t m10v_save_trace_append(m10v_save_trace *,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
/* Explicit new ABI: trace is caller-owned, task_identity is supplied by the
 * proven caller, never guessed from a storage object or named a recipe. */
uint32_t m10v_save_trace_bridge(uint32_t original_object,uint32_t image_info,m10v_save_trace *,uint32_t task_identity);
uint32_t m10v_save_trace_callback(uint32_t proxy,uint32_t opcode,uint32_t payload);
/* These are data-only helpers for a future owner-propagating integration.
 * There are deliberately no automatic global RAW hooks. */
void m10v_save_trace_raw_set(m10v_save_trace *,uint32_t recipe,uint32_t id,uint32_t input,uint32_t caller);
void m10v_save_trace_allocation(m10v_save_trace *,uint32_t recipe,uint32_t id,uint32_t bytes,uint32_t result);
void m10v_save_trace_transfer(m10v_save_trace *,uint32_t source_recipe,uint32_t target_recipe,uint32_t backing,uint32_t source);
void m10v_save_trace_release(m10v_save_trace *,uint32_t recipe,uint32_t id,uint32_t backing,uint32_t caller);
/* Factory ABI and virtual-setter ABI remain unchanged. The locked factory's
 * sole 0x4778-byte recipe allocation grows by sizeof(trace), initialized before
 * construction. No owner pointer is stored globally or inferred from a buffer. */
uint32_t m10v_save_trace_recipe_alloc(uint32_t bytes);
uint32_t m10v_save_trace_recipe_set(uint32_t recipe,uint32_t id,uint32_t backing);
uint32_t m10v_save_trace_recipe_allocate(uint32_t owner,uint32_t recipe,uint32_t id,uint32_t policy);
uint32_t m10v_save_trace_recipe_release(uint32_t owner,uint32_t recipe,uint32_t id);
/* Called only by an existing filesystem-safe consumer. Copies under a bounded
 * try-lock; no retained references. Return number of five-word records. */
uint32_t m10v_save_trace_recipe_mark(uint32_t recipe,uint32_t event,uint32_t a,uint32_t b,uint32_t c);
uint32_t m10v_save_trace_recipe_take(uint32_t recipe,uint32_t *out,uint32_t capacity);
/* Independent control token; no return value comes from diagnostic records. */
uint32_t m10v_save_trace_recipe_raw_status(uint32_t recipe,uint32_t shooting,uint32_t backing,uint32_t source);
void m10v_save_trace_recipe_pool_return(uint32_t recipe,uint32_t id,uint32_t backing,uint32_t result);
#endif
