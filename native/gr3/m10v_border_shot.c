#include "m10v_border_shot.h"
#include "m10v_border_camera.h"
#define SHOT_MAGIC 0x42524400u
#define SHOT_UNAVAILABLE 0x425244ffu
static int valid_word(uint32_t word){
    return (word&~255u)==SHOT_MAGIC&&(word&3u)<=M10V_BORDER_FILM&&((word>>5)&7u)<=M10V_BORDER_PHASE_PREPARED;
}
_Static_assert(M10V_BORDER_SHOT_OFFSET==0x510cu,"border shot layout changed");
_Static_assert(M10V_BORDER_SHOT_OFFSET+4u==M10V_CAPTURE_RAW_TOKEN_OFFSET,"border/RAW overlap");
static __attribute__((always_inline)) inline uint32_t *shot(uint32_t recipe){
    if ((recipe&3u) || recipe<0x55000000u || recipe>0x80000000u-M10V_SAVE_RECIPE_EXTENDED_BYTES ||
        *(const uint32_t *)(uintptr_t)recipe!=0x53d0fc90u ||
        *(const uint32_t *)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC) return 0;
    return (uint32_t *)(uintptr_t)(recipe+M10V_BORDER_SHOT_OFFSET);
}
static uint32_t saved_orientation(uint32_t recipe){
    uint32_t si=*(const volatile uint32_t *)(uintptr_t)(recipe+0x44c8u);
    /* Original53510830 copies exactly74270 bytes into this owned saved SI
     * before the existing5351ea9c producer. Do not read live UI orientation. */
    if((si&3u)||si<0x55000000u||si>0x80000000u-0x74270u)return 0;
    const volatile uint8_t *s=(const volatile uint8_t *)(uintptr_t)si;
    uint32_t override=s[0x71e03],value=override?s[0x71e04]:s[0xc8];
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    if(si!=*(const volatile uint32_t *)(uintptr_t)(recipe+0x44c8u)||
       override!=s[0x71e03]||value!=(override?s[0x71e04]:s[0xc8]))return 0;
    return value==1u?8u:value==2u?3u:value==3u?6u:1u;
}
int m10v_border_shot_freeze(uint32_t recipe){
    uint32_t *p=shot(recipe);if(!p)return 0;
    uint32_t before=__atomic_load_n(p,__ATOMIC_ACQUIRE);
    if(before)return valid_word(before);
    uint32_t style;
    uint32_t frozen=SHOT_UNAVAILABLE;
    if(m10v_border_camera_snapshot(&style)&&style<=M10V_BORDER_FILM){
        uint32_t orientation=style==M10V_BORDER_OFF?1u:saved_orientation(recipe);
        if(orientation)frozen=SHOT_MAGIC|((orientation-1u)<<2)|style;
    }
    uint32_t expected=0;
    if(!__atomic_compare_exchange_n(p,&expected,frozen,0,__ATOMIC_RELEASE,__ATOMIC_ACQUIRE))frozen=expected;
    return valid_word(frozen);
}
int m10v_border_shot_read(uint32_t recipe,uint32_t *style){
    if(!style)return 0;uint32_t *p=shot(recipe);if(!p)return 0;
    uint32_t frozen=__atomic_load_n(p,__ATOMIC_ACQUIRE);
    if(!valid_word(frozen))return 0;
    *style=frozen&3u;return 1;
}
int m10v_border_shot_orientation(uint32_t recipe,uint32_t *orientation){
    if(!orientation)return 0;uint32_t *p=shot(recipe);if(!p)return 0;
    uint32_t frozen=__atomic_load_n(p,__ATOMIC_ACQUIRE);
    if(!valid_word(frozen))return 0;
    *orientation=1u+((frozen>>2)&7u);return 1;
}
uint32_t m10v_border_shot_phase(uint32_t recipe){
    uint32_t *p=shot(recipe);if(!p)return M10V_BORDER_PHASE_UNAVAILABLE;
    uint32_t word=__atomic_load_n(p,__ATOMIC_ACQUIRE);
    return valid_word(word)?((word>>5)&7u):M10V_BORDER_PHASE_UNAVAILABLE;
}
int m10v_border_shot_transition(uint32_t recipe,uint32_t before,uint32_t after){
    if(!((before==0u&&(after==1u||after==5u||after==6u))||
         (before==6u&&(after==1u||after==5u))||(before==1u&&(after==2u||after==5u))||
         (before==2u&&(after==3u||after==4u))))return 0;
    uint32_t *p=shot(recipe);if(!p)return 0;
    uint32_t word=__atomic_load_n(p,__ATOMIC_ACQUIRE);
    if(!valid_word(word)||!(word&3u)||((word>>5)&7u)!=before)return 0;
    uint32_t desired=(word&~224u)|(after<<5);
    return __atomic_compare_exchange_n(p,&word,desired,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
}
