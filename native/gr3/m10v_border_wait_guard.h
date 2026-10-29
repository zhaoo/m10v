#ifndef M10V_BORDER_WAIT_GUARD_H
#define M10V_BORDER_WAIT_GUARD_H
#include <stdint.h>
#include "m10v_border_fill_bundle.h"
/* OFFLINE PROTOTYPE: not linked/installed by any production builder.
 * GR III 2.10 ABI; GR IIIx 1.60 only after installer whole-span validation.
 * First Transfer worker allocation MUST be extended from
 * 0x44 to 0x58 BEFORE its constructor runs; tail is not stock padding.
 * Every owned operation retains client, original caller stack, descriptors,
 * source/destination allocations until exact native notify has fully returned.
 * No timeout, kernel error or fatal counter permits memory release. */
/* REQUIRED admission contract: ONE owned stage gate must serialize the entire
 * frame's private Fill/Resize/Transfer chain. Two private IIP pre-release gates
 * at shared count2 can each wait forever for the other to release. Native
 * ungated producer jobs retain stock behavior. The prototype stores its CAS gate at first Transfer worker+0x54. It does
 * not independently lease that native allocation against factory teardown. */
#define M10V_BORDER_REQUIRES_SERIALIZED_PRIVATE_CHAIN 1
#define M10V_BORDER_TRANSFER_STOCK_BYTES 0x44u
#define M10V_BORDER_TRANSFER_OWNED_BYTES 0x58u
#define M10V_BORDER_CLIENT_TAG 0x42574331u
typedef struct {
 uint32_t native[8];
 uint32_t tag;
 volatile uint32_t pending,inflight,completed,wait_failures;
 uint32_t expected_event,expected_mask,worker,job;
 uint32_t fill_bundle;
 volatile uint32_t bundle_error;
} m10v_border_native_client;
void m10v_border_client_construct(m10v_border_native_client *client);
int m10v_border_client_prepare(m10v_border_native_client *client,uint32_t event,uint32_t mask);
uint32_t m10v_border_client_notify(m10v_border_native_client *client,uint32_t event,uint32_t payload);
/* 0 rejects before enqueue. 1 means exact final callback returned, not silicon
 * acceptance. Error after enqueue fatally retains owners, never returns success.
 * Caller constructs private client and establishes all bundle header prerequisites. */
int m10v_border_fill_bundle_submit(m10v_border_native_client *client,const m10v_border_fill_bundle *bundle);
int m10v_border_client_done(m10v_border_native_client *client);
int m10v_border_client_destroy_if_done(m10v_border_native_client *client);
/* Same ABI as original wait. Stock clients are passed through exactly once.
 * Owned clients retry kernel errors indefinitely; after a consumed completion
 * event they yield for notifier tail instead of waiting on that event again. */
uint32_t m10v_border_client_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout);
/* Called ONLY for an enlarged FIRST Transfer worker. */
void *m10v_border_transfer_construct(void *worker);
uint32_t m10v_border_transfer_body(void *worker,void *parameters,uint32_t *job);
uint32_t m10v_border_transfer_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout,void *worker);
#define M10V_BORDER_FILL_STOCK_BYTES 0x58u
#define M10V_BORDER_FILL_OWNED_BYTES 0x68u
#define M10V_BORDER_RESIZE_STOCK_BYTES 0x48u
#define M10V_BORDER_RESIZE_OWNED_BYTES 0x58u
void *m10v_border_fill_construct(void *worker);
void *m10v_border_resize_construct(void *worker);
uint32_t m10v_border_fill_body(void *worker,void *parameters,uint32_t *job);
uint32_t m10v_border_resize_body(void *worker,void *parameters,uint32_t *job);
uint32_t m10v_border_fill_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout,uint32_t *lower_frame,void *context);
uint32_t m10v_border_resize_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout,uint32_t *lower_frame);
uint32_t m10v_border_resize_dma_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout,void *worker);
/* Private pre-release gates: preserve original reservation until native driver
 * conditions are observed under verified service locks. No abort/reset or DMA
 * idle guarantee. Mismatched reservation/failed unlock fatally retain owners. */
uint32_t m10v_border_fill_release(void *service,uint32_t callback,uint8_t *info,uint32_t *lower_frame,void *context);
uint32_t m10v_border_resize_release(void *service,uint32_t callback,uint8_t *info,uint32_t *lower_frame);
/* Complete-frame private chain serialization. Token MUST be nonzero and unique
 * per live frame, never a shared film ID. Enter only from worker phase, never
 * task submission; Off must not call. Return is first Transfer worker handle.
 * Leave only after every synchronous private operation and callback completed.
 * No factory teardown may occur while any chain owns/waits on this handle. */
uint32_t m10v_border_stage_enter(uint32_t frame_token);
uint32_t m10v_border_stage_leave(uint32_t worker_handle,uint32_t frame_token);
#endif
