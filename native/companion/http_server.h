#ifndef M10V_COMPANION_HTTP_SERVER_H
#define M10V_COMPANION_HTTP_SERVER_H
#include "auth.h"
#define M10V_HTTP_RESPONSE_BYTES 4096u
#include "operations.h"
#include "film_upload.h"
enum {M10V_BACKEND_READ_STATE=1,M10V_BACKEND_SUBMIT,M10V_BACKEND_POLL,M10V_BACKEND_FILM_VERIFY,M10V_BACKEND_FILM_POLL};
typedef struct {m10v_film_upload *upload;const uint8_t *data;} m10v_film_backend_request;
typedef struct {unsigned command;const m10v_companion_patch *patch;const m10v_film_backend_request *film;} m10v_backend_request;
typedef struct {unsigned status,has_snapshot;m10v_companion_snapshot *snapshot;} m10v_backend_response;
/* exchange is one NONBLOCKING owner-mailbox turn. Never retain output pointers
 * or run RTOS/storage calls on Linux. BUSY/asynchronous progress is polled. */
typedef struct {void *ctx;int (*exchange)(void*,const m10v_backend_request*,m10v_backend_response*);} m10v_companion_backend;
typedef struct {
 uint8_t key[32],instance_id[16],build_id[32],catalog_hash[32],renderer_hash[32];char key_id[33];
 m10v_random_bytes random;void *random_ctx;
 uint64_t (*now_ms)(void*);void *clock_ctx;
 uint32_t operation_timeout_ms;
 uint8_t read_state,write_state,upload_film,capture_evidence,wifi_verified;
 uint8_t wifi_address[4];char wifi_interface[16];
} m10v_companion_server_config;
typedef struct {uint8_t request_id[16],digest[32];m10v_companion_snapshot snapshot;uint8_t status,error,has_snapshot,occupied;} m10v_operation_receipt;
typedef struct {
 const m10v_companion_server_config *config;m10v_companion_backend backend;m10v_auth_state auth;
 uint8_t input[M10V_HTTP_MAX_BODY];union {uint8_t bytes[M10V_HTTP_RESPONSE_BYTES];m10v_json_token tokens[M10V_JSON_TOKENS];} output;
 uint8_t staging[12288];union {uint8_t reserved[128];m10v_film_upload upload;} film;uint8_t seen_operations[256];
 m10v_operation_receipt receipts[32];m10v_companion_patch pending_patch;
 m10v_http_request request;uint64_t pending_since;int pending_index;
 uint32_t receipt_cursor,output_bytes,status;char session[33],response_signature[65];uint8_t authenticated;
} m10v_companion_server;
int m10v_companion_server_init(m10v_companion_server*,const m10v_companion_server_config*,const m10v_companion_backend*);
int m10v_companion_process(m10v_companion_server*,const char *head,uint32_t head_bytes,const uint8_t *body,uint32_t body_bytes);
int m10v_companion_process_parsed(m10v_companion_server*,const uint8_t*,uint32_t);
void m10v_companion_bad_request(m10v_companion_server*);
void m10v_companion_tick(m10v_companion_server*);
int m10v_companion_serve(const m10v_companion_server_config*,const m10v_companion_backend*);
#endif
