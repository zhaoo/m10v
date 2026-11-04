#include "m10v_spatial_accel.h"
#include <stddef.h>
#if defined(__arm__)
#include <arm_neon.h>

static inline uint16x8_t halo_energy8(const uint8_t *y,const uint8_t *chroma,uint8x8_t gate){
    uint8x8_t light=vld1_u8(y);
    if(chroma){
        uint8x8_t uv=vld1_u8(chroma);
        uint8x8_t cr=vuzp_u8(uv,uv).val[1];
        cr=vzip_u8(cr,cr).val[0];
        int16x8_t delta=vreinterpretq_s16_u16(vsubl_u8(cr,vdup_n_u8(128)));
        /* 359 = 256 + 103. Both signed terms fit in 16 bits. */
        int16x8_t correction=vaddq_s16(delta,vshrq_n_s16(vmulq_n_s16(delta,103),8));
        int16x8_t red=vaddq_s16(vreinterpretq_s16_u16(vmovl_u8(light)),correction);
        light=vmax_u8(light,vqmovun_s16(vsubq_s16(red,vdupq_n_s16(24))));
    }
    uint8x8_t excess=vqsub_u8(light,gate);
    return vshlq_n_u16(vmull_u8(excess,excess),3);
}

static inline uint16x4_t halo_tap4(uint16x4_t left,uint16x4_t center,uint16x4_t right){
    uint32x4_t sum=vaddl_u16(left,right);
    return vshrn_n_u32(vaddq_u32(sum,vshll_n_u16(center,1)),2);
}
#endif

uint32_t m10v_spatial_halo_cell(const uint8_t *y,const uint8_t *chroma,
    uint32_t stride,uint32_t width,uint32_t rows,uint32_t gate,uint32_t *peak){
#if defined(__arm__)
    uint32x4_t sum=vdupq_n_u32(0);
    uint16x8_t max_energy=vdupq_n_u16(0);
    uint8x8_t threshold=vdup_n_u8((uint8_t)gate);
    for(uint32_t row=0;row<rows;++row){
        const uint8_t *luma=y+row*stride;
        const uint8_t *uv=chroma?chroma+row*stride:NULL;
        for(uint32_t x=0;x<width;x+=8){
            uint16x8_t energy=halo_energy8(luma+x,uv?uv+x:NULL,threshold);
            sum=vpadalq_u16(sum,energy);
            if(peak)max_energy=vmaxq_u16(max_energy,energy);
        }
    }
    if(peak){
        uint16x4_t max4=vmax_u16(vget_low_u16(max_energy),vget_high_u16(max_energy));
        max4=vpmax_u16(max4,max4);
        *peak=vget_lane_u16(vpmax_u16(max4,max4),0);
    }
    uint32x2_t sum2=vadd_u32(vget_low_u32(sum),vget_high_u32(sum));
    return vget_lane_u32(vpadd_u32(sum2,sum2),0);
#else
    uint32_t sum=0,max_energy=0;
    for(uint32_t row=0;row<rows;++row)for(uint32_t x=0;x<width;++x){
        uint32_t at=row*stride;
        int light=y[at+x];
        if(chroma){
            int red=light+((359*((int)chroma[at+(x&~1u)+1]-128))>>8)-24;
            if(red>light)light=red>255?255:red;
        }
        uint32_t excess=light>(int)gate?(uint32_t)light-gate:0;
        uint32_t energy=excess*excess*8;
        sum+=energy;
        if(energy>max_energy)max_energy=energy;
    }
    if(peak)*peak=max_energy;
    return sum;
#endif
}

uint32_t m10v_spatial_halo_line(const uint8_t *y,const uint8_t *chroma,
    uint16_t *line,uint32_t width,uint32_t gate,uint32_t distance){
#if defined(__arm__)
    if(width<24||(distance!=2&&distance!=4))return 0;
    uint8x8_t threshold=vdup_n_u8((uint8_t)gate);
    uint16x8_t prev=halo_energy8(y,chroma,threshold);
    uint16x8_t center=halo_energy8(y+8,chroma+8,threshold);
    uint32_t x=8;
    for(;x+16<=width;x+=8){
        uint16x8_t next=halo_energy8(y+x+8,chroma+x+8,threshold);
        uint16x8_t left=distance==2?vextq_u16(prev,center,6):vextq_u16(prev,center,4);
        uint16x8_t right=distance==2?vextq_u16(center,next,2):vextq_u16(center,next,4);
        vst1q_u16(line+x,vcombine_u16(
            halo_tap4(vget_low_u16(left),vget_low_u16(center),vget_low_u16(right)),
            halo_tap4(vget_high_u16(left),vget_high_u16(center),vget_high_u16(right))));
        prev=center;
        center=next;
    }
    return x;
#else
    (void)y;(void)chroma;(void)line;(void)width;(void)gate;(void)distance;
    return 0;
#endif
}

static uint16_t tap(uint16_t l,uint16_t m,uint16_t r){
    return (uint16_t)(((uint32_t)l+2u*m+r)>>2);
}
static __attribute__((always_inline)) inline void eight(const uint16_t *l,const uint16_t *m,const uint16_t *r,uint16_t *dst){
#if defined(__arm__)
    /* All additions widen BEFORE summing. Saturating/16-bit addition changes
     * highlights; each original pass rounds once, after the complete sum. */
    __asm__ volatile(
        "vld1.16 {d16,d17}, [%0]\n"
        "vld1.16 {d18,d19}, [%1]\n"
        "vld1.16 {d20,d21}, [%2]\n"
        "vaddl.u16 q11,d16,d20\n"
        "vaddl.u16 q12,d17,d21\n"
        "vaddw.u16 q11,q11,d18\n"
        "vaddw.u16 q12,q12,d19\n"
        "vaddw.u16 q11,q11,d18\n"
        "vaddw.u16 q12,q12,d19\n"
        "vshrn.i32 d16,q11,#2\n"
        "vshrn.i32 d17,q12,#2\n"
        "vst1.16 {d16,d17}, [%3]\n"
        : : "r"(l),"r"(m),"r"(r),"r"(dst)
        : "d16","d17","d18","d19","d20","d21","d22","d23","d24","d25","memory");
#else
    for(uint32_t i=0;i<8;++i)dst[i]=tap(l[i],m[i],r[i]);
#endif
}

int m10v_spatial_blur_u16(uint16_t *a,uint16_t *b,uint32_t capacity,
    uint32_t w,uint32_t h,uint32_t passes,uint32_t d){
    if(!a||!b||((uintptr_t)a&1)||((uintptr_t)b&1)||!w||w>384||!h||h>256||
       passes>9||d<1||d>2||capacity<w*h)return -1;
    uint32_t bytes=2*w*h;uintptr_t aa=(uintptr_t)a,bb=(uintptr_t)b;
    if(aa>UINTPTR_MAX-bytes||bb>UINTPTR_MAX-bytes||(aa<bb+bytes&&bb<aa+bytes))return -1;
    for(uint32_t pass=0;pass<passes;++pass){
        for(uint32_t y=0;y<h;++y){
            const uint16_t *src=a+y*w;uint16_t *dst=b+y*w;uint32_t x=0;
            for(;x<w&&x<d;++x)dst[x]=tap(src[0],src[x],src[x+d<w?x+d:w-1]);
            for(;x+8+d<=w;x+=8)eight(src+x-d,src+x,src+x+d,dst+x);
            for(;x<w;++x)dst[x]=tap(src[x<d?0:x-d],src[x],src[x+d<w?x+d:w-1]);
        }
        for(uint32_t y=0;y<h;++y){
            const uint16_t *top=b+(y<d?0:y-d)*w,*mid=b+y*w,*bot=b+(y+d<h?y+d:h-1)*w;
            uint16_t *dst=a+y*w;uint32_t x=0;
            for(;x+8<=w;x+=8)eight(top+x,mid+x,bot+x,dst+x);
            for(;x<w;++x)dst[x]=tap(top[x],mid[x],bot[x]);
        }
    }
    return 0;
}

int m10v_spatial_grain_work_bytes(uint32_t w,uint32_t h,uint32_t address,uint32_t *required){
    if(!required||((uintptr_t)required&3)||!w||w>6144||!h||h>4096||address>UINT32_MAX-15)return -1;
    uint32_t bytes=((w+15)&~15u)*h,padding=(-address)&15;
    if(address>UINT32_MAX-bytes-padding)return -1;
    *required=bytes+padding;return 0;
}

#if defined(__arm__)
static int stock_ram(uint32_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p;}
static int stock_overlap(uint32_t a,uint32_t an,uint32_t b,uint32_t bn){return a<b+bn&&b<a+an;}
#endif
int m10v_spatial_stock_grain_execute(uint32_t context,const void *source,
    const void *destination,uint32_t strength,void *workspace,uint32_t capacity){
#if defined(__arm__)
    uint32_t src=(uint32_t)(uintptr_t)source,dst=(uint32_t)(uintptr_t)destination,work=(uint32_t)(uintptr_t)workspace;
    if(!stock_ram(context,16)||!stock_ram(src,32)||!stock_ram(dst,32)||!stock_ram(work,capacity)||!capacity||strength<1||strength>3)return -1;
    const uint16_t *s=(const uint16_t *)(src+16),*d=(const uint16_t *)(dst+16);
    uint32_t w=s[0],h=s[1],required=0;
    if(w<2||(w&1)||w>6144||!h||h>4096||d[0]!=w||d[1]!=h||
       s[2]<w||s[2]>16384||d[2]<w||d[2]>16384||
       m10v_spatial_grain_work_bytes(w,h,work,&required)||capacity<required)return -1;
    uint32_t input=((const uint32_t *)source)[1],output=((const uint32_t *)destination)[1];
    uint32_t input_bytes=(uint32_t)s[2]*h,output_bytes=(uint32_t)d[2]*h;
    if(!stock_ram(input,input_bytes)||!stock_ram(output,output_bytes)||
       stock_overlap(src,32,dst,32)||stock_overlap(src,32,context,16)||stock_overlap(dst,32,context,16)||
       stock_overlap(input,input_bytes,src,32)||stock_overlap(input,input_bytes,dst,32)||stock_overlap(input,input_bytes,context,16)||
       stock_overlap(output,output_bytes,src,32)||stock_overlap(output,output_bytes,dst,32)||stock_overlap(output,output_bytes,context,16)||
       stock_overlap(input,input_bytes,output,output_bytes)||
       stock_overlap(work,capacity,input,input_bytes)||stock_overlap(work,capacity,output,output_bytes)||
       stock_overlap(work,capacity,src,32)||stock_overlap(work,capacity,dst,32)||stock_overlap(work,capacity,context,16))return -1;
    typedef int (*stock_fn)(uint32_t,const void *,const void *,uint32_t,void *,uint32_t *);
    return ((stock_fn)0x5367ad3cu)(context,source,destination,strength,workspace,&capacity)?0:-4;
#else
    (void)context;(void)source;(void)destination;(void)strength;(void)workspace;(void)capacity;
    return -3;
#endif
}
