#ifndef M10V_RECORDED_FILM_H
#define M10V_RECORDED_FILM_H

#include "m10v_library.h"

typedef struct {
    uint32_t id;
    uint32_t bank; /* Zero for built-ins, 21–255 for immutable custom records. */
} m10v_recorded_film;

#define M10V_RECORDED_BUILTIN_BASE 0x1000u
#define M10V_RECORDED_CUSTOM_BASE 0x2000u
#define M10V_RECORDED_CUSTOM_FIRST_BANK 21u
#define M10V_RECORDED_CUSTOM_BANKS 235u
#define M10V_RECORDED_CUSTOM_FIRST_ID (M10V_FILM_COUNT + 1u)
#define M10V_RECORDED_CUSTOM_END (M10V_RECORDED_CUSTOM_BASE + \
    (M10V_CUSTOM_MAX_ID - M10V_FILM_COUNT) * M10V_RECORDED_CUSTOM_BANKS)

static inline uint32_t m10v_recorded_film_code(uint32_t id,uint32_t bank){
    if(M10V_BUILTIN(id))return M10V_RECORDED_BUILTIN_BASE+id;
    uint32_t version=bank-M10V_RECORDED_CUSTOM_FIRST_BANK;
    if(!M10V_CUSTOM(id)||version>=M10V_RECORDED_CUSTOM_BANKS)return 0;
    return M10V_RECORDED_CUSTOM_BASE+
        (id-M10V_RECORDED_CUSTOM_FIRST_ID)*M10V_RECORDED_CUSTOM_BANKS+version;
}

/* Decode only stable photograph identities. Legacy slot numbers do not name
 * a film. Missing custom banks must be handled by the consumer, independently
 * of current slot assignments. Invalid input leaves the destination alone. */
static inline uint32_t m10v_recorded_film_read(uint32_t code,m10v_recorded_film *out){
    uint32_t id=code-M10V_RECORDED_BUILTIN_BASE,bank=0;
    if(code>=M10V_RECORDED_CUSTOM_BASE&&code<M10V_RECORDED_CUSTOM_END){
        uint32_t version=code-M10V_RECORDED_CUSTOM_BASE;
        id=M10V_RECORDED_CUSTOM_FIRST_ID+version/M10V_RECORDED_CUSTOM_BANKS;
        bank=M10V_RECORDED_CUSTOM_FIRST_BANK+version%M10V_RECORDED_CUSTOM_BANKS;
    }else if(!M10V_BUILTIN(id))return 0;
    out->id=id;
    out->bank=bank;
    return 1;
}

#endif
