/* GR III Street 2.10 native AppData ABI adapter, independently traced from
 * the official firmware. Stock FS services own their header/CRC/backup path.
 * M10V's two private journal names never overwrite an APData setting record.
 */
#include "m10v_library.h"
#if M10V_COMPANION_ENABLED
#include "m10v_companion_owner.h"
#endif
#include "m10v_tone.h"
#include <stddef.h>
#include "m10v_custom_isp.h"
#if M10V_PHOTO_RECIPE
#include "../companion/auth.h"
#endif
#if M10V_PURE_ISP_EFFECTS
#include "m10v_isp_effects_camera.h"
#endif

typedef uint32_t (*manager_fn)(void);
typedef int (*read_fn)(uint32_t, const char *, uint32_t, void *);
typedef int (*write_fn)(uint32_t, const char *, uint32_t, const void *);
#if M10V_PURE_ISP_EFFECTS
static const char state_names[2][12] = {"M10V7A.bin", "M10V7B.bin"};
static const char pre_effects_names[2][12] = {"M10V6A.bin", "M10V6B.bin"};
#else
static const char state_names[2][12] = {"M10V6A.bin", "M10V6B.bin"};
#endif

static int ram(const void *ptr, uint32_t size) {
    uintptr_t p = (uintptr_t)ptr;
    return !(p & 3) && p >= 0x55000000u && p < 0x80000000u && size <= 0x80000000u - p;
}
#if M10V_PHOTO_RECIPE
/* Native mode switch has already installed box ID and active settings. */
static uint32_t active_box(void){
 if(!(*(const volatile uint32_t *)0x55063ed0u&1u))return 0;
 const uint8_t *header=*(const uint8_t *volatile *)0x55063f30u;
 if(!ram(header,4))return 0;
 return header[0]>=1&&header[0]<=6?header[0]:0;
}

#endif
static uint32_t filesystem(void) {
    uint32_t manager = ((manager_fn)0x53828014u)();
    if (!ram((void *)(uintptr_t)manager, 12)) return 0;
    uint32_t appdata = ((const uint32_t *)(uintptr_t)manager)[2];
    if (!ram((void *)(uintptr_t)appdata, 4)) return 0;
    uint32_t fs = *(const uint32_t *)(uintptr_t)appdata;
    if (!ram((void *)(uintptr_t)fs, 0x24) || !((const uint8_t *)(uintptr_t)fs)[0x20]) return 0;
    return fs;
}
static void copy(m10v_library_state *dst, const m10v_library_state *src) {
    for (uint32_t i = 0; i < sizeof(*src); ++i) ((uint8_t *)dst)[i] = ((const uint8_t *)src)[i];
}
#ifndef M10V_LIVE_COLOR
#define M10V_LIVE_COLOR 0
#endif
#if M10V_LIVE_COLOR
#define PREVIEW_OFFSET 0x213cu
#define PREVIEW_BYTES 0x4000u
#define PREVIEW_MAGIC 0x3856504du
typedef struct {
 uint32_t id,bank;
 m10v_isp_frame_target target;
#if M10V_PHOTO_RECIPE
 uint8_t hash[32];
#endif
} custom_profile;
typedef struct {uint32_t magic,version; m10v_library_state state;custom_profile profiles[M10V_SLOT_COUNT];
#if M10V_PHOTO_RECIPE
 uint32_t adj_tone,box;
 uint32_t detail_tone,detail_ui,detail_box,detail_film;
#endif
#if M10V_ROLL_NATIVE_DEVICE
 uint32_t roll_tone,roll_crc;
 m10v_slot roll_slot;
 m10v_film_effects roll_effect;
#endif
} preview_cache;
_Static_assert(sizeof(preview_cache)<=PREVIEW_BYTES,"preview owner capacity");
static preview_cache *preview_owner(void){
    /* Original5316f350 singleton guard,5316fce0 factory+74 TopMenu owner.
     * Read only: never initialize a UI singleton or allocate from LiveView. */
    if(!(*(const volatile uint32_t *)0x55063910u&1u))return 0;
    uint32_t owner=*(const volatile uint32_t *)(0x55063914u+0x74u);
    if(!ram((const void *)(uintptr_t)owner,PREVIEW_OFFSET+PREVIEW_BYTES))return 0;
    preview_cache *p=(preview_cache *)(uintptr_t)(owner+PREVIEW_OFFSET);
    return p->magic==PREVIEW_MAGIC?p:0;
}
static int refresh_profiles(preview_cache *p,const m10v_library_state *s,uint32_t version){
#if M10V_SD_LIBRARY
 uint8_t *record=0;
 int valid=1;
 for(uint32_t i=0;i<M10V_SLOT_COUNT;i++){
  custom_profile *c=&p->profiles[i];uint32_t id=s->slots[i].film,bank=s->effects[i].reserved[0];
  if(!M10V_CUSTOM(id)){c->id=c->bank=0;continue;}
  if(c->id==id&&c->bank==bank&&bank>=M10V_CUSTOM_IMMUTABLE_FIRST)continue;
  c->id=c->bank=0;
  if(!record)record=(uint8_t *)(uintptr_t)((uint32_t (*)(uint32_t))0x536af2a8u)(M10V_SD_RECORD_BYTES);
  if(!record)continue;
  int loaded=m10v_sd_camera_custom_record(s,i,record,M10V_SD_RECORD_BYTES);
  /* Storage is allowed to reenter UI. Reacquire identity before touching
   * owned memory again; a new constructor starts at version0. */
  if(preview_owner()!=p||__atomic_load_n(&p->version,__ATOMIC_ACQUIRE)!=version){valid=0;break;}
  if(!loaded||m10v_sd_u32(record+M10V_CUSTOM_ISP_OFFSET)!=0x5053494du)continue;
#if M10V_PHOTO_RECIPE
  m10v_sha256(record,M10V_SD_RECORD_BYTES,c->hash);
#endif
  for(uint32_t k=0;k<sizeof(c->target);k++)((uint8_t *)&c->target)[k]=record[M10V_CUSTOM_ISP_OFFSET+16+k];
  c->bank=bank;c->id=id;
 }
 if(record)((void (*)(void *))0x536af2e4u)(record);
 return valid;
#else
 (void)p;(void)s;(void)version;return 1;
#endif
}
static void publish_preview(preview_cache *p,const m10v_library_state *s){
    if(!p||!m10v_library_valid(s)||(s->reserved&510u))return;
    uint32_t v=__atomic_load_n(&p->version,__ATOMIC_ACQUIRE);
    if((v&1u)||!__atomic_compare_exchange_n(&p->version,&v,v+1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return;
    if(!refresh_profiles(p,s,v+1))return;
    copy(&p->state,s);
#if M10V_ROLL_NATIVE_DEVICE
    p->roll_tone=0;
#endif
#if M10V_PHOTO_RECIPE
    p->box=active_box();
#endif
    __atomic_store_n(&p->version,v+2,__ATOMIC_RELEASE);
}
#endif
int m10v_camera_library_mutation_busy(void){
#if M10V_LIVE_COLOR
 preview_cache *p=preview_owner();return p&&(__atomic_load_n(&p->version,__ATOMIC_ACQUIRE)&1u);
#else
 return 0;
#endif
}
int m10v_camera_library_mutation_begin(void){
#if M10V_LIVE_COLOR
 preview_cache *p=preview_owner();if(!p)return 0;
 uint32_t v=__atomic_load_n(&p->version,__ATOMIC_ACQUIRE);
 return !(v&1u)&&__atomic_compare_exchange_n(&p->version,&v,v+1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED);
#else
 return 1;
#endif
}
void m10v_camera_library_mutation_end(const m10v_library_state *state){
#if M10V_LIVE_COLOR
 preview_cache *p=preview_owner();if(!p)return;
 uint32_t v=__atomic_load_n(&p->version,__ATOMIC_ACQUIRE);if(!(v&1u))return;
 if(m10v_library_valid(state)){if(!refresh_profiles(p,state,v))return;copy(&p->state,state);
#if M10V_ROLL_NATIVE_DEVICE
 p->roll_tone=0;
#endif
#if M10V_PHOTO_RECIPE
 p->box=active_box();
#endif
 }
 __atomic_store_n(&p->version,v+1,__ATOMIC_RELEASE);
#else
 (void)state;
#endif
}
static int preview_state(m10v_library_state *out,uint32_t tone){
#if M10V_LIVE_COLOR
    preview_cache *p=preview_owner();if(!p||!ram(out,sizeof(*out)))return 0;
    uint32_t before=__atomic_load_n(&p->version,__ATOMIC_ACQUIRE);
    if(!before||(before&1u))return 0;
#if M10V_PHOTO_RECIPE
    uint32_t box=active_box();
    if(p->box!=box)return 0;
#endif
#if M10V_ROLL_NATIVE_DEVICE
    copy(out,&p->state);
    if(tone&&p->roll_tone==tone){
        uint32_t slot=m10v_tone_slot(tone);
        if(slot>=M10V_SLOT_COUNT)return 0;
        out->slots[slot]=p->roll_slot;
        out->effects[slot]=p->roll_effect;
        out->sequence++;
        out->crc=p->roll_crc;
    }
#else
    (void)tone;copy(out,&p->state);
#endif
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
#if M10V_PHOTO_RECIPE
    if(box!=active_box())return 0;
#endif
    return p->magic==PREVIEW_MAGIC&&before==__atomic_load_n(&p->version,__ATOMIC_RELAXED)&&m10v_library_valid(out)&&!(out->reserved&510u);
#else
    (void)out;(void)tone;return 0;
#endif
}
int m10v_camera_library_preview(m10v_library_state *out){return preview_state(out,0);}
#if M10V_ROLL_NATIVE_DEVICE
int m10v_camera_library_roll_preview(m10v_library_state *out,uint32_t tone){return preview_state(out,tone);}

static int roll_in_memory(void *context,const m10v_library_state *state){
 (void)context;(void)state;return 0;
}

uint32_t m10v_camera_library_roll_prepare(uint32_t film,int apply){
 preview_cache *p=preview_owner();
 if(!p)return 0;
 uint32_t version=__atomic_load_n(&p->version,__ATOMIC_ACQUIRE);
 if(!version||(version&1u))return 0;
 if(!film){
  if(!__atomic_compare_exchange_n(&p->version,&version,version+1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return 0;
  p->roll_tone=0;
  __atomic_store_n(&p->version,version+2,__ATOMIC_RELEASE);
  return 1;
 }
 m10v_library_state state;
 if(!preview_state(&state,0))return 0;
 uint32_t count=m10v_library_count(&state),slot=0;
 while(slot<count&&state.slots[slot].film!=film)slot++;
 int temporary=slot==count;
 if(temporary){
  if(!M10V_BUILTIN(film)||M10V_ANIME(film))return 0;
  slot=count<M10V_SLOT_COUNT?count:0u;
  if(m10v_library_select(&state,slot,film,roll_in_memory,0))return 0;
 }else if(M10V_CUSTOM(film)){
  uint32_t bank=state.effects[slot].reserved[0];
  if(bank<M10V_CUSTOM_IMMUTABLE_FIRST||p->profiles[slot].id!=film||p->profiles[slot].bank!=bank)return 0;
 }
 uint32_t tone=m10v_slot_tone(slot);
 if(!apply)return tone;
 if(preview_owner()!=p||!__atomic_compare_exchange_n(&p->version,&version,version+1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return 0;
 p->roll_tone=temporary?tone:0;
 if(temporary){
  p->roll_slot=state.slots[slot];p->roll_effect=state.effects[slot];p->roll_crc=state.crc;
 }
 __atomic_store_n(&p->version,version+2,__ATOMIC_RELEASE);
 return tone;
}
#endif
int m10v_camera_library_custom_profile(const m10v_library_state *state,uint32_t slot,m10v_isp_frame_target *out){
#if M10V_LIVE_COLOR && M10V_SD_LIBRARY
 preview_cache *p=preview_owner();
 if(!p||!state||!ram(out,sizeof(*out))||slot>=M10V_SLOT_COUNT)return 0;
 uint32_t v=__atomic_load_n(&p->version,__ATOMIC_ACQUIRE);
 if(!v||(v&1u)||p->state.sequence!=state->sequence)return 0;
 const custom_profile *c=&p->profiles[slot];
 if(!M10V_CUSTOM(c->id)||c->id!=state->slots[slot].film||c->bank!=state->effects[slot].reserved[0])return 0;
 for(uint32_t i=0;i<sizeof(*out);i++)((uint8_t *)out)[i]=((const uint8_t *)&c->target)[i];
 __atomic_thread_fence(__ATOMIC_ACQUIRE);
 return p->magic==PREVIEW_MAGIC&&v==__atomic_load_n(&p->version,__ATOMIC_RELAXED);
#else
 (void)state;(void)slot;(void)out;return 0;
#endif
}
#if M10V_PHOTO_RECIPE
void m10v_camera_library_adj_tone_set(uint32_t tone){
 preview_cache *p=preview_owner();
 if(p)__atomic_store_n(&p->adj_tone,tone,__ATOMIC_RELEASE);
}
uint32_t m10v_camera_library_adj_tone(void){
 preview_cache *p=preview_owner();
 return p?__atomic_load_n(&p->adj_tone,__ATOMIC_ACQUIRE):0;
}
/* A native Fn route exits ADJ before its child snapshots the look. Keep that
 * explicit route handoff separate from the disposable LiveView candidate. */
uint32_t m10v_camera_library_detail_stage(uint32_t tone){
 preview_cache *p=preview_owner();if(!p)return 0;
 m10v_library_state state;
 uint32_t slot=m10v_tone_slot(tone);
 if(slot>=M10V_SLOT_COUNT||!preview_state(&state,0)||preview_owner()!=p||
    slot>=m10v_library_count(&state))tone=0;
 p->detail_ui=0;p->detail_box=active_box();p->detail_tone=tone;
 p->detail_film=tone?state.slots[slot].film:0;
 return tone;
}
uint32_t m10v_camera_library_detail_claim(uint32_t ui){
 preview_cache *p=preview_owner();if(!p||!ram((const void *)(uintptr_t)ui,0x1a0))return 0;
 uint32_t tone=p->detail_tone,slot=m10v_tone_slot(tone);
 uint32_t route=*(const uint32_t *)(uintptr_t)(ui+0x124),parent=*(const uint32_t *)(uintptr_t)(ui+0x150);
 /* Cached controllers can enter from MENU without running their ctor again.
  * Once BaseController has supplied routing, an ADJ handoff is valid only
  * for its genuine ImageControl detail child and ADJ parent. */
 /* Native ctor starts both routes at10000000. Offset128 is a flag (1),
  * never a route; genuine enter5316dfe8/5316dff0 supplies124/150 later. */
 if((route&&route!=0x10000000u&&route!=0x02000014u)||
    (parent&&parent!=0x10000000u&&parent!=0x02000000u)){
  p->detail_tone=0;p->detail_ui=0;return 0;
 }
 m10v_library_state state;
 if(!tone||slot>=M10V_SLOT_COUNT||p->detail_box!=active_box()||
    !preview_state(&state,0)||preview_owner()!=p||
    state.slots[slot].film!=p->detail_film)return 0;
 if(p->detail_ui){
  if(p->detail_ui!=ui)return 0;
  /* The genuine detail ctor531afe24 resets198 to stock tone11. A reused
   * allocation belongs to a new page and cannot inherit an earlier handoff. */
  if(*(const uint8_t *)(uintptr_t)(ui+0x198)!=tone){p->detail_tone=0;p->detail_ui=0;return 0;}
 }else p->detail_ui=ui;
 return tone;
}

int m10v_camera_library_custom_hash(const m10v_library_state *state,uint32_t slot,uint8_t out[32]){
 preview_cache *p=preview_owner();
 if(!p||!state||!ram(out,32)||slot>=M10V_SLOT_COUNT)return 0;
 uint32_t v=__atomic_load_n(&p->version,__ATOMIC_ACQUIRE);
 if(!v||(v&1u)||p->state.sequence!=state->sequence)return 0;
 const custom_profile *c=&p->profiles[slot];
 if(!M10V_CUSTOM(c->id)||c->id!=state->slots[slot].film||
    c->bank<M10V_CUSTOM_IMMUTABLE_FIRST||c->bank!=state->effects[slot].reserved[0])return 0;
 for(uint32_t i=0;i<32;i++)out[i]=c->hash[i];
 __atomic_thread_fence(__ATOMIC_ACQUIRE);
 return p->magic==PREVIEW_MAGIC&&v==__atomic_load_n(&p->version,__ATOMIC_RELAXED);
}
#endif
void m10v_camera_library_preview_init(uint32_t owner){
#if M10V_LIVE_COLOR
    if(!ram((void *)(uintptr_t)owner,PREVIEW_OFFSET+PREVIEW_BYTES))return;
    preview_cache *p=(preview_cache *)(uintptr_t)(owner+PREVIEW_OFFSET);
    p->magic=0;p->version=0;
#if M10V_ROLL_NATIVE_DEVICE
    p->roll_tone=0;
#endif
#if M10V_PHOTO_RECIPE
    p->adj_tone=0;p->box=0;
    p->detail_tone=p->detail_ui=p->detail_box=p->detail_film=0;
#endif
    for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)p->profiles[i].id=p->profiles[i].bank=0;
    p->magic=PREVIEW_MAGIC;
    /* Constructor is allocation-only: storage may re-enter the factory.
     * Ready/load publishes after the original factory has installed owner+74. */
#else
    (void)owner;
#endif
}
void m10v_camera_library_preview_clear(uint32_t owner){
#if M10V_LIVE_COLOR
    if(ram((void *)(uintptr_t)owner,PREVIEW_OFFSET+PREVIEW_BYTES)){
        preview_cache *p=(preview_cache *)(uintptr_t)(owner+PREVIEW_OFFSET);
        p->magic=0;
    }
#else
    (void)owner;
#endif
}
#if M10V_PHOTO_RECIPE
/* Native box IDs are 1..6. Stock assignment can point multiple U positions
 * at a box, so the extension follows that same box when the user reassigns it. */
static const char dial_names[6][2][12]={
 {"M10VU1A.BIN","M10VU1B.BIN"},{"M10VU2A.BIN","M10VU2B.BIN"},
 {"M10VU3A.BIN","M10VU3B.BIN"},{"M10VU4A.BIN","M10VU4B.BIN"},
 {"M10VU5A.BIN","M10VU5B.BIN"},{"M10VU6A.BIN","M10VU6B.BIN"}
};
const char *m10v_camera_library_box_path(uint32_t box,uint32_t group,uint32_t page){
 static const char names[6][3][2][12]={
  {{"U1HD0.BIN","U1HD1.BIN"},{"U1BD0.BIN","U1BD1.BIN"},{"U1FX0.BIN","U1FX1.BIN"}},
  {{"U2HD0.BIN","U2HD1.BIN"},{"U2BD0.BIN","U2BD1.BIN"},{"U2FX0.BIN","U2FX1.BIN"}},
  {{"U3HD0.BIN","U3HD1.BIN"},{"U3BD0.BIN","U3BD1.BIN"},{"U3FX0.BIN","U3FX1.BIN"}},
  {{"U4HD0.BIN","U4HD1.BIN"},{"U4BD0.BIN","U4BD1.BIN"},{"U4FX0.BIN","U4FX1.BIN"}},
  {{"U5HD0.BIN","U5HD1.BIN"},{"U5BD0.BIN","U5BD1.BIN"},{"U5FX0.BIN","U5FX1.BIN"}},
  {{"U6HD0.BIN","U6HD1.BIN"},{"U6BD0.BIN","U6BD1.BIN"},{"U6FX0.BIN","U6FX1.BIN"}}
 };
 return box&&box<=6&&group<3&&page<2?names[box-1][group][page]:0;
}
uint32_t m10v_camera_library_box_id(void){return active_box();}
static const char (*library_names(uint32_t box))[12]{
 return box?dial_names[box-1]:state_names;
}
#else
static uint32_t active_box(void){return 0;}
static const char (*library_names(uint32_t box))[12]{(void)box;return state_names;}
#endif
static int read_library_pair(uint32_t,const char names[2][12],m10v_library_state *);

static int store_guarded(void *context, const m10v_library_state *next,uint32_t remote) {
#if M10V_COMPANION_ENABLED
    uint32_t token=m10v_companion_ui_storage_enter(remote);if(!token)return -1;
#else
    (void)remote;
#endif
    uint32_t fs = (uint32_t)(uintptr_t)context;
#if M10V_LIVE_COLOR && M10V_COMPANION_ENABLED
    preview_cache *origin=preview_owner();
#endif
    m10v_library_state readback;int result=-1;
    uint32_t box=active_box();
#if M10V_PHOTO_RECIPE
    if(origin&&origin->box!=box&&__atomic_load_n(&origin->version,__ATOMIC_ACQUIRE))goto finish;
#endif
    const char *name = library_names(box)[next->sequence & 1];
    for (uint32_t i = 0; i < sizeof(readback); ++i) ((uint8_t *)&readback)[i] = 0;
    if (!((write_fn)0x53825fa8u)(fs, name, sizeof(*next), next))goto finish;
#if M10V_COMPANION_ENABLED
    if(!m10v_companion_ui_storage_current(token))goto finish;
#endif
    if (!((read_fn)0x53825648u)(fs, name, sizeof(readback), &readback) ||
        !m10v_library_valid(&readback)) goto finish;
    for (uint32_t i = 0; i < sizeof(readback); ++i)
        if (((const uint8_t *)&readback)[i] != ((const uint8_t *)next)[i]) goto finish;
#if M10V_COMPANION_ENABLED
    if(!m10v_companion_ui_storage_current(token))goto finish;
#endif
#if M10V_LIVE_COLOR
#if M10V_COMPANION_ENABLED
    if(preview_owner()!=origin||active_box()!=box)goto finish;
    publish_preview(origin,next);
#else
    publish_preview(preview_owner(),next);
#endif
#endif
    result=0;
finish:
#if M10V_COMPANION_ENABLED
    if(!m10v_companion_ui_storage_leave(token))result=-1;
#endif
    return result;
}
static int store(void *context,const m10v_library_state *next){return store_guarded(context,next,0);}
#if M10V_COMPANION_ENABLED
/* Remote observations never migrate, synthesize defaults or publish UI caches.
 * Keep the original local loader and its migration behavior unchanged. */
int m10v_camera_library_read_current(m10v_library_state *state){
    if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();if(!fs)return M10V_LIBRARY_INVALID;
    uint32_t box=active_box();
    int found=read_library_pair(fs,library_names(box),state);
    if(!found&&box)found=read_library_pair(fs,state_names,state);
    return found&&active_box()==box?M10V_LIBRARY_OK:M10V_LIBRARY_INVALID;
}
int m10v_camera_library_commit_snapshot(const m10v_library_state *next){
    if(!m10v_library_valid(next)||!m10v_camera_library_mutation_busy())return M10V_LIBRARY_INVALID;
    m10v_library_state prior;
    if(m10v_camera_library_read_current(&prior)!=0||prior.sequence==0xffffffffu||next->sequence!=prior.sequence+1u)return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();
    return fs&&store_guarded((void*)(uintptr_t)fs,next,1)==0?M10V_LIBRARY_OK:M10V_LIBRARY_STORE_FAILED;
}
#endif
typedef struct {uint32_t magic;uint16_t version,size;uint32_t sequence;m10v_slot slots[5];uint8_t stamp,format,corner,color;m10v_film_effects effects[5];uint32_t reserved,crc;} legacy_state;
static const char legacy_names[2][12]={"M10V5A.bin","M10V5B.bin"};
static uint32_t state_crc(const void *v,uint32_t bytes){uint32_t crc=0xffffffffu;const uint8_t *p=v;for(uint32_t i=0;i<bytes;i++){crc^=p[i];for(uint32_t b=0;b<8;b++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return ~crc;}
static void expand_legacy(m10v_library_state *out,const legacy_state *old){
 m10v_library_init(out);for(uint32_t i=0;i<M10V_SLOT_COUNT;i++){m10v_slot v={0};m10v_film_effects e={0};out->slots[i]=v;out->effects[i]=e;}
 out->sequence=old->sequence;out->stamp=old->stamp;out->format=old->format;out->corner=old->corner;out->color=old->color;out->reserved=old->reserved;
 uint32_t count=0;for(uint32_t i=0;i<5;i++){uint32_t duplicate=0;for(uint32_t j=0;j<count;j++)if(out->slots[j].film==old->slots[i].film)duplicate=1;if(duplicate)continue;out->slots[count]=old->slots[i];out->effects[count]=old->effects[i];if(M10V_CUSTOM(old->slots[i].film))out->effects[count].reserved[0]+=(uint8_t)(2*i);count++;}
 out->crc=state_crc(out,offsetof(m10v_library_state,crc));
}
static int legacy_state_valid(const legacy_state *old){
 if(old->magic!=0x5630314du||old->version!=4||old->size!=104||old->crc!=state_crc(old,100))return 0;
 for(uint32_t i=0;i<5;i++)if(!old->slots[i].film|| (M10V_CUSTOM(old->slots[i].film)&&(old->effects[i].reserved[0]<1||old->effects[i].reserved[0]>2)))return 0;
 /* Validate every old slot, including later duplicate selections that the
  * ordered enable-list migration discards. */
 for(uint32_t i=0;i<5;i++){
  m10v_library_state one;m10v_library_init(&one);
  for(uint32_t j=0;j<M10V_SLOT_COUNT;j++){m10v_slot v={0};m10v_film_effects e={0};one.slots[j]=v;one.effects[j]=e;}
  one.slots[0]=old->slots[i];one.effects[0]=old->effects[i];one.stamp=old->stamp;one.format=old->format;one.corner=old->corner;one.color=old->color;one.reserved=old->reserved;one.crc=state_crc(&one,offsetof(m10v_library_state,crc));
  if(!m10v_library_valid(&one))return 0;
 }
 m10v_library_state expanded;expand_legacy(&expanded,old);return m10v_library_valid(&expanded);
}
static void legacy_state_init(legacy_state *old){m10v_library_state init;m10v_library_init(&init);for(uint32_t i=0;i<sizeof(*old);i++)((uint8_t *)old)[i]=0;old->magic=init.magic;old->version=4;old->size=104;for(uint32_t i=0;i<5;i++){old->slots[i]=init.slots[i];old->effects[i]=init.effects[i];}old->crc=state_crc(old,100);}
static void legacy_copy(legacy_state *out,const legacy_state *in){for(uint32_t i=0;i<sizeof(*out);i++)((uint8_t *)out)[i]=((const uint8_t *)in)[i];}
static uint32_t little32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static int legacy_valid(const uint8_t *p){
    if(little32(p)!=0x5630314du||p[4]!=1||p[5]||p[6]!=44||p[7]||p[32]>2||p[33]>3||p[34]>3||p[35]>3||little32(p+36))return 0;
    for(uint32_t i=0;i<5;++i){const uint8_t *v=p+12+4*i;if(!v[0]||v[0]>33||v[1]||v[2]>3||v[3]>3)return 0;}
    uint32_t crc=0xffffffffu;for(uint32_t i=0;i<40;++i){crc^=p[i];for(uint32_t bit=0;bit<8;++bit)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}
    return ~crc==little32(p+40);
}
static void reset_migrated_effects(legacy_state *state){
    for(uint32_t i=0;i<5;i++){m10v_film_effects e={1,0,0,4,0,0,{0,0}};state->effects[i]=e;}
}
static int migrate_v2(uint32_t fs,legacy_state *state,uint32_t energy){
    static const char energy_names[2][12]={"M10V3A.bin","M10V3B.bin"};
    static const char old_names[2][12]={"M10V2A.bin","M10V2B.bin"};
    const char (*names)[12]=energy?energy_names:old_names;
    uint8_t records[2][64];int good[2]={0,0};
    for(uint32_t k=0;k<2;k++){
        for(uint32_t i=0;i<64;i++)records[k][i]=0;
        uint8_t *p=records[k];
        if(!((read_fn)0x53825648u)(fs,names[k],64,p))continue;
        if(little32(p)!=0x5630314du||p[4]!=2||p[5]||p[6]!=64||p[7]||p[52]>2||p[53]>3||p[54]>3||p[55]>3||little32(p+56))continue;
        int valid=1;
        for(uint32_t i=0;i<5;i++){uint8_t *v=p+12+i*8;
            if(!v[0]||v[0]>65||v[1]||v[2]>3||v[3]>3||v[4]>8||v[5]>8||v[6]>8||v[7]>3)valid=0;}
        uint32_t crc=0xffffffffu;for(uint32_t i=0;i<60;i++){crc^=p[i];for(uint32_t bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}
        good[k]=valid&&~crc==little32(p+60);
    }
    if(!good[0]&&!good[1])return 1;
    uint32_t index=!good[0]||(good[1]&&little32(records[1]+8)>little32(records[0]+8));
    reset_migrated_effects(state);
    for(uint32_t i=8;i<56;i++)((uint8_t *)state)[i]=records[index][i];
    if(!energy)for(uint32_t i=0;i<5;i++){m10v_slot *v=&state->slots[i];v->halo_gain=(v->halo_gain&&v->halo_profile)?3:0;v->halo_spread=3;v->halo_threshold=5;v->halo_profile=2;}
    uint32_t crc=0xffffffffu;for(uint32_t i=0;i<100;i++){crc^=((uint8_t *)state)[i];for(uint32_t bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}state->crc=~crc;
    return legacy_state_valid(state)?2:-1;
}
static int migrate(uint32_t fs,legacy_state *state){
    static const char names[2][12]={"M10V0.bin","M10V1.bin"};
    uint8_t records[2][44];int good[2];
    for(uint32_t i=0;i<88;++i)((uint8_t *)records)[i]=0;
    for(uint32_t i=0;i<2;++i)good[i]=((read_fn)0x53825648u)(fs,names[i],44,records[i])&&legacy_valid(records[i]);
    if(!good[0]&&!good[1])return 1;
    uint32_t selected=!good[0]||(good[1]&&little32(records[1]+8)>little32(records[0]+8));const uint8_t *old=records[selected];
    reset_migrated_effects(state);
    state->sequence=little32(old+8);
    for(uint32_t i=0;i<5;++i){state->slots[i].film=old[12+4*i];state->slots[i].grain=old[14+4*i];state->slots[i].soft=old[15+4*i];}
    state->stamp=old[32];state->format=old[33];state->corner=old[34];state->color=old[35];
    uint32_t crc=0xffffffffu;const uint8_t *bytes=(const uint8_t *)state;
    for(uint32_t i=0;i<100;++i){crc^=bytes[i];for(uint32_t bit=0;bit<8;++bit)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}state->crc=~crc;
    return legacy_state_valid(state)?3:-1;
}
/* Published texture schema3: verify old CRC before converting the header.
 * The new exposure byte was reserved and must be zero in every old slot. */
static uint32_t texture_crc(const legacy_state *state){
    uint32_t crc=0xffffffffu;for(uint32_t i=0;i<100;i++){crc^=((const uint8_t *)state)[i];for(uint32_t b=0;b<8;b++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return ~crc;
}
static int read_texture_v3(uint32_t fs,const char *name,legacy_state *state){
    if(!((read_fn)0x53825648u)(fs,name,sizeof(*state),state)||state->version!=3||state->size!=104||state->crc!=texture_crc(state))return 0;
    for(uint32_t i=0;i<5;i++)if(state->slots[i].film>66||state->effects[i].film_exposure)return 0;
    state->version=4;state->crc=texture_crc(state);return legacy_state_valid(state);
}
static int load_legacy_library(legacy_state *state) {
    if (!ram(state, sizeof(*state))) return M10V_LIBRARY_INVALID;
    legacy_state_init(state);
    uint32_t fs = filesystem(); if (!fs) return M10V_LIBRARY_INVALID;
    legacy_state candidates[2]; int available[2];uint32_t experimental_source=0;
    for (uint32_t i = 0; i < sizeof(candidates); ++i) ((uint8_t *)candidates)[i] = 0;
    for (uint32_t i = 0; i < 2; ++i)
        available[i] = ((read_fn)0x53825648u)(fs, legacy_names[i], sizeof(*state), &candidates[i]) &&
                       legacy_state_valid(&candidates[i]);
    if (!available[0] && !available[1]) {
        static const char published[2][12]={"M10V4A.bin","M10V4B.bin"};
        for(uint32_t i=0;i<2;i++)available[i]=read_texture_v3(fs,published[i],&candidates[i]);
        if(!available[0]&&!available[1]){
            static const char experimental[2][12]={"M10V3A.bin","M10V3B.bin"};
            for(uint32_t i=0;i<2;i++)available[i]=read_texture_v3(fs,experimental[i],&candidates[i]);
            experimental_source=1;
            if(!available[0]&&!available[1]){
                int old=migrate_v2(fs,state,1);if(old==1)old=migrate_v2(fs,state,0);
                return old==1?migrate(fs,state):old;
            }
        }
    }
    uint32_t selected = !available[0] || (available[1] && candidates[1].sequence > candidates[0].sequence);
    legacy_copy(state, &candidates[selected]);
    if(experimental_source){
        for(uint32_t i=0;i<5;i++){m10v_slot *v=&state->slots[i];v->halo_gain=(v->halo_gain&&v->halo_profile)?3:0;v->halo_spread=3;v->halo_threshold=5;v->halo_profile=2;}
        uint32_t crc=0xffffffffu;for(uint32_t i=0;i<100;i++){crc^=((uint8_t *)state)[i];for(uint32_t bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}state->crc=~crc;return 2;
    }
    return M10V_LIBRARY_OK;
}
static int read_library_pair(uint32_t fs,const char names[2][12],m10v_library_state *state){
 m10v_library_state candidates[2];int good[2]={0,0};
 for(uint32_t k=0;k<2;k++){for(uint32_t i=0;i<sizeof(*state);i++)((uint8_t *)&candidates[k])[i]=0;good[k]=((read_fn)0x53825648u)(fs,names[k],sizeof(*state),&candidates[k])&&m10v_library_valid(&candidates[k]);}
 if(!good[0]&&!good[1])return 0;
 uint32_t selected=!good[0]||(good[1]&&candidates[1].sequence>candidates[0].sequence);
 copy(state,&candidates[selected]);return 1;
}
static int load_library(m10v_library_state *state){
 if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
 uint32_t fs=filesystem();if(!fs)return M10V_LIBRARY_INVALID;
 uint32_t box=active_box();
 if(box&&read_library_pair(fs,library_names(box),state))return active_box()==box?0:M10V_LIBRARY_INVALID;
 if(read_library_pair(fs,state_names,state))return active_box()==box?0:M10V_LIBRARY_INVALID;
#if M10V_PURE_ISP_EFFECTS
 if(read_library_pair(fs,pre_effects_names,state))return 0;
#endif
 legacy_state old;int result=load_legacy_library(&old);if(result<0)return result;expand_legacy(state,&old);return result==0?4:result;
}
#if M10V_PHOTO_RECIPE
/* User's stock Save Settings action is the only operation which copies a
 * whole library to another native box. Dial changes merely load a journal. */
int m10v_camera_library_save_box(uint32_t box){
 if(box<1||box>6)return 0;
 preview_cache *p=preview_owner();
 m10v_library_state next,prior,back;
 if(!p||!m10v_camera_library_preview(&next))return 0;
 for(uint32_t slot=0;slot<M10V_SLOT_COUNT;slot++)
  if(M10V_CUSTOM(next.slots[slot].film)&&
     next.effects[slot].reserved[0]<M10V_CUSTOM_IMMUTABLE_FIRST)return 0;
 uint32_t token=m10v_companion_ui_storage_enter(0);
 if(!token)return 0;
 uint32_t fs=filesystem(),source_box=active_box();
 int saved=0;
 if(!fs||!m10v_companion_ui_storage_current(token)||preview_owner()!=p)goto finish;
 int have_prior=read_library_pair(fs,dial_names[box-1],&prior);
 if(have_prior&&prior.sequence>=next.sequence)next.sequence=prior.sequence;
 if(next.sequence==UINT32_MAX)goto finish;
 next.sequence++;
 next.crc=state_crc(&next,offsetof(m10v_library_state,crc));
 if(active_box()!=source_box||!m10v_companion_ui_storage_current(token))goto finish;
 const char *name=dial_names[box-1][next.sequence&1u];
 if(!((write_fn)0x53825fa8u)(fs,name,sizeof(next),&next)||
    !m10v_companion_ui_storage_current(token)||
    !read_library_pair(fs,dial_names[box-1],&back))goto finish;
 for(uint32_t i=0;i<sizeof(next);i++)
  if(((const uint8_t *)&back)[i]!=((const uint8_t *)&next)[i])goto finish;
 if(preview_owner()!=p||active_box()!=source_box)goto finish;
 if(source_box==box)publish_preview(p,&next);
 saved=1;
finish:
 return m10v_companion_ui_storage_leave(token)&&saved;
}

int m10v_camera_library_reload_box(void){
 preview_cache *p=preview_owner();
 if(!p)return -1;
 uint32_t version=__atomic_load_n(&p->version,__ATOMIC_ACQUIRE);
 if(version&1u)return -1;
 if(version&&p->box==active_box()&&p->state.magic)return (int)p->state.sequence;
 /* Retire cached data immediately so a card error cannot leak another
  * box's configuration into a later exposure. Custom targets are refreshed
  * during the UI load and captured frames retain their existing snapshot. */
 if(!__atomic_compare_exchange_n(&p->version,&version,version+1u,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return -1;
 p->state.magic=0;
 __atomic_store_n(&p->version,version+2u,__ATOMIC_RELEASE);
 m10v_library_state state;
 int result=m10v_camera_library_load(&state);
 return result>=0&&m10v_camera_library_preview(&state)?(int)state.sequence:-1;
}
#endif
int m10v_camera_library_load(m10v_library_state *state){
    int result=load_library(state);
#if !M10V_FOUR_LOOKS_NATIVE || !M10V_MARLBORO_NATIVE || !M10V_THREE_FILM_NATIVE || !M10V_LEICA_NATIVE
    if(result>=0){
        /* A journal moved from GR III must not enable an unverified look on
         * another model. Keep all supported slots and their settings; do not
         * rewrite the user's journal merely because it was read here. */
        uint32_t count=0,changed=0;
        for(uint32_t i=0;i<M10V_SLOT_COUNT;i++){
            if((!M10V_LEICA_NATIVE&&M10V_LEICA(state->slots[i].film))||(!M10V_FOUR_LOOKS_NATIVE&&M10V_FOUR_LOOKS(state->slots[i].film))||(!M10V_MARLBORO_NATIVE&&state->slots[i].film==M10V_MARLBORO_ID)||(!M10V_THREE_FILM_NATIVE&&M10V_THREE_FILM(state->slots[i].film))){changed=1;continue;}
            state->slots[count]=state->slots[i];state->effects[count]=state->effects[i];count++;
        }
        if(changed){
            for(;count<M10V_SLOT_COUNT;count++){
                for(uint32_t j=0;j<sizeof(m10v_slot);j++)((uint8_t *)&state->slots[count])[j]=0;
                for(uint32_t j=0;j<sizeof(m10v_film_effects);j++)((uint8_t *)&state->effects[count])[j]=0;
            }
            state->reserved&=1u;state->crc=state_crc(state,offsetof(m10v_library_state,crc));
        }
    }
#endif
#if M10V_LIVE_COLOR
    if(result>=0)publish_preview(preview_owner(),state);
#endif
    return result;
}
int m10v_camera_library_select(m10v_library_state *state, uint32_t slot, uint32_t film) {
#if !M10V_MARLBORO_NATIVE
    if(film==M10V_MARLBORO_ID)return M10V_LIBRARY_INVALID;
#endif
#if !M10V_THREE_FILM_NATIVE
    if(M10V_THREE_FILM(film))return M10V_LIBRARY_INVALID;
#endif
#if !M10V_LEICA_NATIVE
    if(M10V_LEICA(film))return M10V_LIBRARY_INVALID;
#endif
#if !M10V_FOUR_LOOKS_NATIVE
    if(M10V_FOUR_LOOKS(film))return M10V_LIBRARY_INVALID;
#endif
#if !M10V_LIVE_COLOR
    if(film==294||(M10V_THREE_FILM(film)||M10V_ANIME_E6(film)||M10V_C41(film)||M10V_EXTRA_FILM(film)))return M10V_LIBRARY_INVALID;
#endif
    if (!ram(state, sizeof(*state))) return M10V_LIBRARY_INVALID;
    uint32_t fs = filesystem();
    return fs ? m10v_library_select(state, slot, film, store, (void *)(uintptr_t)fs) : M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_select_custom(m10v_library_state *state,uint32_t slot,uint32_t film,uint32_t bank){
 if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
 uint32_t fs=filesystem();return fs?m10v_library_select_custom(state,slot,film,bank,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_texture(m10v_library_state *state, uint32_t slot, uint32_t grain, uint32_t soft) {
    if (!ram(state, sizeof(*state))) return M10V_LIBRARY_INVALID;
#if !M10V_ISP_NATIVE_GRAIN_MODE
    if(grain)return M10V_LIBRARY_INVALID;
#endif
    uint32_t fs = filesystem();
    return fs ? m10v_library_texture(state, slot, grain, soft, store, (void *)(uintptr_t)fs) : M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_halation(m10v_library_state *state,uint32_t slot,uint32_t gain,uint32_t spread,uint32_t threshold,uint32_t profile){
    if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();return fs?m10v_library_halation(state,slot,gain,spread,threshold,profile,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_detail(m10v_library_state *state,uint32_t slot,uint32_t gain,uint32_t spread,uint32_t threshold,uint32_t grain,uint32_t soft){
#if !M10V_ISP_NATIVE_GRAIN_MODE
 if(grain)return M10V_LIBRARY_INVALID;
#endif
    if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();
    return fs?m10v_library_detail(state,slot,gain,spread,threshold,grain,soft,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_stamp(m10v_library_state *state, uint32_t enabled, uint32_t format,
                             uint32_t corner, uint32_t color) {
    if (!ram(state, sizeof(*state))) return M10V_LIBRARY_INVALID;
    uint32_t fs = filesystem();
    return fs ? m10v_library_stamp(state, enabled, format, corner, color, store, (void *)(uintptr_t)fs) : M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_film_name_stamp(m10v_library_state *state,uint32_t enabled){
    if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();
    return fs?m10v_library_film_name_stamp(state,enabled,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}

int m10v_camera_library_effects(m10v_library_state *state,uint32_t slot,uint32_t field,uint32_t value){
    if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();return fs?m10v_library_effects(state,slot,field,value,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}
#if M10V_PURE_ISP_EFFECTS
int m10v_camera_library_grain(m10v_library_state *state,uint32_t slot,uint32_t size,uint32_t value){
    if(!ram(state,sizeof(*state))||!m10v_library_valid(state)||slot>=M10V_SLOT_COUNT||
       !state->slots[slot].film||value>(size?2u:3u)||state->sequence==0xffffffffu)
        return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();if(!fs)return M10V_LIBRARY_STORE_FAILED;
    m10v_library_state next;copy(&next,state);
    m10v_film_effects *effects=&next.effects[slot];
    uint32_t grain=next.slots[slot].grain;
    if(!m10v_film_fx_tagged(effects))m10v_film_fx_set(effects,grain?grain-1u:0,0,0,0,0);
    if(size)effects->grain_size=(uint8_t)value;
    else next.slots[slot].grain=(uint8_t)value;
    next.sequence++;
    next.crc=state_crc(&next,offsetof(m10v_library_state,crc));
    if(store((void *)(uintptr_t)fs,&next))return M10V_LIBRARY_STORE_FAILED;
    copy(state,&next);
    return M10V_LIBRARY_OK;
}
#endif
int m10v_camera_library_reset(m10v_library_state *state,uint32_t slot){
    if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();return fs?m10v_library_reset(state,slot,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}

int m10v_camera_library_remove(m10v_library_state *state,uint32_t slot){
 if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
 uint32_t fs=filesystem();return fs?m10v_library_remove(state,slot,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}

/* UI lifecycle only. Pending remap and compacted state share one CRC-framed
 * journal commit, so interrupted upgrades can finish without guessing. */
int m10v_camera_library_reconcile_legacy_selection(uint32_t model){
 if(!ram((void *)(uintptr_t)model,4))return M10V_LIBRARY_INVALID;
 uint32_t fs=filesystem();if(!fs)return M10V_LIBRARY_STORE_FAILED;
 m10v_library_state state;int provenance=load_library(&state);if(provenance<0)return provenance;
 typedef uint32_t (*get_tone_fn)(uint32_t);typedef uint32_t (*set_tone_fn)(uint32_t,uint32_t);
 uint32_t bank=((get_tone_fn)0x532bd6d4u)(model);
 if(bank>2)return M10V_LIBRARY_INVALID;
 uint32_t tone=((get_tone_fn)0x532bd6b4u)(model),old_slot=bank?M10V_SLOT_COUNT:m10v_tone_slot(tone);
 if(!(state.reserved&510u)&&provenance!=0&&provenance!=1){
  legacy_state old;if(load_legacy_library(&old)<0)return M10V_LIBRARY_INVALID;
  if(old_slot<5){uint32_t film=old.slots[old_slot].film,new_slot=M10V_SLOT_COUNT;
   for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)if(state.slots[i].film==film)new_slot=i;
   if(new_slot>=M10V_SLOT_COUNT)return M10V_LIBRARY_INVALID;
   if(new_slot!=old_slot)state.reserved|=((old_slot+1)<<1)|((new_slot+1)<<5);
  }
  if(state.sequence==0xffffffffu)return M10V_LIBRARY_INVALID;
  state.sequence++;state.crc=state_crc(&state,offsetof(m10v_library_state,crc));
  if(store((void *)(uintptr_t)fs,&state))return M10V_LIBRARY_STORE_FAILED;
 }
 if(state.reserved&510u){
  uint32_t from=((state.reserved>>1)&15u)-1,to=((state.reserved>>5)&15u)-1;
  if(to>=m10v_library_count(&state))return M10V_LIBRARY_INVALID;
  /* Custom1/2 own their stock bank. Its underlying tone is not the
   * active M10V carrier and must never trigger a selection setter. */
  if(!bank&&tone==m10v_slot_tone(from)){
   ((set_tone_fn)0x532c26c0u)(model,m10v_slot_tone(to));
   if(((get_tone_fn)0x532bd6b4u)(model)!=m10v_slot_tone(to))return M10V_LIBRARY_STORE_FAILED;
  }else if(!bank&&tone!=m10v_slot_tone(to)&&m10v_tone_slot(tone)<M10V_SLOT_COUNT){
   /* An unrelated carrier after interrupted startup has no authenticated
    * old identity. Preserve safety with the ordinary Standard engine. */
   ((set_tone_fn)0x532c26c0u)(model,11u);
   if(((get_tone_fn)0x532bd6b4u)(model)!=11u)return M10V_LIBRARY_STORE_FAILED;
  }
  if(state.sequence==0xffffffffu)return M10V_LIBRARY_INVALID;
  state.reserved&=1u;state.sequence++;state.crc=state_crc(&state,offsetof(m10v_library_state,crc));
  if(store((void *)(uintptr_t)fs,&state))return M10V_LIBRARY_STORE_FAILED;
 }
#if M10V_PURE_ISP_EFFECTS
 uint32_t pending=0;
 for(uint32_t i=0;i<m10v_library_count(&state);i++)pending|=!m10v_film_fx_tagged(&state.effects[i]);
 if(pending){
  m10v_isp_effects_settings legacy;
  for(uint32_t i=0;i<sizeof(legacy);i++)((volatile uint8_t *)&legacy)[i]=0;
  if(provenance!=1&&m10v_isp_effects_camera_read_legacy(fs,&legacy)<0)return M10V_LIBRARY_STORE_FAILED;
  for(uint32_t i=0;i<m10v_library_count(&state);i++){
   m10v_film_effects *e=&state.effects[i];
   if(m10v_film_fx_tagged(e))continue;
   uint32_t grain=state.slots[i].grain,size=grain?grain-1u:0u;
   if(!grain&&legacy.grain_mode>=M10V_ISP_GRAIN_WEAK){
    state.slots[i].grain=(uint8_t)(legacy.grain_mode-1u);size=legacy.grain_size;
   }
   static const uint8_t position[]={0,2,4};
   m10v_film_fx_set(e,size,legacy.leak_gain,position[legacy.leak_position],legacy.leak_spread,legacy.blur_gain);
   e->leak_variation|=(uint8_t)(legacy.blur_range<<2);
  }
  if(state.sequence==0xffffffffu)return M10V_LIBRARY_INVALID;
  state.sequence++;state.crc=state_crc(&state,offsetof(m10v_library_state,crc));
  if(store((void *)(uintptr_t)fs,&state))return M10V_LIBRARY_STORE_FAILED;
 }
#endif
#if M10V_PRESERVE_EXISTING
 /* Upgrade-only opt-in: a valid existing current journal owns the user's
  * selection even if an old compiled-seed receipt is absent or unreadable.
  * Keep normal exports' one-time selection semantics below unchanged. */
 if(provenance!=0){
#endif
 /* Apply a changed exported film selection once, in the safe UI lifecycle.
  * The journal alone cannot distinguish a reflash from an ordinary restart.
  * Keep globals, but let the new selection replace custom as well as builtin
  * slots. Persist state before the receipt; interrupted writes retry safely. */
 m10v_library_state defaults;m10v_library_init(&defaults);
 uint32_t receipt[4]={0x31474643u,defaults.crc,~defaults.crc,0x31474643u^defaults.crc};
 uint32_t seen[4]={0,0,0,0};
 int applied=((read_fn)0x53825648u)(fs,"M10VCFG.bin",sizeof(seen),seen);
 for(uint32_t i=0;i<4;i++)if(seen[i]!=receipt[i])applied=0;
 if(!applied){
  if(state.sequence==0xffffffffu)return M10V_LIBRARY_INVALID;
  bank=((get_tone_fn)0x532bd6d4u)(model);tone=((get_tone_fn)0x532bd6b4u)(model);
  uint32_t selected=bank?M10V_SLOT_COUNT:m10v_tone_slot(tone);
  if(selected<M10V_SLOT_COUNT&&state.slots[selected].film!=defaults.slots[selected].film){
   ((set_tone_fn)0x532c26c0u)(model,11u);
   if(((get_tone_fn)0x532bd6b4u)(model)!=11u)return M10V_LIBRARY_STORE_FAILED;
  }
  for(uint32_t i=0;i<M10V_SLOT_COUNT;i++){
#if M10V_PURE_ISP_EFFECTS
   uint32_t film=defaults.slots[i].film;
   m10v_film_effects *e=&defaults.effects[i];
   if(film&&!m10v_film_fx_tagged(e)){
    uint32_t grain=defaults.slots[i].grain;
    m10v_film_fx_set(e,grain?grain-1u:0,0,0,0,0);
    for(uint32_t j=0;j<m10v_library_count(&state);j++){
     if(state.slots[j].film!=film)continue;
     const m10v_film_effects *prior=&state.effects[j];
     if(!grain)defaults.slots[i].grain=state.slots[j].grain;
     m10v_film_fx_set(e,grain?grain-1u:prior->grain_size,prior->leak_gain,
         prior->leak_position,prior->leak_spread,prior->leak_variation&3u);
     e->leak_variation=prior->leak_variation;
     break;
    }
   }
#endif
  }
  for(uint32_t i=0;i<M10V_SLOT_COUNT;i++){state.slots[i]=defaults.slots[i];state.effects[i]=defaults.effects[i];}
  state.reserved&=1u;state.sequence++;state.crc=state_crc(&state,offsetof(m10v_library_state,crc));
  if(store((void *)(uintptr_t)fs,&state))return M10V_LIBRARY_STORE_FAILED;
  if(!((write_fn)0x53825fa8u)(fs,"M10VCFG.bin",sizeof(receipt),receipt)||
     !((read_fn)0x53825648u)(fs,"M10VCFG.bin",sizeof(seen),seen))return M10V_LIBRARY_STORE_FAILED;
  for(uint32_t i=0;i<4;i++)if(seen[i]!=receipt[i])return M10V_LIBRARY_STORE_FAILED;
 }
#if M10V_PRESERVE_EXISTING
 }
#endif
 /* Retire the three removed styles only at the existing safe UI migration
  * gate. Preserve every other slot/effect and the journal ABI. Reads never
  * write. A surviving active film follows its compacted slot using the
  * existing restart-safe selection transaction above. */
 uint32_t used=m10v_library_count(&state),kept=0,removed=0;
 bank=((get_tone_fn)0x532bd6d4u)(model);tone=((get_tone_fn)0x532bd6b4u)(model);
 uint32_t selected=bank?M10V_SLOT_COUNT:m10v_tone_slot(tone),active=selected<used?state.slots[selected].film:0;
 for(uint32_t i=0;i<used;i++){
  if(M10V_ANIME(state.slots[i].film)){removed=1;continue;}
  state.slots[kept]=state.slots[i];state.effects[kept]=state.effects[i];kept++;
 }
 if(removed){
  for(uint32_t i=kept;i<M10V_SLOT_COUNT;i++){m10v_slot empty={0};m10v_film_effects effects={0};state.slots[i]=empty;state.effects[i]=effects;}
  uint32_t target=0;while(target<kept&&state.slots[target].film!=active)target++;
  if(selected<used&&target==kept){
   ((set_tone_fn)0x532c26c0u)(model,11u);
   if(((get_tone_fn)0x532bd6b4u)(model)!=11u)return M10V_LIBRARY_STORE_FAILED;
  }else if(selected<used&&target!=selected)state.reserved|=((selected+1)<<1)|((target+1)<<5);
  if(state.sequence==0xffffffffu)return M10V_LIBRARY_INVALID;
  state.sequence++;state.crc=state_crc(&state,offsetof(m10v_library_state,crc));
  if(store((void *)(uintptr_t)fs,&state))return M10V_LIBRARY_STORE_FAILED;
  if(state.reserved&510u)return m10v_camera_library_reconcile_legacy_selection(model);
 }
 return M10V_LIBRARY_OK;
}
uint32_t m10v_camera_library_shooting_count(void){
 m10v_library_state state;
 if(!m10v_camera_library_preview(&state)&&m10v_camera_library_load(&state)<0)return 12u;
 if(!m10v_library_valid(&state)||(state.reserved&510u))return 12u;
 return 12u+(M10V_APPENDED_SLOTS?m10v_library_count(&state):0u);
}
uint32_t m10v_camera_library_menu_index(void){return M10V_APPENDED_SLOTS?m10v_camera_library_shooting_count()+2u:12u;}
