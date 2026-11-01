#ifndef M10V_COMPANION_TARGET_ADAPTER_H
#define M10V_COMPANION_TARGET_ADAPTER_H
#include "mailbox.h"
/* Consumer calls run on the verified RTOS owner, never Linux or capture hooks.
 * The callback uses an output capacity in *length and returns actual length. */
typedef struct m10v_companion_target {
 void *ctx;
 int (*snapshot)(void*,unsigned command,uint8_t*,uint32_t *length);
 int (*is_busy)(void*);
 int (*wake_owner)(void*);
 int (*is_owner_alive)(void*,uint32_t generation);
} m10v_companion_target;
/* Current GR III adapter explicitly unavailable until evidence is supplied by
 * a reviewed target implementation. There is no runtime bypass/ready bit. */
const m10v_companion_target *m10v_gr3_companion_target(void);
struct m10v_companion_owner_services;
int m10v_gr3_companion_owner_available(void);
const struct m10v_companion_owner_services *m10v_gr3_companion_owner_services(void);
#endif
