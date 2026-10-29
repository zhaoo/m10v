#include "m10v_tone.h"
#include "m10v_settings.h"
#include "m10v_film_directory.h"
#include "m10v_sd_library.h"
static int ready(const m10v_settings_ops *o){return o&&o->load&&o->item&&o->install&&o->remove&&o->stamp&&o->film_name_stamp;}
static uint32_t item(const m10v_settings_ops *o,uint32_t i){
 if(i>=M10V_SD_DIRECTORY_LIMIT)return 0;
 uint32_t id=o->item(o->context,i);return (i<M10V_DIRECTORY_COUNT?id==m10v_directory[i].id:M10V_CUSTOM(id))?id:0;
}
static uint32_t value(const m10v_library_state *s,uint32_t field){
 return field==0?s->stamp:field==1?s->format:field==2?s->corner:field==3?s->color:s->reserved&1u;
}
int m10v_settings_open(m10v_settings *p,const m10v_settings_ops *o,uint32_t screen){
 if(!p||!ready(o))return -1;
 p->screen=M10V_SETTINGS_CLOSED;
 if(screen!=M10V_SETTINGS_FILMS&&screen!=M10V_SETTINGS_STAMP&&screen!=M10V_SETTINGS_NAME&&screen!=M10V_SETTINGS_AB&&screen!=M10V_SETTINGS_WATERMARK)return -1;
 if(o->load(o->context,&p->saved)<0)return -1;
 if(p->saved.stamp>2||p->saved.format>3||p->saved.corner>3||p->saved.color>3)return -1;
 if(!m10v_library_valid(&p->saved))return -1;
 p->focus=p->slot=p->index=p->expected=p->value=p->error=p->group=0;
 p->screen=screen==M10V_SETTINGS_FILMS?M10V_SETTINGS_CATALOG:screen;
 if(p->screen==M10V_SETTINGS_CATALOG){
  /* Cache the extent on open; browsing must not scan the entire card per key. */
  p->group=o->extent?o->extent(o->context):M10V_DIRECTORY_COUNT;
  if(!o->extent)while(p->group<M10V_SD_DIRECTORY_LIMIT&&item(o,p->group))p->group++;
  if(p->group<M10V_DIRECTORY_COUNT||p->group>M10V_SD_DIRECTORY_LIMIT){
   p->group=M10V_DIRECTORY_COUNT;p->error=M10V_SETTINGS_SAVE_FAILED;return 0;
  }
  while(p->index+1<p->group&&!item(o,p->index))p->index++;
  p->expected=item(o,p->index);if(!p->expected)p->error=M10V_SETTINGS_EMPTY;
 }
 if(screen==M10V_SETTINGS_AB){p->slot=1;p->index=5;}if(screen==M10V_SETTINGS_NAME)p->value=p->saved.reserved&1u;return 0;
}
void m10v_settings_key(m10v_settings *p,const m10v_settings_ops *o,uint32_t key){
 if(!p||!ready(o)||key>M10V_KEY_CLEAN)return;
 uint32_t previous=key==M10V_KEY_LEFT||key==M10V_KEY_UP;
 uint32_t next=key==M10V_KEY_RIGHT||key==M10V_KEY_DOWN;
 if(p->screen==M10V_SETTINGS_CATALOG&&key==M10V_KEY_CLEAN){
   /* Explicit maintenance only: loading/browsing never migrates a journal. */
   for(uint32_t n=0;n<M10V_SLOT_COUNT;n++){
    m10v_library_state fresh;
    if(o->load(o->context,&fresh)<0||!m10v_library_valid(&fresh)){p->error=M10V_SETTINGS_SAVE_FAILED;return;}
    for(uint32_t b=0;b<sizeof(fresh);b++)((uint8_t *)&p->saved)[b]=((const uint8_t *)&fresh)[b];
    uint32_t count=m10v_library_count(&fresh),slot=0;
    while(slot<count&&(m10v_directory_name(fresh.slots[slot].film)||M10V_CUSTOM(fresh.slots[slot].film)))slot++;
    if(slot==count){p->error=0;return;}
    if(o->remove(o->context,slot)!=0){p->error=M10V_SETTINGS_SAVE_FAILED;return;}
   }
   if(o->load(o->context,&p->saved)<0){p->error=M10V_SETTINGS_SAVE_FAILED;return;}
   p->error=0;return;
 }else if(p->screen==M10V_SETTINGS_AB){
  p->value=0;
  if(key==M10V_KEY_UP&&p->focus)p->focus--;
  if(key==M10V_KEY_DOWN&&p->focus<3)p->focus++;
  uint32_t *slot=p->focus==0?&p->slot:&p->index;
  if(p->focus<2){
   if(key==M10V_KEY_LEFT&&*slot)(*slot)--;
   if(key==M10V_KEY_RIGHT&&*slot+1<M10V_TONE_CHOICES)(*slot)++;
  }
  if(key==M10V_KEY_BACK){p->screen=M10V_SETTINGS_CLOSED;p->error=0;}
  if(key==M10V_KEY_OK&&p->focus>=2)p->value=p->focus-1;
 }else if(p->screen==M10V_SETTINGS_CATALOG){
  /* Retry a failed header read on user input, rather than freezing a truncated
   * directory for the lifetime of the page. No storage mutations occur here. */
  if(o->extent&&(p->error==M10V_SETTINGS_SAVE_FAILED||p->error==M10V_SETTINGS_EMPTY)&&key!=M10V_KEY_BACK){
   uint32_t extent=o->extent(o->context);
   if(extent<M10V_DIRECTORY_COUNT||extent>M10V_SD_DIRECTORY_LIMIT)return;
   p->group=extent;
   if(p->index>=extent)p->index=0;
   while(p->index+1<extent&&!item(o,p->index))p->index++;
   p->expected=item(o,p->index);
   p->error=p->expected?0:M10V_SETTINGS_EMPTY;
   return; /* Refresh only; never install a newly discovered film on this key. */
  }
  if(key==M10V_KEY_BACK){p->screen=M10V_SETTINGS_CLOSED;p->error=0;return;}
  uint32_t first=0,end=p->group;
  if(end<M10V_DIRECTORY_COUNT||end>M10V_SD_DIRECTORY_LIMIT)return;
  if(p->index<first||p->index>=end)return;
  uint32_t i=p->index;
  if(key==M10V_KEY_LEFT&&i>first)i--;
  if(key==M10V_KEY_RIGHT)i++;
  if(key==M10V_KEY_UP)i=p->index>=first+5?p->index-5:first;
  if(key==M10V_KEY_DOWN)i=p->index+5;
  if(key==M10V_KEY_PREVIOUS)i=p->index>=first+10?p->index-10:first;
  if(key==M10V_KEY_NEXT)i=p->index+10;
  if(i>=end)i=end-1;
  if(i!=p->index){
   uint32_t id=item(o,i);
   if(i>p->index){
    while(!id&&i+1<end){i++;id=item(o,i);}
    while(!id&&i>p->index){i--;id=item(o,i);}
   }else{
    while(!id&&i>first){i--;id=item(o,i);}
    while(!id&&i<p->index){i++;id=item(o,i);}
   }
   if(id){p->index=i;p->expected=id;p->error=0;}
  }
  if(key==M10V_KEY_OK){
   if(!p->expected||item(o,p->index)!=p->expected){p->error=M10V_SETTINGS_CHANGED;return;}
   m10v_library_state fresh;if(o->load(o->context,&fresh)<0){p->error=M10V_SETTINGS_SAVE_FAILED;return;}
   uint32_t count=m10v_library_count(&fresh),slot=0;
   while(slot<count&&fresh.slots[slot].film!=p->expected)slot++;
   if(slot==count&&count>=(M10V_APPENDED_SLOTS?10u:5u)){p->error=M10V_SETTINGS_FULL;return;}
   int r=slot<count?o->remove(o->context,slot):o->install(o->context,p->index,p->expected,count);
   if(r||o->load(o->context,&p->saved)<0){p->error=M10V_SETTINGS_SAVE_FAILED;return;}
   p->error=0;
  }
 }else if(p->screen==M10V_SETTINGS_WATERMARK){
  if(previous)p->focus=0;
  if(next)p->focus=1;
  if(key==M10V_KEY_BACK)p->screen=M10V_SETTINGS_CLOSED;
  if(key==M10V_KEY_OK){
   p->group=1;
   p->screen=p->focus?M10V_SETTINGS_NAME:M10V_SETTINGS_STAMP;
   p->value=p->saved.reserved&1u;p->focus=0;p->error=0;
  }
 }else if(p->screen==M10V_SETTINGS_NAME){
  if(previous)p->value=0;
  if(next)p->value=1;
  if(key==M10V_KEY_BACK){p->screen=p->group?M10V_SETTINGS_WATERMARK:M10V_SETTINGS_CLOSED;p->focus=1;p->error=0;}
  if(key==M10V_KEY_OK){
   if(o->film_name_stamp(o->context,p->value)!=0){p->error=M10V_SETTINGS_SAVE_FAILED;return;}
   p->saved.reserved=p->value;p->screen=p->group?M10V_SETTINGS_WATERMARK:M10V_SETTINGS_CLOSED;p->focus=1;p->error=0;
  }
 }else if(p->screen==M10V_SETTINGS_STAMP){
  if(p->focus>=4)return;
  if(previous&&p->focus)p->focus--;
  if(next&&p->focus<3)p->focus++;
  if(key==M10V_KEY_BACK){p->screen=p->group?M10V_SETTINGS_WATERMARK:M10V_SETTINGS_CLOSED;p->focus=0;p->error=0;}
  if(key==M10V_KEY_OK){p->value=value(&p->saved,p->focus);p->screen=M10V_SETTINGS_VALUE;p->error=0;}
 }else if(p->screen==M10V_SETTINGS_VALUE){
  if(p->focus>=4)return;
  uint32_t max=p->focus==0?2:3;
  if(previous&&p->value)p->value--;
  if(next&&p->value<max)p->value++;
  if(key==M10V_KEY_BACK){p->screen=M10V_SETTINGS_STAMP;p->error=0;}
  if(key==M10V_KEY_OK){
   uint32_t v[4]={p->saved.stamp,p->saved.format,p->saved.corner,p->saved.color};
   if(p->value>max)return;
   if(p->focus<4)v[p->focus]=p->value;
   if(o->stamp(o->context,v[0],v[1],v[2],v[3])!=0){p->error=M10V_SETTINGS_SAVE_FAILED;return;}
   p->saved.stamp=(uint8_t)v[0];p->saved.format=(uint8_t)v[1];
   p->saved.corner=(uint8_t)v[2];p->saved.color=(uint8_t)v[3];
   p->screen=M10V_SETTINGS_STAMP;p->error=0;
  }
 }
}
