#ifndef M10V_HALATION_ENERGY_H
#define M10V_HALATION_ENERGY_H
#if M10V_SPATIAL_NEON
#include "m10v_spatial_accel.h"
#endif
/* Production 800T spatial model, independent of the legacy experimental core.
 * Unity-built with m10v_library.c: bounded 3 x uint16 planes, no allocation,
 * no external services or divisions. Input is full-range software YCbCr422,
 * NOT scene-linear RAW. Squared excess is an explicit exposure approximation.
 * Caller validates dimensions, disjoint buffers and 6*cells scratch first. */
static uint32_t energy_edge(uint32_t x, uint32_t n, int delta) {
    if (delta < 0 && x < (uint32_t)-delta) return 0;
    uint32_t v = delta < 0 ? x - (uint32_t)-delta : x + (uint32_t)delta;
    return v < n ? v : n - 1;
}
static void energy_blur(uint16_t *a, uint16_t *b, uint32_t w, uint32_t h, uint32_t passes, int distance) {
#if M10V_SPATIAL_NEON
    if(m10v_spatial_blur_u16(a,b,w*h,w,h,passes,(uint32_t)distance)==0)return;
#endif
    uint32_t d=(uint32_t)distance;
    for (uint32_t pass=0; pass<passes; ++pass) {
        for(uint32_t row=0;row<h;++row) {
            const uint16_t *src=a+row*w;uint16_t *dst=b+row*w;
            /* Only the boundary lanes need clamping. Interior pixels use
             * direct offsets, preserving the original per-pass rounding. */
            uint32_t x=0;
            for(;x<w && x<d;++x)
                dst[x]=(uint16_t)((src[0]+2u*src[x]+src[x+d<w?x+d:w-1])>>2);
            for(;x<w && x+d<w;++x)
                dst[x]=(uint16_t)((src[x-d]+2u*src[x]+src[x+d])>>2);
            for(;x<w;++x)
                dst[x]=(uint16_t)((src[x-d]+2u*src[x]+src[w-1])>>2);
        }
        for(uint32_t row=0;row<h;++row) {
            const uint16_t *top=b+energy_edge(row,h,-distance)*w;
            const uint16_t *mid=b+row*w,*bottom=b+energy_edge(row,h,distance)*w;
            uint16_t *dst=a+row*w;
            for(uint32_t x=0;x<w;++x)
                dst[x]=(uint16_t)((top[x]+2u*mid[x]+bottom[x])>>2);
        }
    }
}
static uint32_t energy_sample(const uint16_t *a,uint32_t w,uint32_t h,uint32_t x,uint32_t row,uint32_t shift) {
    uint32_t step=1u<<shift,half=step>>1;
    uint32_t px=x<half?0:x-half,py=row<half?0:row-half;
    uint32_t gx=px>>shift,gy=py>>shift,fx=px&(step-1),fy=py&(step-1);
    uint32_t nx=gx+1<w?gx+1:gx,ny=gy+1<h?gy+1:gy;
    uint32_t top=a[gy*w+gx]*(step-fx)+a[gy*w+nx]*fx;
    uint32_t bottom=a[ny*w+gx]*(step-fx)+a[ny*w+nx]*fx;
    return (top*(step-fy)+bottom*fy)>>(2*shift);
}
static uint8_t energy_clamp(int v) { return (uint8_t)(v<0?0:v>255?255:v); }
static uint32_t energy_pixel(const m10v_library_image *im,uint32_t x,uint32_t row,uint32_t gate,int red_sensitive) {
    uint32_t light=im->y[row*im->stride+x];
    if(red_sensitive) {
        int red=(int)light+((359*((int)im->chroma[row*im->stride+(x&~1u)+1]-128))>>8)-24;
        if(red>255)red=255;if(red>(int)light)light=(uint32_t)red;
    }
    uint32_t excess=light>gate?light-gate:0;return excess*excess*8;
}
static void energy_line(const m10v_library_image *im,uint16_t *line,uint32_t row,uint32_t gate,int distance) {
    uint32_t width=im->width,step=(uint32_t)distance;
#if M10V_SPATIAL_NEON
    uint32_t at=row*im->stride;
    uint32_t end=m10v_spatial_halo_line(im->y+at,im->chroma+at,line,width,gate,step);
    if(end){
        for(uint32_t x=0;x<width;++x){
            if(x==8)x=end;
            line[x]=(uint16_t)((energy_pixel(im,energy_edge(x,width,-distance),row,gate,1)+
                2u*energy_pixel(im,x,row,gate,1)+energy_pixel(im,energy_edge(x,width,distance),row,gate,1))>>2);
        }
        return;
    }
#endif
    /* Traverse each distance lane with a rolling three-tap window. The
     * previous right sample becomes the next center, so original red energy
     * is evaluated once per pixel instead of three times. Replicated borders
     * and the final integer rounding remain exactly the same. No extra plane
     * or mutable state is needed; rows still come from the original image. */
    for(uint32_t lane=0;lane<step && lane<width;++lane) {
        uint32_t left=energy_pixel(im,0,row,gate,1);
        uint32_t center=energy_pixel(im,lane,row,gate,1);
        for(uint32_t x=lane;x<width;x+=step) {
            uint32_t next=x+step<width?x+step:width-1;
            uint32_t right=energy_pixel(im,next,row,gate,1);
            line[x]=(uint16_t)((left+2*center+right)>>2);
            left=center;center=right;
        }
    }
}
static inline __attribute__((always_inline)) uint32_t energy_cell(const m10v_library_image *im,uint32_t x0,uint32_t y0,
    uint32_t step,uint32_t gate,int red_sensitive,uint32_t *peak){
#if M10V_SPATIAL_NEON
    if((step==8||step==16)&&x0+step<=im->width){
        uint32_t rows=im->height-y0;
        uint32_t at=y0*im->stride+x0;
        return m10v_spatial_halo_cell(im->y+at,red_sensitive?im->chroma+at:0,
            im->stride,step,rows<step?rows:step,gate,peak);
    }
#endif
    uint32_t sum=0,max_energy=0;
    for(uint32_t row=y0;row<y0+step&&row<im->height;++row){
        for(uint32_t x=x0;x<x0+step&&x<im->width;++x){
            uint32_t energy=energy_pixel(im,x,row,gate,red_sensitive);
            sum+=energy;
            if(energy>max_energy)max_energy=energy;
        }
    }
    if(peak)*peak=max_energy;
    return sum;
}
static uint32_t energy_source(const m10v_library_image *im,uint16_t *a,uint32_t gw,uint32_t gh,uint32_t shift,uint32_t gate,int red_sensitive) {
    uint32_t step=1u<<shift,active=0;
    for(uint32_t gy=0;gy<gh;++gy)for(uint32_t gx=0;gx<gw;++gx) {
        /* Integrate actual covered pixel energy; missing edge pixels are zero.
         * Maximum 16*16*49928 < 2^24; average stays <=49928. */
        uint32_t sum=energy_cell(im,gx<<shift,gy<<shift,step,gate,red_sensitive,0);
        a[gy*gw+gx]=(uint16_t)(sum>>(2*shift));
        active|=sum;
    }
    return active;
}
static uint32_t energy_project(const uint16_t *top,const uint16_t *bottom,
    uint32_t x,uint32_t step,uint32_t fy){
    return top[x]*(step-fy)+bottom[x]*fy;
}
static void m10v_800t_effects(m10v_library_image *im,const m10v_slot *choice,uint8_t *scratch,uint32_t gw,uint32_t gh,uint32_t shift) {
    uint32_t cells=gw*gh;
    uint16_t *a=(uint16_t *)scratch,*b=a+cells,*halo=b+cells;
    uint32_t gain=choice->halo_gain,soft=choice->soft;
    if(gain && !energy_source(im,a,gw,gh,shift,176+8u*choice->halo_threshold,1))gain=0;
    if(gain) {
        /* Nine distinct variances. Narrow kernel retains local light, broader
         * kernel contributes 1/4 of the energy without boosting tiny tails. */
        energy_blur(a,b,gw,gh,1u+choice->halo_spread,1);
        for(uint32_t i=0;i<cells;++i)halo[i]=a[i];
        energy_blur(a,b,gw,gh,2,2);
        for(uint32_t i=0;i<cells;++i)halo[i]=(uint16_t)((3u*halo[i]+a[i])>>2);
    }
    if(soft) {
        /* Both masks are extracted before any pixel writes. Softness cannot
         * create a halo seed and halo cannot feed back into neutral bloom. */
        if(energy_source(im,a,gw,gh,shift,192,0))energy_blur(a,b,gw,gh,4,2);
        else soft=0;
    }
    /* Test raw integrated energy, not the rounded grid: tiny lamps can have
     * zero coarse energy but a nonzero fine fringe. Never discard those. */
    if(!gain&&!soft)return;
    /* Fine near field uses a rolling buffer of ORIGINAL rows, reusing the
     * now-free blur temporary b. Never sample previously written image rows.
     * This retains tiny lamps without max-pooling them into a large source. */
    uint32_t distance=shift>2?1u<<(shift-2):1,lines=2*distance+1;
    while(distance>1 && lines*im->width>cells){distance>>=1;lines=2*distance+1;}
    int fine=gain && lines*im->width<=cells;uint32_t head=0;
    if(fine)for(uint32_t i=0;i<lines;++i)
        energy_line(im,b+i*im->width,energy_edge(0,im->height,(int)i-(int)distance),176+8u*choice->halo_threshold,(int)distance);
    uint32_t step=1u<<shift,half=step>>1;
    for(uint32_t row=0;row<im->height;++row) {
      uint32_t py=row<half?0:row-half,gy=py>>shift,ny=gy+1<gh?gy+1:gy;
      uint32_t fy=py&(step-1),at_row=row*im->stride;
      const uint16_t *near_top=0,*near_mid=0,*near_bot=0;
      if(fine){
          uint32_t mid=head+distance,bot=head+2*distance;
          if(mid>=lines)mid-=lines;
          if(bot>=lines)bot-=lines;
          near_top=b+head*im->width;near_mid=b+mid*im->width;near_bot=b+bot*im->width;
      }
      for(uint32_t x=0;x<im->width;){
        uint32_t px=x<half?0:x-half,gx=px>>shift,nx=gx+1<gw?gx+1:gx;
        uint32_t end=(((gx+1)<<shift)+half+1u)&~1u;
        if(end>im->width)end=im->width;
        uint32_t left=gain?energy_project(halo+gy*gw,halo+ny*gw,gx,step,fy):0;
        uint32_t right=gain?energy_project(halo+gy*gw,halo+ny*gw,nx,step,fy):0;
        if(!(left|right)&&!fine&&!soft){x=end;continue;}
        for(;x<end;x+=2){
        uint32_t near=0;
        if(fine){
            near=(near_top[x]+near_top[x+1]+2u*(near_mid[x]+near_mid[x+1])+
                near_bot[x]+near_bot[x+1])>>3;
        }
        if(!(left|right|near)&&!soft)continue;
        uint32_t at=at_row+x,y0=im->y[at],y1=im->y[at+1],peak=y0>y1?y0:y1;
        uint32_t protect=(255-peak)*4;if(protect>255)protect=255;
        /* Broad halo needs its own exposure gain: cell integration plus repeated
         * normalized blur otherwise rounds real6000px lamp fringes to zero.
         * Keep fine gain unchanged; maximum sum17*49928*8*255 fits uint32. */
        if(!protect&&!soft)continue;
        uint32_t fx=x<half?0:(x-half)&(step-1);
        uint32_t scatter=near+16u*((left*(step-fx)+right*fx)>>(2*shift));
        uint32_t r=(scatter*gain*protect)>>16;
        if(r>192)r=192;
        /* An exactly zero contribution leaves all four destination bytes
         * unchanged. Fine-source row rotation still happens below. */
        if(!r&&!soft)continue;
        /* Red-dominant exposure; the stronger near fringe admits some green.
         * Preserve neutral clipped cores and the original shared chroma ABI. */
        uint32_t g=(r>>3)+((r*r)>>11);
        uint32_t lift=(77*r+150*g+128)>>8;
        int cb=(int)im->chroma[at]-(int)((43*r+85*g+128)>>8);
        int cr=(int)im->chroma[at+1]+(int)((128*r-107*g+128)>>8);
        uint32_t bloom=soft?(energy_sample(a,gw,gh,x,row,shift)*soft)>>11:0;
        im->y[at]=energy_clamp((int)(y0+lift+((bloom*(255-y0))>>8)));
        im->y[at+1]=energy_clamp((int)(y1+lift+((bloom*(255-y1))>>8)));
        im->chroma[at]=energy_clamp(cb);im->chroma[at+1]=energy_clamp(cr);
        }
      }
      if(fine && row+1<im->height) {
          energy_line(im,b+head*im->width,energy_edge(row,im->height,(int)distance+1),176+8u*choice->halo_threshold,(int)distance);
          if(++head==lines)head=0;
      }
    }
}
#endif
