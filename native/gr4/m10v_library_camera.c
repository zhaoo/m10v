/* GR IV 1.04 native AppData ABI adapter, independently traced from
 * the official firmware. Stock FS services own their header/CRC/backup path.
 * M10V's two private journal names never overwrite an APData setting record.
 */
#include "m10v_library.h"
#include <stddef.h>

typedef uint32_t (*manager_fn)(void);
typedef int (*read_fn)(uint32_t, const char *, uint32_t, void *);
typedef int (*write_fn)(uint32_t, const char *, uint32_t, const void *);
static const char state_names[2][12] = {"M10V6A.bin", "M10V6B.bin"};

static int ram(const void *ptr, uint32_t size) {
    uintptr_t p = (uintptr_t)ptr;
    return !(p & 3) && p >= 0x55000000u && p < 0x80000000u && size <= 0x80000000u - p;
}
static uint32_t filesystem(void) {
    uint32_t manager = ((manager_fn)0x53a81480u)();
    if (!ram((void *)(uintptr_t)manager, 12)) return 0;
    uint32_t appdata = ((const uint32_t *)(uintptr_t)manager)[2];
    if (!ram((void *)(uintptr_t)appdata, 8)) return 0;
    uint32_t fs = ((const uint32_t *)(uintptr_t)appdata)[1];
    if (!ram((void *)(uintptr_t)fs, 0x50) || !((const uint8_t *)(uintptr_t)fs)[0x4c]) return 0;
    return fs;
}
/* GR IV loader returns the allocation through an output parameter. Validate
 * physical size and CRC-framed payload before copying; stock sized read alone
 * does not establish that a truncated record contains enough bytes. */
static int read_record(uint32_t fs,const char *name,uint32_t size,void *out){
    typedef uint32_t (*stat_fn)(uint32_t,const char *,void *);
    typedef void (*load_fn)(uint32_t,const char *,uint32_t *,uint32_t *);
    typedef int (*check_fn)(uint32_t,uint32_t,uint32_t,uint32_t *,uint32_t *);
    typedef void (*release_fn)(uint32_t,uint32_t);
    char path[32]={'F',':','\\',0};uint32_t i=0;
    while(name[i]&&i<27){path[i+3]=name[i];i++;}if(name[i])return 0;path[i+3]=0;
    uint32_t manager=((const uint32_t *)(uintptr_t)fs)[11];
    if(!ram((void *)(uintptr_t)manager,4)||((stat_fn)0x5383b154u)(manager,path,0)!=size+8)return 0;
    uint32_t raw=0,n=0,bytes=0,content=0;int ok=0;
    ((load_fn)0x5383b288u)(manager,path,&raw,&n);
    if(!raw)return 0;
    if(n==size+8&&ram((void *)(uintptr_t)raw,n)&&
       ((check_fn)0x53a7ee80u)(fs,n,raw,&bytes,&content)&&bytes==size&&content==raw+8){
        for(uint32_t j=0;j<size;j++)((uint8_t *)out)[j]=((const uint8_t *)(uintptr_t)content)[j];ok=1;
    }
    ((release_fn)0x53838afcu)(manager,raw);return ok;
}
static void copy(m10v_library_state *dst, const m10v_library_state *src) {
    for (uint32_t i = 0; i < sizeof(*src); ++i) ((uint8_t *)dst)[i] = ((const uint8_t *)src)[i];
}
static int store(void *context, const m10v_library_state *next) {
    uint32_t fs = (uint32_t)(uintptr_t)context;
    const char *name = state_names[next->sequence & 1];
    m10v_library_state readback;
    for (uint32_t i = 0; i < sizeof(readback); ++i) ((uint8_t *)&readback)[i] = 0;
    if (!((write_fn)0x53a7fb1cu)(fs, name, sizeof(*next), next) ||
        !read_record(fs, name, sizeof(readback), &readback) ||
        !m10v_library_valid(&readback)) return -1;
    for (uint32_t i = 0; i < sizeof(readback); ++i)
        if (((const uint8_t *)&readback)[i] != ((const uint8_t *)next)[i]) return -1;
    return 0;
}
typedef struct {uint32_t magic;uint16_t version,size;uint32_t sequence;m10v_slot slots[5];uint8_t stamp,format,corner,color;m10v_film_effects effects[5];uint32_t reserved,crc;} legacy_state;
static const char legacy_names[2][12]={"M10V5A.bin","M10V5B.bin"};
static uint32_t state_crc(const void *v,uint32_t bytes){uint32_t crc=0xffffffffu;const uint8_t *p=v;for(uint32_t i=0;i<bytes;i++){crc^=p[i];for(uint32_t b=0;b<8;b++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return ~crc;}
static void expand_legacy(m10v_library_state *out,const legacy_state *old){
 m10v_library_init(out);for(uint32_t i=0;i<M10V_SLOT_COUNT;i++){m10v_slot v={0};m10v_film_effects e={0};out->slots[i]=v;out->effects[i]=e;}
 out->sequence=old->sequence;out->stamp=old->stamp;out->format=old->format;out->corner=old->corner;out->color=old->color;out->reserved=old->reserved;
 for(uint32_t i=0;i<5;i++){out->slots[i]=old->slots[i];out->effects[i]=old->effects[i];if(M10V_CUSTOM(old->slots[i].film))out->effects[i].reserved[0]+=(uint8_t)(2*i);}
 out->crc=state_crc(out,offsetof(m10v_library_state,crc));
}
static int legacy_state_valid(const legacy_state *old){
 if(old->magic!=0x5630314du||old->version!=4||old->size!=104||old->crc!=state_crc(old,100))return 0;
 for(uint32_t i=0;i<5;i++)if(!old->slots[i].film|| (M10V_CUSTOM(old->slots[i].film)&&(old->effects[i].reserved[0]<1||old->effects[i].reserved[0]>2)))return 0;
 /* Validate every positional legacy recipe without compacting duplicates. */
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
        if(!read_record(fs,names[k],64,p))continue;
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
    for(uint32_t i=0;i<2;++i)good[i]=read_record(fs,names[i],44,records[i])&&legacy_valid(records[i]);
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
    if(!read_record(fs,name,sizeof(*state),state)||state->version!=3||state->size!=104||state->crc!=texture_crc(state))return 0;
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
        available[i] = read_record(fs, legacy_names[i], sizeof(*state), &candidates[i]) &&
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
 for(uint32_t k=0;k<2;k++){for(uint32_t i=0;i<sizeof(*state);i++)((uint8_t *)&candidates[k])[i]=0;good[k]=read_record(fs,state_names[k],sizeof(*state),&candidates[k])&&m10v_library_valid(&candidates[k]);}
 if(good[0]||good[1]){uint32_t selected=!good[0]||(good[1]&&candidates[1].sequence>candidates[0].sequence);copy(state,&candidates[selected]);return 0;}
 legacy_state old;int result=load_legacy_library(&old);if(result<0)return result;expand_legacy(state,&old);return result==0?4:result;
}
int m10v_camera_library_load(m10v_library_state *state){
 int result=load_library(state);
 if(result>=0){
  /* A shared journal can arrive from GR III/IIIx. Keep the user's other
   * slots in RAM without rewriting a record containing unsupported ISP color. */
  uint32_t count=0,changed=0;
  for(uint32_t i=0;i<M10V_SLOT_COUNT;i++){
   if(state->slots[i].film==M10V_MARLBORO_ID){changed=1;continue;}
   state->slots[count]=state->slots[i];state->effects[count]=state->effects[i];count++;
  }
  if(changed){
   for(;count<M10V_SLOT_COUNT;count++){
    for(uint32_t j=0;j<sizeof(m10v_slot);j++)((uint8_t*)&state->slots[count])[j]=0;
    for(uint32_t j=0;j<sizeof(m10v_film_effects);j++)((uint8_t*)&state->effects[count])[j]=0;
   }
   uint32_t crc=0xffffffffu;
   for(uint32_t i=0;i<sizeof(*state)-4;i++){crc^=((uint8_t*)state)[i];for(uint32_t bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}
   state->crc=~crc;
  }
 }
 return result;
}
int m10v_camera_library_select(m10v_library_state *state, uint32_t slot, uint32_t film) {
    if(film==M10V_MARLBORO_ID)return M10V_LIBRARY_INVALID;
    if (!ram(state, sizeof(*state))) return M10V_LIBRARY_INVALID;
    uint32_t fs = filesystem();
    return fs ? m10v_library_select(state, slot, film, store, (void *)(uintptr_t)fs) : M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_texture(m10v_library_state *state, uint32_t slot, uint32_t grain, uint32_t soft) {
    if (!ram(state, sizeof(*state))) return M10V_LIBRARY_INVALID;
    uint32_t fs = filesystem();
    return fs ? m10v_library_texture(state, slot, grain, soft, store, (void *)(uintptr_t)fs) : M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_halation(m10v_library_state *state,uint32_t slot,uint32_t gain,uint32_t spread,uint32_t threshold,uint32_t profile){
    if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();return fs?m10v_library_halation(state,slot,gain,spread,threshold,profile,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_detail(m10v_library_state *state,uint32_t slot,uint32_t gain,uint32_t spread,uint32_t threshold,uint32_t grain,uint32_t soft){
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

int m10v_camera_library_effects(m10v_library_state *state,uint32_t slot,uint32_t field,uint32_t value){
    if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();return fs?m10v_library_effects(state,slot,field,value,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}
int m10v_camera_library_reset(m10v_library_state *state,uint32_t slot){
    if(!ram(state,sizeof(*state)))return M10V_LIBRARY_INVALID;
    uint32_t fs=filesystem();return fs?m10v_library_reset(state,slot,store,(void *)(uintptr_t)fs):M10V_LIBRARY_STORE_FAILED;
}
