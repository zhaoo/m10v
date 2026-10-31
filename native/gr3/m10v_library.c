#include "m10v_capture_profile.h"
/* Original M10V runtime. Existing simulation tables are embedded losslessly
 * with their source notices; no third-party camera runtime or signed film
 * package is loaded. Camera services have separately verified ABI boundaries. */
#include "m10v_library.h"
#include "m10v_film_directory.h"
#include "halation_core.h"
#include "film_5207.h"
#include "m10v_color_cache.h"
#include <stddef.h>
#ifndef M10V_LEGACY_SETTINGS
#define M10V_LEGACY_SETTINGS 0
#endif
#include "m10v_legacy_data.h"
#include "halation_energy.h"
#if M10V_UNIVERSAL_HALATION
#include "m10v_universal_halation.h"
#endif

typedef struct {
    char name[24];
    int16_t contrast, saturation, turn;
    int8_t lift, bend, cb, cr;
} film;

/* Original M10V looks, specified in a software Y/CbCr color domain.
 * Names describe these looks; they do not claim a measured film-stock match. */
static const film films[33] = {
    {"M10V Neutral",256,256,0,0,0,0,0},
    {"Amber Day",268,264,0,2,5,-8,10},
    {"Cool Dusk",252,238,0,4,-2,12,-5},
    {"Warm Fade",232,224,0,12,4,-6,8},
    {"Deep Street",294,244,0,-3,-4,3,1},
    {"Soft Portrait",238,226,0,8,6,-3,5},
    {"Ocean Blue",264,272,-8,0,3,10,-6},
    {"Autumn Copper",270,248,12,2,4,-10,12},
    {"Muted Olive",242,202,-12,8,1,-5,-3},
    {"Clear Morning",252,250,0,5,8,1,2},
    {"Night Cyan",286,236,-4,-2,-3,10,-3},
    {"Sunset Rose",254,258,8,4,5,-3,12},
    {"Bleached Noon",278,164,0,5,-2,-2,3},
    {"Pastel Sky",222,218,0,13,9,4,0},
    {"Dense Color",290,302,0,-1,1,0,0},
    {"Earth Tone",264,224,6,6,0,-8,5},
    {"Silver Mono",270,0,0,1,1,0,0},
    {"Soft Mono",222,0,0,12,6,0,0},
    {"Hard Mono",316,0,0,-5,-2,0,0},
    {"Warm Mono",252,0,0,6,3,-4,5},
    {"Cold Mono",266,0,0,3,-1,6,-3},
    {"Green Glass",256,246,-10,4,2,-6,-6},
    {"Lilac Haze",234,222,8,10,6,7,5},
    {"Desert Light",274,236,0,8,8,-10,5},
    {"Urban Steel",272,208,-3,2,-4,8,-4},
    {"Spring Leaf",246,280,-8,7,4,-3,-3},
    {"Red Brick",276,270,9,0,1,-5,10},
    {"Paper White",236,180,0,14,8,0,0},
    {"Blue Hour",268,216,-6,5,-2,14,-7},
    {"Golden Shade",244,242,4,10,4,-9,8},
    {"Low Key Color",304,250,0,-6,-4,2,3},
    {"High Key Color",230,230,0,17,10,-2,3},
    {"800T",264,238,0,1,3,10,-16}
};

static uint32_t checksum(const m10v_library_state *state) {
    const uint8_t *bytes = (const uint8_t *)state;
    uint32_t crc = 0xffffffffu;
    for (uint32_t i = 0; i < offsetof(m10v_library_state, crc); ++i) {
        crc ^= bytes[i];
        for (uint32_t bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}
static void copy_state(m10v_library_state *dst, const m10v_library_state *src) {
    for (uint32_t i = 0; i < sizeof(*src); ++i)
        ((uint8_t *)dst)[i] = ((const uint8_t *)src)[i];
}
void m10v_library_init(m10v_library_state *state) {
    if (!state) return;
    for (uint32_t i = 0; i < sizeof(*state); ++i) ((uint8_t *)state)[i] = 0;
#ifdef M10V_INITIAL_STATE_BYTES
    static const uint8_t initial[sizeof(*state)] = {M10V_INITIAL_STATE_BYTES};
    for (uint32_t i = 0; i < sizeof(*state); ++i) ((uint8_t *)state)[i] = initial[i];
#else
    state->magic = 0x5630314du; state->version = 5; state->size = sizeof(*state);
    for (uint32_t i = 0; i < 5; ++i) {
        state->slots[i].film = (uint16_t)(i == 4 ? 33 : i + 34);
        state->slots[i].halo_gain=0; state->slots[i].halo_spread=3;
        /* Retired texture bytes remain zero for new records. */
        state->slots[i].halo_threshold=5; state->slots[i].halo_profile=2;
    }
    state->crc = checksum(state);
#endif
}
int m10v_library_valid(const m10v_library_state *state) {
    if (!state || state->magic != 0x5630314du || state->version != 5 ||
        state->size != sizeof(*state) || (state->reserved & ~511u) || state->stamp > 2 ||
        state->format > 3 || state->corner > 3 || state->color > 3 || state->crc != checksum(state)) return 0;
    uint32_t migration_old=(state->reserved>>1)&15u,migration_new=(state->reserved>>5)&15u;
    if((!migration_old)!=(!migration_new)||migration_old>M10V_SLOT_COUNT||migration_new>M10V_SLOT_COUNT)return 0;
    for (uint32_t i = 0; i < M10V_SLOT_COUNT; ++i)
        if (( state->slots[i].film > M10V_CUSTOM_MAX_ID && !M10V_BUILTIN(state->slots[i].film)) ||
            state->slots[i].grain > 3 || state->slots[i].soft > 3 || state->slots[i].halo_gain>8 || state->slots[i].halo_spread>8 ||
            state->slots[i].halo_threshold>8 || state->slots[i].halo_profile>6) return 0;
    for(uint32_t i=0;i<M10V_SLOT_COUNT;i++){const m10v_film_effects *e=&state->effects[i];
        if(!state->slots[i].film){for(uint32_t j=0;j<sizeof(m10v_slot);j++)if(((const uint8_t *)&state->slots[i])[j])return 0;for(uint32_t j=0;j<sizeof(*e);j++)if(((const uint8_t *)e)[j])return 0;continue;}
        if(M10V_LEGACY_SETTINGS&&i>=5)return 0;
        if(!M10V_LEGACY_SETTINGS)for(uint32_t j=0;j<i;j++)if(!state->slots[j].film||state->slots[j].film==state->slots[i].film||(M10V_CUSTOM(state->slots[i].film)&&M10V_CUSTOM(state->slots[j].film)&&state->effects[j].reserved[0]==e->reserved[0]&&e->reserved[0]<M10V_CUSTOM_IMMUTABLE_FIRST))return 0;
        if(e->grain_size>2||e->leak_gain>8||e->leak_position>5||e->leak_spread>8||e->leak_variation>1||e->film_exposure>2||(state->slots[i].film==67?e->film_exposure>1:state->slots[i].film!=68&&e->film_exposure)||((state->slots[i].film==M10V_CHAR_ID||M10V_ANIME(state->slots[i].film))?e->reserved[1]>3:e->reserved[1]!=0)||
           (M10V_BUILTIN(state->slots[i].film)?e->reserved[0]!=0:(e->reserved[0]<1||e->reserved[0]>M10V_CUSTOM_MAX_BANK+1)))return 0;}
    return 1;
}
const char *m10v_library_name(uint32_t id) {
    const char *name=m10v_directory_name(id);if(name)return name;
    static const char appended_names[13][20]={"5207","Phoenix II","HARMAN RED","Portra 160","Fuji Industrial 100","Lucky C200","CCD Classic","Fuji C200","ProImage 100","T-Max 100","Aerochrome","2460","5203"};
    if(id==M10V_PIXEL_ID)return "Pixel World";
    static const char style_names[7][24]={"Leica Monochrome","Lomography","Polaroid","Fujifilm Velvia 50","Cyberpunk","Cyanotype","German Cool"};
    if(M10V_STYLE(id))return style_names[id-M10V_STYLE_FIRST];
    if(id==M10V_CHAR_ID)return "Kodak Charmera";
    return !id || id>M10V_FILM_COUNT ? (const char *)0 : id>=66 ? appended_names[id-66] : id<=33 ? films[id-1].name : legacy_records[id-34].name;
}
static int commit(m10v_library_state *state, m10v_library_state *next,
                  m10v_library_store store, void *context) {
    if (!store || state->sequence == 0xffffffffu) return M10V_LIBRARY_INVALID;
    next->sequence = state->sequence + 1; next->crc = checksum(next);
    if(!m10v_library_valid(next))return M10V_LIBRARY_INVALID;
    if (store(context, next) != 0) return M10V_LIBRARY_STORE_FAILED;
    copy_state(state, next); return M10V_LIBRARY_OK;
}
uint32_t m10v_library_count(const m10v_library_state *state){
    uint32_t n=0;if(state)while(n<M10V_SLOT_COUNT&&state->slots[n].film)n++;return n;
}
int m10v_library_remove(m10v_library_state *state,uint32_t slot,m10v_library_store store,void *context){
    if(!m10v_library_valid(state)||slot>=m10v_library_count(state))return M10V_LIBRARY_INVALID;
    m10v_library_state next;copy_state(&next,state);
    for(uint32_t i=slot;i+1<M10V_SLOT_COUNT;i++){next.slots[i]=next.slots[i+1];next.effects[i]=next.effects[i+1];}
    m10v_slot empty={0};m10v_film_effects effects={0};next.slots[M10V_SLOT_COUNT-1]=empty;next.effects[M10V_SLOT_COUNT-1]=effects;
    return commit(state,&next,store,context);
}
int m10v_library_reset(m10v_library_state *state,uint32_t slot,m10v_library_store store,void *context){
    if(!m10v_library_valid(state)||slot>=M10V_SLOT_COUNT||!state->slots[slot].film)return M10V_LIBRARY_INVALID;
    m10v_library_state next,defaults;copy_state(&next,state);m10v_library_init(&defaults);
    uint32_t id=state->slots[slot].film;
    if(defaults.slots[slot].film!=id){
        m10v_slot *v=&defaults.slots[slot];v->film=(uint16_t)id;
        v->grain=0;v->soft=0;
        v->halo_gain=0;v->halo_spread=3;v->halo_threshold=5;v->halo_profile=id==66?1:2;
        m10v_film_effects e={0};defaults.effects[slot]=e;
    }
    defaults.slots[slot].grain=defaults.slots[slot].soft=defaults.slots[slot].halo_gain=0;
    defaults.effects[slot].leak_gain=0;
    next.slots[slot]=defaults.slots[slot];next.effects[slot]=defaults.effects[slot];
    if(M10V_CUSTOM(id))next.effects[slot].reserved[0]=state->effects[slot].reserved[0];
    return commit(state,&next,store,context);
}
int m10v_library_select(m10v_library_state *state, uint32_t slot, uint32_t id,
                        m10v_library_store store, void *context) {
    if (!m10v_library_valid(state) || slot >= (M10V_LEGACY_SETTINGS?5u:M10V_SLOT_COUNT) || (!M10V_LEGACY_SETTINGS&&slot>m10v_library_count(state)) || !M10V_BUILTIN(id) || M10V_ANIME(id))
        return M10V_LIBRARY_INVALID;
    if(!M10V_LEGACY_SETTINGS)for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)if(i!=slot&&state->slots[i].film==id)return M10V_LIBRARY_INVALID;
    m10v_library_state next; copy_state(&next, state); next.slots[slot].film = (uint16_t)id;
    next.effects[slot].reserved[0]=0;
    /* Switching film starts with color only. Same-film selection and durable
     * journals preserve manual settings; no migration silently clears them. */
    if(state->slots[slot].film!=id){
        m10v_slot *v=&next.slots[slot];v->grain=0;v->soft=0;v->halo_gain=0;
        v->halo_spread=3;v->halo_threshold=5;v->halo_profile=id==66?1:2;
        m10v_film_effects e={0};next.effects[slot]=e;
    }
    if(id!=M10V_CHAR_ID)next.effects[slot].reserved[1]=0;
    if(id==M10V_CHAR_ID&&state->slots[slot].film!=id)next.slots[slot].grain=0;
    if(id!=state->slots[slot].film||(id!=67&&id!=68))next.effects[slot].film_exposure=0;
    return commit(state, &next, store, context);
}
int m10v_library_select_custom(m10v_library_state *state,uint32_t slot,uint32_t id,uint32_t bank,m10v_library_store store,void *context){
 if(!m10v_library_valid(state)||slot>=(M10V_LEGACY_SETTINGS?5u:M10V_SLOT_COUNT)||id<=M10V_FILM_COUNT||id>M10V_CUSTOM_MAX_ID||(!M10V_LEGACY_SETTINGS&&slot>m10v_library_count(state))||bank>M10V_CUSTOM_MAX_BANK)return M10V_LIBRARY_INVALID;
 if(!M10V_LEGACY_SETTINGS)for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)if(i!=slot&&state->slots[i].film==id)return M10V_LIBRARY_INVALID;
 m10v_library_state next;copy_state(&next,state);next.slots[slot].film=(uint16_t)id;
 next.slots[slot].grain=next.slots[slot].soft=next.slots[slot].halo_gain=0;
 if(state->slots[slot].film!=id||state->effects[slot].reserved[0]!=(uint8_t)(bank+1))next.slots[slot].halo_profile=2;
 if(state->slots[slot].film!=id)next.effects[slot].leak_gain=0;
 next.effects[slot].reserved[1]=0;next.effects[slot].film_exposure=0;next.effects[slot].reserved[0]=(uint8_t)(bank+1);
 return commit(state,&next,store,context);
}
int m10v_library_texture(m10v_library_state *state, uint32_t slot, uint32_t grain, uint32_t soft,
                         m10v_library_store store, void *context) {
    if (!m10v_library_valid(state) || slot >= M10V_SLOT_COUNT || !state->slots[slot].film || grain > 3 || soft > 3 ||
        (grain && (state->slots[slot].film==M10V_CHAR_ID || state->slots[slot].film==M10V_PIXEL_ID)))
        return M10V_LIBRARY_INVALID;
    m10v_library_state next; copy_state(&next, state);
    next.slots[slot].grain = (uint8_t)grain; next.slots[slot].soft = (uint8_t)soft;
    return commit(state, &next, store, context);
}
int m10v_library_halation(m10v_library_state *state,uint32_t slot,uint32_t gain,uint32_t spread,uint32_t threshold,uint32_t profile,m10v_library_store store,void *context) {
    if(!m10v_library_valid(state)||slot>=M10V_SLOT_COUNT||!state->slots[slot].film||(!M10V_UNIVERSAL_HALATION&&(state->slots[slot].film==66||state->slots[slot].film==68)&&profile<=3)||gain>8||spread>8||threshold>8||profile>6)return M10V_LIBRARY_INVALID;
    m10v_library_state next;copy_state(&next,state);
    next.slots[slot].halo_gain=(uint8_t)gain;next.slots[slot].halo_spread=(uint8_t)spread;
    next.slots[slot].halo_threshold=(uint8_t)threshold;next.slots[slot].halo_profile=(uint8_t)profile;
    return commit(state,&next,store,context);
}
int m10v_library_detail(m10v_library_state *state,uint32_t slot,uint32_t gain,uint32_t spread,uint32_t threshold,uint32_t grain,uint32_t soft,m10v_library_store store,void *context) {
    if(!m10v_library_valid(state)||slot>=M10V_SLOT_COUNT||state->slots[slot].film!=33||gain>8||spread>8||threshold>8||grain>3||soft>3)return M10V_LIBRARY_INVALID;
    m10v_library_state next;copy_state(&next,state);
    m10v_slot *v=&next.slots[slot];v->halo_gain=(uint8_t)gain;v->halo_spread=(uint8_t)spread;
    v->halo_threshold=(uint8_t)threshold;v->grain=(uint8_t)grain;v->soft=(uint8_t)soft;v->halo_profile=2;
    return commit(state,&next,store,context);
}
int m10v_library_stamp(m10v_library_state *state, uint32_t enabled, uint32_t format,
                       uint32_t corner, uint32_t color, m10v_library_store store, void *context) {
    if (!m10v_library_valid(state) || enabled > 2 || format > 3 || corner > 3 || color > 3)
        return M10V_LIBRARY_INVALID;
    m10v_library_state next; copy_state(&next, state);
    next.stamp = (uint8_t)enabled; next.format = (uint8_t)format;
    next.corner = (uint8_t)corner; next.color = (uint8_t)color;
    return commit(state, &next, store, context);
}
int m10v_library_film_name_stamp(m10v_library_state *state,uint32_t enabled,m10v_library_store store,void *context){
    if(!m10v_library_valid(state)||enabled>1)return M10V_LIBRARY_INVALID;
    m10v_library_state next;copy_state(&next,state);next.reserved=(next.reserved&~1u)|enabled;
    return commit(state,&next,store,context);
}
int m10v_library_effects(m10v_library_state *state,uint32_t slot,uint32_t field,uint32_t value,m10v_library_store store,void *ctx){
    if(!m10v_library_valid(state)||slot>=M10V_SLOT_COUNT||!state->slots[slot].film||field>7)return M10V_LIBRARY_INVALID;
    if(field==7?(state->slots[slot].film!=M10V_CHAR_ID||value>3):field==6?(state->slots[slot].film==67?value>1:state->slots[slot].film!=68||value>2):field<=5?value!=0:0)return M10V_LIBRARY_INVALID;
    m10v_library_state next;copy_state(&next,state);
    if(field==5){
        m10v_film_effects e={0,0,0,0,0,next.effects[slot].film_exposure,{0,0}};next.effects[slot]=e;
        next.effects[slot].reserved[0]=state->effects[slot].reserved[0];
        next.effects[slot].reserved[1]=state->effects[slot].reserved[1];
        next.slots[slot].grain=next.slots[slot].halo_gain=0;next.slots[slot].soft=0;
    } else if(field==7)next.effects[slot].reserved[1]=(uint8_t)value;
    else if(field==6)next.effects[slot].film_exposure=(uint8_t)value;
    else ((uint8_t *)&next.effects[slot])[field]=(uint8_t)value;
    return commit(state,&next,store,ctx);
}
#include "m10v_charmera.h"
#include "m10v_pixel_world.h"
static uint8_t clamp(int value) { return (uint8_t)(value < 0 ? 0 : value > 255 ? 255 : value); }
static int overlap(const void *a, uint32_t an, const void *b, uint32_t bn) {
    uintptr_t x = (uintptr_t)a, z = (uintptr_t)b;
    return x <= UINTPTR_MAX - an && z <= UINTPTR_MAX - bn && x < z + bn && z < x + an;
}
static int date_valid(const m10v_library_date *date) {
    static const uint8_t days[12] = {31,28,31,30,31,30,31,31,30,31,30,31};
    if (!date || date->year < 1980 || date->year > 2199 || !date->month || date->month > 12 ||
        !date->day || date->hour > 23 || date->minute > 59) return 0;
    uint32_t max = days[date->month - 1];
    if (date->month == 2 && date->year % 4 == 0 && (date->year % 100 != 0 || date->year % 400 == 0)) ++max;
    return date->day <= max;
}
static void digits(char *dst, uint32_t value, uint32_t count) {
    while (count) { --count; dst[count] = (char)('0' + value % 10); value /= 10; }
}
static uint32_t date_text(char *text, const m10v_library_date *date, uint32_t format, uint32_t mode) {
    uint32_t n = format == 3 ? 8 : 10;
    if (format == 1) { digits(text, date->day, 2); text[2] = '.'; digits(text + 3, date->month, 2);
        text[5] = '.'; digits(text + 6, date->year, 4); }
    else { uint32_t y = format == 3 ? 2 : 4; digits(text, date->year, y);
        text[y] = format == 2 ? '-' : '.'; digits(text + y + 1, date->month, 2);
        text[y + 3] = text[y]; digits(text + y + 4, date->day, 2); }
    if (mode == 2) { text[n++] = ' '; digits(text + n, date->hour, 2); n += 2;
        text[n++] = ':'; digits(text + n, date->minute, 2); n += 2; }
    return n;
}
/* Compact beveled segment outlines in a 55 x 108 design space. The same
 * slanted strokes serve dates and film names; no font atlas or frame allocation. */
static const uint8_t stamp_segments[13][13] = {
    {6,9,0,47,0,53,6,47,12,9,12,3,6},
    {6,49,14,55,8,55,43,49,49,43,43,43,20},
    {6,49,53,55,59,55,94,49,100,43,94,43,59},
    {6,9,96,47,96,53,102,47,108,9,108,3,102},
    {6,0,59,6,53,12,59,12,94,6,100,0,94},
    {6,0,8,6,14,12,20,12,43,6,49,0,43},
    {6,9,48,47,48,53,54,47,60,9,60,3,54},
    {5,14,17,21,19,30,42,26,47,21,43},
    {5,35,43,30,47,26,42,35,19,40,17},
    {5,21,65,26,61,30,66,21,89,14,91},
    {5,40,91,35,89,26,66,30,61,35,65},
    {6,24,15,30,15,32,19,32,42,27,47,22,42},
    {6,27,61,32,66,32,90,28,94,22,90,22,66},
};
static uint32_t stamp_mask(char c) {
    static const uint16_t numbers[10] = {63,6,91,79,102,109,125,7,127,111};
    static const uint16_t letters[26] = {119,127,57,63,121,113,125,118,6153,30,1328,56,438,1206,63,115,1087,1139,109,6145,62,816,1590,1920,4480,777};
    if(c>='0'&&c<='9')return numbers[c-'0'];
    if(c>='a'&&c<='z')c=(char)(c-'a'+'A');
    if(c>='A'&&c<='Z')return letters[c-'A'];
    if(c==' ')return 0;
    if(c=='-'||c=='_')return 1u<<(c=='-'?6:3);
    if(c=='/')return (1u<<8)|(1u<<9);
    if(c=='+')return (1u<<6)|(1u<<11)|(1u<<12);
    if(c=='(')return (1u<<5)|(1u<<4);
    if(c==')')return (1u<<1)|(1u<<2);
    if(c=='&')return 0x1ed9u;
    return (1u<<0)|(1u<<1)|(1u<<6)|(1u<<12);
}
static void stamp_pixel(m10v_library_image *image,const m10v_library_state *state,uint32_t x,uint32_t y,uint32_t pass,uint32_t direction){
    /* EXIF directions 1/2/3 display as CCW90/180/CW90. Transform only
     * a glyph sample, never the image planes or descriptors. */
    uint32_t sx=x,sy=y;
    if(direction==1){sx=image->width-1-y;sy=x;}
    else if(direction==2){sx=image->width-1-x;sy=image->height-1-y;}
    else if(direction==3){sx=y;sy=image->height-1-x;}
    x=sx;y=sy;
    static const uint8_t colors[4][3]={{235,128,128},{180,80,185},{82,90,240},{210,16,146}};
    if(x>=image->width||y>=image->height)return;
    image->y[y*image->stride+x]=pass?colors[state->color][0]:16;
    /* An odd visible width has no complete final CbCr pair. Do not write
     * its missing partner into padding, even for a rotated glyph. */
    if((x&~1u)+1>=image->width)return;
    uint32_t at=y*image->stride+(x&~1u);
    if(at+1>=image->chroma_bytes)return;
    image->chroma[at]=pass?colors[state->color][1]:128;
    image->chroma[at+1]=pass?colors[state->color][2]:128;
}
static void stamp_line_oriented(m10v_library_image *image,const m10v_library_state *state,const char *text,uint32_t count,uint32_t left,uint32_t top,uint32_t height,uint32_t direction){
    uint32_t advance=(height*76+107)/108,shadow=height/36+1;
    for(uint32_t pass=0;pass<2;++pass)for(uint32_t i=0;i<count;++i){
        char c=text[i];uint32_t mask=stamp_mask(c),offset=pass?0:shadow;
        if(c=='.'||c==':'||c=='\''){
            uint32_t size=height/12+1;
            for(uint32_t dot=0;dot<(c==':'?2u:1u);++dot){
                uint32_t yy=c=='\''?0:c==':'?(dot?height*2/3:height/3):height-size;
                for(uint32_t y=0;y<size;++y)for(uint32_t x=0;x<size;++x)
                    stamp_pixel(image,state,left+i*advance+height/4+x+offset,top+yy+y+offset,pass,direction);
            }
            continue;
        }
        for(uint32_t segment=0;segment<13;++segment){
            if(!(mask&(1u<<segment)))continue;
            const uint8_t *p=stamp_segments[segment];int32_t vx[6],vy[6];
            int32_t minx=100000,miny=100000,maxx=0,maxy=0;
            for(uint32_t n=0;n<p[0];++n){
                /* Rightward shear, strongest at the top, with beveled ends. */
                vx[n]=(int32_t)((p[1+n*2]*8u+108u-p[2+n*2])*height/864u);
                vy[n]=(int32_t)(p[2+n*2]*height/108u);
                if(vx[n]<minx)minx=vx[n];if(vx[n]>maxx)maxx=vx[n];
                if(vy[n]<miny)miny=vy[n];if(vy[n]>maxy)maxy=vy[n];
            }
            for(int32_t y=miny;y<maxy;++y)for(int32_t x=minx;x<maxx;++x){
                uint32_t inside=1;
                for(uint32_t n=0;n<p[0];++n){uint32_t next=n+1==p[0]?0:n+1;
                    if((vx[next]-vx[n])*(2*y+1-2*vy[n])-(vy[next]-vy[n])*(2*x+1-2*vx[n])<0){inside=0;break;}}
                if(inside)stamp_pixel(image,state,left+i*advance+(uint32_t)x+offset,top+(uint32_t)y+offset,pass,direction);
            }
        }
    }
}
static void stamp_line(m10v_library_image *image,const m10v_library_state *state,const char *text,uint32_t count,uint32_t left,uint32_t top,uint32_t height){stamp_line_oriented(image,state,text,count,left,top,height,0);}
static uint32_t stamp_width(uint32_t count,uint32_t height){return count*((height*76+107)/108)+height/36+1;}
static void stamp_oriented(m10v_library_image *image,const m10v_library_state *state,const m10v_library_date *date,const char *name,uint32_t direction){
    if(direction>3)direction=0;
    uint32_t width=(direction&1)?image->height:image->width;
    uint32_t height=(direction&1)?image->width:image->height;
    char text[24];uint32_t count=state->stamp&&date_valid(date)?date_text(text,date,state->format,state->stamp):0;
    uint32_t name_count=0;
    if((state->reserved&1u)&&name){while(name_count<24&&name[name_count]>=' '&&name[name_count]<='~')name_count++;
        if(!name_count||name_count>23||name[name_count])name_count=0;}
    if(!count&&!name_count)return;
    uint32_t edge=image->width<image->height?image->width:image->height;
    uint32_t dh=edge*27/1000,nh=edge*24/1000,margin=edge/64+2;
    if(dh<7)dh=7;if(nh<7)nh=7;
    uint32_t tw,th,gap;
    for(;;){
        uint32_t dw=count?stamp_width(count,dh):0,nw=name_count?stamp_width(name_count,nh):0;
        tw=dw>nw?dw:nw;gap=(count&&name_count)?dh/5+2:0;
        th=(count?dh+dh/36+1:0)+(name_count?nh+nh/36+1:0)+gap;
        if(tw+2*margin<width&&th+2*margin<height)break;
        if(dh<=3&&nh<=3)return;
        if(dh>3)--dh;if(nh>3)--nh;
    }
    uint32_t left=(state->corner&1)?width-margin-tw:margin;
    uint32_t top=(state->corner&2)?height-margin-th:margin;
    if(count&&!direction)stamp_line(image,state,text,count,left+((state->corner&1)?tw-stamp_width(count,dh):0),top,dh);
    else if(count)stamp_line_oriented(image,state,text,count,left+((state->corner&1)?tw-stamp_width(count,dh):0),top,dh,direction);
    if(name_count)stamp_line_oriented(image,state,name,name_count,left+((state->corner&1)?tw-stamp_width(name_count,nh):0),top+(count?dh+dh/36+1+gap:0),nh,direction);
}
static void stamp(m10v_library_image *image,const m10v_library_state *state,const m10v_library_date *date,const char *name){stamp_oriented(image,state,date,name,0);}
/* Existing tables are decoded exactly; RGB evaluation is an explicitly new
 * saved-JPEG path, not a claim that it reproduces the stock ISP pixel-for-pixel. */
int m10v_library_tables(uint32_t id,int16_t *matrix,int16_t *post,uint16_t *curves,uint16_t *knots){
    if(id<34||id>65||!matrix||!post||!curves||!knots)return -1;
    const m10v_legacy_record *record=&legacy_records[id-34];
    uint32_t at=record->offset,end=at+record->size;
    if(end>sizeof(legacy_bytes))return -1;
    for(uint32_t i=0;i<9;++i){matrix[i]=record->matrix[i];post[i]=record->post[i];}
    for(uint32_t bank=0;bank<2;++bank)for(uint32_t channel=0;channel<3;++channel){
        uint32_t value=0,count=bank?33:256;
        for(uint32_t i=0;i<count;++i){
            if(at>=end)return -1;uint32_t byte=legacy_bytes[at++],delta=byte&127;
            if(byte&128){if(at>=end||legacy_bytes[at]&128)return -1;delta|=(uint32_t)legacy_bytes[at++]<<7;}
            value+=delta;if(value>16383)return -1;
            if(bank)knots[channel*33+i]=(uint16_t)value;else curves[channel*256+i]=(uint16_t)value;
        }
    }
    return at==end?0:-1;
}
static int rounded(int value,uint32_t shift){
    int half=1<<(shift-1);return value>=0?(value+half)>>shift:-((-value+half)>>shift);
}
static int curve14(const uint16_t *curve,int input){
    if(input<=0)return curve[0];if(input>=255*8192)return curve[255];
    uint32_t index=(uint32_t)input>>13,fraction=(uint32_t)input&8191;
    return curve[index]+rounded((int)(curve[index+1]-curve[index])*(int)fraction,13);
}
static void legacy_rgb(uint8_t y,uint8_t cb,uint8_t cr,const int16_t *m,const int16_t *p,const uint16_t *curves,int *out){
    int u=(int)cb-128,v=(int)cr-128;
    int rgb[3]={clamp((int)y+rounded(91881*v,16)),clamp((int)y-rounded(22554*u+46802*v,16)),clamp((int)y+rounded(116130*u,16))};
    int mapped[3];
    for(uint32_t row=0;row<3;++row)mapped[row]=curve14(curves+256*row,rgb[0]*m[row*3]+rgb[1]*m[row*3+1]+rgb[2]*m[row*3+2]);
    for(uint32_t row=0;row<3;++row){
        int color=rounded(mapped[0]*p[row*3]+mapped[1]*p[row*3+1]+mapped[2]*p[row*3+2],9);
        if(color<0)color=0;if(color>16383)color=16383;out[row]=(color*255+8191)/16383;
    }
}
static __attribute__((always_inline)) inline int legacy_color_loop(m10v_library_image *image,uint32_t id,void *memory,uint32_t cached){
    int16_t matrix[9],post[9];uint16_t curves[768],knots[99];
    if(m10v_library_tables(id,matrix,post,curves,knots))return -1;
    for(uint32_t row=0;row<image->height;++row)for(uint32_t x=0;x<image->width;x+=2){
        uint32_t at=row*image->stride+x;int a[3],b[3];
        uint8_t cb=image->chroma[at],cr=image->chroma[at+1];
        for(uint32_t k=0;k<2;k++){
            uint8_t rgb[3];int *out=k?b:a;
            uint32_t key=(uint32_t)image->y[at+k]|((uint32_t)cb<<8)|((uint32_t)cr<<16);
            uint32_t *entry=cached?m10v_color_cache_slot(memory,key):0;
            if(!cached||entry[0]!=(key|0x01000000u)){
                legacy_rgb(image->y[at+k],cb,cr,matrix,post,curves,out);
                for(uint32_t c=0;c<3;c++)rgb[c]=(uint8_t)out[c];
                if(cached)m10v_color_cache_write(entry,key,rgb);
            }else {m10v_color_cache_read(entry,rgb);for(uint32_t c=0;c<3;c++)out[c]=rgb[c];}
        }
        image->y[at]=clamp(rounded(19595*a[0]+38470*a[1]+7471*a[2],16));
        image->y[at+1]=clamp(rounded(19595*b[0]+38470*b[1]+7471*b[2],16));
        int r=a[0]+b[0],g=a[1]+b[1],blue=a[2]+b[2];
        image->chroma[at]=clamp(128+rounded(-11059*r-21709*g+32768*blue,17));
        image->chroma[at+1]=clamp(128+rounded(32768*r-27439*g-5329*blue,17));
    }
    return 0;
}

static int legacy_color(m10v_library_image *image,uint32_t id,void *memory){
    memory=m10v_color_cache_prepare(memory,image);
    return memory?legacy_color_loop(image,id,memory,1):legacy_color_loop(image,id,0,0);
}
static uint8_t custom_sample(const uint8_t *lut,uint32_t r,uint32_t g,uint32_t b,uint32_t channel){
 uint32_t x=r*12u*256u/255u,y=g*12u*256u/255u,z=b*12u*256u/255u;
 uint32_t xi=x>>8,yi=y>>8,zi=z>>8,fx=x&255u,fy=y&255u,fz=z&255u;
 uint32_t xx=xi<12?xi+1:xi,yy=yi<12?yi+1:yi,zz=zi<12?zi+1:zi;
 #define AT(a,c,d) lut[(((d)*13u+(c))*13u+(a))*3u+channel]
 uint32_t a=(AT(xi,yi,zi)*(256-fx)+AT(xx,yi,zi)*fx+128)>>8;
 uint32_t c=(AT(xi,yy,zi)*(256-fx)+AT(xx,yy,zi)*fx+128)>>8;
 uint32_t d=(AT(xi,yi,zz)*(256-fx)+AT(xx,yi,zz)*fx+128)>>8;
 uint32_t e=(AT(xi,yy,zz)*(256-fx)+AT(xx,yy,zz)*fx+128)>>8;
 #undef AT
 uint32_t low=(a*(256-fy)+c*fy+128)>>8,high=(d*(256-fy)+e*fy+128)>>8;
 return (uint8_t)((low*(256-fz)+high*fz+128)>>8);
}
static void custom_color(m10v_library_image *image,const uint8_t *lut){
 for(uint32_t row=0;row<image->height;++row)for(uint32_t x=0;x<image->width;x+=2){
  uint32_t at=row*image->stride+x;int a[3],b[3];
  int cb=(int)image->chroma[at]-128,cr=(int)image->chroma[at+1]-128;
  for(uint32_t k=0;k<2;k++){
   int y=image->y[at+k],r=clamp(y+rounded(91881*cr,16)),g=clamp(y-rounded(22554*cb+46802*cr,16)),blue=clamp(y+rounded(116130*cb,16));
   int *out=k?b:a;for(uint32_t c=0;c<3;c++)out[c]=custom_sample(lut,(uint32_t)r,(uint32_t)g,(uint32_t)blue,c);
  }
  image->y[at]=clamp(rounded(19595*a[0]+38470*a[1]+7471*a[2],16));
  image->y[at+1]=clamp(rounded(19595*b[0]+38470*b[1]+7471*b[2],16));
  int rs=a[0]+b[0],gs=a[1]+b[1],bs=a[2]+b[2];
  image->chroma[at]=clamp(128+rounded(-11059*rs-21709*gs+32768*bs,17));
  image->chroma[at+1]=clamp(128+rounded(32768*rs-27439*gs-5329*bs,17));
 }
}

/* Assumed Phoenix II orange/red scatter, weaker than the 800T grade. Build
 * the source from ORIGINAL luminance, then composite after colour rendering.
 * The vendor provides no measured PSF or hue: these are bounded design choices. */
static void phoenix_halation_source(const m10v_library_image *im,const m10v_slot *v,uint8_t *scratch,uint32_t gw,uint32_t gh,uint32_t shift){
    uint16_t *a=(uint16_t *)scratch,*b=a+gw*gh;
    uint32_t step=1u<<shift,gate=176+8u*v->halo_threshold;
    for(uint32_t gy=0;gy<gh;++gy)for(uint32_t gx=0;gx<gw;++gx){
        uint32_t sum=0,peak=0;
        for(uint32_t dy=0;dy<step;++dy){
            uint32_t row=(gy<<shift)+dy;if(row>=im->height)break;
            for(uint32_t dx=0;dx<step;++dx){
                uint32_t x=(gx<<shift)+dx;if(x>=im->width)break;
                uint32_t light=im->y[row*im->stride+x];
                uint32_t excess=light>gate?light-gate:0,energy=excess*excess*8;
                sum+=energy;if(energy>peak)peak=energy;
            }
        }
        /* Preserve tiny lamps at step16 without another image scan. A small
         * bounded peak contribution supplements integrated cell energy; it
         * is not a claim of calibrated source area or a measured near PSF.
         * Max 49928 + 49928/16 < 65536, including partial edge cells. */
        a[gy*gw+gx]=(uint16_t)((sum>>(2*shift))+(shift?peak>>4:0));
    }
    energy_blur(a,b,gw,gh,1+v->halo_spread,1);
}
static void phoenix_halation_compose(m10v_library_image *im,const m10v_slot *v,const uint8_t *scratch,uint32_t gw,uint32_t gh,uint32_t shift){
    const uint16_t *a=(const uint16_t *)scratch;
    uint32_t step=1u<<shift,half=step>>1;
    for(uint32_t row=0;row<im->height;++row){
      uint32_t py=row<half?0:row-half,gy=py>>shift,ny=gy+1<gh?gy+1:gy;
      for(uint32_t x=0;x<im->width;){
        uint32_t px=x<half?0:x-half,gx=px>>shift,nx=gx+1<gw?gx+1:gx;
        uint32_t end=(((gx+1)<<shift)+half+1u)&~1u;
        if(end<=x)end=x+2;if(end>im->width)end=im->width;
        /* Bilinear energy is exactly zero over this interval iff all four
         * support samples are zero. Never threshold a weak real halo. */
        if(!(a[gy*gw+gx]|a[gy*gw+nx]|a[ny*gw+gx]|a[ny*gw+nx])){x=end;continue;}
        for(;x<end;x+=2){
        uint32_t at=row*im->stride+x,y0=im->y[at],y1=im->y[at+1],peak=y0>y1?y0:y1;
        /* Shared chroma must not tint either member of a clipped bright pair. */
        if(peak>=240)continue;
        uint32_t protect=(255-peak)*4;if(protect>255)protect=255;
        uint32_t red=(energy_sample(a,gw,gh,x,row,shift)*v->halo_gain*protect)>>12;
        if(!red)continue;
        uint32_t limit=6u*v->halo_gain;if(red>limit)red=limit;
        /* Orange shoulder: more green than 800T, with a six-level red cap
         * per gain step (800T permits 192). All products fit uint32_t. */
        uint32_t green=red>>2,lift=(77*red+150*green+128)>>8;
        im->y[at]=clamp((int)(y0+lift));im->y[at+1]=clamp((int)(y1+lift));
        im->chroma[at]=clamp((int)im->chroma[at]-(int)((43*red+85*green+128)>>8));
        im->chroma[at+1]=clamp((int)im->chroma[at+1]+(int)((128*red-107*green+128)>>8));
        }
      }
    }
}
static int render_stages(m10v_library_image *image,const m10v_library_state *state,
                        uint32_t slot,const m10v_library_date *date,uint32_t seed,
                        uint8_t *scratch,uint32_t scratch_bytes,uint32_t completed,const uint8_t *custom_lut,const char *custom_name,uint32_t direction
#if M10V_CAPTURE_PROFILE
                        ,m10v_capture_profile *profile
#endif
                        ) {
    if(completed & ~M10V_NATIVE_ALL)return M10V_LIBRARY_INVALID;
    if (!image || !m10v_library_valid(state) || (state->reserved&510u) || slot >= M10V_SLOT_COUNT || !state->slots[slot].film ||
        !image->y || !image->chroma || image->width < 2 || image->width > 6144 ||
        (image->width & 1) || !image->height || image->height > 4096 ||
        image->stride < image->width || image->stride > 16384 || (image->stride & 1))
        return M10V_LIBRARY_INVALID;
    uint32_t bytes = image->stride * image->height;
    if (bytes > image->y_bytes || bytes > image->chroma_bytes ||
        (uintptr_t)image->y > UINTPTR_MAX - bytes || (uintptr_t)image->chroma > UINTPTR_MAX - bytes ||
        overlap(image->y, bytes, image->chroma, bytes) ||
        overlap(image->y, bytes, state, sizeof(*state)) || overlap(image->chroma, bytes, state, sizeof(*state)) ||
        overlap(image->y, bytes, image, sizeof(*image)) || overlap(image->chroma, bytes, image, sizeof(*image)) ||
        (state->stamp && !date_valid(date) && !(state->reserved&1u)) ||
        (state->stamp && date && (overlap(image->y, bytes, date, sizeof(*date)) ||
          overlap(image->chroma, bytes, date, sizeof(*date))))) return M10V_LIBRARY_INVALID;
    const m10v_slot *choice = &state->slots[slot];
    /* New looks are ISP-only color. Never map these identities to old CPU LUTs. */
    if(M10V_ANIME(choice->film))return M10V_LIBRARY_INVALID;
    if((M10V_FOUR_LOOKS(choice->film)||M10V_ANIME_E6(choice->film)||M10V_C41(choice->film)||M10V_EXTRA_FILM(choice->film))&&!(completed&M10V_NATIVE_COLOR))return M10V_LIBRARY_INVALID;
    if(M10V_CUSTOM(choice->film)&&!custom_lut)return M10V_LIBRARY_INVALID;
    uint32_t shift = 0, gw = image->width, gh = image->height;
    /* Power-of-two sampling must not depend on an ARM division runtime. */
    while (gw > 384 || gh > 256) {
        ++shift;
        uint32_t mask = (1u << shift) - 1;
        gw = (image->width + mask) >> shift; gh = (image->height + mask) >> shift;
    }
    uint32_t cells = gw * gh;
    uint32_t use_halo = !(completed&M10V_NATIVE_HALO) && m10v_halo_enabled(choice->film,choice->halo_gain,choice->halo_profile);
    uint32_t special_halo=use_halo;
#if M10V_UNIVERSAL_HALATION
    special_halo=use_halo && choice->halo_profile==M10V_HALO_SPILL && (choice->film==33||choice->film==67);
#endif
    /* Legacy per-film soft is retired, including imported SD/journal values.
     * Digital HDF runs upstream in the original native Clarity owner. */
    const uint32_t soft=0;
    (void)seed; /* Grain is exclusively owned by the native ISP. */
    m10v_film_effects effects=state->effects[slot];
    uint32_t needed = use_halo?((m10v_halo_workspace_planes(choice->film,choice->halo_profile) * cells + 3) & ~3u):0;
    if ((soft || use_halo) && (!scratch || ((uintptr_t)scratch & 3) || scratch_bytes < needed ||
        (uintptr_t)scratch > UINTPTR_MAX - needed || overlap(scratch, needed, image->y, bytes) ||
        overlap(scratch, needed, image->chroma, bytes) || overlap(scratch, needed, state, sizeof(*state)) ||
        overlap(scratch, needed, image, sizeof(*image)) ||
        (state->stamp && overlap(scratch, needed, date, sizeof(*date))))) return M10V_LIBRARY_INVALID;
    if (use_halo) {
        if(custom_lut&&overlap(scratch,needed,custom_lut,6591u))return M10V_LIBRARY_INVALID;
        /* Keep the previous full-capacity preflight without linking the
         * retired halation renderer; the energy model below owns 800T. */
        if((uintptr_t)image->y>UINTPTR_MAX-image->y_bytes ||
           (uintptr_t)image->chroma>UINTPTR_MAX-image->chroma_bytes ||
           overlap(image->y,image->y_bytes,image->chroma,image->chroma_bytes))return M10V_LIBRARY_INVALID;
        if ((uintptr_t)scratch > UINTPTR_MAX-scratch_bytes ||
            overlap(scratch,scratch_bytes,image->y,image->y_bytes) ||
            overlap(scratch,scratch_bytes,image->chroma,image->chroma_bytes) ||
            overlap(scratch,scratch_bytes,state,sizeof(*state)) ||
            overlap(scratch,scratch_bytes,image,sizeof(*image)) ||
            (state->stamp && overlap(scratch,scratch_bytes,date,sizeof(*date)))) return M10V_LIBRARY_INVALID;
    }
    /* Optional exact color cache follows spatial storage. Missing capacity
     * keeps the previous ABI and renderer. Validate before the first write. */
    uint32_t spatial=(use_halo && !(choice->film==33&&special_halo))?4*cells:0;
    void *color_memory=0;
    if(choice->film>33 && scratch && !((uintptr_t)scratch&3) &&
       scratch_bytes>=spatial+M10V_COLOR_CACHE_BYTES &&
       (uintptr_t)scratch<=UINTPTR_MAX-scratch_bytes &&
       !overlap(scratch,scratch_bytes,image->y,image->y_bytes) &&
       !overlap(scratch,scratch_bytes,image->chroma,image->chroma_bytes) &&
       !overlap(scratch,scratch_bytes,state,sizeof(*state)) &&
       !overlap(scratch,scratch_bytes,image,sizeof(*image)) &&
       !(state->stamp&&overlap(scratch,scratch_bytes,date,sizeof(*date))))
        color_memory=scratch+spatial;
    if(choice->film==33 && (special_halo || soft)){
        m10v_slot spatial_choice=*choice;
        if(completed&M10V_NATIVE_HALO)spatial_choice.halo_gain=0;
        spatial_choice.soft=(uint8_t)soft;
        m10v_800t_effects(image,&spatial_choice,scratch,gw,gh,shift);
    }
    if(choice->film==67&&special_halo)phoenix_halation_source(image,choice,scratch,gw,gh,shift);
#if M10V_UNIVERSAL_HALATION
    if(use_halo&&!special_halo)m10v_universal_halation_source(image,choice,scratch,gw,gh,shift);
#endif
    M10V_PROFILE(7);
    uint32_t *texture_stats=0;
#if M10V_CAPTURE_PROFILE
    uint32_t texture_work[3]={0};texture_stats=texture_work;
#endif
    if(M10V_CUSTOM(choice->film)){
        if(!(completed&M10V_NATIVE_COLOR))custom_color(image,custom_lut);
    }
    else if(choice->film==M10V_PIXEL_ID){
        m10v_pixel_world_render(image);
    }
    else if(choice->film==M10V_CHAR_ID){
        m10v_charmera_render(image,effects.reserved[1]);
    }
    else if(completed&M10V_NATIVE_COLOR){
        /* Also when a stamp/halo retains this CPU residual pass: the fitted
         * ISP color has already run, so never apply the original LUT again. */
    }
    else if(choice->film==77||choice->film==M10V_5213_ID){
        m10v_5207_texture_cached_stats_q8(image,&effects,0,0,choice->film==77?14:24,color_memory,texture_stats);
    }
    else if(M10V_D76(choice->film)){
        /* Compatibility fallback only when native completion is absent. */
        m10v_5207_texture_cached_stats_q8(image,&effects,0,0,choice->film-M10V_D76_FIRST+25,color_memory,texture_stats);
    }
    else if(M10V_STYLE(choice->film)){
        /* Compatibility fallback only when native completion is absent. */
        m10v_5207_texture_cached_stats_q8(image,&effects,0,0,choice->film-M10V_STYLE_FIRST+17,color_memory,texture_stats);
    }
    else if(choice->film==66){m10v_5207_texture_cached_stats_q8(image,&effects,0,0,1,color_memory,texture_stats);}
    else if(choice->film>=67){
        uint32_t exposure=state->effects[slot].film_exposure;
        m10v_5207_texture_cached_stats_q8(image,&effects,0,0,choice->film>=69?choice->film-63:choice->film==67?(exposure?16:2):3+exposure,color_memory,texture_stats);
    }
    else if(choice->film>33){if(legacy_color(image,choice->film,color_memory))return M10V_LIBRARY_INVALID;}
    else {
    const film *look = &films[choice->film - 1];
    uint8_t curve[256];
    for (int v = 0; v < 256; ++v) curve[v] = clamp(128 + ((v - 128) * look->contrast) / 256 +
        (look->lift * (255 - v)) / 255 + (look->bend * v * (255 - v)) / 16384);
    for (uint32_t row = 0; row < image->height; ++row) for (uint32_t x = 0; x < image->width; x += 2) {
        uint32_t at = row * image->stride + x;
        int light = (image->y[at] + image->y[at + 1]) / 2;
        int weight = 255 - (light > 127 ? 2 * light - 255 : 255 - 2 * light);
        int cb = image->chroma[at] - 128, cr = image->chroma[at + 1] - 128;
        image->chroma[at] = clamp(128 + (cb * look->saturation + cr * look->turn) / 256 + look->cb * weight / 255);
        image->chroma[at + 1] = clamp(128 + (cr * look->saturation - cb * look->turn) / 256 + look->cr * weight / 255);
        image->y[at] = curve[image->y[at]]; image->y[at + 1] = curve[image->y[at + 1]];
    }
    }
#if M10V_CAPTURE_PROFILE
    if(choice->film>=66&&profile&&profile->count<32){
        uint32_t *e=profile->events[profile->count++];e[0]=134;e[1]=profile->context;
        e[2]=texture_work[0];e[3]=texture_work[1];e[4]=texture_work[2];
    }
#endif
    M10V_PROFILE(8);
    if(choice->film==67&&special_halo)phoenix_halation_compose(image,choice,scratch,gw,gh,shift);
#if M10V_UNIVERSAL_HALATION
    if(use_halo&&!special_halo)m10v_universal_halation_compose(image,choice,scratch,gw,gh,shift);
#endif
    M10V_PROFILE(9);
    if (state->stamp||(state->reserved&1u)){
        const char *name=M10V_CUSTOM(choice->film)?custom_name:m10v_library_name(choice->film);
        if(direction)stamp_oriented(image,state,date,name,direction);else stamp(image,state,date,name);
    }
    M10V_PROFILE(10);
    return M10V_LIBRARY_OK;
}


int m10v_library_render_native(m10v_library_image *image,const m10v_library_state *state,uint32_t slot,const m10v_library_date *date,uint32_t seed,uint8_t *scratch,uint32_t bytes,uint32_t completed){
    return render_stages(image,state,slot,date,seed,scratch,bytes,completed,0,0,0
#if M10V_CAPTURE_PROFILE
      ,0
#endif
    );
}
int m10v_library_render_custom(m10v_library_image *image,const m10v_library_state *state,uint32_t slot,const m10v_library_date *date,uint32_t seed,uint8_t *scratch,uint32_t bytes,uint32_t completed,const uint8_t *lut,const char *name){
 if(!lut||!state||slot>=M10V_SLOT_COUNT||!M10V_CUSTOM(state->slots[slot].film))return M10V_LIBRARY_INVALID;
 return render_stages(image,state,slot,date,seed,scratch,bytes,completed,lut,name,0
#if M10V_CAPTURE_PROFILE
 ,0
#endif
 );
}
int m10v_library_render(m10v_library_image *image,const m10v_library_state *state,uint32_t slot,const m10v_library_date *date,uint32_t seed,uint8_t *scratch,uint32_t bytes){
    return m10v_library_render_native(image,state,slot,date,seed,scratch,bytes,0);
}
#if M10V_CAPTURE_PROFILE
int m10v_library_render_profiled(m10v_library_image *image,const m10v_library_state *state,uint32_t slot,const m10v_library_date *date,uint32_t seed,uint8_t *scratch,uint32_t bytes,m10v_capture_profile *profile){
    return render_stages(image,state,slot,date,seed,scratch,bytes,0,0,0,0,profile);
}
int m10v_library_render_native_profiled(m10v_library_image *image,const m10v_library_state *state,uint32_t slot,const m10v_library_date *date,uint32_t seed,uint8_t *scratch,uint32_t bytes,uint32_t completed,m10v_capture_profile *profile){
    return render_stages(image,state,slot,date,seed,scratch,bytes,completed,0,0,0,profile);
}
#endif

int m10v_library_render_oriented(m10v_library_image *image,const m10v_library_state *state,uint32_t slot,const m10v_library_date *date,uint32_t seed,uint8_t *scratch,uint32_t bytes,const m10v_library_render_context *context){
    if(!context)return M10V_LIBRARY_INVALID;
    if(state&&slot<M10V_SLOT_COUNT&&M10V_CUSTOM(state->slots[slot].film)&&!context->lut)return M10V_LIBRARY_INVALID;
    return render_stages(image,state,slot,date,seed,scratch,bytes,context->completed,context->lut,context->name,context->direction
#if M10V_CAPTURE_PROFILE
      ,0
#endif
    );
}
#if M10V_CAPTURE_PROFILE
int m10v_library_render_oriented_profiled(m10v_library_image *image,const m10v_library_state *state,uint32_t slot,const m10v_library_date *date,uint32_t seed,uint8_t *scratch,uint32_t bytes,const m10v_library_render_context *context,m10v_capture_profile *profile){
    if(!context)return M10V_LIBRARY_INVALID;
    if(state&&slot<M10V_SLOT_COUNT&&M10V_CUSTOM(state->slots[slot].film)&&!context->lut)return M10V_LIBRARY_INVALID;
    return render_stages(image,state,slot,date,seed,scratch,bytes,context->completed,context->lut,context->name,context->direction,profile);
}
#endif
