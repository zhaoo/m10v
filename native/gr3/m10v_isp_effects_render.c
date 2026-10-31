#include "m10v_isp_effects_render.h"
#include "m10v_isp_effect_transfer.h"
#include "m10v_isp_effect_transfer_runtime.h"
#include "m10v_isp_effect_granulation.h"
#include "m10v_isp_effect_render_bindings.h"
#include "m10v_isp_effect_memory.h"
#define U(p) ((uint32_t)(uintptr_t)(p))
static int ram(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x55000000u&&n<=0x30000000u&&p<=0x80000000u-n;}
static int overlap(uint32_t a,uint32_t an,uint32_t b,uint32_t bn){return a<b+bn&&b<a+an;}
static void copy_words(uint32_t *out,const uint32_t *in,uint32_t n){for(uint32_t k=0;k<n;k++)out[k]=in[k];}
static int prepare(const m10v_isp_effect_texture *t,uint32_t work,uint32_t capacity,uint32_t w,uint32_t h,uint32_t sw,uint32_t sh,uint32_t phase,uint32_t format,m10v_isp_effect_transfer *plan,uint32_t token){
 if(m10v_isp_effect_transfer_plan_format(t,work,capacity,w,h,sw,sh,phase,format,plan)!=1)return -4;
 return m10v_isp_effect_transfer_execute(plan,token)==1?1:-4;
}
int m10v_isp_effects_render(uint32_t ctx,const uint32_t photo[8],uint32_t work,uint32_t capacity,const m10v_isp_effects_shot_snapshot *shot){
 if(!ram(U(shot),sizeof(*shot)))return -1;
 m10v_isp_effects_shot_snapshot frozen;
 copy_words((uint32_t*)&frozen,(const uint32_t*)shot,sizeof(frozen)/4u);
 const m10v_isp_effects_settings *s=&frozen.settings;
 if(frozen.magic!=M10V_ISP_EFFECTS_SHOT_MAGIC||!ram(frozen.owner,4)||frozen.ready!=1||frozen.planned!=1||!frozen.source_si||frozen.failed||
    frozen.effective_grain_strength>3||s->leak_gain>3||s->leak_position>2||s->leak_spread>2||s->grain_mode>4||s->grain_size>2||s->blur_gain>3||s->blur_range>2||s->reserved||frozen.reserved||
    (frozen.saved_orientation!=1&&frozen.saved_orientation!=3&&frozen.saved_orientation!=6&&frozen.saved_orientation!=8)||
    (s->grain_mode&&frozen.effective_grain_strength!=s->grain_mode-1u))return -1;
 if(!s->leak_gain&&!frozen.effective_grain_strength)return 1;
 if(!ram(U(photo),32)||!ram(ctx,0x40))return -1;
 uint32_t p[8];copy_words(p,photo,8);
 uint32_t format=p[0]&255u,w=p[4]&65535u,h=p[4]>>16,stride=p[5]&65535u,rows=p[5]>>16;
 uint32_t left=p[6]&65535u,top=p[6]>>16,uvh=format==1?h:h/2u;
 if((format!=1&&format!=2)||w<2||h<2||w>6144||h>6144||((w|h|rows)&1u)||stride<w||stride>16384||rows<h||rows>16384||
    left>stride-w||top>rows-h||(left&1u)||(format==2&&(top&1u))||frozen.planned_width!=w||frozen.planned_height!=h)return -1;
 uint32_t original_y=p[1],original_uv=p[2],allocation_y=stride*rows,allocation_uv=format==1?allocation_y:allocation_y/2u;
 uint32_t yoffset=top*stride+left,uvoffset=(format==1?top:top/2u)*stride+left;
 uint32_t y=stride*h,uv=stride*uvh,noise_stride=(w+15u)&~15u,noise_y=noise_stride*h;
 uint32_t needed=s->leak_gain&&format==1?noise_y*2u:noise_y+noise_y/2u;
 /* Original Granulation ignores ROI offsets and its native cache helper covers
  * stride*height from the bound plane, including the final row's padding.
  * Shift only our descriptor snapshot, and prove THAT complete native span
  * stays in each original allocation. Visible-last-row bounds alone are not
  * sufficient when a nonzero left crop reaches the allocation's last row. */
 if(!m10v_isp_effect_buffer_span(original_y,allocation_y)||!m10v_isp_effect_buffer_span(original_uv,allocation_uv)||overlap(original_y,allocation_y,original_uv,allocation_uv)||
    yoffset>allocation_y-y||uvoffset>allocation_uv-uv||((original_y+yoffset)|(original_uv+uvoffset))&3u||
    !m10v_isp_effect_buffer_span(work,needed)||(work&15u)||capacity<needed||frozen.workspace_bytes<needed||
    overlap(work,needed,original_y,allocation_y)||overlap(work,needed,original_uv,allocation_uv)||
    overlap(work,needed,U(photo),32)||overlap(work,needed,U(shot),sizeof(*shot))||overlap(work,needed,ctx,0x40)||
    overlap(original_y,allocation_y,ctx,0x40)||overlap(original_uv,allocation_uv,ctx,0x40)||
    overlap(original_y,allocation_y,U(photo),32)||overlap(original_uv,allocation_uv,U(photo),32)||
    overlap(original_y,allocation_y,U(shot),sizeof(*shot))||overlap(original_uv,allocation_uv,U(shot),sizeof(*shot)))return -1;
 p[1]=original_y+yoffset;p[2]=original_uv+uvoffset;p[5]=stride|(h<<16);p[6]=0;
 m10v_isp_effect_transfer plan;uint32_t uvview[8],maskview[8];
 if(overlap(work,needed,U(maskview),sizeof(maskview))||overlap(original_y,allocation_y,U(maskview),sizeof(maskview))||overlap(original_uv,allocation_uv,U(maskview),sizeof(maskview)))return -1;
 if(overlap(work,needed,U(&plan),sizeof(plan))||overlap(work,needed,U(p),sizeof(p))||overlap(work,needed,U(uvview),sizeof(uvview))||overlap(work,needed,U(&frozen),sizeof(frozen)))return -1;
 if(overlap(original_y,allocation_y,U(&plan),sizeof(plan))||overlap(original_uv,allocation_uv,U(&plan),sizeof(plan))||
    overlap(original_y,allocation_y,U(p),sizeof(p))||overlap(original_uv,allocation_uv,U(p),sizeof(p))||
    overlap(original_y,allocation_y,U(uvview),sizeof(uvview))||overlap(original_uv,allocation_uv,U(uvview),sizeof(uvview))||
    overlap(original_y,allocation_y,U(&frozen),sizeof(frozen))||overlap(original_uv,allocation_uv,U(&frozen),sizeof(frozen)))return -1;
 if(s->leak_gain){
  uint32_t position=s->leak_position,orientation=frozen.saved_orientation;
  if((orientation==3u||orientation==6u)&&position<2u)position^=1u;
  uint32_t at=position*3u+s->leak_spread,profile=(s->leak_gain-1u)*3u;
  const m10v_isp_effect_texture (*fields)[2]=(orientation==6u||orientation==8u)?m10v_render_leaks_vertical:m10v_render_leaks;
  const m10v_isp_effect_texture *field=&fields[at][0];
  if(prepare(field,work,capacity,w,h,field->width,field->height,0,format,&plan,frozen.source_si)!=1)return -4;
  copy_words(uvview,p,8);uvview[1]=p[2];uvview[2]=0;uvview[4]=w|(uvh<<16);uvview[5]=stride|(uvh<<16);
  copy_words(maskview,uvview,8);maskview[1]=work+noise_y;maskview[5]=noise_stride|(uvh<<16);
  if(m10v_isp_effect_granulation_luma((void*)(uintptr_t)ctx,maskview,p,m10v_render_curves[9])!=1)return -4;
  if(m10v_isp_effect_granulation_owned((void*)(uintptr_t)ctx,uvview,uvview,1,(void*)(uintptr_t)(work+noise_y),noise_stride*uvh,m10v_render_curves[profile+1u])!=1)return -4;
  field=&fields[at][1];
  if(prepare(field,work,capacity,w,h,field->width,field->height,0,format,&plan,frozen.source_si)!=1)return -4;
  if(m10v_isp_effect_granulation_luma((void*)(uintptr_t)ctx,maskview,p,m10v_render_curves[9])!=1)return -4;
  if(m10v_isp_effect_granulation_owned((void*)(uintptr_t)ctx,uvview,uvview,1,(void*)(uintptr_t)(work+noise_y),noise_stride*uvh,m10v_render_curves[profile+2u])!=1)return -4;
  /* Original Y stays intact for BOTH chroma gates. Last Resize retained the
   * identical spatial Y mask; finish exposure only after both luma reads. */
  if(m10v_isp_effect_granulation_owned((void*)(uintptr_t)ctx,p,p,1,(void*)(uintptr_t)work,noise_y,m10v_render_curves[profile])!=1)return -4;
 }
 if(frozen.effective_grain_strength){
  static const uint16_t crops[3][2]={{3000,2000},{1500,1000},{1008,672}};
  uint32_t size=s->grain_size;
  if(prepare(&m10v_render_grain,work,capacity,w,h,crops[size][0],crops[size][1],frozen.source_si&63u,2,&plan,frozen.source_si)!=1)return -4;
  if(m10v_isp_effect_granulation_owned((void*)(uintptr_t)ctx,p,p,4u-frozen.effective_grain_strength,(void*)(uintptr_t)work,noise_y,0)!=1)return -4;
 }
 return 1;
}
