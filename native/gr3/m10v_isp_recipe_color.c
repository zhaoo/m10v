#include "m10v_tone.h"
#include "m10v_isp_recipe_color.h"
#include <stddef.h>
#if M10V_BORDER_SHOT
#include "m10v_border_shot.h"
#endif
#if M10V_ISP_NATIVE_LOOK
#include "m10v_isp_native_look.h"
#endif
#ifndef M10V_ISP_RECIPE_COLOR_OBSERVER
#define M10V_ISP_RECIPE_COLOR_OBSERVER 1
#endif
#ifndef M10V_ISP_RECIPE_COLOR_PRODUCER
#define M10V_ISP_RECIPE_COLOR_PRODUCER 0
#endif
#if M10V_ISP_SHARED_HDF
extern void m10v_hdf_task_snapshot(uint32_t);
extern uint32_t m10v_hdf_settings(uint32_t,uint32_t);
extern void m10v_hdf_done(uint32_t,uint32_t,uint32_t);
#endif
_Static_assert(sizeof(m10v_isp_recipe_color)==M10V_SAVE_COLOR_BYTES,"recipe color extent");
_Static_assert(sizeof(m10v_stamp_recipe)==M10V_SAVE_STAMP_BYTES,"stamp extent");
_Static_assert(M10V_SAVE_COLOR_OFFSET+M10V_SAVE_COLOR_BYTES<=M10V_CAPTURE_RAW_TOKEN_OFFSET,"color before RAW token");
_Static_assert(M10V_CAPTURE_RAW_TOKEN_OFFSET+M10V_CAPTURE_RAW_TOKEN_BYTES<=M10V_SAVE_STAMP_OFFSET,"RAW and HDF before stamp owner");
_Static_assert(M10V_SAVE_STAMP_OFFSET+M10V_SAVE_STAMP_BYTES==M10V_SAVE_RECIPE_EXTENDED_BYTES,"stamp allocation extent");
#if M10V_ISP_RECIPE_COLOR_PRODUCER || M10V_ISP_LIVE_COLOR
static int config_ram(uintptr_t p,uint32_t bytes){return !(p&3)&&p>=0x55000000u&&p<=0x80000000u-bytes;}
#endif
#if M10V_ISP_LIVE_COLOR
/* Original UI Property singleton: 5320b31c returns 55063f30 only after
 * guard55063ed0. Shooting setters5327b394/b3b4/b3d4 write data+1c2/4/6
 * synchronously; getter53244284 selects the bank via data+1c0. This UI
 * commit precedes the backend copy used by53549ee8, which camera logs show
 * can still describe the previous film on the first exposure. Borrow scalar
 * bytes only: no singleton initialization, mutex, allocation or retained data. */
static uint32_t ui_shooting_tone(void){
    if(!(*(const volatile uint32_t *)0x55063ed0u&1u))return 0;
    uintptr_t data=__atomic_load_n((const uint32_t *)0x55063f34u,__ATOMIC_ACQUIRE);
    if(!config_ram(data,0x1c8))return 0;
    const volatile uint8_t *p=(const volatile uint8_t *)data;
    uint32_t bank=p[0x1c0];if(bank>2)return 0;
    uint32_t tone=p[0x1c2+bank*2];
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    if(data!=__atomic_load_n((const uint32_t *)0x55063f34u,__ATOMIC_RELAXED)||
       bank!=p[0x1c0]||tone!=p[0x1c2+bank*2]||
       !(*(const volatile uint32_t *)0x55063ed0u&1u))return 0;
    return m10v_tone_valid(tone)?tone:0;
}
/* Original active-tone getter 532bd6b4 -> 53549ee8 -> 5355155c.
 * Singleton53525d5c owns guard553458ac and backend553458b0; ctor53543198
 * installs vptr53d1a528 and config+518. Config[0] is committed after5355198c.
 * Its retained singleton owns the two configuration buffers; we borrow them
 * only during this read and never initialize or retain a backend pointer.
 * Only a fallback when the UI Property is unavailable. Never assume this
 * backend is newer than the front-end selection. Read without its mutex;
 * reject a concurrent buffer swap and preserve the frame's own tone on failure. */
static uint32_t committed_tone(uint32_t fallback){
    uint32_t ui=ui_shooting_tone();if(ui)return ui;
    if(!(*(const volatile uint32_t *)0x553458acu&1u))return fallback;
    uintptr_t backend=*(const volatile uint32_t *)0x553458b0u;
    if(!config_ram(backend,0x51c)||*(const volatile uint32_t *)backend!=0x53d1a528u)return fallback;
    uintptr_t config=*(const volatile uint32_t *)(backend+0x518u);
    if(!config_ram(config,8))return fallback;
    uintptr_t current=__atomic_load_n((const uint32_t *)config,__ATOMIC_ACQUIRE);
    if(!config_ram(current,0x1040))return fallback;
    uint32_t tone=*(const volatile uint8_t *)(current+0x77cu);
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    if(current!=__atomic_load_n((const uint32_t *)config,__ATOMIC_RELAXED)||
       config!=*(const volatile uint32_t *)(backend+0x518u)||
       backend!=*(const volatile uint32_t *)0x553458b0u)return fallback;
    return m10v_tone_valid(tone)?tone:fallback;
}
#endif
static uint32_t selected_tone(const m10v_isp_recipe_color *s,uint32_t frame_tone){
    return s->selected_tone?s->selected_tone:frame_tone;
}
static m10v_isp_recipe_color *owned(void *recipe){
    uintptr_t address=(uintptr_t)recipe;
    if((address&3)||address<0x55000000u||address>0x80000000u-M10V_SAVE_RECIPE_EXTENDED_BYTES||
       *(uint32_t *)recipe!=0x53d0fc90u)return 0;
    /* Factory extension initializes trace first; never probe beyond stock
     * object based on a coincidental vptr alone. Integration installs the sole
     * factory allocation hook together with this module. */
    if(*(uint32_t *)((uint8_t *)recipe+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC)return 0;
    return (m10v_isp_recipe_color *)((uint8_t *)recipe+M10V_SAVE_COLOR_OFFSET);
}
static m10v_isp_recipe_color *from_context(const void *context){
    if(!context)return 0;
    uintptr_t parameters=((const uint32_t *)context)[0x30/4];
    if(parameters<0x1a8)return 0;
    return owned((void *)(parameters-0x1a8));
}
int m10v_isp_frame_recipe_snapshot(void *recipe,const m10v_library_state *state){
    m10v_isp_recipe_color *s=owned(recipe);
    if(!s||!m10v_library_valid(state))return 0;
    if(s->magic==M10V_ISP_RECIPE_COLOR_MAGIC&&s->busy)return 0;
    s->magic=0;
    ((m10v_stamp_recipe *)((uint8_t *)recipe+M10V_SAVE_STAMP_OFFSET))->magic=0;
    for(uint32_t i=0;i<sizeof(*state);i++)((uint8_t *)&s->state)[i]=((const uint8_t *)state)[i];
    s->version=1;s->bytes=sizeof(*s);s->status=M10V_ISP_RECIPE_READY;
    s->sequence=state->sequence;s->tone=0;s->selected_tone=0;s->si=0;
    s->info=0;s->tuning=0;s->busy=0;
#if M10V_ISP_NATIVE_GRAIN_MODE
    s->native_grain.magic=0;
#endif
    s->magic=M10V_ISP_RECIPE_COLOR_MAGIC;
    return 1;
}
uint32_t m10v_isp_frame_recipe_direction(void *recipe,uint32_t shooting){
    m10v_isp_recipe_color *s=owned(recipe);
    if(!s||s->magic!=M10V_ISP_RECIPE_COLOR_MAGIC||s->version!=1||s->bytes!=sizeof(*s)||s->status==M10V_ISP_RECIPE_MUTATING)return 0;
    const m10v_stamp_recipe *stamp=(const m10v_stamp_recipe *)((const uint8_t *)recipe+M10V_SAVE_STAMP_OFFSET);
    if(stamp->magic!=M10V_SAVE_STAMP_MAGIC||stamp->owner!=(uint32_t)(uintptr_t)recipe||stamp->shooting!=shooting||stamp->direction>3)return 0;
    return stamp->direction;
}
int m10v_isp_frame_recipe_state(void *recipe,m10v_library_state *out){
    m10v_isp_recipe_color *s=owned(recipe);
    if(!s||!out||s->status==M10V_ISP_RECIPE_MUTATING||s->magic!=M10V_ISP_RECIPE_COLOR_MAGIC||s->version!=1||s->bytes!=sizeof(*s))return 0;
    for(uint32_t i=0;i<sizeof(*out);i++)((uint8_t *)out)[i]=((const uint8_t *)&s->state)[i];
    return m10v_library_valid(out);
}
static int producer_mutating(m10v_isp_recipe_color *s){
 s->version=1;s->bytes=sizeof(*s);s->status=M10V_ISP_RECIPE_MUTATING;s->busy=0;s->selected_tone=0;s->magic=M10V_ISP_RECIPE_COLOR_MAGIC;return 0;
}
int m10v_isp_frame_recipe_producer(void *recipe){
#if M10V_ISP_RECIPE_COLOR_PRODUCER
#if M10V_ISP_SHARED_HDF
    m10v_hdf_task_snapshot((uint32_t)(uintptr_t)recipe);
#endif
    m10v_isp_recipe_color *s=owned(recipe);
    if(!s)return 0;
#if M10V_BORDER_SHOT
    /* Independent of film carriers: stock ImageControl also gets borders.
     * Freeze before this first processing task is enqueued. */
    m10v_border_shot_freeze((uint32_t)(uintptr_t)recipe);
#endif
    if(s->magic==M10V_ISP_RECIPE_COLOR_MAGIC)return 1;
    /* Original5351ea9c receives THIS recipe in r1 before constructing and
     * sending its first processing packet. 5351ae2c is buffer retirement,
     * not processing submission. Freeze once; later commands/UI cannot
     * retarget this shot. The scheduler may hold backend locks, so this
     * helper only reads the already published owner cache: no FS/alloc/lock. */
    m10v_library_state state;
    if(m10v_camera_library_mutation_busy())return producer_mutating(s);
    if(!m10v_camera_library_preview(&state))return 0;
    if(state.reserved&510u)return producer_mutating(s);
    uintptr_t si=*(const uint32_t *)((const uint8_t *)recipe+0x44c8u);
    if(!config_ram(si,0x94c))return 0;
    uint32_t producer_tone=((const volatile uint8_t *)si)[0x77c];
    if(!m10v_tone_valid(producer_tone))return 0;
    if(m10v_camera_library_mutation_busy())return producer_mutating(s);
    m10v_library_state verify;
    if(!m10v_camera_library_preview(&verify)||verify.sequence!=state.sequence)return producer_mutating(s);
    if(si!=*(const uint32_t *)((const uint8_t *)recipe+0x44c8u)||
       producer_tone!=((const volatile uint8_t *)si)[0x77c])return producer_mutating(s);
    if(!m10v_isp_frame_recipe_snapshot(recipe,&state))return 0;
    /* The exposed frame owns its tone. UI Property can already name a later
     * shot by task submission; never use it to recolor a queued exposure. */
    s->selected_tone=(uint16_t)producer_tone;
    if(state.stamp||(state.reserved&1u)){
        /* Read this recipe's ShootingInfo, precisely the byte bound by the
         * official EXIF setter535f63d0. Never sample the live/UI singleton:
         * its direction can belong to a later exposure at this task ingress. */
        m10v_stamp_recipe *stamp=(m10v_stamp_recipe *)((uint8_t *)recipe+M10V_SAVE_STAMP_OFFSET);
        uint32_t direction=((const uint8_t *)si)[0xc8];
        stamp->owner=(uint32_t)(uintptr_t)recipe;stamp->shooting=(uint32_t)si;
        stamp->direction=direction<=3?direction:0;
        stamp->magic=M10V_SAVE_STAMP_MAGIC;
    }
    return 1;
#else
    (void)recipe;return 0;
#endif
}
int m10v_isp_frame_recipe_begin(const void *context,void *tuning,void *info){
    m10v_isp_recipe_color *s=from_context(context);
    if(!s||s->magic!=M10V_ISP_RECIPE_COLOR_MAGIC||s->version!=1||s->bytes!=sizeof(*s)||
       (s->status!=M10V_ISP_RECIPE_READY&&s->status!=M10V_ISP_RECIPE_APPLIED&&s->status!=M10V_ISP_RECIPE_OBSERVED)||s->busy||!tuning||!info||
       *(uint32_t *)tuning!=0x53dbd8a0u)return 0;
#if M10V_ISP_NATIVE_LOOK
    /* Native completion is consumed by this recipe's own JPEG. Cross-recipe
     * configurations keep their original software route until the ownership
     * transfer itself supplies an explicit completion handoff. Stock setup
     * writes R+99c=C+30, R+9a0=C+34: C begins at R+96c. */
    if((uintptr_t)context!=(uintptr_t)s-M10V_SAVE_COLOR_OFFSET+0x96cu)return 0;
#endif
    const uint8_t *f=info;
    uint32_t si=*(const uint32_t *)(f+0x82d0);
    if(f[0x82ac]>1||!si||((const uint32_t *)context)[0x34/4]!=si){
        s->status=M10V_ISP_RECIPE_MISMATCH;return 0;
    }
    const uint8_t *shot=(const uint8_t *)(uintptr_t)si;
    if(f[0x82ac])shot+=0x71248;
    /* Stock base neutralization only owns carrier frames. Never turn an
     * unrelated stock frame into a custom recipe because UI selection is newer. */
    uint32_t raw_tone=shot[0x77c];
    if(m10v_tone_slot(raw_tone)>=M10V_SLOT_COUNT)return 0;
    uint32_t tone=selected_tone(s,raw_tone),slot;
    if(m10v_tone_slot(tone)<M10V_SLOT_COUNT)slot=m10v_tone_slot(tone);
    else return 0;
    if(!s->state.slots[slot].film)return 0;
    /* Encoder identity is base SI even when tuning uses a stage1 sub-shot. */
    if(!s->selected_tone)s->selected_tone=(uint16_t)tone;
    s->tone=((const uint8_t *)(uintptr_t)si)[0x77c];s->si=si;
#if !M10V_ISP_RECIPE_COLOR_OBSERVER && !M10V_ISP_NATIVE_LOOK
    uint32_t film=s->state.slots[slot].film;
    if(film<34||film>65){s->status=M10V_ISP_RECIPE_UNSUPPORTED;return 0;}
    uint16_t knots[99];
    if(m10v_library_tables(film,s->target.matrix_q13,s->target.post_q9,
                           &s->target.curves[0][0],knots)){
        s->status=M10V_ISP_RECIPE_REJECTED;return 0;
    }
#else
    (void)slot;
#endif
    s->info=(uint32_t)(uintptr_t)info;s->tuning=(uint32_t)(uintptr_t)tuning;
    s->busy=1;return 1;
}
int m10v_isp_frame_recipe_finish(const void *context){
    m10v_isp_recipe_color *s=from_context(context);
    if(!s||s->magic!=M10V_ISP_RECIPE_COLOR_MAGIC||!s->busy)return 0;
    void *info=(void *)(uintptr_t)s->info;
    const uint8_t *tuning=(const uint8_t *)(uintptr_t)s->tuning;
    s->info=0;s->tuning=0;s->busy=0;
    if(!info||!tuning||*(const uint32_t *)tuning!=0x53dbd8a0u){s->status=M10V_ISP_RECIPE_MISMATCH;return 0;}
#if M10V_ISP_RECIPE_COLOR_OBSERVER
    s->status=M10V_ISP_RECIPE_OBSERVED;return 1;
#else
    const void *gamma=*(const void *const *)(tuning+0x17c);
    /* Original536dc474..494 derives context color space from shot+7be==1.
     * The temporary Still Make stack context has returned; retain no pointer. */
    const uint8_t *shot=(const uint8_t *)(uintptr_t)s->si;
    if(((const uint8_t *)info)[0x82ac])shot+=0x71248;
    uint32_t cs=shot[0x7be]==1;
#if M10V_ISP_NATIVE_LOOK
    uint32_t tone=selected_tone(s,s->tone);
    uint32_t slot=m10v_tone_slot(tone);
    uint32_t film=s->state.slots[slot].film;
    /* Still and live color use the same fitted ISP profiles. Spatial Pixel
     * World and Charmera's exact pairwise palette remain software effects;
     * their live approximation must never authorize skipping those effects. */
    if(film==M10V_CHAR_ID||film==M10V_PIXEL_ID){s->status=M10V_ISP_RECIPE_UNSUPPORTED;return 0;}
    uint32_t exposure=(film==67||film==68)?s->state.effects[slot].film_exposure:0;
    uint32_t generation=(uint32_t)(uintptr_t)s^s->si^s->sequence;
    if(!generation)generation=1;
    m10v_isp_native_look look;
    int result=m10v_isp_native_look_prepare(&look,film,exposure,generation)&&
        m10v_isp_native_look_apply(&look,gamma,info,cs)&&
        m10v_isp_native_look_matches(&look,film,exposure,generation);
#else
    int result=m10v_isp_frame_apply(gamma,info,&s->target,cs);
#endif
    s->status=result?M10V_ISP_RECIPE_APPLIED:M10V_ISP_RECIPE_REJECTED;
    return result;
#endif
}

uint32_t m10v_isp_frame_recipe_completed(void *recipe,uint32_t shooting,uint32_t tone,const m10v_library_state *state){
#if M10V_ISP_NATIVE_LOOK
    m10v_isp_recipe_color *s=owned(recipe);
    if(!s||!state||!shooting||s->magic!=M10V_ISP_RECIPE_COLOR_MAGIC||s->version!=1||s->bytes!=sizeof(*s)||
       s->busy||
       !m10v_library_valid(state)||s->sequence!=state->sequence)return 0;
    for(uint32_t i=0;i<sizeof(*state);i++)if(((const uint8_t *)state)[i]!=((const uint8_t *)&s->state)[i])return 0;
    uint32_t completed=s->status==M10V_ISP_RECIPE_APPLIED&&s->si==shooting&&s->tone==tone?M10V_NATIVE_COLOR:0;
#if M10V_ISP_NATIVE_GRAIN_MODE
    uint32_t effective=selected_tone(s,tone);
    uint32_t slot=m10v_tone_slot(effective);
    if(slot<M10V_SLOT_COUNT&&s->native_grain.magic==0x374e5247u&&s->native_grain.si==shooting&&s->native_grain.tone==tone&&s->native_grain.done&&
       s->native_grain.grain==state->slots[slot].grain)completed|=M10V_NATIVE_GRAIN;
#endif
    return completed;
#else
    (void)recipe;(void)shooting;(void)tone;(void)state;return 0;
#endif
}

#if M10V_ISP_NATIVE_GRAIN_MODE
static int grain_ram(uintptr_t p,uint32_t bytes){return !(p&3)&&p>=0x55000000u&&p<=0x80000000u-bytes;}
static m10v_isp_recipe_color *grain_owner(const void *context){
    if(!grain_ram((uintptr_t)context,0x40)||*(const uint32_t *)context!=0x53d0fc60u)return 0;
    m10v_isp_recipe_color *s=from_context(context);
    uint32_t si=((const uint32_t *)context)[0x34/4];
    if(s&&(uintptr_t)context!=(uintptr_t)s-M10V_SAVE_COLOR_OFFSET+0x4320u)return 0;
    if(!s||s->magic!=M10V_ISP_RECIPE_COLOR_MAGIC||s->version!=1||s->bytes!=sizeof(*s)||s->busy||!grain_ram(si,0x94c)||!m10v_library_valid(&s->state))return 0;
    return s;
}
#endif
uint32_t m10v_isp_frame_recipe_grain_settings(const void *context,void *params,uint32_t execution){
#if M10V_ISP_NATIVE_GRAIN_MODE
    if(execution>1||!grain_ram((uintptr_t)context,0x40)||*(const uint32_t *)context!=0x53d0fc60u||!grain_ram((uintptr_t)params,0x34))return 0;
    uint32_t hdf=0;
#if M10V_ISP_SHARED_HDF
    hdf=m10v_hdf_settings((uint32_t)(uintptr_t)context,(uint32_t)(uintptr_t)params);
#endif
    uint32_t si=((const uint32_t *)context)[0x34/4];
    if(!grain_ram(si,0x94c))return hdf;
    m10v_isp_recipe_color *s=grain_owner(context);
    uint32_t tone=*(const uint8_t *)(uintptr_t)(si+0x77c);
    if(m10v_tone_slot(tone)>=M10V_SLOT_COUNT)return hdf;
    uint32_t effective=s?selected_tone(s,tone):tone,slot;
    slot=m10v_tone_slot(effective);if(slot>=M10V_SLOT_COUNT)return hdf;
    uintptr_t values=((const uint32_t *)params)[0x10/4];
    if(!grain_ram(values,12))return hdf;
    /* The carrier's original menu grain is not the queued custom grain. If
     * ownership/planning rejects, keep grain off; never run a CPU fallback. */
    ((int16_t *)values)[2]=0;
    if(!s||!s->state.slots[slot].film)return hdf;
    /* Palette/cell renderers overwrite upstream grain. No software fallback.
     * Imported old records remain readable; shared HDF remains independent. */
    if(s->state.slots[slot].film==M10V_PIXEL_ID||s->state.slots[slot].film==M10V_CHAR_ID){
        s->native_grain.planned=0;s->native_grain.armed=0;s->native_grain.done=0;
        return hdf;
    }
    uint32_t grain=s->state.slots[slot].grain,size=0;
    if(grain>3)return hdf;
    if(execution){
        if(s->native_grain.magic!=0x374e5247u||!s->native_grain.planned||s->native_grain.si!=si||s->native_grain.tone!=tone||s->native_grain.grain!=grain||s->native_grain.size!=size)return hdf;
        s->native_grain.armed=1;s->native_grain.done=0;s->native_grain.noise_ready=0;
    }else{
        s->native_grain.magic=0x374e5247u;s->native_grain.si=si;s->native_grain.tone=tone;s->native_grain.grain=grain;s->native_grain.size=size;
        s->native_grain.planned=1;s->native_grain.armed=0;s->native_grain.noise_ready=0;s->native_grain.done=0;
    }
    ((int16_t *)values)[2]=(int16_t)(grain?4-grain:0);
    return grain!=0||hdf;
#else
    (void)context;(void)params;(void)execution;return 0;
#endif
}
void m10v_isp_frame_recipe_grain_done(const void *context,const void *params,uint32_t result){
#if M10V_ISP_SHARED_HDF
    m10v_hdf_done((uint32_t)(uintptr_t)context,(uint32_t)(uintptr_t)params,result);
#endif
#if M10V_ISP_NATIVE_GRAIN_MODE
    m10v_isp_recipe_color *s=grain_owner(context);
    if(!s||s->native_grain.magic!=0x374e5247u||!s->native_grain.armed)return;
    uintptr_t values=grain_ram((uintptr_t)params,0x34)?((const uint32_t *)params)[0x10/4]:0;
    s->native_grain.done=result==1&&s->native_grain.grain&&grain_ram(values,12)&&
      ((const int16_t *)values)[2]==(int16_t)(4-s->native_grain.grain)&&s->native_grain.si==((const uint32_t *)context)[0x34/4];
    s->native_grain.armed=0;
#else
    (void)context;(void)params;(void)result;
#endif
}

/* Only the LiveView Make vtable callback calls this. It updates bounded ISP
 * parameter banks, never photo pixels, live buffers, filesystem or graph queues. */
int m10v_isp_frame_live_color(void *tuning,void *info){
#if M10V_ISP_LIVE_COLOR
    uintptr_t a=(uintptr_t)tuning,f=(uintptr_t)info;
    if((a&3)||(f&3)||a<0x55000000u||a>0x80000000u-0x400u||f<0x55000000u||f>0x80000000u-0x9000u||
       *(const uint32_t *)tuning!=0x53dbd938u)return 0;
    const uint8_t *frame=info;
    uint32_t si=*(const uint32_t *)(frame+0x82d0);
    if(frame[0x82ac]>1||!si||si<0x55000000u||si>0x80000000u-0x80000u)return 0;
    const uint8_t *shot=(const uint8_t *)(uintptr_t)si+(frame[0x82ac]?0x71248:0);
    uint32_t raw_tone=shot[0x77c];
    /* Original base hook neutralizes only raw carrier frames. Preserve stock
     * routing until SI itself enters that range, even if UI has moved ahead. */
    if(m10v_tone_slot(raw_tone)>=M10V_SLOT_COUNT)return 0;
    uint32_t tone=committed_tone(raw_tone),slot=m10v_tone_slot(tone);
    if(slot>=M10V_SLOT_COUNT)return 0;
    m10v_library_state state;if(!m10v_camera_library_preview(&state))return 0;
    uint32_t film=state.slots[slot].film,exposure=(film==67||film==68)?state.effects[slot].film_exposure:0;
    if(film==M10V_CHAR_ID)exposure=state.effects[slot].reserved[1];
    m10v_isp_native_look look;
    return m10v_isp_native_look_prepare(&look,film,exposure,state.sequence+1u)&&
        m10v_isp_native_look_apply(&look,*(const void *const *)((const uint8_t *)tuning+0x17c),info,shot[0x7be]==1);
#else
    (void)tuning;(void)info;return 0;
#endif
}

void m10v_isp_frame_live_prepare(void *tuning,const void *info){
#if M10V_ISP_LIVE_COLOR
    uintptr_t a=(uintptr_t)tuning,f=(uintptr_t)info;
    if((a&3)||(f&3)||a<0x55000000u||a>0x80000000u-0x400u||f<0x55000000u||f>0x80000000u-0x9000u||*(const uint32_t *)tuning!=0x53dbd938u)return;
    const uint8_t *frame=info;uint32_t si=*(const uint32_t *)(frame+0x82d0);
    if(frame[0x82ac]>1||si<0x55000000u||si>0x80000000u-0x80000u)return;
    uint32_t raw_tone=*((const uint8_t *)(uintptr_t)si+(frame[0x82ac]?0x71248:0)+0x77c);
    m10v_library_state state;
    uint32_t raw_slot=m10v_tone_slot(raw_tone);
    /* Clear the previous custom banks even when current UI tone is stock.
     * Raw stock frames remain entirely outside our base-neutralization route. */
    if(raw_slot<M10V_SLOT_COUNT&&m10v_camera_library_preview(&state)&&state.slots[raw_slot].film>=33){
        /* Original Live Make otherwise reuses already written frame banks.
         * Invalidate only its internal cached-tone byte; original Make restores
         * it from unmodified SI and reconstructs clean base parameters. */
        ((uint8_t *)tuning)[0x1a8]=255;
    }
#else
    (void)tuning;(void)info;
#endif
}
