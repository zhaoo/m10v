/* Native ADJ host. Draft selection is isolated from the formal setter; only
 * Start/Exit enters native LiveView. Keep the validated r3 lifecycle. */
extern uint32_t m10v_ab_adj_refresh_original(uint32_t);
extern uint32_t m10v_ab_adj_exit_original(uint32_t);
extern uint32_t m10v_ab_adj_destroy_original(uint32_t);
extern uint32_t m10v_ab_adj_changed_original(uint32_t);
#define AB_HOST_PAGE 7u
static m10v_native_ab_host *ab_host(m10v_settings_controller *p){return p&&p->page==AB_HOST_PAGE?&p->host:0;}
static int ab_host_owned(m10v_native_ab_host *h,uint32_t c){return h&&h->mode==2&&h->controller==c;}
static uint32_t ab_host_word(uint32_t c,uint32_t off){return *(const uint32_t *)(uintptr_t)(c+off);}
static void ab_host_caption(uint32_t w,uint32_t id){((fn3)0x53396f80u)(w,id,0);}
/* Native list capacity is fixed by its constructor. Page within that vector;
 * six 60px rows fit y60..420, as in the pinned GRKit/native layout. */
static uint32_t ab_host_page_size(m10v_native_ab_host *h){
 uint32_t list=ab_host_word(h->controller,0x1f0),first=ab_host_word(list,0xf4),end=ab_host_word(list,0xf8);
 return end>=first&&end-first>=24?6:3;
}
static uint32_t ab_host_start_row(uint32_t focus,uint32_t size){uint32_t start=0;for(uint32_t i=0;i<8;i++){if(start+size>focus)break;start+=size;}return start;}
static uint32_t ab_host_film(m10v_native_ab_host *h,uint32_t choice){uint32_t slot=m10v_ab_slot(choice);return slot<M10V_SLOT_COUNT?h->films[slot]:0;}
static uint32_t ab_host_icon(m10v_native_ab_host *h,uint32_t choice){
 uint32_t id=ab_host_film(h,choice);
 if(M10V_FOUR_LOOKS(id))return M10V_FOUR_LOOKS_ICON(id);
 if(M10V_EXTRA_FILM(id))return M10V_EXTRA_FILM_ICON(id);
 if(M10V_C41(id))return M10V_C41_ICON_FIRST+id-312;
 if(M10V_ANIME_E6(id))return M10V_ANIME_E6_ICON_FIRST+id-M10V_ANIME_FIRST;
 if(M10V_D76(id))return 775+id-M10V_D76_FIRST;
 if(m10v_ab_slot(choice)<M10V_SLOT_COUNT)return id==M10V_5213_ID?774:M10V_CUSTOM(id)?754:M10V_STYLE(id)?762+id-M10V_STYLE_FIRST:id==M10V_PIXEL_ID?761:id==M10V_CHAR_ID?755:id>=1&&id<=78?670+id:0;
 return ((fn2)0x532a9988u)(0,m10v_ab_tone(choice));
}
static void ab_host_name(m10v_native_ab_host *h,uint32_t choice,char *out,uint32_t prefix){
 const char *name=m10v_ab_stock_name(choice);char custom[24];m10v_library_state fresh;
 uint32_t slot=m10v_ab_slot(choice),id=ab_host_film(h,choice),n=0;
 if(slot<M10V_SLOT_COUNT){
  name=m10v_library_name(id);
  if(M10V_CUSTOM(id)&&m10v_camera_library_load(&fresh)>=0&&fresh.slots[slot].film==id&&
     m10v_sd_camera_custom_name(&fresh,slot,custom,sizeof(custom)))name=custom;
 }
 if(prefix){out[n++]=(char)prefix;out[n++]=':';out[n++]=' ';}
 if(!name)name="Film";
 for(uint32_t i=0;name[i]&&n<76;i++)out[n++]=name[i];out[n]=0;
}
static void ab_host_render(m10v_settings_controller *p){
 m10v_native_ab_host *h=&p->host;uint32_t c=h->controller,list=ab_host_word(c,0x1f0);
 uint32_t available=m10v_camera_library_shooting_count();if(h->focus>=available)h->focus=0;
 uint32_t size=ab_host_page_size(h),start=ab_host_start_row(h->focus,size);
 uint32_t rows=available-start;if(rows>size)rows=size;
 h->rebuilding=1;((fn2)0x53394e8cu)(list,rows);
 for(uint32_t i=0;i<rows;i++){
  uint32_t row=((fn2)0x53394758u)(list,i),choice=start+i;
  ((fn2)0x533a1734u)(row,ab_host_icon(h,choice));((fn2)0x533a18e0u)(row,0);
  if(M10V_CUSTOM(ab_host_film(h,choice))){
   char text[80];ab_host_name(h,choice,text,0);
   ((fn2)0x533a1808u)(row,0);((fn2)0x533a18e0u)(row,(uint32_t)(uintptr_t)text);
  }else ((fn2)0x533a1808u)(row,m10v_ab_caption(choice,ab_host_film(h,choice)));
  ((fn2)0x533a19b4u)(row,h->level==2&&choice==h->a);
 }
 uint32_t width=((fn1)0x533948c4u)(list),rect[4]={720-width,420-60*rows,width,60*rows};
 uint32_t vt=*(const uint32_t *)(uintptr_t)list;
 ((fn2)(uintptr_t)*(const uint32_t *)(uintptr_t)(vt+0x18))(list,(uint32_t)(uintptr_t)rect);
 ((fn2)0x53395430u)(list,h->focus-start);
 ab_host_caption(ab_host_word(c,0x160),h->level==1?992:993);
 ab_host_caption(ab_host_word(c,0x164),h->error?h->error:1019);
 ((fn2)0x533ad3c0u)(ab_host_word(c,0x168),0);((fn2)0x533ad3c0u)(ab_host_word(c,0x1ac),0);
 ((fn1)0x533ad308u)(ab_host_word(c,0x15c));h->rebuilding=0;
 M10V_LOG(97,20,c,list,h->origin);
}
static int ab_host_valid(uint32_t c){
 return ab_ram(c,0x274)&&ab_host_word(c,0)==0x53b394e0u&&
  *(uint8_t *)(uintptr_t)(c+0x270)!=1&&ab_ram(ab_host_word(c,0x1f0),0x10c)&&ab_ram(ab_host_word(c,0x15c),0xf8);
}
static void ab_host_cancel(m10v_settings_controller *p,uint32_t c){
 (void)c;
 m10v_native_ab_host *h=&p->host;h->mode=0;h->controller=0;h->rebuilding=0;
 p->pending_source=0;p->ab.down=0;M10V_LOG(97,22,c,h->origin,0);
}
static void ab_host_attach(m10v_settings_controller *p,uint32_t c){
 if(!ab_host_valid(c)){ab_host_cancel(p,c);return;}
 m10v_native_ab_host *h=&p->host;
 uint32_t list=ab_host_word(c,0x1f0);
 h->controller=c;h->rebuilding=1;
 ((fn3)0x533947f0u)(list,(uint32_t)(uintptr_t)&h->position,(uint32_t)(uintptr_t)&h->offset);
 h->mode=2;p->pending_source=0;ab_host_render(p);
}
static void ab_host_restore(m10v_settings_controller *p,uint32_t c){
 m10v_native_ab_host *h=ab_host(p);if(!ab_host_owned(h,c))return;
 M10V_EXIT_LOG(232,c,h->mode,h->origin,ab_host_word(c,0x1f0));
 h->mode=0;h->rebuilding=1;p->pending_source=0;
 M10V_EXIT_LOG(233,c,0,0,0);
 m10v_ab_adj_refresh_original(c);
 M10V_EXIT_LOG(234,c,0,0,0);
 M10V_EXIT_LOG(235,c,h->position,h->offset,ab_host_word(c,0x1f0));
 ((fn3)0x53395224u)(ab_host_word(c,0x1f0),h->position,h->offset);
 M10V_EXIT_LOG(236,c,0,0,0);
 h->controller=0;h->rebuilding=0;M10V_LOG(97,21,c,h->origin,0);
}
#if M10V_AB_NATIVE_HOST
static uint32_t ab_host_wrap(uint32_t value,uint32_t count){while(value>=count)value-=count;return value;}
static void ab_host_open(m10v_settings_controller *p,uint32_t c,uint32_t origin){
 p->page=AB_HOST_PAGE;m10v_native_ab_host *h=&p->host;
 for(uint32_t i=0;i<sizeof(*h);i++)((uint8_t *)h)[i]=0;
 h->mode=1;h->origin=origin;h->source=c;p->pending_source=origin==0x02000000u?0:c;
 if(!p->ab.enabled)ab_pair(&p->ab);h->a=p->ab.a;h->b=p->ab.b;
 uint32_t available=m10v_camera_library_shooting_count();
 if(h->a>=available)h->a=0;if(h->b>=available)h->b=1;
 h->level=1;h->focus=h->a;
 m10v_library_state fresh;if(m10v_camera_library_load(&fresh)<0)h->error=945;
 else for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)h->films[i]=fresh.slots[i].film;
 if(origin==0x02000000u)ab_host_attach(p,c);
 else ((fn3)0x5316c9d8u)(c,0x02000000u,0x02000012u);
}
static int ab_host_followup(m10v_settings_controller *p,uint32_t c,uint32_t key,uint32_t route){
 m10v_native_ab_host *h=ab_host(p);
 if(!h||!h->back_pending||h->origin!=route||h->source!=c)return 0;
 if(key==8){h->back_pending=0;return 0;}
 if(key==0xd8){h->back_pending=0;return 1;}return 0;
}
static void ab_host_live(m10v_settings_controller *p,uint32_t c){
 p->ab_exit_source=c;M10V_EXIT_LOG(272,c,0x08000000u,0,0);
 M10V_EXIT_LOG(248,c,p->host.mode,p->host.origin,p->ab.enabled);
 ab_host_restore(p,c);
 M10V_EXIT_LOG(249,c,0x08000000u,0x10000000u,0);
 ((fn3)0x5316c9d8u)(c,0x08000000u,0x10000000u);
 M10V_EXIT_LOG(250,c,0,0,0);
}
static void ab_host_start(m10v_settings_controller *p,uint32_t c){
 m10v_native_ab_host *h=&p->host;m10v_library_state fresh;
 if(h->a==h->b){h->error=1018;ab_host_render(p);return;}
 if(h->a>=m10v_camera_library_shooting_count()||h->b>=m10v_camera_library_shooting_count()||m10v_camera_library_load(&fresh)<0){h->error=945;ab_host_render(p);return;}
 uint32_t sa=m10v_ab_slot(h->a),sb=m10v_ab_slot(h->b);
 if((sa<M10V_SLOT_COUNT&&(!fresh.slots[sa].film||fresh.slots[sa].film!=h->films[sa]))||
    (sb<M10V_SLOT_COUNT&&(!fresh.slots[sb].film||fresh.slots[sb].film!=h->films[sb]))||ab_save(h->a,h->b)||ab_apply(h->a)){
  h->error=945;ab_host_render(p);return;
 }
 ab_clear(&p->ab);
 m10v_ab_start(&p->ab,h->a,h->b,h->a,sa<M10V_SLOT_COUNT?fresh.slots[sa].film:0,sb<M10V_SLOT_COUNT?fresh.slots[sb].film:0);
 ab_host_live(p,c);
}
static int ab_host_event(m10v_settings_controller *p,uint32_t c,uint32_t event){
 m10v_native_ab_host *h=ab_host(p);if(!ab_host_owned(h,c))return 0;
 uint32_t key=ab_event_key(event);
 /* Native MENU switch packets include press/repeat/release. Follow GRKit's
  * phase2/repeat0 action boundary so a picker cancellation cannot also close
  * the root on the second packet of the same physical press. */
 if(key==5){uint32_t packet=ab_host_word(event,4);
  if(ab_ram(packet,8)&&(*(const uint8_t *)(uintptr_t)packet!=2||ab_host_word(packet,4)!=0))return 1;
 }
 if(key==0x36){p->ab.down=0;return 1;}
 if(key==0x37){if(!p->ab.down){ab_stop(&p->ab);p->ab.down=1;ab_host_live(p,c);}return 1;}
 if(key==0x38||key==0x30)return 1;
 if(key==8){h->back_pending=0;return 0;}
 if(key==0xd8&&h->back_pending){h->back_pending=0;return 1;}
 if(key==0xd0||key==0xd4||key==0xd1||key==0xd5){
  uint32_t count=m10v_camera_library_shooting_count();
  h->focus=(key==0xd0||key==0xd4)?(h->focus?h->focus-1:count-1):ab_host_wrap(h->focus+1,count);
  h->error=0;ab_host_render(p);return 1;
 }
 if(key==0xce||key==0xcf){
  uint32_t n=ab_host_page_size(h);h->focus=ab_host_wrap(h->focus+m10v_camera_library_shooting_count()+(key==0xce?m10v_camera_library_shooting_count()-n:n),m10v_camera_library_shooting_count());
  h->error=0;ab_host_render(p);return 1;
 }
 if(key==0xd8){
  if(h->level==1){h->a=h->focus;h->level=2;h->focus=h->b;h->error=0;ab_host_render(p);}
  else {h->b=h->focus;ab_host_start(p,c);}return 1;
 }
 if(key==5||key==0x89||key==0xaa){
  if(h->level==2){h->focus=h->a;h->level=1;h->error=0;h->back_pending=key==5;ab_host_render(p);return 1;}
  uint32_t origin=h->origin;h->back_pending=key==5;ab_host_restore(p,c);
  if(origin==0x02000012u){((fn1)0x5316ca28u)(c);return 1;}
 }
 if(key==0x1b)ab_host_restore(p,c);
 /* Power/main and unknown events remain entirely native. */
 return 0;
}
#endif
uint32_t m10v_settings_controller_ab_adj_refresh(uint32_t c){
 M10V_EXIT_LOG(260,c,0,0,0);
 m10v_settings_controller *p=ab_owner();m10v_native_ab_host *h=ab_host(p);
 int target=ab_ram(c,0x274)&&ab_host_word(c,0)==0x53b394e0u&&ab_host_word(c,0x124)==0x02000000u;
 int render=h&&(h->mode==1||ab_host_owned(h,c))&&target;
 if(render){h->controller=c;h->rebuilding=1;}
 uint32_t r=m10v_ab_adj_refresh_original(c);
 if(render){
  if(ab_host_valid(c)){if(h->mode==1)ab_host_attach(p,c);else ab_host_render(p);}
  else ab_host_cancel(p,c);
 }M10V_EXIT_LOG(261,c,r,render,0);return r;
}
uint32_t m10v_settings_controller_ab_adj_changed(uint32_t c){
 m10v_native_ab_host *h=ab_host(ab_owner());
 if(h&&h->controller==c&&h->rebuilding){M10V_EXIT_LOG(259,c,h->mode,h->rebuilding,0);return 0;}
 if(ab_host_owned(h,c)){
  uint32_t cursor=((fn1)0x53394820u)(ab_host_word(c,0x1f0)),size=ab_host_page_size(h);
  uint32_t next=ab_host_start_row(h->focus,size)+cursor;
  if(next<m10v_camera_library_shooting_count()){h->focus=next;h->error=0;ab_host_render(ab_owner());}return 0;
 }
 M10V_EXIT_LOG(267,c,0,0,0);
 return m10v_ab_adj_changed_original(c);
}
uint32_t m10v_settings_controller_ab_adj_exit(uint32_t c){
 M10V_EXIT_LOG(237,c,ab_ram(c,0x280)?ab_host_word(c,0x124):0,ab_ram(c,0x280)?ab_host_word(c,0x1f0):0,ab_ram(c,0x280)?*(const uint8_t *)(uintptr_t)(c+0x270):0xffffffffu);
 m10v_settings_controller *p=ab_owner();ab_host_restore(p,c);
 M10V_EXIT_LOG(264,c,0,0,0);
 uint32_t r=m10v_ab_adj_exit_original(c);
 M10V_EXIT_LOG(238,c,r,0,0);return r;
}
uint32_t m10v_settings_controller_ab_adj_destroy(uint32_t c){
 M10V_EXIT_LOG(265,c,0,0,0);
 m10v_settings_controller *p=ab_owner();m10v_native_ab_host *h=ab_host(p);
 if(p&&p->ab_exit_source==c)p->ab_exit_source=0;
 if(h&&h->controller==c){h->controller=0;h->mode=0;h->rebuilding=0;p->pending_source=0;}
 uint32_t r=m10v_ab_adj_destroy_original(c);
 M10V_EXIT_LOG(266,c,r,0,0);return r;
}
