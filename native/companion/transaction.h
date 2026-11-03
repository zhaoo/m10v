#ifndef M10V_COMPANION_TRANSACTION_H
#define M10V_COMPANION_TRANSACTION_H
#include "operations.h"
enum {M10V_IO_OK=0,M10V_IO_NOT_WRITTEN=1,M10V_IO_UNCERTAIN=2};
typedef struct {uint8_t boot_id[16],build_id[32],catalog_hash[32],renderer_hash[32];uint32_t owner_generation;} m10v_companion_metadata;
typedef struct {unsigned status,code,has_snapshot;m10v_companion_snapshot snapshot;} m10v_companion_result;
typedef struct {uint8_t id[16],digest[32];m10v_companion_result result;m10v_companion_snapshot expected;unsigned present,remote;} m10v_companion_owner_record;
typedef struct {m10v_companion_owner_record remote_cache,pending;} m10v_companion_owner;
typedef struct m10v_companion_owner_services {
 void *ctx;m10v_companion_owner *owner;m10v_companion_metadata metadata;
 /* enter pins the owner allocation and serializes local/remote/capture busy
  * transitions. leave releases the pin; is_current must not touch freed owner. */
 int (*is_current)(void*);int (*enter)(void*);void (*leave)(void*);int (*is_busy)(void*);
 int (*snapshot)(void*,m10v_companion_snapshot*);
 int (*persist_once)(void*,const m10v_library_state*);
 int (*set_tone)(void*,unsigned slot);
 int (*commit_settled)(void*);
 int (*resolve_custom)(void*,unsigned slot,unsigned stable_id,const uint8_t hash[32],unsigned *bank);
} m10v_companion_owner_services;
void m10v_companion_owner_init(m10v_companion_owner*);
void m10v_companion_state_seal(m10v_library_state*,uint32_t sequence);
int m10v_companion_snapshot_identity(const m10v_companion_metadata*,m10v_companion_snapshot*);
int m10v_companion_apply(const m10v_companion_snapshot*,const m10v_companion_patch*,const m10v_companion_owner_services*,m10v_companion_result*);
int m10v_companion_apply_local(const m10v_companion_snapshot*,const m10v_companion_patch*,const m10v_companion_owner_services*,m10v_companion_result*);
int m10v_companion_owner_poll(const m10v_companion_owner_services*,const uint8_t request_id[16],m10v_companion_result*);
#endif
