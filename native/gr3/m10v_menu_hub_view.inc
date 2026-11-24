/* Included by the owned settings view. Frames are straight RGBA and are
 * routed through the same native icon blitter as the film cards. */
enum { HUB_ROOT, HUB_FRAME, HUB_ERROR, HUB_BACK, HUB_NAME, HUB_DIAG, HUB_COUNT };
enum { HUB_WIDTH=720, HUB_HEIGHT=480, HUB_PIXELS=HUB_WIDTH*HUB_HEIGHT,
 HUB_RECORDS_R5=384, HUB_CANISTER_FIRST=512, HUB_RECORDS_R8=HUB_CANISTER_FIRST+M10V_DIRECTORY_COUNT+2,
 HUB_CANISTER_W=144,HUB_CANISTER_H=197,HUB_CANISTER_PALETTE=256,
 HUB_PATCH_BYTES=48*1024, HUB_DESCRIPTOR=HUB_PIXELS*4,
 HUB_DIRECTORY=HUB_DESCRIPTOR+8,
 HUB_SCRATCH=HUB_DIRECTORY+(M10V_HUB_BITMAP_ID-M10V_CARD_FIRST+1)*4,
 HUB_VALID=54 };
typedef struct {uint32_t offset,hash;uint16_t x,y,w,h;} hub_record;
_Static_assert(sizeof(hub_record)==16,"menu directory record ABI");
_Static_assert(HUB_CANISTER_PALETTE*4+HUB_CANISTER_W*HUB_CANISTER_H<=HUB_PATCH_BYTES,
               "canister uses the existing patch buffer");
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
                           uint32_t records,uint32_t index,int full,uint32_t *frame,uint32_t *scratch){
 hub_record r;
 if(index>=records||!hub_read(fs,v,h,16+index*sizeof(r),&r,sizeof(r)))return 0;
 if(r.x+r.w>HUB_WIDTH||r.y+r.h>HUB_HEIGHT||!r.w||!r.h)return 0;
 uint32_t indexed=index>=HUB_CANISTER_FIRST,words=r.w*r.h;
 if(indexed&&(full||r.x||r.y||r.w!=HUB_CANISTER_W||r.h!=HUB_CANISTER_H))return 0;
 uint32_t bytes=indexed?HUB_CANISTER_PALETTE*4+words:words*4;
 if((full&&(r.x||r.y||words!=HUB_PIXELS))||(!full&&bytes>HUB_PATCH_BYTES)||
    r.offset<16+records*sizeof(r)||r.offset>size||bytes>size-r.offset)return 0;
 uint32_t *pixels=full?frame:scratch;
 if(!hub_read(fs,v,h,r.offset,pixels,bytes))return 0;
 uint32_t hash=2166136261u;
 for(uint32_t i=0;i<bytes/4;i++)hash=(hash^pixels[i])*16777619u;
 if(hash!=r.hash)return 0;
 if(!full&&!indexed)for(uint32_t y=0;y<r.h;y++)for(uint32_t x=0;x<r.w;x++)
  frame[(r.y+y)*HUB_WIDTH+r.x+x]=scratch[y*r.w+x];
 return 1;
}
static int hub_roll_art(uint32_t fs,const uint32_t *v,uint32_t h,uint32_t size,
                        const m10v_hub_paint *paint,uint32_t *frame,uint32_t *scratch){
 uint32_t film=paint->film,index=0;
 while(index<M10V_DIRECTORY_COUNT&&m10v_directory[index].id!=film)index++;
 if(index==M10V_DIRECTORY_COUNT&&film!=0x10016u){index++;film=0;}
 if(!hub_record_read(fs,v,h,size,HUB_RECORDS_R8,HUB_CANISTER_FIRST+index,0,frame,scratch)||
    scratch[0]!=film)return 0;
 const uint8_t *tile=(const uint8_t *)(scratch+HUB_CANISTER_PALETTE);
 uint32_t display=paint->frame==M10V_HUB_ROLL_FRAME;
 uint32_t left=display?163:86,top=display?123:138;
 uint32_t width=display?HUB_CANISTER_W:109,height=display?HUB_CANISTER_H:150;
 uint32_t step_x=HUB_CANISTER_W-width,step_y=HUB_CANISTER_H-height;
 /* Advance the source by either one or two pixels per destination pixel. */
 uint32_t source_y=0,remainder_y=0;
 for(uint32_t y=0;y<height;y++){
  const uint8_t *source=tile+source_y*HUB_CANISTER_W;
  uint32_t *row=frame+(top+y)*HUB_WIDTH+left;
  uint32_t source_x=0,remainder_x=0;
  for(uint32_t x=0;x<width;x++){
   uint32_t pixel=source[source_x++];
   if(pixel)row[x]=scratch[pixel];
   remainder_x+=step_x;
   if(remainder_x>=width){remainder_x-=width;source_x++;}
  }
  source_y++;
  remainder_y+=step_y;
  if(remainder_y>=height){remainder_y-=height;source_y++;}
 }
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
    size>=16+HUB_RECORDS_R5*sizeof(hub_record)&&size<32u*1024*1024&&
    hub_read(fs,v,handle,0,header,sizeof(header))&&header[3]==size){
  uint32_t version=header[1],records=header[2];
  int legacy=header[0]==0x35554e4du&&version==5&&records==HUB_RECORDS_R5;
  int extended=header[0]==0x38554e4du&&version==8&&records==HUB_RECORDS_R8;
  if((legacy||extended)&&size>=16+records*sizeof(hub_record)){
   ok=hub_record_read(fs,v,handle,size,records,paint->frame,1,frame,scratch);
   for(uint32_t i=0;ok&&i<7;i++)if(paint->patch[i])
    ok=paint->patch[i]<HUB_CANISTER_FIRST&&
       hub_record_read(fs,v,handle,size,records,paint->patch[i],0,frame,scratch);
   if(ok&&extended&&paint->frame>=4&&paint->frame<8&&paint->film_index)
    ok=hub_record_read(fs,v,handle,size,records,paint->film_index,0,frame,scratch);
   if(ok&&extended&&paint->frame>=M10V_HUB_ROLL_FRAME&&paint->frame<=M10V_HUB_ROLL_ACTIVE)
    ok=hub_roll_art(fs,v,handle,size,paint,frame,scratch);
   if(ok)ok=version;
  }
 }
 error=0;
 return ((hub_close_fn)v[8])(fs,handle,&error)&&!error?ok:0;
}
int m10v_settings_view_hub_create(m10v_settings_view *v){
 if(v->count)return v->count==HUB_COUNT?0:-1;
 if(make(v,1,0,0,720,480)||make(v,10,0,0,720,480)||
    make(v,17,42,208,640,52)||make(v,17,42,263,640,52)||make(v,0,279,228,350,38)||
    make(v,0,48,368,510,40))goto fail;
 ((fn2)0x5339658cu)(v->widgets[HUB_NAME],31);
 ((fn2)0x5339658cu)(v->widgets[HUB_DIAG],31);
 ((fn2)0x5339aa30u)(v->widgets[HUB_FRAME],1);
 ((fn2)0x5339aa44u)(v->widgets[HUB_FRAME],1);
 uint32_t root=v->widgets[HUB_ROOT],*table=(uint32_t *)(uintptr_t)*(uint32_t *)(uintptr_t)root;
 ((fn1)(uintptr_t)table[0x28/4])(root);
 ((fn1)(uintptr_t)table[0x34/4])(root);
 return 0;
fail:m10v_settings_view_destroy(v);return -1;
}
uint32_t m10v_settings_view_hub_artwork(const m10v_settings_view *v){
 return v->count==HUB_COUNT?v->widgets[HUB_VALID]:0;
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
 uint32_t *pixels=(uint32_t *)(uintptr_t)heap,version=heap?hub_load(pixels,paint):0;
 uint32_t ok=version!=0;
 if(ok){
  pixels[HUB_PIXELS]=HUB_WIDTH|(HUB_HEIGHT<<16);pixels[HUB_PIXELS+1]=heap/4;
  for(uint32_t i=HUB_DIRECTORY/4;i<HUB_SCRATCH/4;i++)pixels[i]=0;
  pixels[HUB_DIRECTORY/4+M10V_HUB_BITMAP_ID-M10V_CARD_FIRST]=heap+HUB_DESCRIPTOR;
  uint32_t height=M10V_HUB_ROW_HEIGHT,rows=7;
  if(version==8&&paint->frame>=4&&paint->frame<8){height=M10V_HUB_EFFECT_R6_HEIGHT;rows=8;}
  if(paint->focus<rows){
   uint32_t top=M10V_HUB_ROW_Y+paint->focus*height;
   for(uint32_t y=top;y<top+height-1;y++){
    uint32_t *row=pixels+y*HUB_WIDTH;
    for(uint32_t x=34;x<686;x++)if(row[x]==0xff1d1a17u)row[x]=0xff2c2a26u;
    if(y>=top+6&&y<top+height-6)row[34]=row[35]=row[36]=0xff7ac4eau;
   }
   if((paint->frame==13&&paint->patch[0]!=390)||paint->frame==14){
    for(int y=-5;y<=5;y++)for(int x=-5;x<=5;x++)
     if(x*x+y*y<=25)pixels[(top+26+y)*HUB_WIDTH+660+x]=0xff7ac4eau;
   }
  }
  if(version==8&&paint->frame>=M10V_HUB_DECK_EXTENDED){
   uint32_t x=paint->marker_x,y=paint->marker_y;
   if(x&&x<HUB_WIDTH-2&&y<HUB_HEIGHT-16)
    for(uint32_t i=0;i<16;i++){
     pixels[(y+i)*HUB_WIDTH+x]=0xff7ac4eau;
     pixels[(y+i)*HUB_WIDTH+x+1]=0xff7ac4eau;
    }
  }
 }
 v->widgets[HUB_VALID]=version;
 if(ok)((fn2)0x5339a9a0u)(v->widgets[HUB_FRAME],M10V_HUB_BITMAP_ID);
 visible(v->widgets[HUB_FRAME],ok);
 uint32_t display=paint->frame==M10V_HUB_ROLL_FRAME;
 uint32_t id=paint->film;
 const char *catalog_name=ok&&id?m10v_directory_name(id):0;
 uint32_t show_name=ok&&id&&(!display||(!catalog_name&&id!=0x10016u));
 visible(v->widgets[HUB_NAME],show_name);
 if(show_name){
  char custom[24];
  const char *name=catalog_name;
  if(id==0x10016u)name="原厂负片";
  else if(M10V_CUSTOM(id)){
   if(paint->film_index>=M10V_DIRECTORY_COUNT&&
      m10v_sd_camera_catalog_name(paint->film_index,id,custom,sizeof(custom)))name=custom;
   else{
    m10v_library_state state;
    if(m10v_camera_library_preview(&state))
     for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)if(state.slots[i].film==id&&
        m10v_sd_camera_custom_name(&state,i,custom,sizeof(custom))){name=custom;break;}
   }
   if(!name)name="自定义 LUT";
  }else if(!name)name=m10v_library_name(id);
  uint32_t name_top=paint->frame==M10V_HUB_ROLL_NEW?228:244;
  const uint32_t rect[4]={display?310:279,display?208:name_top,display?332:350,38};
  ((void (*)(uint32_t,const uint32_t *))0x533ab548u)(v->widgets[HUB_NAME],rect);
  ((fn2)0x53390ef8u)(v->widgets[HUB_NAME],ptr(name?name:"未知胶卷"));
 }
 visible(v->widgets[HUB_ERROR],!ok||paint->save_error==1);
 visible(v->widgets[HUB_BACK],!ok);
 uint32_t code=paint->save_error;
 visible(v->widgets[HUB_DIAG],ok&&code>=100);
 if(!ok){caption(v->widgets[HUB_ERROR],1245);caption(v->widgets[HUB_BACK],1246);}
 else if(code==1)caption(v->widgets[HUB_ERROR],M10V_VIEW_FAILED);
 else if(code>=M10V_HUB_ASPECT_LOCKED&&code<=M10V_HUB_ASPECT_LOCKED+6u){
  static const char *const labels[]={
   "本卷画幅已锁定：3:2","本卷画幅已锁定：4:3","本卷画幅已锁定：16:9",
   "本卷画幅已锁定：1:1","本卷画幅已锁定：XPan","本卷画幅已锁定：6x7",
   "本卷画幅已锁定：Half"
  };
  const uint32_t rect[4]={260,25,426,35};
  ((void (*)(uint32_t,const uint32_t *))0x533ab548u)(v->widgets[HUB_DIAG],rect);
  ((fn2)0x53390ef8u)(v->widgets[HUB_DIAG],ptr(labels[code-M10V_HUB_ASPECT_LOCKED]));
 }
 else if(code>=100){
  const uint32_t rect[4]={48,368,510,40};
  ((void (*)(uint32_t,const uint32_t *))0x533ab548u)(v->widgets[HUB_DIAG],rect);
  char text[10]={'R','O','L','L',' ', 'E', '0', '0', '0', 0};
  if(code>=200&&paint->frame==13){text[0]='L';text[1]='I';text[2]='V';text[3]='E';code-=200;}
  else code-=100;
  text[6]+=(char)(code/100);text[7]+=(char)((code/10)%10);text[8]+=(char)(code%10);
  ((fn2)0x53390ef8u)(v->widgets[HUB_DIAG],ptr(text));
 }
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
 uint32_t imprint=effect==M10V_HUB_IMPRINT_THEME;
 if(!hub_ram(owner,M10V_SETTINGS_HUB_BYTES)||rows>(imprint?8u:4u))return 0;
 m10v_settings_controller *p=(m10v_settings_controller *)(uintptr_t)(owner+M10V_SETTINGS_HUB_OFFSET);
 if(selected>=rows)selected=8;
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
  uint32_t height=imprint?M10V_HUB_IMPRINT_HEIGHT:M10V_HUB_ROW_HEIGHT;
  uint32_t end=M10V_HUB_ROW_Y+rows*height,arrow_y=rows?40:27;
  for(uint32_t y=0;y<480;y++){
   uint32_t *row=bitmap+y*720;
   line(row,0,720,0xff1d1a17u);
   if(y>=arrow_y-7&&y<=arrow_y+7){
    uint32_t dx=y>=arrow_y?y-arrow_y:arrow_y-y;
    uint32_t x=rows?50:37;
    line(row,x+dx,x+dx+2,0xffe8eeefu);
   }
   if(rows&&y==71)line(row,33,687,0xff3e3a34u);
   if(y>=M10V_HUB_ROW_Y&&y<end){
    uint32_t item=(y-M10V_HUB_ROW_Y)/height,dy=y-M10V_HUB_ROW_Y-item*height;
    uint32_t active=item==selected;
    uint32_t ink=dy==height-1?0xff3e3a34u:active?0xff2c2a26u:0xff1d1a17u;
    uint32_t accent=0xff7ac4eau;
    line(row,34,686,ink);
    if(active&&dy>=6&&dy<height-6)line(row,34,37,accent);
    if(effect==2||imprint){
     uint32_t center=height/2;
     if(dy>=center-7&&dy<center+8){
      static const uint8_t inset[8]={5,3,2,1,1,0,0,0};
      uint32_t d=dy<center?dy-(center-7):center+7-dy;
      uint32_t edge=inset[d];
      line(row,49+edge,64-edge,active?accent:0xff8b7b77u);
      if(d)line(row,50+edge,63-edge,ink);
      if(active&&d>=4)line(row,53,60,accent);
     }
    }
    if(effect==3&&active&&dy>=20&&dy<=32){
     uint32_t dx=dy>=26?dy-26:26-dy;
     line(row,485+dx,487+dx,accent);
     line(row,674-dx,676-dx,accent);
    }
   }
   if(effect>=2&&y>=419&&y<464)
    panel_scan(row,y,419,464,effect==3?578:558,687,effect==3?0xff7ac4eau:0xff453b29u);
  }
  bitmap[HUB_PIXELS]=720|(480u<<16);bitmap[HUB_PIXELS+1]=heap/4;
  bitmap[THEME_DIRECTORY/4-1]=heap+HUB_DESCRIPTOR;
  p->theme_key=key;
 }
 ((fn2)0x5339a9a0u)(widget,M10V_THEME_BITMAP_ID);
 return 1;
}
