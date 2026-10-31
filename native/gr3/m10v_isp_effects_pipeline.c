/* CPU metadata validation/coordination only. All pixels belong to native ISP. */
#include "m10v_isp_effects_pipeline.h"
#include "m10v_save_trace.h"
#include "m10v_isp_recipe_color.h"
#include "m10v_tone.h"
#include "m10v_debug.h"
#include "m10v_isp_effect_memory.h"
#ifndef M10V_ISP_EFFECTS_SHOT_OFFSET
#error "Pipeline requires the matching explicitly allocated shot tail"
#endif

static int pipeline_ram(uint32_t p,uint32_t n){
    return !(p&3u)&&p>=0x55000000u&&n<=0x2b000000u&&p<=0x80000000u-n;
}
static uint32_t pipeline_word(const void *p,uint32_t off){
    return *(const uint32_t*)((const uint8_t*)p+off);
}
static int pipeline_overlap(uint32_t a,uint32_t an,uint32_t b,uint32_t bn){
    return an&&bn&&a<b+bn&&b<a+an;
}
static void pipeline_diagnostic(uint32_t recipe,uint32_t stage,uint32_t detail){
#if M10V_DEBUG_MODE
    /* Worker-only bounded checkpoint, never task ingress or a wait loop.
     * All calls precede our submissions or follow returned native calls.
     * A diagnostic error never authorizes completion or resource release. */
    uint32_t records[11][5],count=1;
    records[0][0]=198;records[0][1]=recipe;records[0][2]=0x46584800u;
    records[0][3]=stage;records[0][4]=detail;
    if(pipeline_ram(recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)&&
       *(const uint32_t*)(uintptr_t)recipe==0x53d0fc90u&&
       *(const uint32_t*)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)==M10V_SAVE_TRACE_MAGIC){
        const m10v_isp_effects_shot_snapshot *s=(const void*)(uintptr_t)(recipe+M10V_ISP_EFFECTS_SHOT_OFFSET);
        uint32_t si=*(const uint32_t*)(uintptr_t)(recipe+0x44c8u),native=0xffffffffu;
        if(pipeline_ram(si,0x94c)){
            const uint8_t *p=(const void*)(uintptr_t)si;native=p[0x77c]|((uint32_t)p[0x795]<<16);
        }
        const uint32_t pairs[10][2]={{s->magic,s->owner},{s->ready,s->sequence},
            {s->settings.leak_gain,s->settings.blur_gain},{s->planned,s->native_completed},
            {s->failed,s->source_si},{s->stock_workspace_bytes,s->stock_query_valid},
            {s->effective_grain_strength,s->settings.grain_mode},{si,native},
            {s->planned_width,s->planned_height},{s->workspace_bytes,s->saved_orientation}};
        for(uint32_t i=0;i<10;i++){
            uint32_t *r=records[count++];r[0]=198;r[1]=recipe;r[2]=0x46583030u+i;
            r[3]=pairs[i][0];r[4]=pairs[i][1];
        }
    }
    (void)m10v_debug_batch(&records[0][0],count);
#else
    (void)recipe;(void)stage;(void)detail;
#endif
}
static __attribute__((noreturn)) void pipeline_hold(uint32_t recipe,uint32_t reason,uint32_t detail){
    /* Native callers ignore spatial r0 on several continuation branches.
     * Retain their frame/workspace instead of allowing a partial JPEG. This
     * follows actual native cleanup and never claims DMA quiescence. */
    pipeline_diagnostic(recipe,reason,detail);
    for(;;)((void(*)(uint32_t))0x536b0a74u)(1);
}
static int16_t *pipeline_values(const void *params){
    if(!pipeline_ram((uint32_t)(uintptr_t)params,0x34))return 0;
    uint32_t values=pipeline_word(params,0x10);
    return pipeline_ram(values,12)?(void*)(uintptr_t)values:0;
}
static int pipeline_photo(uint32_t descriptor,uint32_t *width,uint32_t *height){
    if(!pipeline_ram(descriptor,32))return 0;
    const uint32_t *photo=(const void*)(uintptr_t)descriptor;
    const uint16_t *s=(const void*)(uintptr_t)(descriptor+0x10);
    /* Native constructors/copy536a3d84 use STRB/LDRB for the format.
     * Bytes1..3 are padding, not zeroed or copied by that ABI. */
    uint32_t format=*(const uint8_t*)(uintptr_t)descriptor;
    uint32_t w=s[0],h=s[1],stride=s[2],rows=s[3];
    if((format!=1&&format!=2)||w<2||h<2||w>6144||h>6144||((w|h)&1u)||
       stride<w||stride>16384||rows<h||rows>16384||(stride&1u)||(rows&1u)||
       (uint32_t)s[4]+w>stride||(uint32_t)s[5]+h>rows)return 0;
    uint32_t ybytes=stride*rows,uvbytes=format==1?ybytes:ybytes/2u;
    if((photo[1]&15u)||(photo[2]&15u)||!m10v_isp_effect_buffer_span(photo[1],ybytes)||
       !m10v_isp_effect_buffer_span(photo[2],uvbytes)||pipeline_overlap(photo[1],ybytes,photo[2],uvbytes))return 0;
    *width=w;*height=h;return 1;
}
static uint32_t pipeline_mask(const m10v_isp_effects_shot_snapshot *s){
    return (s->effective_grain_strength?M10V_ISP_EFFECTS_NATIVE_GRAIN:0u)|
        (s->settings.leak_gain?M10V_ISP_EFFECTS_NATIVE_LEAK:0u)|
        (s->settings.blur_gain?M10V_ISP_EFFECTS_NATIVE_BLUR:0u);
}
static int pipeline_params(uint32_t recipe,const void *params,
    m10v_isp_effects_shot_snapshot *shot){
    int16_t *values=pipeline_values(params);uint32_t aw,ah,bw,bh;
    if(!values||pipeline_word(params,0x20)!=recipe||values[2]||values[3]||
       !m10v_isp_effects_shot_read(recipe,shot)||!shot->planned||shot->failed||
       !pipeline_photo(pipeline_word(params,4),&aw,&ah)||
       !pipeline_photo(pipeline_word(params,8),&bw,&bh)||
       aw!=bw||ah!=bh||aw!=shot->planned_width||ah!=shot->planned_height)return 0;
    return 1;
}
uint32_t m10v_isp_effects_pipeline_settings(uint32_t recipe,uint32_t si,
    void *params,uint32_t slot_grain_strength){
    if(!pipeline_ram((uint32_t)(uintptr_t)params,0x34))return 0;
    ((uint32_t*)params)[0x20/4]=0;
    int16_t *values=pipeline_values(params);if(!values)return 0;
    values[2]=0;
    m10v_isp_effects_shot_snapshot shot;uint32_t aw,ah,bw,bh;
    if(!m10v_isp_effects_shot_read(recipe,&shot)||shot.failed||values[3]||
       !pipeline_photo(pipeline_word(params,4),&aw,&ah)||
       !pipeline_photo(pipeline_word(params,8),&bw,&bh)||aw!=bw||ah!=bh||
       !m10v_isp_effects_shot_plan(recipe,si,aw,ah,slot_grain_strength)||
       !m10v_isp_effects_shot_read(recipe,&shot))return 0;
    if(shot.settings.blur_gain){
        uint32_t grade=values[1]>=5&&values[1]<=7?(uint32_t)values[1]-4u:0;
        values[1]=(int16_t)(8u+grade*9u+(shot.settings.blur_gain-1u)*3u+shot.settings.blur_range);
    }
    ((uint32_t*)params)[0x20/4]=recipe;
    if(pipeline_mask(&shot))pipeline_diagnostic(recipe,1,
        (uint16_t)values[0]|((uint32_t)(uint16_t)values[1]<<16));
    return pipeline_mask(&shot)!=0;
}
uint32_t m10v_isp_effects_pipeline_workspace(const void *params,
    uint32_t *queried_bytes,uint32_t stock_result){
    if(stock_result!=1||!pipeline_ram((uint32_t)(uintptr_t)queried_bytes,4)||
       !pipeline_ram((uint32_t)(uintptr_t)params,0x34))return 0;
    uint32_t recipe=pipeline_word(params,0x20);
    m10v_isp_effects_shot_snapshot shot;
    uint32_t output=(uint32_t)(uintptr_t)queried_bytes;
    if(!pipeline_params(recipe,params,&shot)||
       pipeline_overlap(output,4,(uint32_t)(uintptr_t)params,0x34)||
       pipeline_overlap(output,4,recipe,M10V_ISP_EFFECTS_SHOT_OFFSET+M10V_ISP_EFFECTS_SHOT_BYTES)||
       pipeline_overlap(output,4,pipeline_word(params,0x10),12)||
       pipeline_overlap(output,4,pipeline_word(params,4),32)||
       pipeline_overlap(output,4,pipeline_word(params,8),32)||
       !m10v_isp_effects_shot_stock_query(recipe,shot.source_si,*queried_bytes))return 0;
    if(*queried_bytes<shot.workspace_bytes)*queried_bytes=shot.workspace_bytes;
    if(pipeline_mask(&shot))pipeline_diagnostic(recipe,2,*queried_bytes);
    return 1;
}
static int pipeline_workspace_ok(uint32_t recipe,uint32_t context,const void *params,
    const m10v_isp_effects_shot_snapshot *shot,uint32_t *view,uint32_t *view_capacity,uint32_t *reason){
    uint32_t work=pipeline_word(params,0x2c),capacity=pipeline_word(params,0x30);
    uint32_t needed=shot->workspace_bytes>shot->stock_workspace_bytes?
        shot->workspace_bytes:shot->stock_workspace_bytes;
    *reason=0;
    if(!pipeline_ram(context,0x38)){*reason=1;return 0;}
    if(capacity<needed){*reason=2;return 0;}
    *view=work;*view_capacity=capacity;
    if(!needed)return 1;
    if((work&3u)||!m10v_isp_effect_buffer_span(work,capacity)){*reason=3;return 0;}
    if(!shot->workspace_bytes)return 1;
    /* Original query53503398..39c adds16 allocation bytes. Original native
     * stages also align inside their supplied allocation (5367ad8c..adac).
     * Borrow an aligned private view; leave native parameters/free pointer
     * untouched and subtract every skipped byte from available capacity. */
    uint32_t skip=(0u-work)&15u;
    if(skip>capacity||shot->workspace_bytes>capacity-skip){*reason=4;return 0;}
    *view=work+skip;*view_capacity=capacity-skip;
    uint32_t metadata[6]={recipe,(uint32_t)(uintptr_t)params,pipeline_word(params,0x10),
        pipeline_word(params,4),pipeline_word(params,8),context};
    uint32_t bytes[6]={M10V_ISP_EFFECTS_SHOT_OFFSET+M10V_ISP_EFFECTS_SHOT_BYTES,0x34,12,32,32,0x38};
    for(uint32_t i=0;i<6;i++)if(pipeline_overlap(work,capacity,metadata[i],bytes[i])){*reason=5u+i;return 0;}
    if(pipeline_overlap(work,capacity,shot->source_si,0x74270u)){*reason=11;return 0;}
    for(uint32_t i=0;i<2;i++){
        const uint32_t *p=(const void*)(uintptr_t)pipeline_word(params,4u+i*4u);
        const uint16_t *s=(const void*)((const uint8_t*)p+0x10);
        uint32_t plane=(uint32_t)s[2]*s[3],uv=(p[0]&255u)==1u?plane:plane/2u;
        if(pipeline_overlap(work,capacity,p[1],plane)){*reason=12u+i*2u;return 0;}
        if(pipeline_overlap(work,capacity,p[2],uv)){*reason=13u+i*2u;return 0;}
    }
    return 1;
}
int m10v_isp_effects_pipeline_execute(uint32_t recipe,uint32_t native_context,
    void *params,uint32_t stock_result){
    m10v_isp_effects_shot_snapshot shot;
    if(!pipeline_params(recipe,params,&shot)){
        if(pipeline_ram((uint32_t)(uintptr_t)params,0x34)&&pipeline_word(params,0x20)==recipe)pipeline_hold(recipe,10,stock_result);
        return 0;
    }
    /* No own stage touched this image. Preserve the original stage's result
     * and failure policy rather than manufacturing a new effects failure. */
    if(!pipeline_mask(&shot))return stock_result==1;
    uint32_t failure=11,failure_detail=stock_result;
    if(stock_result!=1||!shot.stock_query_valid)goto failed;
    failure=12;
    uint32_t view=0,view_capacity=0,workspace_reason=0;
    int workspace_ok=pipeline_workspace_ok(recipe,native_context,params,&shot,&view,&view_capacity,&workspace_reason);
#if M10V_DEBUG_MODE
    const uint32_t allocation[2][5]={
        {198,recipe,0x46585730u,pipeline_word(params,0x2c),pipeline_word(params,0x30)},
        {198,recipe,0x46585731u,workspace_ok?view:0u,workspace_ok?view_capacity:0u}};
    (void)m10v_debug_batch(&allocation[0][0],2);
#endif
    if(!workspace_ok){failure_detail=workspace_reason;goto failed;}
    pipeline_diagnostic(recipe,3,stock_result);
    int16_t *values=pipeline_values(params);
    if(shot.settings.blur_gain){
        int clarity=values[1];uint32_t own=(shot.settings.blur_gain-1u)*3u+shot.settings.blur_range;
        failure=13;
        if(clarity<8||clarity>43||((uint32_t)clarity-8u)%9u!=own)goto failed;
    }
    uint32_t mask=pipeline_mask(&shot);
    if((shot.native_completed&mask)==mask)return 1;
    failure=14;
    if(shot.native_completed&mask)goto failed;
    if(mask&(M10V_ISP_EFFECTS_NATIVE_GRAIN|M10V_ISP_EFFECTS_NATIVE_LEAK)){
        const uint32_t *photo=(const void*)(uintptr_t)pipeline_word(params,shot.stock_workspace_bytes?8u:4u);
        failure=15;
        if(m10v_isp_effects_render(native_context,photo,view,view_capacity,&shot)!=1)goto failed;
    }
    failure=16;
    if(!m10v_isp_effects_shot_complete(recipe,shot.source_si,mask))goto failed;
    pipeline_diagnostic(recipe,4,mask);
    return 1;
failed:
    m10v_isp_effects_shot_fail(recipe,shot.source_si);
    if(pipeline_mask(&shot))pipeline_hold(recipe,failure,failure_detail);
    return 0;
}
static int pipeline_color_state(const m10v_isp_recipe_color *color){
    const m10v_library_state *state=&color->state;
    if(color->magic!=M10V_ISP_RECIPE_COLOR_MAGIC||color->version!=1||color->bytes!=sizeof(*color)||
       color->busy||color->status==M10V_ISP_RECIPE_MUTATING||color->sequence!=state->sequence||
       state->magic!=0x5630314du||state->version!=5||state->size!=sizeof(*state)||
       (state->reserved&510u))return 0;
    uint32_t crc=0xffffffffu;const uint8_t *p=(const void*)state;
    for(uint32_t i=0;i<sizeof(*state)-4u;i++){
        crc^=p[i];for(uint32_t bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));
    }
    return ~crc==state->crc;
}
int m10v_isp_effects_pipeline_encoder_admit(uint32_t recipe,uint32_t si){
    if(!pipeline_ram(recipe,M10V_ISP_EFFECTS_SHOT_OFFSET+M10V_ISP_EFFECTS_SHOT_BYTES)||
       !pipeline_ram(si,0x94c)||*(const uint32_t*)(uintptr_t)recipe!=0x53d0fc90u||
       *(const uint32_t*)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC||
       si!=*(const uint32_t*)(uintptr_t)(recipe+0x44c8u))pipeline_hold(recipe,20,si);
    const uint8_t *saved=(const void*)(uintptr_t)si;
    uint32_t tone=saved[0x77c],native_grain=saved[0x795];
    uint32_t grain=native_grain>3u?4u:native_grain?4u-native_grain:0u;
    /* Eligibility follows this saved native graph, never live UI. HDR has a
     * separate original topology. Other non-ImageControl routes stay stock. */
    if(!m10v_tone_valid(tone)||tone==14)return 1;
    const m10v_isp_recipe_color *color=(const void*)(uintptr_t)(recipe+M10V_SAVE_COLOR_OFFSET);
    if(pipeline_color_state(color)){
        uint32_t selected=color->selected_tone?color->selected_tone:tone;
        if(!m10v_tone_valid(selected))pipeline_hold(recipe,21,selected);
        uint32_t slot=m10v_tone_slot(selected);
        if(slot<M10V_SLOT_COUNT&&color->state.slots[slot].film){
            uint32_t film=color->state.slots[slot].film;
            if(film==M10V_PIXEL_ID||film==M10V_CHAR_ID)return 1;
            grain=color->state.slots[slot].grain;
        }
    }
    m10v_isp_effects_shot_snapshot shot;m10v_isp_effects_snapshot resolved;
    if(!m10v_isp_effects_shot_read(recipe,&shot)){
        if(m10v_isp_effects_shot_unavailable(recipe,si))return 1;
        pipeline_hold(recipe,22,si);
    }
    if(!m10v_isp_effects_resolve_snapshot(&shot.settings,grain,&resolved))pipeline_hold(recipe,23,grain);
    uint32_t mask=(resolved.effective_grain_strength?M10V_ISP_EFFECTS_NATIVE_GRAIN:0u)|
        (shot.settings.leak_gain?M10V_ISP_EFFECTS_NATIVE_LEAK:0u)|
        (shot.settings.blur_gain?M10V_ISP_EFFECTS_NATIVE_BLUR:0u);
    if(!mask)return 1;
    if(shot.failed||!shot.planned||shot.source_si!=si||!shot.stock_query_valid||
       shot.effective_grain_strength!=resolved.effective_grain_strength||
       (shot.native_completed&mask)!=mask)pipeline_hold(recipe,24,mask);
    return 1;
}
