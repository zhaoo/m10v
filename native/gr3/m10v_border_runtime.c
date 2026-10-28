#include "m10v_border_runtime.h"
#include "m10v_border_prepare.h"
#include "m10v_border_shot.h"
#include "m10v_border_bank.h"
#include "m10v_border_canvas.h"
#include "m10v_border_fill_plan.h"
#include "m10v_border_wait_guard.h"
#include <stddef.h>
extern int m10v_capture_library(uint32_t context);
extern uint32_t m10v_save_trace_recipe_mark(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
extern void border_recovery_transfer_body_hook(void),border_recovery_transfer_wait_hook(void);
extern void border_recovery_fill_body_hook(void),border_recovery_fill_wait_hook(void);
extern void border_recovery_resize_body_hook(void),border_recovery_resize_wait_hook(void);
extern void border_recovery_resize_dma_wait_hook(void),border_recovery_fill_release_hook(void),border_recovery_resize_release_hook(void);
#define U(p) ((uint32_t)(uintptr_t)(p))
static int ram(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x55000000u&&n<=0x80000000u&&p<=0x80000000u-n;}
static uint32_t word(uint32_t p){return *(const volatile uint32_t *)(uintptr_t)p;}
static uint32_t half(uint32_t p){return *(const volatile uint16_t *)(uintptr_t)p;}
static void copy8(uint32_t *d,const uint32_t *s){for(uint32_t i=0;i<8u;++i)((volatile uint32_t *)d)[i]=s[i];}
static int same8(const uint32_t *a,const uint32_t *b){
    if((a[0]&255u)!=(b[0]&255u)||(a[7]&255u)!=(b[7]&255u))return 0;
    for(uint32_t i=1;i<7u;++i)if(a[i]!=b[i])return 0;return 1;
}
static int overlaps(uint32_t a,uint32_t an,uint32_t b,uint32_t bn){return a<b+bn&&b<a+an;}
static uint32_t crop_rows(uint32_t displacement,uint32_t stride,uint32_t bound){
    uint32_t low=0,high=bound;
    while(low<high){uint32_t mid=(low+high+1u)/2u;
        if(mid*stride<=displacement)low=mid;else high=mid-1u;
    }
    return low;
}
static void hold(void){for(;;)((void(*)(uint32_t))0x536b0a74u)(1);}
static void trace_prepare(uint32_t recipe,uint32_t stage,uint32_t reason){
    (void)m10v_save_trace_recipe_mark(recipe,197u,0x424f5244u,stage,reason);
}
void m10v_border_runtime_before_submit(uint32_t module,uint32_t config){
    if(!ram(config,0x60u)||config<0x5500096cu)return;
    uint32_t recipe=config-0x96cu,style;
    if(!m10v_border_shot_read(recipe,&style)||style==M10V_BORDER_OFF)return;
    uint32_t phase=m10v_border_shot_phase(recipe);
    if(phase==M10V_BORDER_PHASE_FAILED_BEFORE_LIBRARY)return;
    if(phase!=M10V_BORDER_PHASE_FROZEN&&phase!=M10V_BORDER_PHASE_PREPARED)hold();
    uint32_t mode=word(recipe+0x18u),request=word(recipe+0x5cu);
    uint32_t reason=0;
    if(mode!=0u&&mode!=5u&&mode!=6u)reason|=1u;
    if(!ram(request,16u))reason|=2u;
    else {
        if(word(request)!=0x53d0fe60u)reason|=4u;
        if(*(const volatile uint8_t *)(uintptr_t)(request+12u)!=1u)reason|=8u;
        if(*(const volatile uint8_t *)(uintptr_t)(request+13u)>1u)reason|=16u;
    }
    if(reason){
        trace_prepare(recipe,1u,reason);
        if(phase==M10V_BORDER_PHASE_PREPARED)hold();
        if(!m10v_border_shot_transition(recipe,phase,M10V_BORDER_PHASE_FAILED_BEFORE_LIBRARY))hold();
        return;
    }
    int result=m10v_border_prepare(module,config);
    if(result==1){
        if(phase==M10V_BORDER_PHASE_FROZEN&&
           !m10v_border_shot_transition(recipe,phase,M10V_BORDER_PHASE_PREPARED))hold();
        return;
    }
    /* Already-produced stripes cannot be rolled back to the original pitch.
     * Retain original worker, caller stack, recipe and banks on this path. */
    if(phase==M10V_BORDER_PHASE_PREPARED)hold();
    trace_prepare(recipe,2u,(uint32_t)(-result));
    if(!m10v_border_shot_transition(recipe,phase,M10V_BORDER_PHASE_FAILED_BEFORE_LIBRARY))hold();
}
static __attribute__((noinline)) int guard_branch(uint32_t at,uint32_t target){
    int32_t delta=(int32_t)(target-at-8u);
    return !(target&3u)&&delta>=-(1<<25)&&delta<(1<<25)&&
           word(at)==(0xeb000000u|(((uint32_t)delta>>2)&0xffffffu));
}
static int ready(void){
    if(word(0x5369a010u)!=0xe3a00058u||word(0x536589fcu)!=0xe3a00068u||
       word(0x53672bacu)!=0xe3a00058u)return 0;
    /* Direct address expressions keep external function relocations in
     * checked ARM MOVW/MOVT pairs, not an unverified ABS32 pointer table. */
    if(!guard_branch(0x5369a01cu,U(m10v_border_transfer_construct))||
       !guard_branch(0x5369ac4cu,U(border_recovery_transfer_body_hook))||
       !guard_branch(0x5369a478u,U(border_recovery_transfer_wait_hook))||
       !guard_branch(0x534aae28u,U(m10v_border_client_wait))||
       !guard_branch(0x53658a08u,U(m10v_border_fill_construct))||
       !guard_branch(0x536594a0u,U(border_recovery_fill_body_hook))||
       !guard_branch(0x5376a370u,U(border_recovery_fill_wait_hook))||
       !guard_branch(0x53672bb8u,U(m10v_border_resize_construct))||
       !guard_branch(0x53674014u,U(border_recovery_resize_body_hook))||
       !guard_branch(0x5377160cu,U(border_recovery_resize_wait_hook))||
       !guard_branch(0x53673244u,U(border_recovery_resize_dma_wait_hook))||
       !guard_branch(0x5367331cu,U(border_recovery_resize_dma_wait_hook))||
       !guard_branch(0x53673384u,U(border_recovery_resize_dma_wait_hook))||
       !guard_branch(0x5376a38cu,U(border_recovery_fill_release_hook))||
       !guard_branch(0x53771968u,U(border_recovery_resize_release_hook)))return 0;
    /* Only cold-boot installation of the checked alloc/ctor pairs admits
     * these appended tags. Getters alone must never recreate live workers. */
    static const uint32_t factories[3][5]={
      {0x5369a0e8u,4,0x44,0x42575431u,0x58},
      {0x53658a68u,4,0x58,0x42465731u,0x68},
      {0x53672c48u,12,0x48,0x42525731u,0x58}};
    for(uint32_t i=0;i<3u;++i){
        const uint32_t *f=factories[i];uint32_t factory=((uint32_t(*)(void))(uintptr_t)f[0])();
        if(!ram(factory,16u))return 0;uint32_t worker=word(factory+f[1]);
        if(!ram(worker,f[4])||word(worker+f[2])!=f[3])return 0;
    }
    return 1;
}
static int preview(uint32_t recipe,uint32_t offset,const m10v_border_bank_info *shape,
                    const m10v_border_canvas_info *canvas,uint32_t d[8]){
    copy8(d,(const uint32_t *)(uintptr_t)(recipe+offset));
    uint32_t f=d[0]&255u,w=d[4]&65535u,h=d[4]>>16,s=d[5]&65535u,rows=d[5]>>16;
    uint32_t x=d[6]&65535u,y=d[6]>>16;
    if((f!=1u&&f!=2u)||d[3]||!w||!h||((w|h|s|x|y)&1u)||
       s<w||s>16384u||rows<h||rows>16384u||(f==2u&&(rows&1u))||
       x>s||w>s-x||y>rows||h>rows-y||s*rows>=0x100000u||
       ((d[7]&255u)!=0u&&(d[7]&255u)!=2u)||((d[1]|d[2])&7u))return 0;
    uint32_t yn=s*rows,cn=f==2u?yn/2u:yn,end=shape->bank+shape->capacity;
    if(d[1]<shape->preview_base||d[2]<shape->preview_base||
       yn>end-shape->preview_base||cn>end-shape->preview_base||
       d[1]>end-yn||d[2]>end-cn||overlaps(d[1],yn,d[2],cn))return 0;
    m10v_border_rect fit;
    if(m10v_border_preview_fit(canvas->layout.outer.width,canvas->layout.outer.height,w,h,&fit))return 0;
    d[4]=fit.width|(fit.height<<16);d[6]=0;return 1;
}
static int preview_overlap(const uint32_t a[8],const uint32_t b[8]){
    uint32_t an=(a[5]&65535u)*(a[5]>>16),bn=(b[5]&65535u)*(b[5]>>16);
    uint32_t ac=(a[0]&255u)==2u?an/2u:an,bc=(b[0]&255u)==2u?bn/2u:bn;
    return overlaps(a[1],an,b[1],bn)||overlaps(a[1],an,b[2],bc)||
           overlaps(a[2],ac,b[1],bn)||overlaps(a[2],ac,b[2],bc);
}
static void publish_previews_fill(m10v_border_fill_plan_info *p,uint32_t d[2][8],uint32_t style){
    for(uint32_t i=0;i<2u;++i){
        copy8(p->descriptors[i],d[i]);
        p->descriptors[i][4]=(d[i][5]&65535u)|(d[i][5]&0xffff0000u);
        p->descriptors[i][6]=0;
        p->rectangles[i].destination=U(p)+offsetof(m10v_border_fill_plan_info,descriptors)+32u*i;
        p->rectangles[i].y=style==M10V_BORDER_POLAROID?255u:0u;
        p->rectangles[i].cb=p->rectangles[i].cr=128;p->rectangles[i].reserved=0;
    }
    p->count=2;p->bytes=36;p->tag=M10V_BORDER_FILL_BUNDLE_TAG;
}
static int fail(uint32_t recipe,uint32_t before,int result){
    uint32_t after=before==M10V_BORDER_PHASE_LIBRARY_ATTEMPTED?
        M10V_BORDER_PHASE_FAILED_AFTER_LIBRARY:M10V_BORDER_PHASE_FAILED_BEFORE_LIBRARY;
    if(after==M10V_BORDER_PHASE_FAILED_BEFORE_LIBRARY)
        trace_prepare(recipe,3u,(uint32_t)(-result));
    if(!m10v_border_shot_transition(recipe,before,after))hold();return result;
}
int m10v_border_runtime_after_resize(uint32_t module,uint32_t config){
    if(!ram(config,0x60u)||config<0x55000904u)return -1;
    uint32_t recipe=config-0x904u,style,orientation;
    if(!m10v_border_shot_read(recipe,&style))return -1;
    if(style==M10V_BORDER_OFF)return 0;
    uint32_t phase=m10v_border_shot_phase(recipe);
    if(phase==M10V_BORDER_PHASE_COMPLETE)return 1;
    if(phase!=M10V_BORDER_PHASE_PREPARED)return -2;
    if(!m10v_border_shot_orientation(recipe,&orientation)||!ram(module,0x8a44u)||
       word(config+0x30u)!=recipe+0x1a8u||word(config+0x34u)!=word(recipe+0x44c8u)||
       word(config+0x38u)!=word(recipe+0x5cu)||word(config+0x3cu)!=recipe+0x70u||
       word(config+0x40u)!=recipe+0xb0u||word(config+0x44u)!=recipe+0x90u||
       word(config+0x48u)!=recipe+0xd0u||word(config+0x4cu)!=recipe+0xf0u)return fail(recipe,phase,-3);
    uint32_t mode=word(recipe+0x18u);
    if(mode!=0u&&mode!=5u&&mode!=6u)return fail(recipe,phase,-4);
    m10v_border_bank_info shape;
    if(m10v_border_bank_shape(style,orientation,half(recipe+0x256u),half(recipe+0x258u),
          word(recipe+0x304u),word(recipe+0x364u),&shape))return fail(recipe,phase,-5);
    uint32_t *source=(uint32_t *)(uintptr_t)(recipe+0x70u),*main=(uint32_t *)(uintptr_t)(recipe+0xb0u);
    uint32_t base=shape.preview_base-2u*shape.plane_bytes;
    m10v_border_canvas_info canvas;
    if(!same8(source,main)||(source[5]&65535u)!=shape.canvas.stride||
       main[2]-main[1]!=shape.plane_bytes||
       m10v_border_canvas_plan(style,orientation,main,base,base+shape.plane_bytes,shape.plane_bytes,&canvas))
        return fail(recipe,phase,-6);
    /* A cropped native descriptor retains old cacheRows; normalize before
     * either the early or a rejected-stage later residual bridge can use it. */
    copy8(source,canvas.inner);copy8(main,canvas.inner);
    uint32_t dest[2][8];
    if(!preview(recipe,0xd0u,&shape,&canvas,dest[0])||!preview(recipe,0xf0u,&shape,&canvas,dest[1])||
       preview_overlap(dest[0],dest[1])||!ready())return fail(recipe,phase,-7);
    m10v_border_fill_plan_info *fills=((void*(*)(uint32_t))0x536af2a8u)(sizeof(*fills));
    if(!fills)return fail(recipe,phase,-8);
    if(!ram(U(fills),sizeof(*fills))||overlaps(U(fills),sizeof(*fills),shape.bank,shape.capacity))hold();
    if(m10v_border_fill_plan(&canvas,U(fills),fills)!=1){
        ((void(*)(void*))0x536af2e4u)(fills);return fail(recipe,phase,-8);
    }
    if(!m10v_border_shot_transition(recipe,phase,M10V_BORDER_PHASE_RUNNING)){
        ((void(*)(void*))0x536af2e4u)(fills);return -9;
    }
    uint32_t gate=m10v_border_stage_enter(recipe);
    if(!gate){((void(*)(void*))0x536af2e4u)(fills);return fail(recipe,M10V_BORDER_PHASE_RUNNING,-10);}
    ((void(*)(uint32_t,uint32_t))0x5350e624u)(recipe,6);
    int library=m10v_capture_library(recipe+0x9b8u);
    if(!m10v_border_shot_transition(recipe,M10V_BORDER_PHASE_RUNNING,M10V_BORDER_PHASE_LIBRARY_ATTEMPTED))hold();
    if(library&&library!=M10V_BORDER_LIBRARY_STOCK_BYPASS){
        /* Success/native-only inherits the original cache handoff. No such
         * blanket promise exists for negative residual-render returns. */
        ((void(*)(void*,uint32_t))0x5383c8a8u)((void*)(uintptr_t)canvas.inner[1],
              canvas.layout.stride*canvas.layout.inner.height);
        ((void(*)(void*,uint32_t))0x5383c8a8u)((void*)(uintptr_t)canvas.inner[2],
              canvas.layout.stride*canvas.layout.inner.height);
    }
    if(library&&library!=M10V_BORDER_LIBRARY_STOCK_BYPASS){
        if(!m10v_border_stage_leave(gate,recipe))hold();
        ((void(*)(void*))0x536af2e4u)(fills);
        return fail(recipe,M10V_BORDER_PHASE_LIBRARY_ATTEMPTED,-11);
    }
    if(!same8(source,canvas.inner)||!same8(main,canvas.inner))hold();
    m10v_border_native_client client;m10v_border_client_construct(&client);
    if(!m10v_border_fill_bundle_submit(&client,(const m10v_border_fill_bundle *)fills))hold();
    /* Reuse only after actual native callback tail returned. Two small whole
     * allocations are initialized before resize so JPEG MCU padding is clean. */
    publish_previews_fill(fills,dest,style);
    if(!m10v_border_fill_bundle_submit(&client,(const m10v_border_fill_bundle *)fills))hold();
    for(uint32_t i=0;i<2u;++i){
        if(!m10v_border_client_prepare(&client,0x03020002u,0x40u))hold();
        ((void(*)(void*,const void*,const void*,uint32_t))0x534ab6b8u)(&client,canvas.canvas,dest[i],1);
        if(!m10v_border_client_done(&client)||client.completed!=1u)hold();
    }
    if(!m10v_border_client_destroy_if_done(&client))hold();
    copy8(source,canvas.canvas);copy8(main,canvas.canvas);
    copy8((uint32_t *)(uintptr_t)(recipe+0x110u),canvas.canvas);
    copy8((uint32_t *)(uintptr_t)(recipe+0xd0u),dest[0]);
    copy8((uint32_t *)(uintptr_t)(recipe+0xf0u),dest[1]);
    if(!m10v_border_shot_transition(recipe,M10V_BORDER_PHASE_LIBRARY_ATTEMPTED,M10V_BORDER_PHASE_COMPLETE))hold();
    ((void(*)(void*))0x536af2e4u)(fills);
    if(!m10v_border_stage_leave(gate,recipe))hold();return 1;
}

/* The owner can replace all three large descriptors after BackResize returned.
 * Its copied Y/C addresses still identify the already composited bank. The
 * encoder handoff is the last owned point at which those descriptors may be
 * restored without touching a photo pixel on the CPU. */
int m10v_border_runtime_jpeg(uint32_t context){
    int library=m10v_capture_library(context);
    if(!ram(context,0x50u)||context<0x550009b8u)return library;
    uint32_t recipe=context-0x9b8u,style,orientation;
    if(!m10v_border_shot_read(recipe,&style)||style==M10V_BORDER_OFF||
       !m10v_border_shot_orientation(recipe,&orientation))return library;
    uint32_t phase=m10v_border_shot_phase(recipe);
    if(phase!=M10V_BORDER_PHASE_COMPLETE&&phase!=M10V_BORDER_PHASE_FAILED_BEFORE_LIBRARY)return library;
    m10v_border_bank_info shape;
    if(m10v_border_bank_shape(style,orientation,half(recipe+0x256u),half(recipe+0x258u),
          word(recipe+0x304u),word(recipe+0x364u),&shape))return library;
    uint32_t *source=(uint32_t *)(uintptr_t)(recipe+0x70u),*main=(uint32_t *)(uintptr_t)(recipe+0xb0u);
    uint32_t w=main[4]&65535u,h=main[4]>>16;
    uint32_t fullw=half(recipe+0x256u),fullh=half(recipe+0x258u);
    uint32_t base=shape.preview_base-2u*shape.plane_bytes;
    m10v_border_canvas_info canvas;
    if(phase==M10V_BORDER_PHASE_COMPLETE){
        /* Once IIP completed, the frozen bank and exact inner Y addresses
         * authenticate the pixels. The owner may have restored stale C,
         * stride or auxiliary descriptor words before this JPEG handoff. */
        if(w!=fullw||h!=fullh||(source[4]&65535u)!=fullw||(source[4]>>16)!=fullh||
           (source[0]&255u)!=1u||(main[0]&255u)!=1u||
           (source[7]&255u)!=2u||(main[7]&255u)!=2u||
           source[1]!=shape.source_y||main[1]!=shape.source_y){
            trace_prepare(recipe,4u,10u);return library;
        }
        uint32_t inner[8];copy8(inner,main);
        inner[1]=shape.source_y;inner[2]=shape.source_c;
        inner[3]=0;inner[4]=fullw|(fullh<<16);
        inner[5]=shape.canvas.stride|(fullh<<16);inner[6]=0;
        if(m10v_border_canvas_plan(style,orientation,inner,base,
              base+shape.plane_bytes,shape.plane_bytes,&canvas)||
           canvas.canvas[4]!=(shape.canvas.outer.width|(shape.canvas.outer.height<<16))){
            trace_prepare(recipe,4u,11u);return library;
        }
        copy8(source,canvas.canvas);copy8(main,canvas.canvas);
        copy8((uint32_t *)(uintptr_t)(recipe+0x110u),canvas.canvas);
        trace_prepare(recipe,4u,1u);
        return library;
    }
    if(!same8(source,main)||!w||!h||w>fullw||h>fullh||((w|h)&1u)||
       (source[0]&255u)!=1u||source[3]||source[6]||(source[7]&255u)!=2u||
       main[2]-main[1]!=shape.plane_bytes||main[1]<shape.source_y)return library;
    uint32_t displacement=main[1]-shape.source_y;
    uint32_t crop_y=crop_rows(displacement,shape.canvas.stride,fullh);
    uint32_t crop_x=displacement-crop_y*shape.canvas.stride;
    if((crop_x|crop_y)&1u||crop_x>fullw||w>fullw-crop_x||
       crop_y>fullh||h>fullh-crop_y||
       main[2]!=shape.source_c+displacement)return library;
    uint32_t inner[8];copy8(inner,main);
    inner[5]=shape.canvas.stride|(h<<16);
    if(m10v_border_canvas_plan(style,orientation,inner,base,
          base+shape.plane_bytes,shape.plane_bytes,&canvas))return library;
    /* Only a native crop of the prepared full frame may enter this late path.
     * No fallback bank allocation or CPU frame draw is permitted. */
    if((w==fullw&&h==fullh)||(library&&library!=-4)||!ready())return library;
    uint32_t dest[2][8];
    if(!preview(recipe,0xd0u,&shape,&canvas,dest[0])||
       !preview(recipe,0xf0u,&shape,&canvas,dest[1])||preview_overlap(dest[0],dest[1]))return library;
    m10v_border_fill_plan_info *fills=((void*(*)(uint32_t))0x536af2a8u)(sizeof(*fills));
    if(!fills)return library;
    if(!ram(U(fills),sizeof(*fills))||overlaps(U(fills),sizeof(*fills),shape.bank,shape.capacity))hold();
    if(m10v_border_fill_plan(&canvas,U(fills),fills)!=1){
        ((void(*)(void*))0x536af2e4u)(fills);return library;
    }
    if(!m10v_border_shot_transition(recipe,M10V_BORDER_PHASE_FAILED_BEFORE_LIBRARY,M10V_BORDER_PHASE_RUNNING))hold();
    uint32_t gate=m10v_border_stage_enter(recipe);
    if(!gate)hold();
    m10v_border_native_client client;m10v_border_client_construct(&client);
    if(!m10v_border_fill_bundle_submit(&client,(const m10v_border_fill_bundle *)fills))hold();
    publish_previews_fill(fills,dest,style);
    if(!m10v_border_fill_bundle_submit(&client,(const m10v_border_fill_bundle *)fills))hold();
    for(uint32_t i=0;i<2u;++i){
        if(!m10v_border_client_prepare(&client,0x03020002u,0x40u))hold();
        ((void(*)(void*,const void*,const void*,uint32_t))0x534ab6b8u)(&client,canvas.canvas,dest[i],1);
        if(!m10v_border_client_done(&client)||client.completed!=1u)hold();
    }
    if(!m10v_border_client_destroy_if_done(&client))hold();
    copy8(source,canvas.canvas);copy8(main,canvas.canvas);
    copy8((uint32_t *)(uintptr_t)(recipe+0x110u),canvas.canvas);
    copy8((uint32_t *)(uintptr_t)(recipe+0xd0u),dest[0]);
    copy8((uint32_t *)(uintptr_t)(recipe+0xf0u),dest[1]);
    if(!m10v_border_shot_transition(recipe,M10V_BORDER_PHASE_RUNNING,M10V_BORDER_PHASE_LIBRARY_ATTEMPTED)||
       !m10v_border_shot_transition(recipe,M10V_BORDER_PHASE_LIBRARY_ATTEMPTED,M10V_BORDER_PHASE_COMPLETE))hold();
    ((void(*)(void*))0x536af2e4u)(fills);
    if(!m10v_border_stage_leave(gate,recipe))hold();
    trace_prepare(recipe,4u,2u);
    return library;
}
