/* M10V menu adapters for the exact official ImageControlController ABI.
 * Count/index/max adapters are called only from this controller; the global
 * stock model APIs remain unchanged for ADJ and detail controllers.
 * Browsing private entries never writes a private ID to stock tone storage.
 * Explicit confirmation commits a validated journal and then activates one of
 * the five real stock slots. The original controller owns view allocation.
 */
#include "m10v_tone.h"
#include "m10v_library.h"
#include "m10v_debug.h"
#ifndef M10V_ISP_NATIVE_GRAIN_MODE
#define M10V_ISP_NATIVE_GRAIN_MODE 0
#endif
#if M10V_SD_LIBRARY
#include "m10v_sd_library.h"
#endif
#ifndef M10V_NATIVE_BASE
#define M10V_NATIVE_BASE 0x540b6000u
#endif
typedef uint32_t (*get_fn)(uint32_t);
typedef uint32_t (*call2_fn)(uint32_t, uint32_t);
typedef uint32_t (*call3_fn)(uint32_t, uint32_t, uint32_t);
typedef uint32_t (*root_fn)(void);
#if M10V_SD_LIBRARY
extern uint32_t m10v_settings_controller_ab_setup(uint32_t,uint32_t,uint32_t);
#endif

/* The persistent catalog keeps IDs 1..65 for existing journals. Only the
 * curated 800T and original 32 simulations are offered for replacement. */
static const uint8_t counts[23] = {M10V_TONE_CHOICES+1,7,55,4,0,7,5,4,4,4,3,9,9,9,0,0,0,0,0,0,0,3,4};
static uint8_t *model(void) {
    uint32_t root = ((root_fn)0x5320ad88u)();
    return (uint8_t *)(uintptr_t)((get_fn)0x5320ba9cu)(root);
}
static int supported(const uint8_t *m) {
    return (uintptr_t)m == 0x55068200u && m[0x1b] == 0;
}
static uint32_t mode(const uint8_t *m) { return supported(m) && m[0x1d] <= 22 ? m[0x1d] : 0; }
static uint32_t slot(const uint8_t *m) {
    /* Byte 0x1e is padding after the stock last member at 0x1c. Keep
     * the original m[0] entry snapshot intact for stock cancellation. */
    uint32_t tone = mode(m) && m[0x1e] ? m[0x1e] : m[0];
    for (uint32_t i = 0; i < M10V_SLOT_COUNT; ++i) if (tone == m10v_slot_tone(i)) return i;
    return 0;
}
static uint32_t root_rows(const uint8_t *m,uint32_t index){
    m10v_library_state state;uint32_t film=0;
    if(m10v_camera_library_load(&state)>=0)film=state.slots[slot(m)].film;
    uint32_t rows[5],n=0;
    if(M10V_ISP_NATIVE_GRAIN_MODE&&film!=M10V_CHAR_ID&&film!=M10V_PIXEL_ID)rows[n++]=130;
    rows[n++]=132;
    if(film==33||film==67||film==68||film==M10V_CHAR_ID)rows[n++]=film==M10V_CHAR_ID?359:film==68?340:film==67?339:214;
    return index==0xffffffffu?n:index<n?rows[index]:0;
}
static uint32_t group_count(uint32_t group,const uint8_t *m){
    if(group==0)return m10v_camera_library_shooting_count()+1;
    if(group==6){m10v_library_state state;m10v_camera_library_load(&state);return m10v_library_count(&state);}
    if(group==1)return root_rows(m,0xffffffffu);
    if(group==3){m10v_library_state state;if(!M10V_ISP_NATIVE_GRAIN_MODE||m10v_camera_library_load(&state)<0||state.slots[slot(m)].film==M10V_CHAR_ID||state.slots[slot(m)].film==M10V_PIXEL_ID)return 0;}
    return counts[group];
}
uint32_t m10v_menu_count(uint32_t address) {
    const uint8_t *m = (const uint8_t *)(uintptr_t)address;
    if (!supported(m)) return ((get_fn)(M10V_NATIVE_BASE + 0x80u))(address);
    return group_count(mode(m),m);
}
uint32_t m10v_menu_max_count(void) { return 55; }
uint32_t m10v_menu_index(uint32_t address, uint32_t index) {
    const uint8_t *m = (const uint8_t *)(uintptr_t)address;
    if (!supported(m)) return ((call2_fn)(M10V_NATIVE_BASE + 0x90u))(address, index);
    uint32_t group = mode(m);
    if (!group) {
        if(index==m10v_camera_library_menu_index())return 128;
        if(M10V_APPENDED_SLOTS&&index>=12&&index<14)return 23+index-12;
        if(M10V_APPENDED_SLOTS&&index>=14&&index<m10v_camera_library_menu_index())return 25+index-14;
        return ((call2_fn)(M10V_NATIVE_BASE + 0x90u))(address,index);
    }
    if (index >= group_count(group,m)) return 0;
    static const uint8_t first[15] = {0,129,144,176,180,184,208,192,196,200,218,224,224,224,233};
    if(group==0)return m10v_camera_library_shooting_count()+1;
    if(group==6){m10v_library_state state;m10v_camera_library_load(&state);return m10v_library_count(&state);}
    if(group==1)return root_rows(m,index);
    if(group==22)return 355+index;
    if(group==2&&index==47)return 360;
    if(group==2&&index==14)return 354;
    if(group==2&&index>=48&&index<=54)return 400+index-48;
    if(group==2&&index==47)return 360;
    if(group==2&&index>14)index--;
    if(group==2)return index==0?213:index<=13?(index<=3?287+index:340+index):256+index-14;
    if(group==21)return 341+index;

    return first[group]+index;
}
static uint32_t resource(uint32_t tone) {
    if(tone==360)return M10V_SD_LIBRARY?1023:953;
    if(tone>=400&&tone<=406)return (M10V_SD_LIBRARY?1104:954)+tone-400;
    if(tone==354)return M10V_SD_LIBRARY?1012:947;
    if(tone==359)return M10V_SD_LIBRARY?1013:948;
    if(tone>=355&&tone<=358)return (M10V_SD_LIBRARY?1014:949)+tone-355;
    if(tone>=344&&tone<=353)return (M10V_SD_LIBRARY?978:937)+tone-344;
    if(tone==288)return 911;
    if(tone==289||tone==290)return 930+tone-289;
    if(tone==339)return 932;
    if(tone>=340&&tone<=343)return 933+tone-340;
    if(tone>=256&&tone<288)return 879+tone-256;
    if(tone==214)return 861;
    if(tone>=218&&tone<222)return 862+tone-218;
    if(tone>=224&&tone<233)return 866+tone-224;
    if(tone>=233&&tone<237)return 875+tone-233;
    if (tone == 213) return 860;
    if (tone >= 144 && tone < 176) return 786 + tone - 144;
    for (uint32_t i = 0; i < M10V_SLOT_COUNT; ++i) if (tone == m10v_slot_tone(i)) return i<5?818+i:818;
    if (tone == 128) return 825;
    if (tone >= 129 && tone < 134) return 826 + tone - 129;
    if (tone >= 176 && tone < 180) return 831 + tone - 176;
    if (tone >= 180 && tone < 184) return 835 + tone - 180;
    if (tone >= 184 && tone < 191) return 839 + tone - 184;
    if (tone >= 192 && tone < 196) return 846 + tone - 192;
    if (tone >= 196 && tone < 200) return 850 + tone - 196;
    if (tone >= 200 && tone < 204) return 854 + tone - 200;
    if (tone >= 208 && tone < 213) return 818 + tone - 208;
    return 0;
}
static uint32_t film_resource(uint32_t film) {
    if(M10V_EXTRA_FILM(film))return M10V_EXTRA_FILM_NAME(film);
    if(M10V_C41(film))return M10V_C41_NAME_FIRST+film-312;
    if(M10V_ANIME_E6(film))return 1142+film-306;
    if(M10V_D76(film))return (M10V_SD_LIBRARY?1130:962)+film-M10V_D76_FIRST;
    if(film==M10V_5213_ID)return M10V_SD_LIBRARY?1128:961;
    if(film==M10V_PIXEL_ID)return M10V_SD_LIBRARY?1023:953;
    if(M10V_STYLE(film))return (M10V_SD_LIBRARY?1104:954)+film-M10V_STYLE_FIRST;
    if(film==M10V_CHAR_ID)return M10V_SD_LIBRARY?1012:947;
    if (film >= 1 && film <= 32) return 786 + film - 1;
    if (film == 66) return 911;
    if (film >= 69 && film <= 78) return (M10V_SD_LIBRARY?978:937)+film-69;
    if (film >= 67 && film <= 68) return 930+film-67;
    if (film == 33) return 860;
    if (film >= 34 && film <= 65) return 879 + film - 34;
    return 0;
}
uint32_t m10v_menu_name(uint32_t translator, uint32_t tone) {
    if(M10V_APPENDED_SLOTS&&(tone==23||tone==24))return ((call2_fn)(M10V_NATIVE_BASE+0x20u))(translator,tone);
    for (uint32_t i = 0; i < M10V_SLOT_COUNT; ++i) {
        if ((tone == m10v_slot_tone(i) || (i<5&&tone == 208 + i)) && (M10V_APPENDED_SLOTS||supported(model()))) {
            m10v_library_state state;
            /* Load initializes the compiled defaults even when storage is
             * unavailable. Never index a catalog with an unchecked journal. */
            m10v_camera_library_load(&state);
            if (m10v_library_valid(&state)) {
#if M10V_SD_LIBRARY
                if(M10V_CUSTOM(state.slots[i].film))return i<5?1007+i:1111+i-5;
#endif
                return film_resource(state.slots[i].film);
            }
        }
    }
    uint32_t id = resource(tone);
    return id ? id : ((call2_fn)(M10V_NATIVE_BASE + 0x10u))(translator, tone);
}
uint32_t m10v_menu_value_name(uint32_t translator, uint32_t value) {
    if(M10V_APPENDED_SLOTS&&m10v_tone_slot(value)<M10V_SLOT_COUNT)return m10v_menu_name(translator,value);
    if (mode(model()) && (value == 23 || value == 24)) return value == 23 ? 858 : 859;
    return ((call2_fn)(M10V_NATIVE_BASE + 0x20u))(translator, value);
}
uint32_t m10v_menu_icon(uint32_t translator, uint32_t tone) {
    if(M10V_APPENDED_SLOTS&&(tone==23||tone==24))return ((call2_fn)(M10V_NATIVE_BASE+0x40u))(translator,tone);
    if(tone==360)return M10V_SD_LIBRARY?761:755;
    if(tone>=400&&tone<=406)return 762+tone-400;
    if(tone==354)return M10V_SD_LIBRARY?755:749;
    if(tone>=144 && tone<176)return 671+tone-144;
    if(tone>=344&&tone<=353)return 739+tone-344;
    if(tone>=288&&tone<=290)return 736+tone-288;
    if(tone==213)return 703;
    if(tone>=256 && tone<288)return 704+tone-256;
    uint8_t *m=model();
    if(M10V_APPENDED_SLOTS||supported(m))for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)if(tone==m10v_slot_tone(i) || (i<5&&tone==208+i)){
        m10v_library_state state;
        if(m10v_camera_library_load(&state)>=0){
#if M10V_SD_LIBRARY
            if(M10V_CUSTOM(state.slots[i].film))return 754;
#endif
            if(M10V_EXTRA_FILM(state.slots[i].film))return M10V_EXTRA_FILM_ICON(state.slots[i].film);
            if(M10V_C41(state.slots[i].film))return M10V_C41_ICON_FIRST+state.slots[i].film-312;
            if(M10V_ANIME_E6(state.slots[i].film))return M10V_ANIME_E6_ICON_FIRST+state.slots[i].film-M10V_ANIME_FIRST;
            if(M10V_D76(state.slots[i].film))return 775+state.slots[i].film-M10V_D76_FIRST;
            if(state.slots[i].film==M10V_5213_ID)return 774;
            if(M10V_STYLE(state.slots[i].film))return 762+state.slots[i].film-M10V_STYLE_FIRST;
            return state.slots[i].film==M10V_PIXEL_ID?(M10V_SD_LIBRARY?761:755):state.slots[i].film==M10V_CHAR_ID?(M10V_SD_LIBRARY?755:749):670+state.slots[i].film;
        }
    }
    return tone==128?671:tone>=128?0x224:((call2_fn)(M10V_NATIVE_BASE + 0x30u))(translator, tone);
}
uint32_t m10v_menu_value_icon(uint32_t translator, uint32_t value) {
    if(M10V_APPENDED_SLOTS&&m10v_tone_slot(value)<M10V_SLOT_COUNT)return m10v_menu_icon(translator,value);
    return ((call2_fn)(M10V_NATIVE_BASE + 0x40u))(translator, value);
}
/* This tag comes from the photograph's ImageTone, never the selected journal. */
uint32_t m10v_menu_recorded_icon(uint32_t tag){
 if((tag&0xffff0000u)!=0x20000u)return tag>=0x1000cu&&tag<=0x10015u?876:0;
 uint32_t code=(tag&65535u)+0x100u;
 if(code>=0x2000u&&code<=0xe0c5u)return 754;
 uint32_t film=code-0x1000u;if(!M10V_BUILTIN(film))return 0;
 if(M10V_EXTRA_FILM(film))return M10V_EXTRA_FILM_ICON(film);
 if(M10V_C41(film))return M10V_C41_ICON_FIRST+film-312;
 if(M10V_ANIME_E6(film))return M10V_ANIME_E6_ICON_FIRST+film-M10V_ANIME_FIRST;
 if(M10V_D76(film))return 775+film-M10V_D76_FIRST;
 if(film==M10V_5213_ID)return 774;
 if(M10V_STYLE(film))return 762+film-M10V_STYLE_FIRST;
 return film==M10V_PIXEL_ID?(M10V_SD_LIBRARY?761:755):film==M10V_CHAR_ID?(M10V_SD_LIBRARY?755:749):670+film;
}
uint32_t m10v_menu_focus(uint32_t controller, uint32_t index) {
    uint8_t *m = model();
    M10V_LOG(30,controller,index,m[0],(uint32_t)m[0x1d]|((uint32_t)m[0x1e]<<8));
    uint32_t result=0;
    if(M10V_APPENDED_SLOTS&&supported(m)&&!mode(m)&&index>=12&&index<m10v_camera_library_menu_index()){
        ((call2_fn)0x532bd61cu)((uint32_t)(uintptr_t)m,index<14?index-11:0);
        if(index>=14){uint32_t tone=25+index-14;
            if(((get_fn)0x532bd6b4u)((uint32_t)(uintptr_t)m)!=tone)
                ((call2_fn)0x532c26c0u)((uint32_t)(uintptr_t)m,tone);
        }return 0;
    }
    if (!(supported(m) && (mode(m) || index == m10v_camera_library_menu_index())))
        result=((call2_fn)(M10V_NATIVE_BASE + 0xa0u))(controller, index);
    M10V_LOG(31,controller,index,result,(uint32_t)m[0x1d]|((uint32_t)m[0x1e]<<8));
    return result;
}
static void redraw(uint32_t controller) {
    M10V_LOG(50,controller,0,0,0);
    ((get_fn)0x531ac074u)(controller);
    uint32_t view = *(const uint32_t *)(uintptr_t)(controller + 0x174u);
    uint8_t *m=model();uint32_t group=mode(m),selected=0,target=slot(m);
    if(group==6)selected=target;
    else if(group>=2&&group!=10){
        m10v_library_state state;
        if(m10v_camera_library_load(&state)>=0){const m10v_slot *v=&state.slots[target];
            /* Hidden historical looks stay active until an explicit confirm.
             * Their browsing cursor safely starts at 800T without a write. */
            if(group==2)selected=M10V_STYLE(v->film)?48+v->film-M10V_STYLE_FIRST:v->film==M10V_PIXEL_ID?47:v->film==M10V_CHAR_ID?14:v->film==33?0:v->film>=66?v->film-65:v->film>=34?v->film-19:0;
            else if(group==3)selected=v->grain;else if(group==4)selected=0;
            else if(group==5)selected=state.stamp;else if(group==7)selected=state.format;
            else if(group==8)selected=state.corner;else if(group==9)selected=state.color;
            else if(group==22)selected=state.effects[target].reserved[1];
            else if(group==21)selected=state.effects[target].film_exposure;
            else if(group==11)selected=v->halo_gain;else if(group==12)selected=v->halo_spread;
            else if(group==13)selected=v->halo_threshold;else if(group==14)selected=v->halo_profile;
        }
    }
    ((call2_fn)0x53395430u)(view, selected);
    M10V_LOG(51,controller,selected,group,target);
}
static void activate(uint8_t *m,uint32_t tone){
    if(M10V_APPENDED_SLOTS)((call2_fn)0x532bd61cu)((uint32_t)(uintptr_t)m,0);
    ((call2_fn)(M10V_NATIVE_BASE+0x00u))((uint32_t)(uintptr_t)m,tone);
}
static void failure(uint32_t controller) {
    uint32_t caption = *(const uint32_t *)(uintptr_t)(controller + 0x160u);
    ((call3_fn)0x53396f80u)(caption, 824, 0);
}
#if M10V_DEBUG_MODE
static uint32_t menu_confirm_impl(uint32_t controller) {
#else
uint32_t m10v_menu_confirm(uint32_t controller) {
#endif
    uint8_t *m = model();
    if (!supported(m)) return ((get_fn)(M10V_NATIVE_BASE + 0x60u))(controller);
    uint32_t view = *(const uint32_t *)(uintptr_t)(controller + 0x174u);
    uint32_t index = ((get_fn)0x53394820u)(view), group = mode(m);
    if((group>=15&&group<=20)||group==4)return 0;
    if (!group) {
        if (index != m10v_camera_library_menu_index()) return ((get_fn)(M10V_NATIVE_BASE + 0x60u))(controller);
        /* The stock entry snapshot at m[0] does not follow live browsing.
         * Capture the actual tone before switching to the private menu. */
        uint32_t active = ((get_fn)0x532bd6b4u)((uint32_t)(uintptr_t)m);
        m[0x1e] = 0;
        for (uint32_t i = 0; i < M10V_SLOT_COUNT; ++i) if (active == m10v_slot_tone(i)) m[0x1e] = (uint8_t)active;
        m[0x1d] = 1; redraw(controller); return 0;
    }
    if (index == group_count(group,m)) {
        m[0x1d] = group==1?0:group==22?1:group==21?1:group>=11?10:group==10?1:group>=7?5:1;
        redraw(controller); return 0;
    }
    if (index == (uint32_t)group_count(group,m) + 1) {
        m[0x1d] = 0; return ((get_fn)(M10V_NATIVE_BASE + 0x60u))(controller);
    }
    if (index >= group_count(group,m)) return 0;
    if(group==1){
        uint32_t item=root_rows(m,index);
        m[0x1d]=(uint8_t)(item==129?2:item==130?3:item==132?5:item==133?6:item==340?21:item==359?22:10);
        redraw(controller);return 0;
    }
    if (group == 6) {
        m[0x1e] = m10v_slot_tone(index);
        activate(m,m10v_slot_tone(index));
        m[0x1d] = 1; redraw(controller); return 0;
    }
    if (group == 5 && index >= 3) {
        if (index <= 5) m[0x1d] = (uint8_t)(index + 4);
        else m[0x1d] = 1;
        redraw(controller); return 0;
    }
    if(group==10){m[0x1d]=(uint8_t)(11+index);redraw(controller);return 0;}
    m10v_library_state state;
    if (m10v_camera_library_load(&state) < 0) { failure(controller); return 0; }
    uint32_t target = slot(m); int result;
    M10V_LOG(60,controller,index,group,target);
    if(group==22)result=m10v_camera_library_effects(&state,target,7,index);
    else if(group==21)result=m10v_camera_library_effects(&state,target,6,index);
    else if(group>=11){const m10v_slot *v=&state.slots[target];
        result=m10v_camera_library_halation(&state,target,group==11?index:v->halo_gain,group==12?index:v->halo_spread,group==13?index:v->halo_threshold,group==14?index:v->halo_profile);
    }
    else if (group == 2) result = m10v_camera_library_select(&state, target, index>=48&&index<=54?M10V_STYLE_FIRST+index-48:index==47?M10V_PIXEL_ID:index==14?M10V_CHAR_ID:index==0?33:index<=13?65+index:19+index);
    else if (group == 3) result = m10v_camera_library_texture(&state, target, index, state.slots[target].soft);
    else if (group == 4) return M10V_LIBRARY_INVALID;
    else result = m10v_camera_library_stamp(&state, group == 5 ? index : state.stamp,
        group == 7 ? index : state.format, group == 8 ? index : state.corner, group == 9 ? index : state.color);
    M10V_LOG(61,controller,(uint32_t)result,group,state.slots[target].film);
    if (result) { failure(controller); return 0; }
    if (group == 2) activate(m,m10v_slot_tone(target));
    m[0x1d] = group==22?1:group==21?1:group>=11?10:group >= 7 || group == 5 ? 5 : 1;
    redraw(controller); return 0;
}
#if M10V_DEBUG_MODE
uint32_t m10v_menu_confirm(uint32_t controller) {
    uint8_t *m=model();M10V_LOG(40,controller,m[0],m[0x1d],m[0x1e]);
    uint32_t result=menu_confirm_impl(controller);
    M10V_LOG(41,controller,result,m[0x1d],m[0x1e]);return result;
}
static uint32_t menu_key_impl(uint32_t controller, uint32_t event) {
#else
uint32_t m10v_menu_key(uint32_t controller, uint32_t event) {
#endif
    uint8_t *m = model();
#if M10V_SD_LIBRARY
    if(m10v_settings_controller_ab_setup(controller,event,0x02000012u))return 1;
#endif
    if (supported(m)) {
        uint16_t key = *(const uint16_t *)(uintptr_t)event;
        if (key == 0xd8) return m10v_menu_confirm(controller);
        if (mode(m) && key == 0xde) return 0;
        if (key == 0x89 || key == 0xda) m[0x1d] = 0;
        if (mode(m) && (key == 0x86 || key == 0x87)) {
            m[0x1d] = 0; return ((get_fn)(M10V_NATIVE_BASE + 0x60u))(controller);
        }
    }
    return ((call2_fn)(M10V_NATIVE_BASE + 0x50u))(controller, event);
}
#if M10V_DEBUG_MODE
uint32_t m10v_menu_key(uint32_t controller,uint32_t event) {
    uint16_t key=*(const uint16_t *)(uintptr_t)event;
    uint8_t *m=model();M10V_LOG(20,controller,key,m[0],m[0x1d]);
    uint32_t result=menu_key_impl(controller,event);
    M10V_LOG(21,controller,key,result,m[0x1d]);return result;
}
#endif
uint32_t m10v_menu_enter(uint32_t controller) {
    M10V_LOG(10,controller,0,0,0);
    uint8_t *m = model(); if (supported(m)) { m[0x1d] = 0; m[0x1e] = 0; }
    uint32_t result=((get_fn)(M10V_NATIVE_BASE + 0xb0u))(controller);
    M10V_LOG(11,controller,result,m[0],m[0x1d]);return result;
}

#if M10V_SD_LIBRARY
/* The resource adapter reserves 80 bytes in the ORIGINAL getter's stack frame.
 * Descriptor + UTF-16 live until that getter restores SP from FP; no retained
 * heap pointer, writable ROM descriptor or shared scratch is published. The
 * first 16 bytes remain available for original outgoing stack arguments. */
uint32_t m10v_menu_custom_resource(uint32_t resource,uint32_t *out){
 uint32_t slot;
 if(resource>=1007&&resource<=1011)slot=resource-1007;
 else if(resource>=1111&&resource<=1115)slot=resource-1111+5;
 else return 0;
 if(!out)return 0;
 char name[24];const char *text="Custom LUT";m10v_library_state state;
 if(m10v_camera_library_load(&state)>=0&&m10v_sd_camera_custom_name(&state,slot,name,sizeof(name)))text=name;
 uint16_t *utf=(uint16_t *)(out+2);uint32_t n=0;
 for(;n<23&&text[n];n++)utf[n]=(uint8_t)text[n];utf[n++]=0;
 out[0]=n|0x100u;out[1]=(uint32_t)(uintptr_t)utf;
 return (uint32_t)(uintptr_t)out;
}
#endif
