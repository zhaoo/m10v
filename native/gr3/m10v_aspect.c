/* GR III 2.10 crop extension. Identity 5 is private to 6x7; old photos
 * retain their identities and geometry. No RAW pixel data is accessed. */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
#define WORD(p,o) (*(u32 *)((p)+(o)))
#define BYTE(p,o) (*(u8 *)((p)+(o)))
#define CALL(a,t) ((t)(a))

/* Recognizable immutable record, rebound after the film resource range. */
__attribute__((used)) const volatile u32 m10v_aspect_id_record[3]={0x36523741,811,785};
const u8 m10v_aspect_values[6]={0,3,1,2,4,5};
const u8 m10v_aspect_classes[5]={2,1,3,4,0};

u32 m10v_aspect_id(void) { return m10v_aspect_id_record[1]; }
u32 m10v_aspect_count(void) { return 6; }
u32 m10v_aspect_next(u32 value) {
    for(u32 i=0;i<6;i++) if(m10v_aspect_values[i]==value)
        return m10v_aspect_values[i==5?0:i+1];
    return 0;
}
u32 m10v_aspect_current(void) {
    u32 root=CALL(0x53525d5c,u32 (*)(void))();
    return root && WORD(root,0) ? CALL(0x5354a778,u32 (*)(u32))(WORD(root,0)) : 0;
}
u32 m10v_aspect_mask_active(void) {
    u32 ratio=m10v_aspect_current();
    if(ratio!=4 && ratio!=5) return 0;
    u32 root=CALL(0x53525d5c,u32 (*)(void))();
    if(!root || !WORD(root,0) || CALL(0x53549958,u32 (*)(u32))(WORD(root,0))==1) return 0;
    u32 manager=CALL(0x53654150,u32 (*)(void))();
    return manager && !CALL(0x53654220,u32 (*)(u32,u32))(manager,0x4a);
}

/* Exact integer-mm float values only; no VFP state or writable global state. */
u32 m10v_aspect_mm(u32 bits) {
    if(bits<0x3f800000 || bits>0x40649249) return 0;
    u32 shift=(bits>>23)==127?10:9;
    u32 q=((bits&0x7fffff)|0x800000)+(1u<<(shift-1));
    q>>=shift;
    u32 mm=(q*28+4096)/8192;
    if(mm<28 || mm>100) return 0;
    u32 mantissa=((mm<<23)+14)/28;
    u32 expected=0x3f000000+mantissa;
    if(mm>=56) expected=0x3f800000+(((mm<<22)+14)/28);
    return bits==expected?mm:0;
}
static u32 stock_q13(u32 q) {
    return q==0x2000 || q==0x2800 || q==0x38f6 || q==0x3925;
}

void m10v_aspect_resolution(u32 mag,u32 quality,u16 *width,u16 *height) {
    static const u16 sizes[4][2]={{4672,4000},{3728,3200},{2608,2240},{1488,1280}};
    if(quality>3 || !width || !height) return;
    u32 index=quality;
    if(mag==0x3fa00000 && index<1) index=1;
    else if((mag==0x3fe3d70a || mag==0x3fe49249) && index<2) index=2;
    else if(mag!=0x3f800000 && mag!=0x3fa00000 && mag!=0x3fe3d70a && mag!=0x3fe49249) {
        u32 mm=m10v_aspect_mm(mag);
        if(!mm) return;
        u32 w=(4672*28/mm/16)*16,h=(4000*28/mm/16)*16;
        *width=w<sizes[index][0]?w:sizes[index][0];
        *height=h<sizes[index][1]?h:sizes[index][1];
        return;
    }
    *width=sizes[index][0]; *height=sizes[index][1];
}
/* Native filter radius follows the diagonal of the output, normalized by
 * the uncropped 6000x4000 frame, as in the existing wide crop adapter. */
u32 m10v_aspect_filter(u32 mag,u32 crop_enabled) {
    if(crop_enabled) return 0x3f5a583c;
    if(mag==0x3fa00000) return 0x3f2e6ac0;
    if(mag==0x3fe3d70a || mag==0x3fe49249) return 0x3ef418fc;
    return 0x3f5a583c;
}
u32 m10v_aspect_live_width(u32 a,u32 b,u32 c,u32 d,u32 ratio) {
    u32 width=CALL(0x540b8678,u32 (*)(u32,u32,u32,u32,u32))(a,b,c,d,0);
    return ratio==5 && !m10v_aspect_mask_active()?2*((width*7+9)/18):width;
}
u32 m10v_aspect_live_height(u32 a,u32 b,u32 c,u32 d,u32 ratio) {
    u32 height=CALL(0x540b8680,u32 (*)(u32,u32,u32,u32,u32))(a,b,c,d,0);
    return ratio==4 && !m10v_aspect_mask_active()?2*((height*69+125)/250):height;
}
u32 m10v_aspect_write_active(u32 context,u32 unused,u32 mag) {
    (void)unused;
    /* Quantized JPEG dimensions mapped into the native 45x30 Q16 sensor
     * coordinates: width,height,left,top. Crop origins are centered in the
     * complete 6000x4000 sensor, including the native crop magnification.
     */
    static const u32 rects[3][4]={
        {2296381,1966080,326369,0},
        {1832387,1572864,558367,196608},
        {1281884,1101005,833618,432538}
    };
    if(!stock_q13(mag) && mag>=8192 && mag<=29257) {
        CALL(0x53665c2c,void (*)(u32))(context);
        /* Use the native calculator's rectangle, never a second crop table. */
        u32 w=WORD(context,0x24)*7/9,h=WORD(context,0x28);
        WORD(context,0x64)=w; WORD(context,0x68)=h;
        WORD(context,0x6c)=(2949120-w+1)/2;
        WORD(context,0x70)=WORD(context,0x30);
        return CALL(0x536ae870,u32 (*)(u32))(context+0x24bc);
    }
    u32 index=CALL(0x540b62f8,u32 (*)(u32))(mag);
    if(index>2) index=0;
    CALL(0x53665c2c,void (*)(u32))(context);
    for(u32 i=0;i<4;i++) WORD(context,0x64+4*i)=rects[index][i];
    /* Notification can return zero after a valid write. Publish only after
     * the final geometry is stored and retain its native return convention.
     */
    return CALL(0x536ae870,u32 (*)(u32))(context+0x24bc);
}

u32 m10v_aspect_private_active(u32 context,u32 ratio,u32 mag) {
    if(!stock_q13(mag) && mag>=8192 && mag<=29257 && (ratio==2 || ratio==4)) {
        CALL(0x53665c2c,void (*)(u32))(context);
        u32 w=WORD(context,0x24),h=WORD(context,0x28);
        if(ratio==2) w=w*8/9; else h=h*69/250;
        WORD(context,0x64)=w;WORD(context,0x68)=h;
        WORD(context,0x6c)=(2949120-w+1)/2;
        WORD(context,0x70)=(1966080-h+1)/2;
        return CALL(0x536ae870,u32 (*)(u32))(context+0x24bc);
    }
    return CALL(0x540b6240,u32 (*)(u32,u32,u32))(context,ratio,mag);
}

/* Masked live view keeps the native 3:2 focal crop underneath the mask.
 * Both AF and common refresh must publish the SAME source rectangle. Native
 * +24 is recomputed for crop/AF; fixed still-JPEG rectangles cannot replace it.
 * Outside this view (magnified focus/movie), retain the existing adapters. */
u32 m10v_aspect_live_region(u32 context,u32 mode,u32 ratio,u32 mag) {
    if(m10v_aspect_mask_active())
        return CALL(0x53666770,u32 (*)(u32,u32))(context,mag==0x2000?0:1);
    if(ratio==5) return m10v_aspect_write_active(context,mode,mag);
    if(!stock_q13(mag) && mag>=8192 && mag<=29257) {
        CALL(0x53665c2c,void (*)(u32))(context);
        u32 w=WORD(context,0x24),h=WORD(context,0x28)*69/250;
        WORD(context,0x64)=w; WORD(context,0x68)=h;
        WORD(context,0x6c)=WORD(context,0x2c);
        WORD(context,0x70)=(1966080-h+1)/2;
        return CALL(0x536ae870,u32 (*)(u32))(context+0x24bc);
    }
    return CALL(0x540b6240,u32 (*)(u32,u32,u32))(context,4,mag);
}

u32 m10v_aspect_live_icon(u32 owner,u32 ratio);
static void aspect_label(u32 view,u32 surface,u32 ratio) {
    if((ratio!=4 && ratio!=5) || !view || !surface || !BYTE(view,0x9e) || !m10v_aspect_mask_active()) return;
    u32 *canvas=(u32 *)(view+0x30),*clip=(u32 *)(view+0x64);
    if(canvas[0] || canvas[1] || !((canvas[2]==720&&canvas[3]==480)||(canvas[2]==360&&canvas[3]==240))) return;
    u32 id=m10v_aspect_live_icon(0,ratio);
    if(!id) return;
    u32 manager=CALL(0x5320804c,u32 (*)(void))();
    if(!manager) return;
    u32 graphics=CALL(0x53208298,u32 (*)(u32))(manager);
    if(!graphics) return;
    /* Native icon draw packet: surface, destination, clip, ID, rotation.
     * Keep the top status row clear; use the native synchronous RGBA blitter. */
    u32 x=canvas[2]-68,y=48;
    u32 left=clip[0]>x?clip[0]:x,top=clip[1]>y?clip[1]:y;
    u32 right=clip[0]+clip[2],bottom=clip[1]+clip[3];
    if(right>x+60) right=x+60;
    if(bottom>y+40) bottom=y+40;
    if(left>=right || top>=bottom) return;
    u32 packet[11]={surface,x,y,60,40,left,top,right-left,bottom-top,id,0};
    CALL(0x5320a7a8,void (*)(u32,u32 *))(graphics,packet);
}
void m10v_aspect_draw(u32 view,u32 surface) {
    u32 ratio=m10v_aspect_current();
    if(ratio!=4 && ratio!=5) {
        CALL(0x540b8000,void (*)(u32,u32))(view,surface);
        aspect_label(view,surface,ratio);
        return;
    }
    if(!view || !surface || !BYTE(view,0x9e)) return;
    u32 *canvas=(u32 *)(view+0x30),*clip=(u32 *)(view+0x64);
    if(canvas[0] || canvas[1] || !((canvas[2]==720&&canvas[3]==480)||(canvas[2]==360&&canvas[3]==240))) return;
    u32 graphics=CALL(0x5320804c,u32 (*)(void))();
    if(!graphics) return;
    graphics=CALL(0x532081ec,u32 (*)(u32))(graphics);
    if(!graphics) return;
    u32 scale=canvas[2]==720?2:1, mask=(ratio==5?40:54)*scale;
    typedef void (*Draw)(u32,u32,u32 *,u32 *,u32,u32,u32,u32,u32);
    Draw draw=CALL(0x540b88b4,Draw);
    /* Keep the aspect mask; the native view already owns its edge frame. */
    if(ratio==5){
        draw(graphics,surface,canvas,clip,0,0,mask,canvas[3],16);
        draw(graphics,surface,canvas,clip,canvas[2]-mask,0,mask,canvas[3],16);
    }else{
        draw(graphics,surface,canvas,clip,0,0,canvas[2],mask,16);
        draw(graphics,surface,canvas,clip,0,canvas[3]-mask,canvas[2],mask,16);
    }
    aspect_label(view,surface,ratio);
}

/* AF retains the native safety inset and follows all three crop magnifications. */
u32 m10v_aspect_af_bounds(u32 ratio,u32 crop,u32 *out) {
    if(out && (ratio==1 || ratio==4 || ratio==5)) {
        u32 owner=CALL(0x5320ad88,u32 (*)(void))();
        owner=owner?CALL(0x5320b31c,u32 (*)(u32))(owner):0;
        u32 props=owner?WORD(owner,4):0;
        u32 bits=props?WORD(props,0x4c4):0;
        u32 mm=m10v_aspect_mm(bits);
        if(mm && mm!=28 && mm!=35 && mm!=50) {
            u32 shift=(bits>>23)==127?10:9;
            u32 q=(((bits&0x7fffff)|0x800000)+(1u<<(shift-1)))>>shift;
            /* Native Q13 centered crop projected into the aspect view and
             * intersected with the existing AF safety extent. Device AF
             * behavior requires camera validation. Existing size helper caps
             * mode0 at560x360 and modes14/15 at336x216. */
            u32 w=((ratio==1?640:ratio==5?560:720)*8192+q/2)/q;
            u32 h=((ratio==4?264:480)*8192+q/2)/q;
            u32 left=(720-w+1)/2,top=(480-h+1)/2;
            u32 inset=ratio==5?120:80;
            if(left<inset) left=inset;
            if(top<60) top=60;
            out[0]=left;out[1]=top;out[2]=720-left;out[3]=480-top;
            return 1;
        }
    }
    if(ratio!=5) return CALL(0x540b6458,u32 (*)(u32,u32,u32 *))(ratio,crop,out);
    static const u16 rects[3][4]={{120,60,600,420},{136,60,584,420},{203,106,517,374}};
    if(!out) return 0;
    if(crop>2) crop=0;
    for(u32 i=0;i<4;i++) out[i]=rects[crop][i];
    return 1;
}

/* Bound only by the verified integrated composer; zero means no private art. */
u32 m10v_aspect_live_icon(u32 owner,u32 ratio);
__attribute__((used)) const volatile u32 m10v_aspect_icon_record[4]={0x49413741,0,0,(u32)m10v_aspect_live_icon};
u32 m10v_aspect_live_icon(u32 owner,u32 ratio) {
    (void)owner;
    switch(ratio) {
    case 0: return 257;
    case 3: return 256;
    case 1: return 339;
    case 4: return m10v_aspect_icon_record[1];
    case 5: return m10v_aspect_icon_record[2];
    default: return 0;
    }
}
