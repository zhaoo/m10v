/* Optional GR III SD checkpoints. Two CRC-protected pages per channel retain
 * the previous checkpoint if power is lost during a write. No writable ROM,
 * persistent handles or retries; concurrent logger invocations are skipped.
 * Stock filesystem calls may still wait on other camera tasks. */
#include "m10v_debug.h"
#ifndef M10V_DEBUG_BUILD_ID
#define M10V_DEBUG_BUILD_ID 0u
#endif
typedef uint32_t (*get_fn)(void);
typedef void *(*alloc_fn)(uint32_t);
typedef void (*free_fn)(void *);
typedef int (*open_fn)(uint32_t,const char *,uint32_t,uint32_t *,uint32_t *);
typedef int (*io_fn)(uint32_t,uint32_t,void *,uint32_t,uint32_t *);
typedef int (*close_fn)(uint32_t,uint32_t,uint32_t *);
static const char paths[8][16]={"C:\\M10VMN0.BIN","C:\\M10VMN1.BIN","C:\\M10VCP0.BIN","C:\\M10VCP1.BIN","C:\\M10VIO0.BIN","C:\\M10VIO1.BIN","C:\\M10VAK0.BIN","C:\\M10VAK1.BIN"};
static uint32_t event_channel(uint32_t event){return (event>=230&&event<=273)||(event>=85&&event<=99)?4u:event>=180&&event<=209?3u:event>=100?2u:1u;}
static int ram(uint32_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p;}
static int code(uint32_t p,uint32_t n){return !(p&3)&&p>=0x53000000u&&p<0x540b6000u&&n<=0x540b6000u-p;}
static uint32_t crc(const uint32_t *words){
    const uint8_t *bytes=(const uint8_t *)words;uint32_t v=0xffffffffu;
    for(uint32_t i=0;i<60;++i){v^=bytes[i];for(uint32_t b=0;b<8;++b)v=(v>>1)^(0xedb88320u&(0u-(v&1u)));}
    return ~v;
}
static int valid(const uint32_t *p,uint32_t channel){
    if(p[0]!=0x4744564du||p[1]!=1||p[2]!=M10V_DEBUG_BUILD_ID||p[3]>63||p[4]>=63||
       !p[5]||p[5]>=0xffffff00u||p[5]<p[3]||p[6]!=channel||p[15]!=crc(p)||
       (p[3]<63&&p[4]!=p[3]))return 0;
    for(uint32_t i=0;i<p[3];++i){const uint32_t *r=p+16+i*16;
        if(r[0]!=0x474c564du||r[1]!=1||r[8]!=M10V_DEBUG_BUILD_ID||r[9]!=channel||
           !r[2]||r[2]>p[5]||r[15]!=crc(r))return 0;
    }
    return 1;
}
static int transfer(uint32_t fs,const uint32_t *v,const char *path,uint32_t *page,int writing){
    uint32_t handle=0,error=0;
    if(!((open_fn)v[7])(fs,path,writing?0:1,&handle,&error)||!handle)return 0;
    int ok=0;
    if(!error)ok=((io_fn)v[writing?10:9])(fs,handle,page,4096,&error)&&!error;
    uint32_t closing_error=0;
    int closed=((close_fn)v[8])(fs,handle,&closing_error);
    return ok&&closed&&!closing_error;
}
int m10v_debug_batch(const uint32_t *events,uint32_t count){
    if(!count||count>32||!ram((uint32_t)(uintptr_t)events,count*20))return 0;
#if M10V_ADJ_EXIT_TRACE
    /* Diagnostic candidate only: retain exit evidence, suppress unrelated
     * preview/capture/menu traffic and its filesystem transactions. */
    for(uint32_t i=0;i<count;i++)if(events[i*5]<230||events[i*5]>273)return 0;
#endif
    uint32_t channel=event_channel(events[0]),mask=1;
    for(uint32_t i=0;i<count;++i)if(event_channel(events[i*5])!=channel)return 0;
    /* The stock model ends at byte0x1c; byte0x1d is private menu mode,
     * byte0x1e private selected tone. Byte0x1f holds one shared logger busy bit.
     * Channels use separate files but share the stock filesystem mutex; skip
     * concurrent logging rather than waiting for another logger's SD calls.
     * Failed/reentrant writers never clear another invocation's ownership. */
    volatile uint8_t *guard=(volatile uint8_t *)0x5506821fu;
    if(__atomic_fetch_or(guard,(uint8_t)mask,__ATOMIC_ACQUIRE)&mask)return 0;
    int result=0;uint32_t *pages=0;
    uint32_t manager=((get_fn)0x535847d8u)();if(!ram(manager,24))goto done;
    uint32_t fs=((const uint32_t *)(uintptr_t)manager)[5];if(!ram(fs,4))goto done;
    uint32_t vt=*(const uint32_t *)(uintptr_t)fs;if(!code(vt,44))goto done;
    const uint32_t *v=(const uint32_t *)(uintptr_t)vt;
    if(!code(v[7],4)||!code(v[8],4)||!code(v[9],4)||!code(v[10],4))goto done;
    pages=((alloc_fn)0x536af2a8u)(8192);if(!ram((uint32_t)(uintptr_t)pages,8192)){pages=0;goto done;}
    for(uint32_t i=0;i<2048;++i)pages[i]=0;
    uint32_t offset=(channel-1)*2;
    int good0=transfer(fs,v,paths[offset],pages,0)&&valid(pages,channel);
    int good1=transfer(fs,v,paths[offset+1],pages+1024,0)&&valid(pages+1024,channel);
    uint32_t selected=good1&&(!good0||pages[1024+5]>pages[5]);
    uint32_t *page=pages+selected*1024;
    if(!good0&&!good1){for(uint32_t i=0;i<1024;++i)page[i]=0;
        page[0]=0x4744564du;page[1]=1;page[2]=M10V_DEBUG_BUILD_ID;page[6]=channel;}
    for(uint32_t i=0;i<count;++i){
        const uint32_t *event=events+i*5;
        uint32_t sequence=page[5]+1,index=page[4];
        uint32_t *record=page+16+index*16;
        for(uint32_t j=0;j<16;++j)record[j]=0;
        record[0]=0x474c564du;record[1]=1;record[2]=sequence;record[3]=event[0];
        record[4]=event[1];record[5]=event[2];record[6]=event[3];record[7]=event[4];
        record[8]=M10V_DEBUG_BUILD_ID;record[9]=channel;record[15]=crc(record);
        if(page[3]<63)++page[3];page[4]=index==62?0:index+1;page[5]=sequence;
    }
    page[15]=crc(page);
    /* Always overwrite the other page, preserving the valid source page. */
    result=transfer(fs,v,paths[offset+(good0||good1?1-selected:1)],page,1);
done:
    if(pages)((free_fn)0x536af2e4u)(pages);
    __atomic_fetch_and(guard,(uint8_t)~mask,__ATOMIC_RELEASE);
    return result;
}

int m10v_debug_log(uint32_t event,uint32_t a,uint32_t b,uint32_t c,uint32_t d){
    const uint32_t record[5]={event,a,b,c,d};
    return m10v_debug_batch(record,1);
}
