#ifndef M10V_LINUX_ROLL_H
#define M10V_LINUX_ROLL_H

#include "../gr3/m10v_roll_recovery.h"
#include "http_server.h"
extern const m10v_roll_index_source m10v_linux_roll_index_source;

enum { M10V_ROLL_LIST_BYTES = 512, M10V_ROLL_PREFIX_BYTES = 4096,
       M10V_ROLL_WORKSPACE_BYTES = 2 * M10V_ROLL_LIST_BYTES + M10V_ROLL_PREFIX_BYTES };
/* The Linux main loop supplies scratch space while no HTTP request is active. */
int m10v_linux_roll_scan(m10v_roll_recovery *, uint8_t *workspace);

#endif
