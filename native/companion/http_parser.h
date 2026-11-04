#ifndef M10V_COMPANION_HTTP_PARSER_H
#define M10V_COMPANION_HTTP_PARSER_H
#include <stdint.h>
#define M10V_HTTP_MAX_BODY 16384u
#define M10V_HTTP_MAX_HEAD 2048u
typedef struct {
 char method[8],path[96],key_id[33],nonce[33],boot[33],session[33],sequence[21],signature[65],chunk_hash[65];
 uint32_t content_length,fields;
 uint8_t hotspot_host,hotspot_client,browser_origin;
} m10v_http_request;
int m10v_http_parse_head(const char*,uint32_t,m10v_http_request*);
int m10v_http_validate_head(const char*,uint32_t);
#endif
