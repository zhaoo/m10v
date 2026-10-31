/* Independent parameter journal and owner cache. Metadata only, no pixels. */
#include "m10v_isp_effects_camera.h"
#ifndef M10V_ISP_EFFECT_CACHE_OWNER_OFFSET
#error "Builder must reserve ISP effects owner cache and define its offset"
#endif
_Static_assert(sizeof(m10v_isp_effects_settings)==32,"ISP settings ABI");
_Static_assert(sizeof(m10v_isp_effects_camera_cache)==44,"ISP cache ABI");
_Static_assert(!(M10V_ISP_EFFECT_CACHE_OWNER_OFFSET&3u)&&
    M10V_ISP_EFFECT_CACHE_OWNER_OFFSET<=0x2affffd4u,"ISP owner cache bounds");
static const char effect_record_names[2][12]={"ISPFXA.BIN","ISPFXB.BIN"};

static int effect_ram(uintptr_t p,uint32_t bytes){
    return !(p&3u)&&p>=0x55000000u&&p<=0x80000000u-bytes;
}
static m10v_isp_effects_camera_cache *effect_cache(uint32_t owner){
    if(!effect_ram(owner,M10V_ISP_EFFECT_CACHE_OWNER_OFFSET+44u))return 0;
    return (void*)(uintptr_t)(owner+M10V_ISP_EFFECT_CACHE_OWNER_OFFSET);
}
static int effect_same(const void *a,const void *b,uint32_t bytes){
    const uint8_t *x=a,*y=b;
    for(uint32_t i=0;i<bytes;i++)if(x[i]!=y[i])return 0;
    return 1;
}
static int effect_overlap(uintptr_t a,uint32_t an,uintptr_t b,uint32_t bn){
    return a<b+bn&&b<a+an;
}
static uint32_t effect_filesystem(void){
    uint32_t m=((uint32_t(*)(void))0x53828014u)();
    if(!effect_ram(m,12))return 0;
    uint32_t a=*(const uint32_t*)(uintptr_t)(m+8);
    if(!effect_ram(a,4))return 0;
    uint32_t fs=*(const uint32_t*)(uintptr_t)a;
    return effect_ram(fs,0x24)&&*(const uint8_t*)(uintptr_t)(fs+0x20)?fs:0;
}
static int effect_read_cache(m10v_isp_effects_camera_cache *c,
    m10v_isp_effects_settings *settings,uint32_t *sequence,uint32_t *version){
    uint32_t before=__atomic_load_n(&c->version,__ATOMIC_ACQUIRE);
    if(!before||(before&1u)||c->magic!=M10V_ISP_EFFECT_CACHE_MAGIC)return 0;
    m10v_isp_effects_settings local=c->settings;
    uint32_t seq=c->sequence;
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    if(c->magic!=M10V_ISP_EFFECT_CACHE_MAGIC||
       before!=__atomic_load_n(&c->version,__ATOMIC_RELAXED)||
       !m10v_isp_effects_validate(&local))return 0;
    *settings=local;*sequence=seq;*version=before;return 1;
}
static int effect_publish(m10v_isp_effects_camera_cache *c,
    const m10v_isp_effects_settings *settings,uint32_t sequence,uint32_t expected){
    if(expected&1u)return -1;
    uint32_t version=expected;
    if(!__atomic_compare_exchange_n(&c->version,&version,expected+1u,0,
        __ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return -1;
    c->settings=*settings;c->sequence=sequence;c->magic=M10V_ISP_EFFECT_CACHE_MAGIC;
    uint32_t published=expected+2u;
    __atomic_store_n(&c->version,published?published:2u,__ATOMIC_RELEASE);
    return 0;
}
/* 1 selected, 0 neither valid, -1 conflicting/ambiguous valid generations.
 * Buffers are zeroed first so a failed or short native read cannot expose
 * uninitialized stack metadata. The native API itself supplies exact length. */
static int effect_latest(uint32_t fs,m10v_isp_effects_settings *settings,
    uint32_t *sequence,uint8_t *record){
    uint8_t records[2][M10V_ISP_EFFECTS_RECORD_SIZE];
    int good[2];
    for(uint32_t i=0;i<sizeof(records);i++)((volatile uint8_t*)records)[i]=0;
    for(uint32_t i=0;i<2;i++){
        m10v_isp_effects_settings local;uint32_t seq;
        good[i]=((int(*)(uint32_t,const char*,uint32_t,void*))0x53825648u)
            (fs,effect_record_names[i],M10V_ISP_EFFECTS_RECORD_SIZE,records[i])&&
            m10v_isp_effects_decode(records[i],M10V_ISP_EFFECTS_RECORD_SIZE,&local,&seq);
    }
    if(!good[0]&&!good[1])return 0;
    int chosen=m10v_isp_effects_select_newest(records[0],good[0]?M10V_ISP_EFFECTS_RECORD_SIZE:0,
        records[1],good[1]?M10V_ISP_EFFECTS_RECORD_SIZE:0,settings,sequence);
    if(chosen<0)return -1;
    if(record)for(uint32_t i=0;i<M10V_ISP_EFFECTS_RECORD_SIZE;i++)record[i]=records[chosen][i];
    return 1;
}
/* Compare a journal candidate to an authenticated warm cache. Serial ordering
 * has the same less-than-half-range surviving-generation contract as codec. */
static int effect_not_older(const m10v_isp_effects_settings *candidate,uint32_t seq,
    const m10v_isp_effects_settings *cached,uint32_t floor){
    uint32_t delta=seq-floor;
    if(!delta)return effect_same(candidate,cached,sizeof(*cached));
    return delta<0x80000000u;
}
void m10v_isp_effects_camera_init(uint32_t owner){
    m10v_isp_effects_camera_cache *c=effect_cache(owner);
    if(!c)return;
    for(uint32_t i=0;i<sizeof(*c)/4;i++)((volatile uint32_t*)c)[i]=0;
    (void)m10v_isp_effects_camera_refresh(owner);
}
int m10v_isp_effects_camera_refresh(uint32_t owner){
    m10v_isp_effects_camera_cache *c=effect_cache(owner);
    if(!c)return -1;
    m10v_isp_effects_settings old,selected;uint32_t floor,version,seq;
    int warm=effect_read_cache(c,&old,&floor,&version);
    if(!warm){
        if(c->magic||__atomic_load_n(&c->version,__ATOMIC_ACQUIRE))return -2;
        version=0;
    }
    uint32_t fs=effect_filesystem();if(!fs)return -2;
    int found=effect_latest(fs,&selected,&seq,0);
    if(found<0)return -3;
    if(!found){
        m10v_isp_effects_defaults(&selected);seq=0;
        /* ctor publishes unsaved defaults before first menu entry. Reopening
         * that same empty journal must not reject the whole Effects page.
         * A previously persisted/nondefault cache still rejects lost records. */
        if(warm&&(floor||!effect_same(&old,&selected,sizeof(old))))return -2;
    }else if(warm&&!effect_not_older(&selected,seq,&old,floor))return -3;
    return effect_publish(c,&selected,seq,version);
}
int m10v_isp_effects_camera_save(uint32_t owner,const m10v_isp_effects_settings *settings){
    m10v_isp_effects_camera_cache *c=effect_cache(owner);
    if(!c||!effect_ram((uintptr_t)settings,sizeof(*settings)))return -1;
    m10v_isp_effects_settings desired=*settings;
    if(!m10v_isp_effects_validate(&desired))return -1;
    m10v_isp_effects_settings cached,selected;uint32_t floor,version,seq;
    if(!effect_read_cache(c,&cached,&floor,&version))return -2;
    uint32_t fs=effect_filesystem();if(!fs)return -2;
    int found=effect_latest(fs,&selected,&seq,0);
    if(found<0)return -3;
    if(found){
        uint32_t delta=seq-floor;
        if(delta==0x80000000u||(!delta&&!effect_same(&selected,&cached,sizeof(cached))))return -3;
        if(delta&&delta<0x80000000u)floor=seq;
    }
    seq=floor+1u;
    uint8_t record[M10V_ISP_EFFECTS_RECORD_SIZE],back[M10V_ISP_EFFECTS_RECORD_SIZE];
    if(!m10v_isp_effects_encode(&desired,seq,record,sizeof(record)))return -1;
    for(uint32_t i=0;i<sizeof(back);i++)((volatile uint8_t*)back)[i]=0;
    if(!((int(*)(uint32_t,const char*,uint32_t,const void*))0x53825fa8u)
        (fs,effect_record_names[seq&1u],sizeof(record),record))return -4;
    if(!((int(*)(uint32_t,const char*,uint32_t,void*))0x53825648u)
        (fs,effect_record_names[seq&1u],sizeof(back),back)||
        !effect_same(record,back,sizeof(record)))return -5;
    uint32_t winner;
    if(effect_latest(fs,&selected,&winner,back)!=1||winner!=seq||
        !effect_same(record,back,sizeof(record)))return -6;
    return effect_publish(c,&desired,seq,version);
}
int m10v_isp_effects_camera_snapshot(m10v_isp_effects_settings *out,uint32_t *sequence){
    if(!effect_ram((uintptr_t)out,sizeof(*out))||!effect_ram((uintptr_t)sequence,4)||
       effect_overlap((uintptr_t)out,sizeof(*out),(uintptr_t)sequence,4)||
       !(*(const volatile uint32_t*)0x55063910u&1u))return 0;
    uint32_t owner=__atomic_load_n((const uint32_t*)0x55063988u,__ATOMIC_ACQUIRE);
    m10v_isp_effects_camera_cache *c=effect_cache(owner);
    if(!c||effect_overlap((uintptr_t)out,sizeof(*out),(uintptr_t)c,sizeof(*c))||
       effect_overlap((uintptr_t)sequence,4,(uintptr_t)c,sizeof(*c)))return 0;
    m10v_isp_effects_settings local;uint32_t seq,version;
    if(!effect_read_cache(c,&local,&seq,&version)||
       !(*(const volatile uint32_t*)0x55063910u&1u)||
       owner!=__atomic_load_n((const uint32_t*)0x55063988u,__ATOMIC_ACQUIRE))return 0;
    *out=local;*sequence=seq;return 1;
}
