/* Still-JPEG bridge for the original GR III 2.10 recipe topology.
 * The original encoder call is chained separately by an ARM trampoline.
 * CFA is checked as a protected interval and is never read or written.
 */
#include "m10v_tone.h"
#include "m10v_library.h"
#include "m10v_anime.h"
#include "m10v_debug.h"
#include "m10v_capture_profile.h"
#include "m10v_save_trace.h"
/* Builder supplies the complete allocation contract without probing or
 * dereferencing a possibly absent extension merely to reject overlap. */
#ifndef M10V_CAPTURE_RECIPE_BYTES
#define M10V_CAPTURE_RECIPE_BYTES M10V_SAVE_RECIPE_BYTES
#endif
#include "m10v_color_cache.h"
#if M10V_SD_LIBRARY
#include "m10v_sd_library.h"
#endif
#if M10V_RAW_LIFETIME
#include "m10v_save_trace.h"
#endif
#include "m10v_isp_recipe_color.h"
#if M10V_BORDER_ENABLED && M10V_RECIPE_SNAPSHOT
#include "m10v_border_shot.h"
#endif
#if M10V_RECIPE_SNAPSHOT
#endif
#if M10V_CAPTURE_PROFILE
int m10v_library_render_profiled(m10v_library_image *,const m10v_library_state *,uint32_t,const m10v_library_date *,uint32_t,uint8_t *,uint32_t,m10v_capture_profile *);
int m10v_library_render_native_profiled(m10v_library_image *,const m10v_library_state *,uint32_t,const m10v_library_date *,uint32_t,uint8_t *,uint32_t,uint32_t,m10v_capture_profile *);
#endif
typedef void *(*allocate_fn)(uint32_t);
typedef void (*free_fn)(void *);
typedef void (*cache_fn)(void *, uint32_t);
typedef uint32_t (*root_fn)(void);
typedef uint32_t (*get_fn)(uint32_t);
typedef int (*clock_fn)(uint32_t, void *);
#if M10V_DEBUG_MODE
/* Stack-owned, per-capture batches: no global page pointer or shared image state.
 * Persist pre-render and completion separately so a stalled render remains
 * diagnosable without an SD transaction for every individual event. */
#if M10V_CAPTURE_PROFILE
typedef m10v_capture_profile m10v_capture_trace;
#else
typedef struct {uint32_t count;uint32_t events[16][5];} m10v_capture_trace;
#endif
static void trace_append(m10v_capture_trace *trace,uint32_t e,uint32_t a,uint32_t b,uint32_t c,uint32_t d){
#if M10V_CAPTURE_PROFILE
    /* Keep three one-shot film samples inside the existing 63-record page.
     * Timing checkpoints replace CPU hashes and redundant render markers. */
    if(e!=100&&e!=101&&e!=102&&e!=112&&e!=113&&e!=121&&e!=124&&e!=125&&e!=126&&e!=132&&e!=135&&e!=137&&e!=138)return;
#endif
    if(trace->count>=sizeof(trace->events)/sizeof(trace->events[0]))return;
    uint32_t *r=trace->events[trace->count++];r[0]=e;r[1]=a;r[2]=b;r[3]=c;r[4]=d;
}
static void trace_flush(m10v_capture_trace *trace){
    if(trace->count)m10v_debug_batch(&trace->events[0][0],trace->count);
    trace->count=0;
}
#define CAPTURE_LOG(e,a,b,c,d) trace_append(trace,e,a,b,c,d)
#else
#define CAPTURE_LOG(e,a,b,c,d) ((void)0)
#endif
/* Stable rejection IDs; preserve every existing return value and safety gate. */
#define REJECT(result, guard, a, b) do { CAPTURE_LOG(102,context,guard,a,b); return result; } while (0)
#if M10V_DEBUG_MODE && !M10V_CAPTURE_PROFILE
static void pixel_checkpoint(uint32_t event,uint32_t context,const m10v_library_image *image,m10v_capture_trace *trace){
    uint32_t y=2166136261u,c=2166136261u;
    /* A bounded 8x8 grid proves only these CPU samples, never the encoded JPEG.
     * Even x keeps both bytes of every CbCr pair inside the visible image. */
    for(uint32_t row=0;row<8;row++)for(uint32_t col=0;col<8;col++){
        uint32_t at=((image->height-1)*row/7)*image->stride+(((image->width-2)*col/7)&~1u);
        y=(y^image->y[at])*16777619u;y=(y^image->y[at+1])*16777619u;
        c=(c^image->chroma[at])*16777619u;c=(c^image->chroma[at+1])*16777619u;
    }
    CAPTURE_LOG(event,context,y,c,64);
}
#endif
static int ram(uint32_t p, uint32_t size) {
    return !(p & 3) && p >= 0x55000000u && p < 0x80000000u && size <= 0x80000000u - p;
}
static int raw_ram(uint32_t p, uint32_t size) {
    return ram(p, size) || (!(p & 3) && p >= 0xa0000000u && p < 0xe0000000u && size <= 0xe0000000u - p);
}
static int overlap(uint32_t a, uint32_t an, uint32_t b, uint32_t bn) {
    return a < b + bn && b < a + an;
}
/* The UI date service can be unavailable in the capture thread. Never let
 * an unavailable/invalid date suppress unrelated image processing. */
static int capture_date_valid(const uint32_t time[3]) {
    const m10v_library_date *d = (const m10v_library_date *)time;
    static const uint8_t days[12] = {31,28,31,30,31,30,31,31,30,31,30,31};
    if (d->year < 1980 || d->year > 2199 || !d->month || d->month > 12 ||
        !d->day || d->hour > 23 || d->minute > 59 || ((const uint8_t *)time)[6] > 59) return 0;
    uint32_t max = days[d->month - 1];
    if (d->month == 2 && d->year % 4 == 0 && (d->year % 100 != 0 || d->year % 400 == 0)) ++max;
    return d->day <= max;
}
static void skip_capture_stamp(m10v_library_state *state) {
    /* This is a stack copy, never stored. Keep the serialized-state CRC valid
     * for render's validation without changing the persisted configuration. */
    state->stamp = 0;
    uint32_t crc = 0xffffffffu;
    const uint8_t *bytes = (const uint8_t *)state;
    for (uint32_t i = 0; i < sizeof(*state) - sizeof(state->crc); ++i) {
        crc ^= bytes[i];
        for (uint32_t bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    state->crc = ~crc;
}
/* JPEG Setup6 binds these two already-resized secondary sources at R+d0/f0.
 * Native color runs before resize; CPU fallback runs afterward and must also
 * color independent thumbnails. Alias to the main source needs no second pass.
 * Keep optional spatial effects on the full image, never resample CFA here. */
typedef struct { uint32_t y,c,yn,cn,width,height,stride,format; } capture_thumb;
static int thumb_overlaps(const capture_thumb *t,uint32_t p,uint32_t bytes){
    return overlap(t->y,t->yn,p,bytes)||overlap(t->c,t->cn,p,bytes);
}
static int thumb_pair_overlaps(const capture_thumb *a,const capture_thumb *b){
    return thumb_overlaps(a,b->y,b->yn)||thumb_overlaps(a,b->c,b->cn);
}
static int thumb_load(capture_thumb *t,uint32_t descriptor){
    const uint32_t *d=(const uint32_t *)(uintptr_t)descriptor;
    const uint16_t *s=(const uint16_t *)(uintptr_t)(descriptor+16);
    uint32_t format=*(const uint8_t *)d;
    if((format!=1&&format!=2)||s[0]<2||s[0]>6144||(s[0]&1)||!s[1]||s[1]>4096||
       s[2]<s[0]||s[2]>16384||(s[2]&1)||s[3]<s[1]||s[3]>4096||
       (format==2&&((s[1]|s[3])&1))||d[3]||s[4]||s[5]||((const uint8_t *)d)[0x1c]!=2)return 0;
    t->y=d[1];t->c=d[2];t->yn=(uint32_t)s[2]*s[3];t->cn=t->yn/(format==2?2:1);
    t->width=s[0];t->height=s[1];t->stride=s[2];t->format=format;
    return ram(t->y,t->yn)&&ram(t->c,t->cn)&&!overlap(t->y,t->yn,t->c,t->cn);
}
static int thumb_render(m10v_library_image *image,const m10v_library_state *state,uint32_t slot,
                        const uint8_t *record,uint8_t *scratch,uint32_t scratch_bytes){
#if M10V_SD_LIBRARY
    if(M10V_CUSTOM(state->slots[slot].film))
        return m10v_library_render_custom(image,state,slot,0,0,0,0,M10V_NATIVE_ALL&~M10V_NATIVE_COLOR,record+64,(const char *)(record+16));
#else
    (void)record;
#endif
    return m10v_library_render_native(image,state,slot,0,0,scratch,scratch_bytes,M10V_ANIME_E6(state->slots[slot].film)?M10V_NATIVE_ALL:M10V_NATIVE_ALL&~M10V_NATIVE_COLOR);
}
static void capture_thumbnails(uint32_t recipe,const m10v_library_state *state,uint32_t slot,
                               uint32_t raw,uint32_t raw_bytes,uint32_t raw_dims,
                               uint32_t request,uint32_t shooting,uint32_t y,uint32_t c,uint32_t bytes,
                               uint8_t *scratch,uint32_t scratch_bytes,
                               uint32_t preview_y,uint32_t preview_c,uint32_t preview_bytes,uint32_t preview_chroma_bytes){
    const uint32_t *context=(const uint32_t *)(uintptr_t)(recipe+0x9b8);
    if(context[0x40/4]!=recipe+0xd0||context[0x44/4]!=recipe+0xf0)return;
    capture_thumb thumbs[2];uint32_t valid[2]={0,0};
    for(uint32_t i=0;i<2;i++){
        capture_thumb *t=&thumbs[i];
        if(!thumb_load(t,recipe+0xd0+i*0x20))continue;
        if(thumb_overlaps(t,y,bytes)||thumb_overlaps(t,c,bytes)||thumb_overlaps(t,raw,raw_bytes)||
           thumb_overlaps(t,recipe,M10V_CAPTURE_RECIPE_BYTES)||thumb_overlaps(t,request,0x3c)||
           thumb_overlaps(t,shooting,0x94c)||thumb_overlaps(t,raw_dims,raw_dims?4:0)||
           (scratch_bytes&&thumb_overlaps(t,(uint32_t)(uintptr_t)scratch,scratch_bytes)))continue;
        valid[i]=1;
    }
    /* If secondary descriptors alias, process only once. Partial overlap is
     * rejected for both because it cannot establish independent image rows. */
    if(valid[0]&&valid[1]&&thumb_pair_overlaps(&thumbs[0],&thumbs[1])){
        int equal=thumbs[0].y==thumbs[1].y&&thumbs[0].c==thumbs[1].c&&
            thumbs[0].width==thumbs[1].width&&thumbs[0].height==thumbs[1].height&&
            thumbs[0].stride==thumbs[1].stride&&thumbs[0].format==thumbs[1].format;
        valid[1]=0;if(!equal)valid[0]=0;
    }
    m10v_library_state preview;
    for(uint32_t b=0;b<sizeof(preview);b++)((uint8_t *)&preview)[b]=((const uint8_t *)state)[b];
    preview.reserved=0;skip_capture_stamp(&preview);
    for(uint32_t i=0;i<2;i++)if(valid[i]){
        capture_thumb *t=&thumbs[i];uint8_t *stripe=0;
        if(t->format==2&&M10V_ANIME(state->slots[slot].film)&&state->effects[slot].reserved[1]){
            uint32_t yt=(t->height-1)*t->stride+t->width,ct=(t->height/2-1)*t->stride+t->width;
            ((cache_fn)0x5383c8a8u)((void *)(uintptr_t)t->y,yt);((cache_fn)0x5383c8a8u)((void *)(uintptr_t)t->c,ct);
            m10v_library_image im={(uint8_t *)(uintptr_t)t->y,(uint8_t *)(uintptr_t)t->c,t->yn,t->cn,t->width,t->height,t->stride};
            if(!m10v_anime_render420(&im,state->effects[slot].reserved[1],scratch,scratch_bytes)){
                ((cache_fn)0x5383c8a8u)((void *)(uintptr_t)t->y,yt);((cache_fn)0x5383c8a8u)((void *)(uintptr_t)t->c,ct);
            }
            continue;
        }
        if(t->format==2){
            stripe=((allocate_fn)0x536af2a8u)(2*t->stride);
            uint32_t p=(uint32_t)(uintptr_t)stripe,n=2*t->stride;
            int safe=ram(p,n)&&!overlap(p,n,raw,raw_bytes)&&!overlap(p,n,recipe,M10V_CAPTURE_RECIPE_BYTES)&&
                !overlap(p,n,request,0x3c)&&!overlap(p,n,shooting,0x94c)&&!overlap(p,n,raw_dims,raw_dims?4:0)&&
                !overlap(p,n,y,bytes)&&!overlap(p,n,c,bytes)&&
                !overlap(p,n,preview_y,preview_bytes)&&!overlap(p,n,preview_c,preview_chroma_bytes)&&
                !overlap(p,n,(uint32_t)(uintptr_t)scratch,scratch_bytes);
            for(uint32_t j=0;j<2;j++)if(valid[j]&&thumb_overlaps(&thumbs[j],p,n))safe=0;
            if(!safe){if(stripe)((free_fn)0x536af2e4u)(stripe);continue;}
        }
        uint32_t yt=(t->height-1)*t->stride+t->width;
        uint32_t ct=(t->height/(t->format==2?2:1)-1)*t->stride+t->width;
        ((cache_fn)0x5383c8a8u)((void *)(uintptr_t)t->y,yt);
        ((cache_fn)0x5383c8a8u)((void *)(uintptr_t)t->c,ct);
        if(t->format==1){
            m10v_library_image image={(uint8_t *)(uintptr_t)t->y,(uint8_t *)(uintptr_t)t->c,t->yn,t->cn,t->width,t->height,t->stride};
            thumb_render(&image,&preview,slot,scratch,scratch,scratch_bytes);
        }else{
            /* Expand a single 4:2:0 chroma row to two 4:4:4 rows, apply each
             * luma row once, then average CbCr back. Bounded allocation, no
             * full-frame copy, padding writes or second color application. */
            for(uint32_t row=0;row<t->height;row+=2){
                uint8_t *chroma=(uint8_t *)(uintptr_t)(t->c+(row/2)*t->stride);
                for(uint32_t x=0;x<t->width;x++)stripe[x]=stripe[t->stride+x]=chroma[x];
                m10v_library_image image={(uint8_t *)(uintptr_t)(t->y+row*t->stride),stripe,2*t->stride,2*t->stride,t->width,2,t->stride};
                if(!thumb_render(&image,&preview,slot,scratch,scratch,scratch_bytes))
                    for(uint32_t x=0;x<t->width;x++)chroma[x]=(uint8_t)(((uint32_t)stripe[x]+stripe[t->stride+x]+1)/2);
            }
        }
        ((cache_fn)0x5383c8a8u)((void *)(uintptr_t)t->y,yt);
        ((cache_fn)0x5383c8a8u)((void *)(uintptr_t)t->c,ct);
        if(stripe)((free_fn)0x536af2e4u)(stripe);
    }
}
#if M10V_DEBUG_MODE
static int capture_library_impl(uint32_t context,m10v_capture_trace *trace) {
#if M10V_CAPTURE_PROFILE
    m10v_capture_profile *profile=trace;
#endif
#else
int m10v_capture_library(uint32_t context) {
#endif
    if (!ram(context, 0x60) || context < 0x550009b8u) REJECT(-3,1,context,0x60);
    uint32_t recipe = context - 0x9b8u;
    if (!ram(recipe, M10V_CAPTURE_RECIPE_BYTES)) REJECT(-3,2,recipe,M10V_CAPTURE_RECIPE_BYTES);
    const uint32_t *ctx = (const uint32_t *)(uintptr_t)context;
    uint32_t sequence_mode = *(const uint32_t *)(uintptr_t)(recipe + 0x18u);
    if (sequence_mode != 0 && sequence_mode != 1 && sequence_mode != 5 && sequence_mode != 6 &&
        sequence_mode != 7 && sequence_mode != 8 && sequence_mode != 12) REJECT(-4,4,sequence_mode,0);
    if (ctx[0] != 0x53d0fbe0u || ctx[0x30 / 4] != recipe + 0x1a8u ||
        ctx[0x3c / 4] != recipe + 0xb0u || ctx[0x48 / 4] != recipe + 0x110u ||
        ctx[0x4c / 4] != recipe + 0x130u ||
        ctx[0x34 / 4] != *(const uint32_t *)(uintptr_t)(recipe + 0x44c8u) ||
        ctx[0x38 / 4] != *(const uint32_t *)(uintptr_t)(recipe + 0x5cu)) REJECT(-3,3,ctx[0],ctx[0x3c/4]);
    uint32_t request = ctx[0x38 / 4], shooting = ctx[0x34 / 4], descriptor = ctx[0x3c / 4], jpeg = ctx[0x4c / 4];
    if (!ram(request, 14) || !ram(shooting, 0x94c) || !ram(descriptor, 32) || !ram(jpeg, 17) ||
        *(const uint32_t *)(uintptr_t)request != 0x53d0fe60u) REJECT(-3,5,request,shooting);
    const uint8_t *req = (const uint8_t *)(uintptr_t)request;
    if (req[12] != 1 || req[13] > 1 || ((const uint8_t *)(uintptr_t)jpeg)[16] != 1) REJECT(-4,6,req[12],req[13]);
#if M10V_BORDER_ENABLED && M10V_RECIPE_SNAPSHOT
    /* The owned pre-review stage may run the EXISTING residual bridge once
     * before adding a border. Original Setup6/JPEG still run later; a second
     * pass would tint the border or move/apply stamps twice. This marker says
     * only that residual processing was attempted, never that ISP completed. */
    uint32_t border_phase=m10v_border_shot_phase(recipe);
    if(border_phase==M10V_BORDER_PHASE_LIBRARY_ATTEMPTED||
       border_phase==M10V_BORDER_PHASE_COMPLETE||
       border_phase==M10V_BORDER_PHASE_FAILED_AFTER_LIBRARY)return 0;
#endif
    uint32_t tone = ((const uint8_t *)(uintptr_t)shooting)[0x77c], slot = M10V_SLOT_COUNT;

    for (uint32_t i = 0; i < M10V_SLOT_COUNT; ++i) if (m10v_slot_tone(i) == tone) slot = i;
    /* A committed per-exposure selection can precede the backend SI tone.
     * Authenticate the owned snapshot before rejecting that first stock frame.
     * No snapshot means ordinary stock/RAW frames keep their original gates. */
    m10v_library_state state;
    int settings_source=-1;
#if M10V_RECIPE_SNAPSHOT
    const m10v_isp_recipe_color *snapshot=(const m10v_isp_recipe_color *)(uintptr_t)(recipe+M10V_SAVE_COLOR_OFFSET);
    if(ram(recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)&&snapshot->magic==M10V_ISP_RECIPE_COLOR_MAGIC&&snapshot->status==M10V_ISP_RECIPE_MUTATING)REJECT(-5,16,M10V_ISP_RECIPE_MUTATING,0);
    if(ram(recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)&&m10v_isp_frame_recipe_state((void *)(uintptr_t)recipe,&state)){
        settings_source=4;
        if(snapshot->selected_tone){
            uint32_t selected=snapshot->selected_tone;slot=M10V_SLOT_COUNT;
            for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)if(m10v_slot_tone(i)==selected)slot=i;
        }
    }
#endif
    if (slot == M10V_SLOT_COUNT) {
#if M10V_BORDER_ENABLED && M10V_RECIPE_SNAPSHOT
        if(border_phase==M10V_BORDER_PHASE_RUNNING)REJECT(M10V_BORDER_LIBRARY_STOCK_BYPASS,7,tone,0);
#endif
        REJECT(-4,7,tone,0);
    }
    const uint32_t *desc = (const uint32_t *)(uintptr_t)descriptor;
    const uint16_t *dims = (const uint16_t *)(uintptr_t)(descriptor + 16);
    uint32_t width = dims[0], height = dims[1], stride = dims[2], allocated = dims[3];
    if (((const uint8_t *)desc)[0] != 1 || width < 2 || width > 6144 || (width & 1) ||
        !height || height > 4096 || stride < width || stride > 16384 || (stride & 1) ||
        allocated < height || allocated > 4096 || desc[3] || dims[4] || dims[5] ||
        ((const uint8_t *)desc)[0x1c] != 2) REJECT(-3,8,(width<<16)|height,(stride<<16)|allocated);
    uint32_t bytes = stride * allocated;
    if (!ram(desc[1], bytes) || !ram(desc[2], bytes) || overlap(desc[1], bytes, desc[2], bytes)) REJECT(-3,9,desc[1],desc[2]);
    uint32_t raw_source = *(const uint32_t *)(uintptr_t)(recipe + 0x60u);
    CAPTURE_LOG(125,context,tone,sequence_mode,raw_source);
    uint32_t raw_dims = 0, raw_bytes = 0, raw_status = 1;
#if M10V_RAW_LIFETIME
    uint32_t raw_backing = *(const uint32_t *)(uintptr_t)(recipe + 0x2f4u);
    if (!raw_source) raw_status = m10v_save_trace_recipe_raw_status(recipe,shooting,raw_backing,raw_source);
    CAPTURE_LOG(126,context,raw_status,raw_backing,raw_source);
#endif
    /* After a proven native release, neither CFA nor its metadata is ours.
     * The current JPEG/preview topology remains independently validated. */
    if (raw_status != 2) {
        if (!raw_source) REJECT(-3,12,raw_source,0);
        raw_dims = *(const uint32_t *)(uintptr_t)(recipe + 0x230u);
        if (!ram(raw_dims, 4)) REJECT(-3,10,raw_dims,0);
        uint32_t raw_width = ((const uint16_t *)(uintptr_t)raw_dims)[0];
        uint32_t raw_height = ((const uint16_t *)(uintptr_t)raw_dims)[1];
        if (!raw_width || raw_width > 8192 || !raw_height || raw_height > 8192) REJECT(-3,11,raw_width,raw_height);
        raw_bytes = 2 * raw_width * raw_height;
        if (!raw_ram(raw_source, raw_bytes)) REJECT(-3,12,raw_source,raw_bytes);
    }
    uint32_t planes[2] = {desc[1], desc[2]};
    for (uint32_t i = 0; i < 2; ++i)
        if (overlap(planes[i], bytes, raw_source, raw_bytes) || overlap(planes[i], bytes, recipe, M10V_CAPTURE_RECIPE_BYTES) ||
            overlap(planes[i], bytes, request, 0x3c) || overlap(planes[i], bytes, shooting, 0x94c) ||
            overlap(planes[i], bytes, raw_dims, 4)) REJECT(-3,13,planes[i],raw_source);
    const uint32_t *preview = (const uint32_t *)(uintptr_t)(recipe + 0x110u);
    const uint16_t *pd = (const uint16_t *)(uintptr_t)(recipe + 0x120u);
    uint32_t pf = *(const uint8_t *)preview;
    if ((pf != 1 && pf != 2) || !pd[2] || pd[2] > 16384 || !pd[3] || pd[3] > 4096 ||
        preview[3] || ((const uint8_t *)preview)[0x1c] != 2) REJECT(-3,14,pf,(pd[2]<<16)|pd[3]);
    uint32_t preview_bytes = (uint32_t)pd[2] * pd[3];
    uint32_t preview_chroma_bytes = pf == 1 ? preview_bytes : preview_bytes >> 1;
    if (!ram(preview[1], preview_bytes) || !ram(preview[2], preview_chroma_bytes)) REJECT(-3,15,preview[1],preview[2]);
    M10V_PROFILE(2);
    if(settings_source!=4)settings_source=m10v_camera_library_load(&state);
    M10V_PROFILE(3);
    if (settings_source < 0) REJECT(-5,16,(uint32_t)settings_source,0);
    if(state.reserved&510u)REJECT(-5,16,M10V_ISP_RECIPE_MUTATING,0);
    if(!state.slots[slot].film) {
#if M10V_BORDER_ENABLED && M10V_RECIPE_SNAPSHOT
        if(border_phase==M10V_BORDER_PHASE_RUNNING)REJECT(M10V_BORDER_LIBRARY_STOCK_BYPASS,7,tone,slot);
#endif
        REJECT(-4,7,tone,slot);
    }
    uint32_t completed=0;
#if M10V_ISP_NATIVE_LOOK
    completed=m10v_isp_frame_recipe_completed((void *)(uintptr_t)recipe,shooting,tone,&state);
    CAPTURE_LOG(135,context,completed,state.sequence,state.slots[slot].film);
#if M10V_ISP_NATIVE_GRAIN_MODE
    if(completed&M10V_NATIVE_GRAIN)CAPTURE_LOG(137,context,snapshot->native_grain.grain,snapshot->native_grain.size,snapshot->native_grain.noise_ready);
#endif
#endif
    CAPTURE_LOG(113,slot,(uint32_t)settings_source,state.sequence,3);
    uint32_t cpu_stages=m10v_library_cpu_stages(&state,slot,completed);
    CAPTURE_LOG(138,context,completed,cpu_stages,state.slots[slot].film);
    if(!cpu_stages){
        /* ISP owns clean completed planes. Do not touch/invalidate them merely
         * to execute an empty CPU pass; chain the original encoder unchanged. */
        M10V_PROFILE(4);M10V_PROFILE(5);M10V_PROFILE(6);M10V_PROFILE(7);
        M10V_PROFILE(8);M10V_PROFILE(9);M10V_PROFILE(10);M10V_PROFILE(11);
        return 0;
    }
    uint32_t time[3] = {0,0,0};
    uint32_t seed = state.sequence ^ planes[0];
    if (state.stamp) {
        /* Official producer 0x534322d8/0x534fa22c writes this capture
         * metadata date. +0x948 is weekday, not hour. Prefer exposure metadata
         * over the UI cache (which may be unavailable or from a later time). */
        const uint8_t *shot = (const uint8_t *)(uintptr_t)shooting;
        m10v_library_date *date = (m10v_library_date *)time;
        date->year = *(const uint16_t *)(shot + 0x944);
        date->month = shot[0x946]; date->day = shot[0x947];
        date->hour = shot[0x949]; date->minute = shot[0x94a];
        ((uint8_t *)time)[6] = shot[0x94b];
        uint32_t clock_status = 4, source = shooting + 0x944;
        /* 4 capture date, 1 UI date, 2 UI unavailable, 3 invalid date. */
        if (!capture_date_valid(time)) {
            uint32_t root = ((root_fn)0x5320ad88u)();
            source = ((get_fn)0x5320b97cu)(root);
            clock_status = 2;
            if (ram(source, 0x3cc) && ((clock_fn)0x532b36ccu)(source, time))
                clock_status = capture_date_valid(time) ? 1 : 3;
        }
        CAPTURE_LOG(120,context,clock_status,state.stamp,source);
        if (clock_status != 1 && clock_status != 4) {
            skip_capture_stamp(&state);
        } else {
            const m10v_library_date *date = (const m10v_library_date *)time;
            seed ^= ((uint32_t)date->year << 16) ^ ((uint32_t)date->month << 8) ^ date->day ^
                    ((uint32_t)date->hour << 24) ^ ((uint32_t)date->minute << 16) ^
                    ((uint32_t)((const uint8_t *)time)[6] << 8);
        }
    }
    uint8_t *scratch = (uint8_t *)0; uint32_t scratch_bytes = 0;
    uint32_t use_halo=cpu_stages&M10V_NATIVE_HALO;
    uint32_t step=1,shift=0,required=0;
    while (((width+step-1)>>shift)>384 || ((height+step-1)>>shift)>256){step<<=1;++shift;}
    uint32_t cells=((width+step-1)>>shift)*((height+step-1)>>shift);
    if(use_halo)
        required=(m10v_halo_workspace_planes(state.slots[slot].film,state.slots[slot].halo_profile)*cells+3)&~3u;
    if(cpu_stages&M10V_CPU_ANIME){uint32_t need=width*6u;if(need>required)required=need;}
    scratch_bytes=required;
    if(M10V_CUSTOM(state.slots[slot].film)){
#if M10V_SD_LIBRARY
        required+=M10V_SD_RECORD_BYTES;
        scratch_bytes=required;
#else
        REJECT(-5,19,state.slots[slot].film,0);
#endif
    }else if((cpu_stages&M10V_NATIVE_COLOR)&&state.slots[slot].film>33){
        /* Phoenix's source occupies 4*cells; the old 6*cells allocation
         * already leaves room at full size. Other spatial passes finish
         * before color or run afterward, so reuse their storage. */
        uint32_t desired=(use_halo?4*cells:0)+M10V_COLOR_CACHE_BYTES;
        if(desired>scratch_bytes)scratch_bytes=desired;
    }
    if(scratch_bytes){
        scratch=((allocate_fn)0x536af2a8u)(scratch_bytes);
        /* The optional cache must never turn memory pressure into a lost
         * processing opportunity. Retry only the original required storage. */
        if(!scratch&&scratch_bytes>required){
            scratch_bytes=required;
            if(required)scratch=((allocate_fn)0x536af2a8u)(required);
        }
        uint32_t address = (uint32_t)(uintptr_t)scratch;
        if (scratch_bytes&&!ram(address, scratch_bytes)) REJECT(-6,17,address,scratch_bytes);
        if (scratch_bytes&&(overlap(address, scratch_bytes, planes[0], bytes) || overlap(address, scratch_bytes, planes[1], bytes) ||
            overlap(address, scratch_bytes, raw_source, raw_bytes) || overlap(address, scratch_bytes, recipe, M10V_CAPTURE_RECIPE_BYTES) ||
            overlap(address, scratch_bytes, request, 0x3c) || overlap(address, scratch_bytes, shooting, 0x94c) ||
            overlap(address, scratch_bytes, raw_dims, 4) || overlap(address, scratch_bytes, preview[1], preview_bytes) ||
            overlap(address, scratch_bytes, preview[2], preview_chroma_bytes))) {
            ((free_fn)0x536af2e4u)(scratch); REJECT(-6,18,address,scratch_bytes);
        }
    }
#if M10V_SD_LIBRARY
    if(M10V_CUSTOM(state.slots[slot].film) &&
       (!scratch||!m10v_sd_camera_custom_record(&state,slot,scratch,scratch_bytes))){
        if(scratch)((free_fn)0x536af2e4u)(scratch);
        REJECT(-5,19,state.slots[slot].film,slot);
    }
#endif
    M10V_PROFILE(4);
    m10v_library_image image = {(uint8_t *)(uintptr_t)planes[0], (uint8_t *)(uintptr_t)planes[1],
                                bytes, bytes, width, height, stride};
    uint32_t touched = (height - 1) * stride + width;
    M10V_PROFILE(5);
    ((cache_fn)0x5383c8a8u)(image.y, touched); ((cache_fn)0x5383c8a8u)(image.chroma, touched);
    M10V_PROFILE(6);
    CAPTURE_LOG(121,context,planes[0],planes[1],(width<<16)|height);
    CAPTURE_LOG(124,context,stride,allocated,tone);
#if M10V_DEBUG_MODE && !M10V_CAPTURE_PROFILE
    pixel_checkpoint(122,context,&image,trace);
#endif
    CAPTURE_LOG(110,context,slot,state.slots[slot].film,(width<<16)|height);
    CAPTURE_LOG(112,slot,(uint32_t)state.slots[slot].halo_gain|((uint32_t)state.slots[slot].halo_spread<<4)|
        ((uint32_t)state.slots[slot].halo_threshold<<8)|((uint32_t)state.slots[slot].grain<<12)|((uint32_t)state.slots[slot].soft<<16),state.sequence,3);
#if M10V_DEBUG_MODE && !M10V_CAPTURE_PROFILE
    trace_flush(trace);
#endif
    int result;
#if M10V_SD_LIBRARY
    if(M10V_CUSTOM(state.slots[slot].film))
        result=m10v_library_render_custom(&image,&state,slot,(const m10v_library_date *)time,
                                           seed,use_halo?scratch+M10V_SD_RECORD_BYTES:0,use_halo?scratch_bytes-M10V_SD_RECORD_BYTES:0,completed,scratch+64,(const char *)(scratch+16));
    else
#endif
#if M10V_CAPTURE_PROFILE
        result=m10v_library_render_native_profiled(&image,&state,slot,(const m10v_library_date *)time,seed,scratch,scratch_bytes,completed,profile);
#else
        result=m10v_library_render_native(&image,&state,slot,(const m10v_library_date *)time,
                                           seed,scratch,scratch_bytes,completed);
#endif
    CAPTURE_LOG(111,context,(uint32_t)result,(uint32_t)state.slots[slot].halo_gain|((uint32_t)state.slots[slot].halo_spread<<4)|((uint32_t)state.slots[slot].halo_threshold<<8)|((uint32_t)state.slots[slot].halo_profile<<12),scratch_bytes);
    if (!result) {
#if M10V_DEBUG_MODE && !M10V_CAPTURE_PROFILE
        pixel_checkpoint(123,context,&image,trace);
#endif
        ((cache_fn)0x5383c8a8u)(image.y, touched); ((cache_fn)0x5383c8a8u)(image.chroma, touched); }
    if(!result&&(cpu_stages&(M10V_NATIVE_COLOR|M10V_CPU_ANIME)))
        capture_thumbnails(recipe,&state,slot,raw_source,raw_bytes,raw_dims,request,shooting,
                           planes[0],planes[1],bytes,scratch,scratch_bytes,preview[1],preview[2],preview_bytes,preview_chroma_bytes);
    M10V_PROFILE(11);
    if (scratch) ((free_fn)0x536af2e4u)(scratch);
    return result;
}
#if M10V_DEBUG_MODE
int m10v_capture_library(uint32_t context) {
    m10v_capture_trace storage;storage.count=0;m10v_capture_trace *trace=&storage;
#if M10V_CAPTURE_PROFILE
    m10v_capture_profile *profile=trace;profile->context=context;M10V_PROFILE(1);
#endif
    CAPTURE_LOG(100,context,0,0,0);
    int result=capture_library_impl(context,trace);
    M10V_PROFILE(12);
    CAPTURE_LOG(101,context,(uint32_t)result,0,0);
    trace_flush(trace);return result;
}
#endif
