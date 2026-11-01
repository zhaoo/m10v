#ifndef M10V_COMPANION_OPERATIONS_H
#define M10V_COMPANION_OPERATIONS_H
#include "generated_contract.h"
#include "../gr3/m10v_library.h"
#include "json.h"
enum {M10V_ERROR_NONE=0,M10V_ERROR_UNAUTHORIZED,M10V_ERROR_UNSUPPORTED_PROTOCOL,M10V_ERROR_UNSUPPORTED_MODEL,M10V_ERROR_INCOMPATIBLE_RENDERER,M10V_ERROR_INVALID_RECIPE,M10V_ERROR_BUSY,M10V_ERROR_REVISION_CONFLICT,M10V_ERROR_STORE_FAILED,M10V_ERROR_READBACK_MISMATCH,M10V_ERROR_BRIDGE_UNAVAILABLE,M10V_ERROR_RESULT_UNKNOWN};
enum {M10V_OPERATION_QUEUED=0,M10V_OPERATION_APPLYING,M10V_OPERATION_COMMITTED,M10V_OPERATION_REJECTED,M10V_OPERATION_UNKNOWN};
#define M10V_CUSTOM_HASH_FIELD (1u<<M10V_FIELD_COUNT)
typedef struct {
 uint8_t request_id[16],boot_id[16],base_revision[32],catalog_hash[32],renderer_hash[32];
 uint16_t fields[M10V_SLOT_COUNT],values[M10V_SLOT_COUNT][M10V_FIELD_COUNT];uint8_t custom_hashes[M10V_SLOT_COUNT][32];
 int8_t activate_slot;uint16_t slots_mask;
} m10v_companion_patch;
typedef struct {
 m10v_library_state state;
 uint8_t custom_hashes[M10V_SLOT_COUNT][32],config_hash[32],revision[32];int8_t active_slot;uint8_t busy;
} m10v_companion_snapshot;
int m10v_operation_parse(const uint8_t*,uint32_t,m10v_companion_patch*);
int m10v_operation_parse_tokens(const uint8_t*,uint32_t,m10v_json_token*,m10v_companion_patch*);
void m10v_operation_digest(const m10v_companion_patch*,uint8_t out[32]);
uint32_t m10v_patch_size(void);
const char*m10v_error_name(unsigned);
#endif
