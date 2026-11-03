#ifndef M10V_COMPANION_LINUX_TARGET_H
#define M10V_COMPANION_LINUX_TARGET_H
#include "http_server.h"
#include "transaction.h"
#include "resident_bridge.h"
/* All values are generated from the same audited final candidate. Fixed ROM
 * anchor addresses are internal; callers supply their exact candidate bytes. */
typedef struct {
 uint8_t build[32],catalog[32],renderer[32],nonce[16],rom[4][16];
 uint32_t timeout_ms;
} m10v_linux_target_config;
typedef struct {
 void *ctx;
 int (*read)(void*,uint32_t,void*,uint32_t);
 int (*write)(void*,uint32_t,const void*,uint32_t);
 int (*bind_request)(void*,uint32_t,uint32_t);
 uint64_t (*now_ms)(void*);
} m10v_linux_target_transport;
typedef struct {
 m10v_linux_target_config config;m10v_linux_target_transport io;
 uint32_t owner,context,wire,epoch,sequence,pending_command,pending_crc;
 uint64_t pending_since;
 uint8_t ready,failed,pending_id[16],pending_digest[32];
 m10v_resident_message scratch;
} m10v_linux_target;
/* Init performs RO discovery only. HELLO starts the first request write.
 * A nonempty mailbox is rejected: no automatic sequence or lease recovery. */
int m10v_linux_target_init(m10v_linux_target*,const m10v_linux_target_config*,const m10v_linux_target_transport*);
int m10v_linux_target_hello(m10v_linux_target*);
int m10v_linux_target_exchange(void*,const m10v_backend_request*,m10v_backend_response*);
/* open uses O_SYNC and separate RO/RW descriptors. Every actual mmap is RO
 * except bounded request publication. Coherency still needs device proof. */
typedef struct {int read_fd,write_fd;uint32_t request,request_bytes;} m10v_linux_devmem;
int m10v_linux_devmem_open(m10v_linux_devmem*,m10v_linux_target_transport*,uint64_t(*now_ms)(void*));
void m10v_linux_devmem_close(m10v_linux_devmem*);
#endif
