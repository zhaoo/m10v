/* Included by the owned settings view. Frames are straight RGBA and are
 * routed through the same native icon blitter as the film cards. */
enum { HUB_ROOT, HUB_FRAME, HUB_ERROR, HUB_BACK, HUB_COUNT };
enum { HUB_WIDTH=720, HUB_HEIGHT=480, HUB_PIXELS=HUB_WIDTH*HUB_HEIGHT,
 HUB_RECORDS=384, HUB_PATCH_BYTES=48*1024, HUB_DESCRIPTOR=HUB_PIXELS*4,
 HUB_DIRECTORY=HUB_DESCRIPTOR+8,
 HUB_SCRATCH=HUB_DIRECTORY+(M10V_HUB_BITMAP_ID-M10V_CARD_FIRST+1)*4,
 HUB_VALID=54 };
typedef struct {uint32_t offset,hash;uint16_t x,y,w,h;} hub_record;
_Static_assert(sizeof(hub_record)==16,"menu directory record ABI");
typedef int (*hub_open_fn)(uint32_t,const char *,uint32_t,uint32_t *,uint32_t *);
typedef int (*hub_close_fn)(uint32_t,uint32_t,uint32_t *);
typedef int (*hub_tell_fn)(uint32_t,uint32_t,uint32_t *,uint32_t *);
typedef int (*hub_seek_fn)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t *);
typedef int (*hub_read_fn)(uint32_t,uint32_t,void *,uint32_t,uint32_t *);
static int hub_ram(uint32_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<=0x80000000u-n;}
static int hub_code(uint32_t p){return !(p&3)&&p>=0x53000000u&&p<0x540b6000u;}
static int hub_read(uint32_t fs,const uint32_t *v,uint32_t h,uint32_t offset,void *out,uint32_t n){
 uint32_t error=0,pos=0;
 if(!((hub_seek_fn)v[11])(fs,h,offset,0,&error)||error)return 0;
 if(!((hub_tell_fn)v[13])(fs,h,&pos,&error)||error||pos!=offset)return 0;
 return ((hub_read_fn)v[9])(fs,h,out,n,&error)&&!error&&
   ((hub_tell_fn)v[13])(fs,h,&pos,&error)&&!error&&pos==offset+n;
}
static int hub_record_read(uint32_t fs,const uint32_t *v,uint32_t h,uint32_t size,
                           uint32_t index,uint32_t *frame,uint32_t *scratch){
 hub_record r;
 if(index>=HUB_RECORDS||!hub_read(fs,v,h,16+index*sizeof(r),&r,sizeof(r)))return 0;
 if(r.x+r.w>HUB_WIDTH||r.y+r.h>HUB_HEIGHT||!r.w||!r.h)return 0;
 uint32_t words=r.w*r.h,bytes=words*4;
 int full=index<13;
 if((full&&(r.x||r.y||words!=HUB_PIXELS))||(!full&&bytes>HUB_PATCH_BYTES)||
    r.offset<16+HUB_RECORDS*sizeof(r)||r.offset>size||bytes>size-r.offset)return 0;
 uint32_t *pixels=full?frame:scratch;
 if(!hub_read(fs,v,h,r.offset,pixels,bytes))return 0;
 uint32_t hash=2166136261u;
 for(uint32_t i=0;i<words;i++)hash=(hash^pixels[i])*16777619u;
 if(hash!=r.hash)return 0;
 if(!full)for(uint32_t y=0;y<r.h;y++)for(uint32_t x=0;x<r.w;x++)
  frame[(r.y+y)*HUB_WIDTH+r.x+x]=scratch[y*r.w+x];
 return 1;
}
static int hub_load(uint32_t *frame,const m10v_hub_paint *paint){
 uint32_t manager=((uint32_t (*)(void))0x535847d8u)();
 if(!hub_ram(manager,24))return 0;
 uint32_t fs=((const uint32_t *)(uintptr_t)manager)[5];
 if(!hub_ram(fs,4))return 0;
 uint32_t vt=*(const uint32_t *)(uintptr_t)fs;
 if(!hub_code(vt)||!hub_code(vt+52))return 0;
 const uint32_t *v=(const uint32_t *)(uintptr_t)vt;
 for(uint32_t i=7;i<=13;i++)if(i!=10&&!hub_code(v[i]))return 0;
 uint32_t handle=0,error=0,size=0,header[4],ok=0;
 int opened=((hub_open_fn)v[7])(fs,"C:\\M10V\\MENU.M10",1,&handle,&error);
 if(!handle)return 0;
 uint32_t *scratch=frame+HUB_SCRATCH/4;
 if(opened&&!error&&((hub_tell_fn)v[12])(fs,handle,&size,&error)&&!error&&
    size>=16+HUB_RECORDS*sizeof(hub_record)&&size<32u*1024*1024&&
    hub_read(fs,v,handle,0,header,sizeof(header))&&header[0]==0x34554e4du&&
    header[1]==4&&header[2]==HUB_RECORDS&&header[3]==size){
  ok=hub_record_read(fs,v,handle,size,paint->frame,frame,scratch);
  for(uint32_t i=0;ok&&i<7;i++)if(paint->patch[i])
   ok=hub_record_read(fs,v,handle,size,paint->patch[i],frame,scratch);
 }
 error=0;
 return ((hub_close_fn)v[8])(fs,handle,&error)&&!error&&ok;
}
int m10v_settings_view_hub_create(m10v_settings_view *v){
 if(v->count)return v->count==HUB_COUNT?0:-1;
 if(make(v,1,0,0,720,480)||make(v,10,0,0,720,480)||
    make(v,17,42,184,640,52)||make(v,17,42,263,640,52))goto fail;
 ((fn2)0x5339aa30u)(v->widgets[HUB_FRAME],1);
 ((fn2)0x5339aa44u)(v->widgets[HUB_FRAME],1);
 uint32_t root=v->widgets[HUB_ROOT],*table=(uint32_t *)(uintptr_t)*(uint32_t *)(uintptr_t)root;
 ((fn1)(uintptr_t)table[0x28/4])(root);
 ((fn1)(uintptr_t)table[0x34/4])(root);
 return 0;
fail:m10v_settings_view_destroy(v);return -1;
}
uint32_t m10v_settings_view_hub_directory(const m10v_settings_view *v){
 uint32_t heap=v->widgets[M10V_VIEW_HEAP];
 return v->count==HUB_COUNT&&v->widgets[HUB_VALID]&&heap?heap+HUB_DIRECTORY-M10V_CARD_FIRST*4u:0;
}
uint32_t m10v_settings_view_hub(m10v_settings_view *v,const m10v_hub_paint *paint){
 if(v->count!=HUB_COUNT)return 0;
 uint32_t heap=v->widgets[M10V_VIEW_HEAP];
 if(!heap){
  heap=((fn1)0x536af2a8u)(HUB_SCRATCH+HUB_PATCH_BYTES);
  if(heap&&!hub_ram(heap,HUB_SCRATCH+HUB_PATCH_BYTES)){
   ((fn1)0x536af2e4u)(heap);heap=0;
  }
  v->widgets[M10V_VIEW_HEAP]=heap;
 }
 uint32_t *pixels=(uint32_t *)(uintptr_t)heap,ok=heap&&hub_load(pixels,paint);
 if(ok){
  pixels[HUB_PIXELS]=HUB_WIDTH|(HUB_HEIGHT<<16);pixels[HUB_PIXELS+1]=heap/4;
  for(uint32_t i=HUB_DIRECTORY/4;i<HUB_SCRATCH/4;i++)pixels[i]=0;
  pixels[HUB_DIRECTORY/4+M10V_HUB_BITMAP_ID-M10V_CARD_FIRST]=heap+HUB_DESCRIPTOR;
  if(paint->focus<7){
   uint32_t y=M10V_HUB_ROW_Y+1+paint->focus*M10V_HUB_ROW_HEIGHT;
   uint32_t ink=paint->frame<8?0xff94adf0u:0xfff3b9c8u;
   for(uint32_t x=36;x<684;x++)pixels[y*HUB_WIDTH+x]=pixels[(y+M10V_HUB_ROW_HEIGHT-3)*HUB_WIDTH+x]=ink;
   for(uint32_t d=1;d<M10V_HUB_ROW_HEIGHT-3;d++)pixels[(y+d)*HUB_WIDTH+36]=pixels[(y+d)*HUB_WIDTH+683]=ink;
  }
 }
 v->widgets[HUB_VALID]=ok;
 if(ok)((fn2)0x5339a9a0u)(v->widgets[HUB_FRAME],M10V_HUB_BITMAP_ID);
 visible(v->widgets[HUB_FRAME],ok);
 visible(v->widgets[HUB_ERROR],!ok);visible(v->widgets[HUB_BACK],!ok);
 if(!ok){caption(v->widgets[HUB_ERROR],1245);caption(v->widgets[HUB_BACK],1246);}
 ((fn1)0x533ad308u)(v->widgets[HUB_ROOT]);
 return ok;
}

/* The parent TopMenu owns the detail bitmap even for a direct ADJ entry.
 * A separate descriptor keeps the large-card bitmap valid during transitions. */
#define THEME_DIRECTORY (HUB_DIRECTORY+(M10V_THEME_BITMAP_ID-M10V_CARD_FIRST+1)*4u)
uint32_t m10v_settings_view_theme_directory(uint32_t heap){
 return heap?heap+HUB_DIRECTORY-M10V_CARD_FIRST*4u:0;
}
static void line(uint32_t *row,uint32_t left,uint32_t right,uint32_t ink){
 for(uint32_t x=left;x<right;x++)row[x]=ink;
}
static void panel_scan(uint32_t *row,uint32_t y,uint32_t top,uint32_t bottom,uint32_t left,
                       uint32_t right,uint32_t ink){
 static const uint8_t indent[8]={6,4,3,2,1,1,0,0};
 uint32_t above=y-top,below=bottom-1-y;
 uint32_t distance=above<below?above:below;
 uint32_t edge=distance<8?indent[distance]:0;
 line(row,left+edge,right-edge,0xff473d39u);
 if(distance)line(row,left+edge+1,right-edge-1,ink);
}
uint32_t m10v_settings_view_theme(uint32_t widget,uint32_t rows,uint32_t selected,uint32_t effect){
 uint32_t owner=*(const volatile uint32_t *)0x55063988u;
 if(!hub_ram(owner,M10V_SETTINGS_HUB_BYTES)||!rows||rows>4)return 0;
 m10v_settings_controller *p=(m10v_settings_controller *)(uintptr_t)(owner+M10V_SETTINGS_HUB_OFFSET);
 if(selected>=rows)selected=4;
 uint32_t heap=p->theme_heap,key=rows|(selected<<4)|(effect<<8);
 if(!heap){
  heap=((fn1)0x536af2a8u)(THEME_DIRECTORY);
  if(!hub_ram(heap,THEME_DIRECTORY)){
   if(heap)((fn1)0x536af2e4u)(heap);
   return 0;
  }
  p->theme_heap=heap;
 }
 if(p->theme_key!=key){
  uint32_t *bitmap=(uint32_t *)(uintptr_t)heap;
  uint32_t end=86+rows*53;
  for(uint32_t y=0;y<480;y++){
   uint32_t *row=bitmap+y*720;
   uint32_t tone=y<300?(300-y)/64:0;
   line(row,0,720,0xff1b1716u+tone*0x00010101u);
   if(y>=19&&y<61)panel_scan(row,y,19,61,33,76,0xff2e2826u);
   if(y>=33&&y<=47){
    uint32_t dx=y>=40?y-40:40-y;
    line(row,50+dx,52+dx,0xffe1ddda);
   }
   if(y==71)line(row,33,687,0xff483b39u);
   if(y>=85&&y<end){
    uint32_t item=y>85?(y-86)/53:0;
    uint32_t active=item==selected;
    uint32_t ink=active?(effect?0xff383135u:0xff40343au):0xff2c2321u;
    if(y>86&&(y-86)%53==0)ink=0xff3c3431u;
    panel_scan(row,y,85,end,33,687,ink);
    uint32_t accent=effect?0xff94adf0u:0xfff3b9c8u;
    if(active&&y>86&&y+2<end)line(row,36,39,accent);
    if(effect>1&&y>86){
     uint32_t dy=(y-86)%53;
     if(dy>=19&&dy<34){
      static const uint8_t inset[8]={5,3,2,1,1,0,0,0};
      uint32_t d=dy<26?dy-19:33-dy;
      uint32_t edge=inset[d];
      line(row,49+edge,64-edge,active?accent:0xff8b7b77u);
      if(d)line(row,50+edge,63-edge,ink);
      if(active&&d>=4)line(row,53,60,accent);
     }
    }
   }
   if(effect>1&&y>=419&&y<464)panel_scan(row,y,419,464,558,687,0xff453434u);
  }
  bitmap[HUB_PIXELS]=720|(480u<<16);bitmap[HUB_PIXELS+1]=heap/4;
  bitmap[THEME_DIRECTORY/4-1]=heap+HUB_DESCRIPTOR;
  p->theme_key=key;
 }
 ((fn2)0x5339a9a0u)(widget,M10V_THEME_BITMAP_ID);
 return 1;
}
