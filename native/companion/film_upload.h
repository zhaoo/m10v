#ifndef M10V_COMPANION_FILM_UPLOAD_H
#define M10V_COMPANION_FILM_UPLOAD_H
#include "auth.h"
#include "transaction.h"
#define M10V_FILM_BYTES 12288u
#define M10V_FILM_CHUNK_BYTES 4096u
enum {M10V_UPLOAD_EMPTY=0,M10V_UPLOAD_RECEIVING,M10V_UPLOAD_VERIFYING,M10V_UPLOAD_VERIFIED,M10V_UPLOAD_FAILED,M10V_UPLOAD_UNKNOWN};
typedef struct {uint8_t renderer_hash[32],content_hash[32];uint32_t size,chunk_bytes;uint16_t model,schema,stable_id;uint8_t target_slot;} m10v_film_upload_metadata;
typedef struct {m10v_film_upload_metadata metadata;uint8_t id[16];uint32_t received;uint8_t state,bank,error;} m10v_film_upload;
/* Owner-only bounded storage API. enter pins the shared local/remote/capture
 * domain. references includes configured AND queued-capture bank references;
 * unknown references refuse replacement. Linux must never implement this via
 * the photo filesystem. No configuration or tone changes occur here. */
typedef struct {void*ctx;int(*is_current)(void*);int(*enter)(void*);void(*leave)(void*);int(*is_busy)(void*);int(*references)(void*,unsigned slot,unsigned*mask);int(*store_once)(void*,unsigned slot,unsigned bank,const uint8_t*,uint32_t);int(*read)(void*,unsigned slot,unsigned bank,uint32_t offset,uint8_t*,uint32_t);} m10v_film_bank_services;
int m10v_companion_upload_parse(const uint8_t*,uint32_t,m10v_json_token*,m10v_film_upload_metadata*);
int m10v_companion_stage_begin(m10v_film_upload*,const m10v_film_upload_metadata*,const uint8_t id[16],const uint8_t renderer[32]);
int m10v_companion_stage_chunk(m10v_film_upload*,uint8_t staging[M10V_FILM_BYTES],const uint8_t id[16],unsigned index,const uint8_t*,uint32_t,const uint8_t hash[32]);
int m10v_companion_stage_validate(m10v_film_upload*,const uint8_t*,const uint8_t id[16]);
int m10v_companion_stage_verify(m10v_film_upload*,const uint8_t*,const uint8_t id[16],const m10v_film_bank_services*);
#endif
