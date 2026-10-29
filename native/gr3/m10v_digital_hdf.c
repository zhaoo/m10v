/* GR III 2.10 only. No writable globals, pixel loops, locks, DMA, wait or
 * buffer allocation here. The original Clarity owner sizes/submits/waits/frees
 * its unchanged pyramid. Only settings values and coefficient rows change.
 * Standalone uses a16-byte tail; combined builds use the sole trace allocator
 * and its explicitly reserved per-shot words. */
#include "m10v_tone.h"
#include <stdint.h>
#include "m10v_hdf_state.h"
#ifndef M10V_HDF_DEFAULT
#define M10V_HDF_DEFAULT 0u
#endif
#if M10V_HDF_SHARED_RECIPE
#include "m10v_save_trace.h"
#endif
#define STOCK_BYTES 0x4778u
#define HDF_BYTES (STOCK_BYTES+16u)
#define HDF_MAGIC 0x31464448u
#if M10V_HDF_SHARED_RECIPE
/* Sole trace allocator owns these three previously reserved token words.
 * Raw lifetime transitions preserve them; initialization zeroes them. */
typedef struct {uint32_t ready,strength,si;} hdf_shot;
#else
typedef struct {uint32_t magic,ready,strength,si;} hdf_shot;
#endif
static int ram(uintptr_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<=0x80000000u-n;}
static hdf_shot *owner(uintptr_t p){
    if(!ram(p,HDF_BYTES)||*(const uint32_t *)p!=0x53d0fc90u)return 0;
#if M10V_HDF_SHARED_RECIPE
    if(!ram(p,M10V_SAVE_RECIPE_EXTENDED_BYTES)||
       *(const uint32_t *)(p+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC)return 0;
    m10v_capture_raw_lifetime *token=(void *)(p+M10V_CAPTURE_RAW_TOKEN_OFFSET);
    if(token->magic!=0x31574c52u||token->owner!=p)return 0;
    return (hdf_shot *)token->reserved;
#else
    hdf_shot *s=(hdf_shot *)(p+STOCK_BYTES);
    return s->magic==HDF_MAGIC?s:0;
#endif
}
/* A separate 24-byte journal. No film state or film defaults are read. */
typedef struct {uint32_t magic,version,sequence,strength,reserved,crc;} hdf_record;
static const char names[2][12]={"M10VHD0.BIN","M10VHD1.BIN"};
static __attribute__((always_inline)) inline uint32_t crc(const hdf_record *r){
 uint32_t c=0xffffffffu;for(uint32_t i=0;i<20;i++){c^=((const uint8_t *)r)[i];for(uint32_t b=0;b<8;b++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return ~c;
}
static __attribute__((always_inline)) inline int valid(const hdf_record *r){return r->magic==HDF_MAGIC&&r->version==1&&r->strength<4&&!r->reserved&&r->crc==crc(r);}
static uint32_t filesystem(void){
 uint32_t m=((uint32_t (*)(void))0x53828014u)();if(!ram(m,12))return 0;
 uint32_t a=*(const uint32_t *)(uintptr_t)(m+8);if(!ram(a,4))return 0;
 uint32_t fs=*(const uint32_t *)(uintptr_t)a;
 return ram(fs,0x24)&&*(const uint8_t *)(uintptr_t)(fs+0x20)?fs:0;
}
static int latest(uint32_t fs,hdf_record *out){
 hdf_record records[2];int good[2];
 for(uint32_t i=0;i<sizeof(records);i++)((uint8_t *)records)[i]=0;
 for(uint32_t i=0;i<2;i++)good[i]=((int (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,names[i],24,&records[i])&&valid(&records[i]);
 if(!good[0]&&!good[1])return 0;
 uint32_t i=!good[0]||(good[1]&&records[1].sequence>records[0].sequence);
 for(uint32_t n=0;n<6;n++)((uint32_t *)out)[n]=((const uint32_t *)&records[i])[n];return 1;
}
int m10v_hdf_load(uint32_t *strength);
static void publish(uint32_t strength){
#if M10V_HDF_UI_CACHE
 m10v_hdf_ui *p=m10v_hdf_ui_owner();
 if(p&&strength<4)__atomic_store_n(&p->published,0x100u|strength,__ATOMIC_RELEASE);
#else
 (void)strength;
#endif
}
int m10v_hdf_cached(uint32_t *strength){
#if M10V_HDF_UI_CACHE
 m10v_hdf_ui *p=m10v_hdf_ui_owner();if(!p)return -1;
 uint32_t v=__atomic_load_n(&p->published,__ATOMIC_ACQUIRE);
 if((v&~3u)!=0x100u)return -1;*strength=v&3u;return 0;
#else
 return m10v_hdf_load(strength);
#endif
}
int m10v_hdf_load(uint32_t *strength){
 if(!ram((uintptr_t)strength,4))return -1;
 uint32_t fs=filesystem();if(!fs)return -1;
 hdf_record r;*strength=latest(fs,&r)?r.strength:M10V_HDF_DEFAULT;publish(*strength);return 0;
}
int m10v_hdf_save(uint32_t strength){
 if(strength>3)return -1;uint32_t fs=filesystem();if(!fs)return -1;
 hdf_record old,r,back;uint32_t sequence=latest(fs,&old)?old.sequence:0;if(sequence==0xffffffffu)return -1;
 r.magic=HDF_MAGIC;r.version=1;r.sequence=sequence+1;r.strength=strength;r.reserved=0;r.crc=crc(&r);
 for(uint32_t i=0;i<6;i++)((uint32_t *)&back)[i]=0;
 if(!((int (*)(uint32_t,const char *,uint32_t,const void *))0x53825fa8u)(fs,names[r.sequence&1],24,&r)||
    !((int (*)(uint32_t,const char *,uint32_t,void *))0x53825648u)(fs,names[r.sequence&1],24,&back)||!valid(&back))return -1;
 for(uint32_t i=0;i<6;i++)if(((const uint32_t *)&r)[i]!=((const uint32_t *)&back)[i])return -1;publish(strength);return 0;
}
void m10v_hdf_bootstrap(void){
#if M10V_HDF_UI_CACHE
 uint32_t strength;if(m10v_hdf_cached(&strength)<0)m10v_hdf_load(&strength);
#endif
}
#if !M10V_HDF_SHARED_RECIPE
uint32_t m10v_hdf_alloc(uint32_t bytes){
    uint32_t p=((uint32_t (*)(uint32_t))0x5351091cu)(bytes==STOCK_BYTES?HDF_BYTES:bytes);
    if(bytes==STOCK_BYTES&&ram(p,HDF_BYTES)){
        hdf_shot *s=(hdf_shot *)(uintptr_t)(p+STOCK_BYTES);
        s->ready=0;s->strength=0;s->si=0;s->magic=HDF_MAGIC;
    }
    return p;
}
#endif
void m10v_hdf_producer(uint32_t recipe){
    hdf_shot *s=owner(recipe);if(!s)return;
    /* These two callsites are AFTER the original producer mutex release,
     * BEFORE queueing. Refresh on reuse; never load FS in ISP callbacks. */
    s->ready=0;s->si=0;s->strength=0;
    uint32_t strength;
    if(m10v_hdf_cached(&strength)<0){s->ready=128;return;}
    s->strength=strength;s->ready=1;
}
void m10v_hdf_reserve(uint32_t recipe){
    hdf_shot *s=owner(recipe);if(!s)return;
    /* Original post-mutex reservation sites delimit a new exposure even
     * when the native allocator reuses the same recipe/ShootingInfo. They
     * reset ownership only; settings freeze later at actual task ingress. */
    s->ready=0;s->strength=0;s->si=0;
}
void m10v_hdf_task_snapshot(uint32_t recipe){
    hdf_shot *s=owner(recipe);if(!s||s->ready)return;
    /* Original task ingress5351ea9c freezes this shot once, independently
     * of color-cache admission. Later task kinds/UI changes cannot retarget
     * it. Both successful and unavailable-cache decisions stay frozen. */
    m10v_hdf_producer(recipe);
}
void m10v_hdf_gate(uint32_t recipe,uint32_t request,uint32_t si){
    hdf_shot *s=owner(recipe);
    if(!s||!(s->ready&1u)||!s->strength||s->strength>3||!ram(request,0x40)||!ram(si,0xb28)||
       *(const uint32_t *)(uintptr_t)(recipe+0x5c)!=request)return;
    /* Only the still ImageControl tone range; HDR has distinct semantics.
     * Tone20 uses Standard ISP only when installed as a film carrier. Stock
     * Soft Monotone retains its own native graph; device image QA is pending. */
    uint32_t tone=*(const uint8_t *)(uintptr_t)(si+0x77c);
    if(!m10v_tone_valid(tone)||tone==14)return;
    s->si=si;s->ready|=2u;
    *(uint8_t *)(uintptr_t)(request+0x24)=1;
}
uint32_t m10v_hdf_settings(uint32_t context,uint32_t params){
    if(!ram(context,0x40)||*(const uint32_t *)(uintptr_t)context!=0x53d0fc60u||!ram(params,0x34))return 0;
    uint32_t source=*(const uint32_t *)(uintptr_t)(context+0x30);
    if(source<0x1a8)return 0;
    uint32_t recipe=source-0x1a8;
    /* The source recipe must own this very Develop context. Cross-recipe
     * transfer is not guessed; a mismatch retains the original parameters. */
    hdf_shot *s=owner(recipe);
    if(!s)return 0;
    if(context!=recipe+0x4320){s->ready|=64u;return 0;}
    if(!(s->ready&1u)||s->strength<1||s->strength>3)return 0;
    if(!s->si||s->si!=*(const uint32_t *)(uintptr_t)(context+0x34)){
        s->ready|=32u;return 0;
    }
    uint32_t values=*(const uint32_t *)(uintptr_t)(params+0x10);
    if(!ram(values,12))return 0;
    /* Native Clarity5..7 selects new rows9..11. Original -4..4 rows and
     * original scale/shading/grain/HDR fields remain unchanged. */
    ((int16_t *)(uintptr_t)values)[1]=(int16_t)(4+s->strength);
    s->ready|=4u;return 1;
}

/* Called after the original digital-filter execution returns. Diagnostics do
 * not authorize rendering, resize workspaces or change the original result. */
void m10v_hdf_done(uint32_t context,uint32_t params,uint32_t result){
    if(!ram(context,0x40)||*(const uint32_t *)(uintptr_t)context!=0x53d0fc60u||!ram(params,0x34))return;
    uint32_t source=*(const uint32_t *)(uintptr_t)(context+0x30);
    if(source<0x1a8||context!=source-0x1a8+0x4320)return;
    hdf_shot *s=owner(source-0x1a8);
    if(!s||!(s->ready&4u)||s->si!=*(const uint32_t *)(uintptr_t)(context+0x34))return;
    uint32_t values=*(const uint32_t *)(uintptr_t)(params+0x10);
    if(!ram(values,12))return;
    s->ready|=result==1&&((const int16_t *)(uintptr_t)values)[1]==(int16_t)(4+s->strength)?8u:16u;
}
