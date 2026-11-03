#ifndef M10V_COMPANION_AUTH_H
#define M10V_COMPANION_AUTH_H
#include <stdint.h>
#include "http_parser.h"
typedef struct {uint32_t h[8],used;uint64_t total;uint8_t block[64];} m10v_sha256_context;
void m10v_sha256_init(m10v_sha256_context*);
void m10v_sha256_update(m10v_sha256_context*,const uint8_t*,uint32_t);
void m10v_sha256_finish(m10v_sha256_context*,uint8_t out[32]);
void m10v_sha256(const void*,uint32_t,uint8_t out[32]);
void m10v_hmac256(const void *key,uint32_t key_bytes,const void*,uint32_t,uint8_t out[32]);
int m10v_constant_equal(const uint8_t*,const uint8_t*,uint32_t);
void m10v_hex(const uint8_t*,uint32_t,char*);
int m10v_unhex(const char*,uint32_t,uint8_t*);
typedef int (*m10v_random_bytes)(void*,uint8_t*,uint32_t);
typedef struct {
 uint8_t id[16];uint64_t highwater,window;uint32_t nonce_hashes[64];uint8_t nonce_count,nonce_cursor,valid;
} m10v_auth_session;
typedef struct {
 uint8_t key[32],boot[16];char key_id[33];
 m10v_auth_session sessions[8];uint8_t bootstrap_nonces[128][16];uint32_t bootstrap_count;
 m10v_random_bytes random;void *random_context;
} m10v_auth_state;
int m10v_auth_init(m10v_auth_state*,const uint8_t key[32],const char*key_id,const uint8_t boot[16],m10v_random_bytes,void*);
int m10v_auth_accept(m10v_auth_state*,const m10v_http_request*,const uint8_t*,uint32_t,char session[33]);
int m10v_auth_sign_response(const m10v_auth_state*,const m10v_http_request*,const char *session,unsigned status,const uint8_t*,uint32_t,char signature[65]);
#endif
