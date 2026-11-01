#ifndef M10V_LINUX_WIFI_H
#define M10V_LINUX_WIFI_H
#include <stdint.h>
/* IFCONF returns bytes written; other ioctls return zero on success.
 * The wrapper owns architecture-specific struct ifconf packing. */
typedef int (*m10v_wifi_query)(void*,unsigned,void*,unsigned);
int m10v_linux_wifi_discover(void*,m10v_wifi_query,char name[16]);
#endif
