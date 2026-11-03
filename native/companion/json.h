#ifndef M10V_COMPANION_JSON_H
#define M10V_COMPANION_JSON_H
#include <stdint.h>
#define M10V_JSON_TOKENS 512u
#define M10V_JSON_MISSING 65535u
enum {M10V_JSON_OBJECT=1,M10V_JSON_ARRAY,M10V_JSON_STRING,M10V_JSON_NUMBER,M10V_JSON_TRUE,M10V_JSON_FALSE,M10V_JSON_NULL};
typedef struct {uint16_t start,end,next;uint8_t type,count;} m10v_json_token;
/* The v1 write envelope uses unescaped ASCII identifiers/hashes and integers.
 * Unsupported string escapes/floats are rejected, never normalized or stripped. */
int m10v_json_parse(const uint8_t*,uint32_t,m10v_json_token[M10V_JSON_TOKENS],uint16_t*count);
uint16_t m10v_json_get(const uint8_t*,const m10v_json_token*,uint16_t object,const char*key);
int m10v_json_string(const uint8_t*,const m10v_json_token*,char*,uint32_t capacity);
int m10v_json_uint(const uint8_t*,const m10v_json_token*,uint32_t*out);
#endif
