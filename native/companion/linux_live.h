#ifndef M10V_LINUX_LIVE_H
#define M10V_LINUX_LIVE_H

#include "linux_target.h"
#include "../gr3/m10v_live_ingress.h"

extern const m10v_live_source m10v_linux_live_source;
int m10v_linux_live_attach(const m10v_live_ingress_offer *, uint32_t epoch);
void m10v_linux_live_sample(m10v_linux_target *, uint64_t now);
#endif
