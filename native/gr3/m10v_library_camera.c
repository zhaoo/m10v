/* GR III Street 2.10 native AppData ABI adapter, independently traced from
 * the official firmware. Stock FS services own their header/CRC/backup path.
 * M10V's two private journal names never overwrite an APData setting record.
 */
#include "m10v_library.h"
#include "m10v_tone.h"
#include <stddef.h>
#include "m10v_custom_isp.h"

typedef uint32_t (*manager_fn)(void);
typedef int (*read_fn)(uint32_t, const char *, uint32_t, void *);
typedef int (*write_fn)(uint32_t, const char *, uint32_t, const void *);
static const char state_names[2][12] = {"M10V6A.bin", "M10V6B.bin"};

static int ram(const void *ptr, uint32_t size) {
    uintptr_t p = (uintptr_t)ptr;
    return !(p & 3) && p >= 0x55000000u && p < 0x80000000u && size <= 0x80000000u - p;
}
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
typedef struct {uint32_t id,bank;m10v_isp_frame_target target;} custom_profile;
typedef struct {uint32_t magic,version; m10v_library_state state;custom_profile profiles[M10V_SLOT_COUNT];} preview_cache;
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
    copy(&p->state,s);__atomic_store_n(&p->version,v+2,__ATOMIC_RELEASE);
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
 if(m10v_library_valid(state)){if(!refresh_profiles(p,state,v))return;copy(&p->state,state);}
 __atomic_store_n(&p->version,v+1,__ATOMIC_RELEASE);
#else
 (void)state;
#endif
}
int m10v_camera_library_preview(m10v_library_state *out){
#if M10V_LIVE_COLOR
    preview_cache *p=preview_owner();if(!p||!ram(out,sizeof(*out)))return 0;
    uint32_t before=__atomic_load_n(&p->version,__ATOMIC_ACQUIRE);
    if(!before||(before&1u))return 0;
    copy(out,&p->state);__atomic_thread_fence(__ATOMIC_ACQUIRE);
    return p->magic==PREVIEW_MAGIC&&before==__atomic_load_n(&p->version,__ATOMIC_RELAXED)&&m10v_library_valid(out)&&!(out->reserved&510u);
#else
    (void)out;return 0;
#endif
}
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
void m10v_camera_library_preview_init(uint32_t owner){
#if M10V_LIVE_COLOR
    if(!ram((void *)(uintptr_t)owner,PREVIEW_OFFSET+PREVIEW_BYTES))return;
    preview_cache *p=(preview_cache *)(uintptr_t)(owner+PREVIEW_OFFSET);
    p->magic=0;p->version=0;
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
static int store(void *context, const m10v_library_state *next) {
    uint32_t fs = (uint32_t)(uintptr_t)context;
    const char *name = state_names[next->sequence & 1];
    m10v_library_state readback;
    for (uint32_t i = 0; i < sizeof(readback); ++i) ((uint8_t *)&readback)[i] = 0;
    if (!((write_fn)0x53825fa8u)(fs, name, sizeof(*next), next) ||
        !((read_fn)0x53825648u)(fs, name, sizeof(readback), &readback) ||
        !m10v_library_valid(&readback)) return -1;
    for (uint32_t i = 0; i < sizeof(readback); ++i)
        if (((const uint8_t *)&readback)[i] != ((const uint8_t *)next)[i]) return -1;
#if M10V_LIVE_COLOR
    publish_preview(preview_owner(),next);
#endif
    return 0;
}
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
static int load_library(m10v_library_state *state){
 if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
 uint32_t fs=filesystem();if(!fs)return M10V_LIBRARY_INVALID;
 m10v_library_state candidates[2];int good[2]={0,0};
 for(uint32_t k=0;k<2;k++){for(uint32_t i=0;i<sizeof(*state);i++)((uint8_t *)&candidates[k])[i]=0;good[k]=((read_fn)0x53825648u)(fs,state_names[k],sizeof(*state),&candidates[k])&&m10v_library_valid(&candidates[k]);}
 if(good[0]||good[1]){uint32_t selected=!good[0]||(good[1]&&candidates[1].sequence>candidates[0].sequence);copy(state,&candidates[selected]);return 0;}
 legacy_state old;int result=load_legacy_library(&old);if(result<0)return result;expand_legacy(state,&old);return result==0?4:result;
}
int m10v_camera_library_load(m10v_library_state *state){
    int result=load_library(state);
#if !M10V_FOUR_LOOKS_NATIVE
    if(result>=0){
        /* A journal moved from GR III must not enable an unverified look on
         * another model. Keep all supported slots and their settings; do not
         * rewrite the user's journal merely because it was read here. */
        uint32_t count=0,changed=0;
        for(uint32_t i=0;i<M10V_SLOT_COUNT;i++){
            if(M10V_FOUR_LOOKS(state->slots[i].film)){changed=1;continue;}
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
#if !M10V_FOUR_LOOKS_NATIVE
    if(M10V_FOUR_LOOKS(film))return M10V_LIBRARY_INVALID;
#endif
#if !M10V_LIVE_COLOR
    if(film==294||(M10V_ANIME_E6(film)||M10V_C41(film)||M10V_EXTRA_FILM(film)))return M10V_LIBRARY_INVALID;
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
