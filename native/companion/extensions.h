#ifndef M10V_COMPANION_EXTENSIONS_H
#define M10V_COMPANION_EXTENSIONS_H
#include "operations.h"
#define M10V_EXTENSIONS_SCHEMA "m10v.extensions/v1"
#define M10V_EXTENSIONS_HASH "f1a60c6593fad7d22ffdbd168c9199567799b2153de15ab84064efcd215f93dc"
#define M10V_EXTENSION_FIELDS 24u
#define M10V_EXTENSION_MASK ((1u<<M10V_EXTENSION_FIELDS)-1u)
enum {M10V_READ_EXTENSIONS=5,M10V_APPLY_EXTENSIONS=6,M10V_POLL_EXTENSIONS=7};
typedef struct {uint32_t available,busy,values[M10V_EXTENSION_FIELDS];uint8_t revision[32];} m10v_extension_snapshot;
typedef struct {uint8_t request_id[16],boot_id[16],contract_hash[32],base_revision[32];uint32_t field,value;} m10v_extension_patch;
typedef struct {uint32_t status,code,has_snapshot;m10v_extension_snapshot snapshot;} m10v_extension_result;
typedef struct {uint8_t id[16],digest[32];uint32_t present;m10v_extension_result result;m10v_extension_snapshot expected;} m10v_extension_record;
typedef struct {m10v_extension_record pending,cache;} m10v_extension_owner;
/* Owner-thread only. enter/leave share the native film/local mutation lock.
 * blocked reports an unresolved FILM transaction; read includes all journal
 * generations and shared library dependencies in its revision. write performs
 * one field write, returning M10V_IO_OK/NOT_WRITTEN/UNCERTAIN (transaction.h).
 * The portable layer never calls write again after uncertainty. */
typedef struct {
 void *ctx;m10v_extension_owner *owner;uint8_t boot_id[16];
 int (*is_current)(void*);int (*enter)(void*);void (*leave)(void*);
 int (*is_busy)(void*);int (*blocked)(void*);
 int (*read)(void*,m10v_extension_snapshot*);
 int (*write)(void*,uint32_t field,uint32_t value);
} m10v_extension_services;
extern const char *const m10v_extension_names[M10V_EXTENSION_FIELDS];
extern const uint8_t m10v_extension_min[M10V_EXTENSION_FIELDS],m10v_extension_max[M10V_EXTENSION_FIELDS],m10v_extension_persistent[M10V_EXTENSION_FIELDS];
int m10v_extensions_parse(const uint8_t*,uint32_t,m10v_json_token*,m10v_extension_patch*);
int m10v_extensions_valid(const m10v_extension_snapshot*);
void m10v_extensions_owner_init(m10v_extension_owner*);
int m10v_extensions_apply(const m10v_extension_patch*,const m10v_extension_services*,m10v_extension_result*);
int m10v_extensions_poll(const uint8_t request_id[16],const m10v_extension_services*,m10v_extension_result*);
#endif
