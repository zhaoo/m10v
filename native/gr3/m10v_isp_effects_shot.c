/* Per-exposure metadata only. No pixel, filesystem, allocator or wait access. */
#include "m10v_isp_effects_shot.h"
#include "m10v_isp_effects_camera.h"
#include "m10v_save_trace.h"
#ifndef M10V_ISP_EFFECTS_SHOT_OFFSET
#error "Builder must allocate the ISP effects shot tail and define its offset"
#endif
_Static_assert(sizeof(m10v_isp_effects_shot_snapshot)==M10V_ISP_EFFECTS_SHOT_BYTES,"effects shot ABI");
_Static_assert(M10V_ISP_EFFECTS_SHOT_OFFSET>=M10V_SAVE_CUSTOM_ISP_OFFSET+M10V_SAVE_CUSTOM_ISP_BYTES&&
    !(M10V_ISP_EFFECTS_SHOT_OFFSET&3u)&&M10V_ISP_EFFECTS_SHOT_OFFSET<=0x2affffa0u,
    "independent effects shot allocation bounds");

static int shot_ram(uint32_t p,uint32_t bytes){
    return !(p&3u)&&p>=0x55000000u&&p<=0x80000000u-bytes;
}
static void shot_copy(void *destination,const void *source,uint32_t bytes){
    volatile uint8_t *out=destination;const volatile uint8_t *in=source;
    for(uint32_t i=0;i<bytes;i++)out[i]=in[i];
}
static m10v_isp_effects_shot_snapshot *shot_storage(uint32_t recipe){
    if(!shot_ram(recipe,M10V_ISP_EFFECTS_SHOT_OFFSET+M10V_ISP_EFFECTS_SHOT_BYTES)||
       *(const uint32_t*)(uintptr_t)recipe!=0x53d0fc90u||
       *(const uint32_t*)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC)return 0;
    const m10v_capture_raw_lifetime *raw=(const void*)(uintptr_t)(recipe+M10V_CAPTURE_RAW_TOKEN_OFFSET);
    /* An existing token supplies a second independent owner identity. Empty
     * legacy token storage is allowed, a partial/foreign token never is. */
    if((raw->magic||raw->owner)&&(raw->magic!=0x31574c52u||raw->owner!=recipe))return 0;
    return (void*)(uintptr_t)(recipe+M10V_ISP_EFFECTS_SHOT_OFFSET);
}
static m10v_isp_effects_shot_snapshot *shot_owned(uint32_t recipe){
    m10v_isp_effects_shot_snapshot *s=shot_storage(recipe);
    if(!s||__atomic_load_n(&s->magic,__ATOMIC_ACQUIRE)!=M10V_ISP_EFFECTS_SHOT_MAGIC||
       s->owner!=recipe)return 0;
    return s;
}
static int shot_geometry(uint32_t width,uint32_t height){
    return width>=2&&height>=2&&width<=6144&&height<=6144&&!((width|height)&1u);
}
static uint32_t shot_workspace(const m10v_isp_effects_settings *s,
    uint32_t width,uint32_t height,uint32_t grain){
    uint32_t plane=((width+15u)&~15u)*height;
    return s->leak_gain?plane*2u:grain?plane*3u/2u:0;
}
static uint32_t shot_enabled(const m10v_isp_effects_shot_snapshot *s){
    return (s->effective_grain_strength?M10V_ISP_EFFECTS_NATIVE_GRAIN:0u)|
        (s->settings.leak_gain?M10V_ISP_EFFECTS_NATIVE_LEAK:0u)|
        (s->settings.blur_gain?M10V_ISP_EFFECTS_NATIVE_BLUR:0u);
}
static int shot_si(uint32_t recipe,uint32_t si){
    return shot_ram(si,4)&&si==*(const volatile uint32_t*)(uintptr_t)(recipe+0x44c8u);
}
static uint32_t shot_orientation(uint32_t recipe,uint32_t si){
    /* Original535f673c and owned border snapshot: saved SI, never live UI.
     * Native53510830 copies exactly74270 bytes before this owning producer. */
    if(!shot_ram(si,0x74270u)||!shot_si(recipe,si))return 0;
    const volatile uint8_t *p=(const volatile uint8_t*)(uintptr_t)si;
    uint32_t override=p[0x71e03],value=override?p[0x71e04]:p[0xc8];
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    if(!shot_si(recipe,si)||override!=p[0x71e03]||value!=(override?p[0x71e04]:p[0xc8]))return 0;
    return value==1u?8u:value==2u?3u:value==3u?6u:1u;
}
static int shot_valid(uint32_t recipe,const m10v_isp_effects_shot_snapshot *s){
    if(s->magic!=M10V_ISP_EFFECTS_SHOT_MAGIC||s->owner!=recipe||s->ready!=1||
       !m10v_isp_effects_validate(&s->settings)||s->planned>1||s->failed>1||
       s->stock_query_valid>1||(!s->stock_query_valid&&s->stock_workspace_bytes)||
       s->stock_workspace_bytes>0x2b000000u)return 0;
    if(s->reserved||(s->saved_orientation!=1&&s->saved_orientation!=3&&s->saved_orientation!=6&&s->saved_orientation!=8)||
       !shot_si(recipe,s->source_si))return 0;
    if(!s->planned)return !s->planned_width&&!s->planned_height&&!s->workspace_bytes&&
        !s->effective_grain_strength&&!s->native_completed&&!s->failed&&
        !s->stock_query_valid&&!s->stock_workspace_bytes;
    if((s->saved_orientation!=1&&s->saved_orientation!=3&&s->saved_orientation!=6&&s->saved_orientation!=8)||
       !shot_si(recipe,s->source_si)||!shot_geometry(s->planned_width,s->planned_height)||
       s->effective_grain_strength>3||
       (s->settings.grain_mode&&s->effective_grain_strength!=s->settings.grain_mode-1u)||
       s->workspace_bytes!=shot_workspace(&s->settings,s->planned_width,s->planned_height,
            s->effective_grain_strength)||(s->native_completed&~shot_enabled(s)))return 0;
    return 1;
}
void m10v_isp_effects_shot_reserve(uint32_t recipe){
    m10v_isp_effects_shot_snapshot *s=shot_storage(recipe);if(!s)return;
    for(uint32_t i=0;i<sizeof(*s)/4;i++)((volatile uint32_t*)s)[i]=0;
    s->owner=recipe;__atomic_store_n(&s->magic,M10V_ISP_EFFECTS_SHOT_MAGIC,__ATOMIC_RELEASE);
}
int m10v_isp_effects_shot_freeze(uint32_t recipe){
    m10v_isp_effects_shot_snapshot *s=shot_owned(recipe);if(!s)return 0;
    uint32_t ready=__atomic_load_n(&s->ready,__ATOMIC_ACQUIRE);
    if(ready)return ready==1&&shot_valid(recipe,s);
    uint32_t expected=0;
    if(!__atomic_compare_exchange_n(&s->ready,&expected,3,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))
        return expected==1&&shot_valid(recipe,s);
    m10v_isp_effects_settings frozen;uint32_t sequence;
    int valid=m10v_isp_effects_camera_snapshot(&frozen,&sequence)&&m10v_isp_effects_validate(&frozen);
    uint32_t si=*(const volatile uint32_t*)(uintptr_t)(recipe+0x44c8u);
    uint32_t orientation=valid?shot_orientation(recipe,si):0;
    valid=valid&&orientation;
    if(valid){frozen.reserved=0;shot_copy(&s->settings,&frozen,sizeof(frozen));s->sequence=sequence;s->source_si=si;s->saved_orientation=orientation;}
    __atomic_store_n(&s->ready,valid?1u:2u,__ATOMIC_RELEASE);
    return valid;
}
int m10v_isp_effects_shot_read(uint32_t recipe,m10v_isp_effects_shot_snapshot *out){
    uint32_t address=(uint32_t)(uintptr_t)out;
    if(!shot_ram(address,sizeof(*out)))return 0;
    m10v_isp_effects_shot_snapshot *s=shot_owned(recipe);if(!s)return 0;
    uint32_t end=recipe+M10V_ISP_EFFECTS_SHOT_OFFSET+M10V_ISP_EFFECTS_SHOT_BYTES;
    if(address<end&&recipe<address+sizeof(*out))return 0;
    if(__atomic_load_n(&s->ready,__ATOMIC_ACQUIRE)!=1)return 0;
    m10v_isp_effects_shot_snapshot local;shot_copy(&local,s,sizeof(local));
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    if(!shot_valid(recipe,&local)||shot_owned(recipe)!=s||
       __atomic_load_n(&s->ready,__ATOMIC_RELAXED)!=1||
       local.planned!=__atomic_load_n(&s->planned,__ATOMIC_ACQUIRE))return 0;
    shot_copy(out,&local,sizeof(local));return 1;
}
int m10v_isp_effects_shot_plan(uint32_t recipe,uint32_t si,uint32_t width,
    uint32_t height,uint32_t slot_grain_strength){
    m10v_isp_effects_shot_snapshot *s=shot_owned(recipe);
    if(!s||!shot_si(recipe,si)||!shot_geometry(width,height)||
       !shot_valid(recipe,s)||s->failed)return 0;
    m10v_isp_effects_snapshot resolved;
    if(!m10v_isp_effects_resolve_snapshot(&s->settings,slot_grain_strength,&resolved))return 0;
    if(s->planned)return s->source_si==si&&s->planned_width==width&&s->planned_height==height&&
        s->effective_grain_strength==resolved.effective_grain_strength;
    uint32_t expected=0;
    if(!__atomic_compare_exchange_n(&s->planned,&expected,2,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return 0;
    s->planned_width=width;s->planned_height=height;
    s->effective_grain_strength=resolved.effective_grain_strength;
    s->workspace_bytes=shot_workspace(&s->settings,width,height,resolved.effective_grain_strength);
    s->source_si=si;
    __atomic_store_n(&s->planned,1,__ATOMIC_RELEASE);return 1;
}
int m10v_isp_effects_shot_complete(uint32_t recipe,uint32_t si,uint32_t flags){
    m10v_isp_effects_shot_snapshot *s=shot_owned(recipe);
    if(!s||!shot_valid(recipe,s)||!s->planned||s->failed||s->source_si!=si||
       !shot_si(recipe,si)||!flags||(flags&~shot_enabled(s)))return 0;
    __atomic_fetch_or(&s->native_completed,flags,__ATOMIC_ACQ_REL);return 1;
}
void m10v_isp_effects_shot_fail(uint32_t recipe,uint32_t si){
    m10v_isp_effects_shot_snapshot *s=shot_owned(recipe);
    if(!s||!shot_valid(recipe,s)||!s->planned||s->source_si!=si||!shot_si(recipe,si))return;
    __atomic_store_n(&s->failed,1,__ATOMIC_RELEASE);
}
int m10v_isp_effects_shot_stock_query(uint32_t recipe,uint32_t si,uint32_t bytes){
    m10v_isp_effects_shot_snapshot *s=shot_owned(recipe);
    if(!s||!shot_valid(recipe,s)||!s->planned||s->failed||s->source_si!=si||
       !shot_si(recipe,si)||bytes>0x2b000000u)return 0;
    if(s->stock_query_valid)return s->stock_workspace_bytes==bytes;
    s->stock_workspace_bytes=bytes;
    __atomic_store_n(&s->stock_query_valid,1,__ATOMIC_RELEASE);return 1;
}
int m10v_isp_effects_shot_unavailable(uint32_t recipe,uint32_t si){
    m10v_isp_effects_shot_snapshot *s=shot_owned(recipe);
    if(!s||!shot_si(recipe,si)||__atomic_load_n(&s->ready,__ATOMIC_ACQUIRE)!=2)return 0;
    const volatile uint32_t *p=(const volatile uint32_t*)s;
    for(uint32_t i=3;i<sizeof(*s)/4u;i++)if(p[i])return 0;
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    return shot_owned(recipe)==s&&shot_si(recipe,si)&&
        __atomic_load_n(&s->ready,__ATOMIC_RELAXED)==2;
}
