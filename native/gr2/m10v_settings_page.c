#include "m10v_settings_page.h"
#include "m10v_hdf_page.h"
#include "m10v_settings_backend.h"
#include "m10v_ui.h"
#include "m10v_model.h"
#include "../../compat/gr2-v1/native/gr3/m10v_sd_library.h"
#include "m10v_settings_labels.h"
#include "m10v_detail_labels.h"
#define DETAIL_SCREEN 5u
#define PAGE_MAGIC 0x47525047u
typedef struct {
    gr2_overlay overlay;
    uint32_t magic,native_backend;
    m10v_settings state;
    m10v_settings_ops ops;
    gr2_settings_backend backend;
    gr2_detail detail;
    gr2_detail_ops detail_ops;
} page;
static page *active;
/* bit0: film/stamp; bit1: independent HDF; UI owner only. */
static uint32_t menu_entries_enabled;
static void copy(void *out,const void *in,uint32_t bytes){for(uint32_t i=0;i<bytes;i++)((uint8_t *)out)[i]=((const uint8_t *)in)[i];}
static int text(const uint16_t *caption,int16_t left,int16_t top,int16_t right,int16_t bottom){
    uint32_t count=0;while(count<96&&caption[count])count++;
    int16_t box[4]={left,top,right,bottom};return count<96&&gr2_text_draw_full(caption,count,box,0x20001);
}
static int fill(uint32_t index,int16_t left,int16_t top,int16_t right,int16_t bottom,uint32_t color){
    int16_t box[4]={left,top,right,bottom};return gr2_fill_rect(index,box,color);
}
static uint32_t film(page *p,uint32_t index){
    if(p->state.screen==M10V_SETTINGS_CATALOG){
        uint32_t row=(p->state.index/5)*5+index,id=p->ops.item(p->ops.context,row);
        return id>=33&&id<=M10V_CUSTOM_MAX_ID?id:0;
    }
    return p->state.saved.slots[index].film;
}
static int film_name(page *p,uint32_t focus){
    uint32_t id=film(p,focus),number=p->state.screen==M10V_SETTINGS_CATALOG?p->state.index+1:focus+1;
    const char *name=m10v_library_name(id);char custom[24];
    if(id>M10V_FILM_COUNT){
        name="Custom LUT";
        if(p->native_backend){
            uint8_t *record=gr2_allocate(M10V_SD_RECORD_BYTES);
            if(record){
                uint32_t ok=p->state.screen==M10V_SETTINGS_CATALOG?
                    gr2_sd_frozen_record(&p->backend.manifest,p->state.index,id,record,M10V_SD_RECORD_BYTES):
                    (uint32_t)gr2_sd_custom_record(&p->state.saved,focus,record,M10V_SD_RECORD_BYTES);
                if(ok){uint32_t i=0;for(;i<23&&record[16+i];i++)custom[i]=(char)record[16+i];custom[i]=0;name=custom;}
                gr2_release(record);
            }
        }
    }
    uint16_t caption[96];uint32_t n=0;
    if(number>=100)caption[n++]=(uint16_t)('0'+number/100);
    if(number>=10)caption[n++]=(uint16_t)('0'+(number/10)%10);
    caption[n++]=(uint16_t)('0'+number%10);
    if(p->state.screen==M10V_SETTINGS_FILMS){caption[n++]=' ';caption[n++]='/';caption[n++]=' ';caption[n++]='5';}
    caption[n++]=' ';caption[n++]=' ';
    if(name)for(uint32_t i=0;name[i]&&n<95;i++)caption[n++]=(uint8_t)name[i];
    caption[n]=0;return text(caption,24,380,695,423);
}
static int detail_draw(page *p){
    int ok=fill(0,0,0,719,479,0x20000)&&fill(1,0,0,719,479,0x20004);
    ok=text(detail_labels[12],20,12,265,53)&&text(detail_labels[13],20,430,699,469)&&ok;
    const char *name=m10v_library_name(p->detail.saved.slots[p->detail.slot].film);
    if(!name)name="Custom LUT";
    uint16_t caption[96];uint32_t n=0;while(name[n]&&n<95){caption[n]=(uint8_t)name[n];n++;}caption[n]=0;
    ok=text(caption,280,12,699,53)&&ok;
    for(uint32_t i=0;i<5;i++){
        uint32_t row=p->state.focus/5*5+i,field=gr2_detail_field(&p->detail,row);
        if(field==UINT32_MAX)break;
        int16_t y=(int16_t)(80+62*i);
        if(row==p->state.focus)ok=fill(1,24,y-4,695,y+53,0x20001)&&fill(1,28,y,691,y+49,0x20004)&&ok;
        ok=text(detail_labels[field],40,y,420,y+49)&&ok;
        uint32_t value=gr2_detail_value(&p->detail,field);
        caption[0]=(uint16_t)('0'+value);caption[1]=0;
        if(field==10){
            uint32_t film=p->detail.saved.slots[p->detail.slot].film;
            const char *ei=film==67?(value?"120":"200"):value==1?"64":value==2?"250":"125";
            n=0;while(ei[n]){caption[n]=(uint8_t)ei[n];n++;}caption[n]=0;
        }
        if(field!=11)ok=text(caption,500,y,679,y+49)&&ok;
    }
    if(p->detail.error)ok=text(labels[8],20,388,699,427)&&ok;
    p->overlay.dirty=ok?0:1;return ok;
}
static int detail_key(page *p,uint32_t key){
    if(key==M10V_KEY_BACK)return gr2_settings_close();
    if(!p->detail.ready)return 1;
    uint32_t field=gr2_detail_field(&p->detail,p->state.focus);
    if(key==M10V_KEY_UP||key==M10V_KEY_PREVIOUS){if(p->state.focus)p->state.focus--;}
    else if(key==M10V_KEY_DOWN||key==M10V_KEY_NEXT){if(gr2_detail_field(&p->detail,p->state.focus+1)!=UINT32_MAX)p->state.focus++;}
    else if(field==11){if(key==M10V_KEY_OK)gr2_detail_set(&p->detail,&p->detail_ops,11u<<8);}
    else if(key==M10V_KEY_LEFT||key==M10V_KEY_RIGHT){
        uint32_t value=gr2_detail_value(&p->detail,field),next=value;
        if(key==M10V_KEY_LEFT){if(value)next--;}
        else if(value<gr2_detail_limit(&p->detail,field))next++;
        if(next!=value)gr2_detail_set(&p->detail,&p->detail_ops,field<<8|next);
    }
    p->overlay.dirty=1;return 1;
}
static int draw(page *p){
    if(!p||p->magic!=PAGE_MAGIC||p->state.screen==M10V_SETTINGS_CLOSED)return 0;
    if(p->state.screen==DETAIL_SCREEN)return detail_draw(p);
    uint32_t films=p->state.screen==M10V_SETTINGS_FILMS||p->state.screen==M10V_SETTINGS_CATALOG;
    uint32_t focus=p->state.screen==M10V_SETTINGS_CATALOG?p->state.index%5:p->state.focus;
    if(focus>=5)return 0;
    /* Transparent text plane over an opaque stock RGB background. */
    if(!fill(0,0,0,719,479,0x20000)||!fill(1,0,0,719,479,0x20004))return 0;
    uint32_t title=films?(p->state.screen==M10V_SETTINGS_CATALOG?32:0):1;
    if(p->state.screen==M10V_SETTINGS_VALUE)title=focus==4?35:28+focus;
    int ok=text(labels[title],20,12,699,53);
    uint32_t footer=p->state.screen==M10V_SETTINGS_CATALOG?3:films?2:p->state.screen==M10V_SETTINGS_VALUE?5:4;
    ok=text(labels[footer],20,430,699,469)&&ok;
    if(films){
        for(uint32_t i=0;i<5;i++){
            uint32_t id=film(p,i);int16_t x=(int16_t)(24+136*i);
            if(i==focus)ok=fill(1,x-2,102,x+129,233,0x20001)&&fill(1,x,104,x+127,231,0x20004)&&ok;
            if(id)ok=gr2_card_draw(id>M10V_FILM_COUNT?33:id,i,i==focus,(104u<<16)|(uint32_t)x)&&ok;
        }
        ok=film_name(p,focus)&&ok;
    }else{
        uint32_t values[4]={p->state.saved.stamp,p->state.saved.format,p->state.saved.corner,p->state.saved.color};
        static const uint8_t first[4]={13,16,20,24};
        if(p->state.screen==M10V_SETTINGS_VALUE&&focus<4)values[focus]=p->state.value;
        for(uint32_t i=0;i<4;i++){
            if(values[i]>(i?3u:2u))return 0;
            int16_t y=(int16_t)(90+72*i);
            if(i==focus)ok=fill(1,24,y-6,695,y+57,0x20001)&&fill(1,30,y,689,y+51,0x20004)&&ok;
            ok=text(labels[9+i],36,y,335,y+51)&&text(labels[first[i]+values[i]],350,y,679,y+51)&&ok;
        }
        uint32_t enabled=p->state.screen==M10V_SETTINGS_VALUE&&focus==4?p->state.value:p->state.saved.reserved&1u;
        if(enabled>1)return 0;
        uint16_t caption[96];uint32_t n=0;
        if(focus==4){caption[n++]='>';caption[n++]=' ';}
        for(uint32_t i=0;labels[33+enabled][i]&&n<95;i++)caption[n++]=labels[33+enabled][i];caption[n]=0;
        ok=text(caption,24,380,695,423)&&ok;
    }
    if(p->state.error>=1&&p->state.error<=3)ok=text(labels[5+p->state.error],20,375,699,414)&&ok;
    p->overlay.dirty=ok?0:1;return ok;
}
static int destroy(void *owner,uint32_t reason){
    (void)reason;page *p=owner;
    if(active==p)active=0;
    p->magic=0;fill(0,0,0,719,479,0x20000);fill(1,0,0,719,479,0x20000);
    gr2_release(p);return 1;
}
int gr2_settings_active(void){return active!=0;}
int gr2_settings_close(void){return active?gr2_overlay_detach(&active->overlay):0;}
int gr2_settings_key(uint32_t key){
    page *p=active;if(!p||p->magic!=PAGE_MAGIC||key>M10V_KEY_NEXT)return 0;
    if(p->state.screen==DETAIL_SCREEN)return detail_key(p,key);
    if(p->native_backend&&p->state.screen==M10V_SETTINGS_FILMS&&key==M10V_KEY_OK)gr2_settings_backend_refresh(&p->backend);
    m10v_settings_key(&p->state,&p->ops,key);
    if(p->state.screen==M10V_SETTINGS_CLOSED)return gr2_settings_close();
    p->overlay.dirty=1;return 1;
}
/* Run before stock state watchers can translate one raw key into a queued
 * SPEC key. Only the owned page or its three owned menu entries consumes them.
 * MENU/OK is SYS_KEY_OK; no fictitious independent raw MENU is accepted. */
static int menu_key(const uint32_t *message);
int gr2_settings_raw_event(const uint32_t *message){
    if(!message||((uintptr_t)message&3))return 0;
    if(gr2_hdf_page_active())return gr2_hdf_page_raw_event(message);
    if(!active)return menu_key(message);
    uint32_t key;
    switch(message[0]){
        case 0x60001006u:key=M10V_KEY_UP;break;
        case 0x60001007u:key=M10V_KEY_DOWN;break;
        case 0x60001008u:case 0x60001014u:key=M10V_KEY_LEFT;break;
        case 0x60001009u:case 0x60001015u:key=M10V_KEY_RIGHT;break;
        case 0x6000100au:case 0x60001016u:key=M10V_KEY_OK;break;
        case 0x6000100eu:key=M10V_KEY_BACK;break;
        case 0x60001017u:key=M10V_KEY_UP;break;
        case 0x60001018u:key=M10V_KEY_DOWN;break;
        default:return 0;
    }
    return gr2_settings_key(key);
}
static uint32_t event(void *owner,const uint32_t *message){
    page *p=owner;if(!message||p!=active||p->magic!=PAGE_MAGIC)return 0;
    uint32_t id=message[0],key;
    if(id==0x60000003u)return (uint32_t)draw(p);
    if(id==0x60000005u){p->state.screen=M10V_SETTINGS_CLOSED;return 1;}
    switch(id){
        case 0x60002001u:case 0x60002506u:key=M10V_KEY_RIGHT;break;
        case 0x60002002u:case 0x60002505u:key=M10V_KEY_LEFT;break;
        case 0x60002003u:case 0x60002503u:key=M10V_KEY_UP;break;
        case 0x60002004u:case 0x60002504u:key=M10V_KEY_DOWN;break;
        case 0x60002005u:case 0x60002501u:key=M10V_KEY_OK;break;
        case 0x60002006u:case 0x60002502u:key=M10V_KEY_BACK;break;
        default:return 0;
    }
    return (uint32_t)gr2_settings_key(key);
}
void *gr2_settings_open(const m10v_settings_ops *ops,uint32_t screen){
    if(active||gr2_hdf_page_active()||(screen!=M10V_SETTINGS_FILMS&&screen!=M10V_SETTINGS_STAMP))return 0;
    page *p=gr2_allocate(sizeof(*p));if(!p)return 0;
    for(uint32_t i=0;i<sizeof(*p);i++)((uint8_t *)p)[i]=0;
    if(ops)copy(&p->ops,ops,sizeof(*ops));
    else {p->native_backend=1;if(!gr2_settings_backend_bind(&p->backend,&p->ops)){gr2_release(p);return 0;}}
    if(m10v_settings_open(&p->state,&p->ops,screen)||!m10v_library_valid(&p->state.saved)){gr2_release(p);return 0;}
    p->magic=PAGE_MAGIC;p->overlay.event=event;p->overlay.destroy=destroy;
    if(!gr2_overlay_attach(&p->overlay)){gr2_release(p);return 0;}
    active=p;return p;
}
void *gr2_settings_detail_open(uint32_t slot,const gr2_detail_ops *ops){
    if(active||gr2_hdf_page_active()||slot>=5u)return 0;
    page *p=gr2_allocate(sizeof(*p));if(!p)return 0;
    for(uint32_t i=0;i<sizeof(*p);i++)((uint8_t *)p)[i]=0;
    if(ops)copy(&p->detail_ops,ops,sizeof(*ops));else gr2_detail_backend_bind(&p->detail_ops);
    if(!gr2_detail_open(&p->detail,&p->detail_ops,slot)){gr2_release(p);return 0;}
    p->state.screen=DETAIL_SCREEN;p->magic=PAGE_MAGIC;p->overlay.event=event;p->overlay.destroy=destroy;
    if(!gr2_overlay_attach(&p->overlay)){gr2_release(p);return 0;}
    active=p;return p;
}
int gr2_settings_detail_peek(gr2_detail *out,uint32_t *row){
    page *p=active;uintptr_t o=(uintptr_t)out,b=(uintptr_t)p,r=(uintptr_t)row;
    if(!p||p->state.screen!=DETAIL_SCREEN||!out||!row||(o&3u)||(r&3u)||o>UINTPTR_MAX-sizeof(*out)||r>UINTPTR_MAX-4u||
       (o<b+sizeof(*p)&&b<o+sizeof(*out))||(r<b+sizeof(*p)&&b<r+4u)||(o<r+4u&&r<o+sizeof(*out)))return 0;
    copy(out,&p->detail,sizeof(*out));*row=p->state.focus;return 1;
}
int gr2_settings_draw(void){return draw(active);}
int gr2_settings_peek(m10v_settings *out){
    page *p=active;uintptr_t o=(uintptr_t)out,b=(uintptr_t)p;
    if(!p||!out||(o&3)||sizeof(*out)>UINTPTR_MAX-o||(o<b+sizeof(*p)&&b<o+sizeof(*out)))return 0;
    copy(out,&p->state,sizeof(*out));return 1;
}

/* Called on the existing UI owner before public-route conversion. Consume a
 * private route even on allocation/backend failure, so stock FSM never sees
 * an unknown state. The preserved camera menu remains available for retry. */
int gr2_settings_menu_route(uint32_t route){
    if(route!=0x6d100001u&&route!=0x6d100003u&&route!=0x6d100002u&&route!=0x6000400bu)return 0;
    typedef const uint32_t *(*root_fn)(void);
    const uint32_t *root=((root_fn)(uintptr_t)0xA03989C9u)();
    if(route==0x6000400bu){
        /* The stock list emits this route for its TRASH/detail action. State
         * 0x1a is generic: also require this model's effect definition/type. */
        if(!(menu_entries_enabled&1u)||!root||root[0]!=0xA03AD0C7u||root[1]!=0x1au||root[12]!=0x66u||
           ((const uint8_t *)(const void *)root)[0x38]!=3u)return 0;
        typedef uint32_t (*property_fn)(uint32_t);
        uint32_t tone=((property_fn)(uintptr_t)0xA00E0E81u)(0x2bu);
        static const uint8_t carriers[5]={9,10,11,18,8};
        for(uint32_t i=0;i<5;i++)if(tone==carriers[i]){gr2_settings_detail_open(i,0);return 1;}
        return 0;
    }
    if(!root||root[1]!=0x17u)return 0;
    if(route==0x6d100002u){gr2_hdf_page_open();return 1;}
    gr2_settings_open(0,route==0x6d100001u?M10V_SETTINGS_FILMS:M10V_SETTINGS_STAMP);
    return 1;
}

const uint16_t *gr2_menu_text(uint32_t id){
    if(id==0x70068u)return labels[0];
    if(id==0x70069u)return labels[1];
    if(id==0x7006au)return gr2_hdf_page_title();
    typedef const uint16_t *(*lookup)(uint32_t);
    return ((lookup)(uintptr_t)0xA03A4AEFu)(id);
}

/* UI-owner-only extension. Stock refresh must see its original 47-entry
 * source/definition mapping; three owned action rows are appended afterwards.
 * Persistent storage also keeps already-cached widget pointers valid. */
static uint32_t menu_rows[50][8];

static uint32_t owned_count(void){return ((menu_entries_enabled&1u)?2u:0u)+((menu_entries_enabled&2u)?1u:0u);}
extern uint32_t *gr2_menu_categories_original(uint32_t);
static int menu_contract(void){
    const uint32_t *descriptor=(const uint32_t *)(uintptr_t)0xA0439790u;
    const uint32_t *category=(const uint32_t *)(uintptr_t)(0xA0439718u+3u*24u);
    if((descriptor[0]>>16)!=5u||descriptor[2]!=0xA0439718u)return 0;
    return (category[3]==47u&&category[5]==0xA0438B38u)||
           (menu_entries_enabled&&category[3]==47u+owned_count()&&category[5]==(uint32_t)(uintptr_t)menu_rows);
}
static int menu_enable(uint32_t next){
    if(next>3u||!menu_contract())return 0;
    if(next==menu_entries_enabled)return 1;
    uint32_t *category=(uint32_t *)(uintptr_t)(0xA0439718u+3u*24u);
    if(category[5]==(uint32_t)(uintptr_t)menu_rows){category[3]=47;category[5]=0xA0438B38u;}
    menu_entries_enabled=next;return 1;
}
int gr2_menu_entries_enable(uint32_t enabled){return enabled<=1u?menu_enable(enabled?3u:0u):0;}
int gr2_menu_films_enable(uint32_t enabled){return enabled<=1u?menu_enable((menu_entries_enabled&2u)|(enabled?1u:0u)):0;}
int gr2_menu_hdf_enable(uint32_t enabled){return enabled<=1u?menu_enable((menu_entries_enabled&1u)|(enabled?2u:0u)):0;}
uint32_t *gr2_menu_categories(uint32_t flags){
    uint32_t *category=(uint32_t *)(uintptr_t)(0xA0439718u+3u*24u);
    if(menu_entries_enabled){
        if(!menu_contract())return (uint32_t *)(uintptr_t)0xA0439790u;
        category[3]=47;category[5]=0xA0438B38u;
    }
    uint32_t *descriptor=gr2_menu_categories_original(flags);
    if(!menu_entries_enabled||!menu_contract()||descriptor!=(uint32_t *)(uintptr_t)0xA0439790u)return descriptor;
    const uint32_t *source=(const uint32_t *)(uintptr_t)0xA0438B38u;
    for(uint32_t i=0;i<47u;i++)for(uint32_t j=0;j<8u;j++)menu_rows[i][j]=source[i*8u+j];
    uint32_t appended=0;
    for(uint32_t i=0;i<3u;i++){
        if((i<2u&&!(menu_entries_enabled&1u))||(i==2u&&!(menu_entries_enabled&2u)))continue;
        uint32_t *row=menu_rows[47u+appended++];
        row[0]=0x70068u+i;row[1]=0;row[2]=0x01000000u;row[3]=i==2u?0x6d100002u:i?0x6d100003u:0x6d100001u;
        row[4]=2;row[5]=1;row[6]=1;row[7]=0;
    }
    category[3]=47u+appended;category[5]=(uint32_t)(uintptr_t)menu_rows;
    return descriptor;
}

/* Stock setup rows use RIGHT for type1 activation and ordinary MENU/OK can
 * close the camera menu. Add OK only for these three owned rows, before stock
 * watchers; all stock rows retain their original physical-key behavior. */
static int menu_key(const uint32_t *message){
    if(!menu_entries_enabled||(message[0]!=0x6000100au&&message[0]!=0x60001016u)||!menu_contract())return 0;
    typedef const uint8_t *(*root_fn)(void);
    const uint8_t *root=((root_fn)(uintptr_t)0xA03989C9u)();
    if(!root||((const uint32_t *)(const void *)root)[1]!=0x17u||root[0x3b0]!=1u||
       ((const uint32_t *)(const void *)root)[0x170/4]!=(uint32_t)(uintptr_t)menu_rows)return 0;
    uint32_t selected=*(const uint16_t *)(const void *)(root+0xb8);
    if(selected<47u||selected>=47u+owned_count())return 0;
    return gr2_settings_menu_route(menu_rows[selected][3]);
}

/* Resolve geometry/font metadata through a real stock setup-title contract,
 * then replace only the resolved UTF-16 pointer for the private caption. */
extern uint32_t gr2_menu_descriptor_original(uint32_t,uint32_t *);
uint32_t gr2_menu_descriptor(uint32_t context,uint32_t *descriptor){
    uint32_t id=descriptor[0],owned=id>=0x70068u&&id<=0x7006au;
    if(owned)descriptor[0]=670u;
    uint32_t result=gr2_menu_descriptor_original(context,descriptor);
    if(owned){descriptor[0]=id;descriptor[12]=(uint32_t)(uintptr_t)gr2_menu_text(id);}
    return result;
}
