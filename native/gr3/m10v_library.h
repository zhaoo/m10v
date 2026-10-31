#ifndef M10V_LIBRARY_H
#define M10V_LIBRARY_H
#include <stdint.h>

#ifndef M10V_UNIVERSAL_HALATION
#define M10V_UNIVERSAL_HALATION 0
#endif
/* Legacy 0..3 never opts an old journal into the new capability. */
#define M10V_HALO_OFF 6u
#define M10V_HALO_SPILL 4u
#define M10V_HALO_STREAK 5u
static inline uint32_t m10v_halo_enabled(uint32_t film,uint32_t gain,uint32_t profile){
#if M10V_UNIVERSAL_HALATION
    (void)film;return gain && (profile==M10V_HALO_SPILL||profile==M10V_HALO_STREAK);
#else
    return gain && profile<=3 && (film==33||film==67);
#endif
}
static inline uint32_t m10v_halo_workspace_planes(uint32_t film,uint32_t profile){
#if M10V_UNIVERSAL_HALATION
    if(profile==M10V_HALO_STREAK || (profile==M10V_HALO_SPILL&&film!=33&&film!=67))return 4;
#else
    (void)film;(void)profile;
#endif
    return 6;
}
#define M10V_FILM_COUNT 78u
#define M10V_CUSTOM_MAX_ID 288u
/* 79..288 are existing custom identities. Never reuse them. */
#define M10V_CHAR_ID 289u
#define M10V_PIXEL_ID 290u
#define M10V_5213_ID 298u
#define M10V_STYLE_FIRST 291u
#define M10V_STYLE_LAST 297u
#define M10V_STYLE(id) ((id)>=M10V_STYLE_FIRST && (id)<=M10V_STYLE_LAST)
#define M10V_D76_FIRST 299u
#define M10V_D76_LAST 305u
#define M10V_D76(id) ((id)>=M10V_D76_FIRST && (id)<=M10V_D76_LAST)
#define M10V_ANIME_FIRST 306u
#define M10V_ANIME_LAST 308u
#define M10V_ANIME(id) ((id)>=306u && (id)<=308u)
#define M10V_E6(id) ((id)>=309u && (id)<=311u)
#define M10V_FOUR_LOOKS(id) ((id)>=318u && (id)<=321u)
#ifndef M10V_FOUR_LOOKS_NATIVE
#define M10V_FOUR_LOOKS_NATIVE 0
#endif
#define M10V_FOUR_LOOKS_ICON(id) (878u+(id)-318u)
#define M10V_FOUR_LOOKS_NAME(id) (1159u+(id)-318u)
#define M10V_EXTRA_FILM(id) ((id)>=314u && (id)<=317u)
#define M10V_EXTRA_FILM_ICON(id) ((id)==317u?875u:M10V_EXTRA_FILM_ICON_FIRST+(id)-314u)
#define M10V_EXTRA_FILM_NAME(id) ((id)==317u?1158u:M10V_EXTRA_FILM_NAME_FIRST+(id)-314u)
#define M10V_EXTRA_FILM_ICON_FIRST 871u
#define M10V_EXTRA_FILM_NAME_FIRST 1152u
#define M10V_C41(id) ((id)>=312u && (id)<=313u)
#define M10V_C41_ICON_FIRST 869u
#define M10V_C41_NAME_FIRST 1150u
#define M10V_ANIME_E6(id) ((id)>=306u && (id)<=311u)
#define M10V_ANIME_E6_ICON_FIRST 858u
#define M10V_ANIME_VALUE_FIRST 864u
#define M10V_ANIME_SCALE_ICON 868u
#define M10V_ANIME_CAPTION 1148u
#define M10V_BUILTIN(id) ((id)>0 && ((id)<=M10V_FILM_COUNT || (id)==M10V_CHAR_ID || (id)==M10V_PIXEL_ID || (id)==M10V_5213_ID || M10V_STYLE(id) || M10V_D76(id) || M10V_ANIME_E6(id)||M10V_C41(id)||M10V_EXTRA_FILM(id)||M10V_FOUR_LOOKS(id)))
#define M10V_CUSTOM(id) ((id)>M10V_FILM_COUNT && (id)<=M10V_CUSTOM_MAX_ID)
#define M10V_SLOT_COUNT 10u
#define M10V_CUSTOM_IMMUTABLE_FIRST 21u
#define M10V_CUSTOM_MAX_BANK 254u
#define M10V_LIBRARY_OK 0
#define M10V_LIBRARY_INVALID -1
#define M10V_LIBRARY_STORE_FAILED -2

typedef struct { uint16_t film; uint8_t grain, soft, halo_gain, halo_spread, halo_threshold, halo_profile; } m10v_slot;
/* Retired grain_size/leak_* bytes retain their per-film layout. */
typedef struct { uint8_t grain_size, leak_gain, leak_position, leak_spread, leak_variation, film_exposure, reserved[2]; } m10v_film_effects;
typedef struct {
    uint32_t magic;
    uint16_t version, size;
    uint32_t sequence;
    m10v_slot slots[M10V_SLOT_COUNT];
    uint8_t stamp, format, corner, color;
    m10v_film_effects effects[M10V_SLOT_COUNT];
    uint32_t reserved, crc;
} m10v_library_state;
typedef struct {
    uint8_t *y, *chroma;
    uint32_t y_bytes, chroma_bytes, width, height, stride;
} m10v_library_image;
typedef struct { uint16_t year; uint8_t month, day, hour, minute; } m10v_library_date;
typedef int (*m10v_library_store)(void *, const m10v_library_state *);

int m10v_library_effects(m10v_library_state *,uint32_t slot,uint32_t field,uint32_t value,m10v_library_store,void *);
int m10v_camera_library_effects(m10v_library_state *,uint32_t slot,uint32_t field,uint32_t value);
int m10v_library_reset(m10v_library_state *,uint32_t slot,m10v_library_store,void *);
int m10v_camera_library_reset(m10v_library_state *,uint32_t slot);
uint32_t m10v_library_count(const m10v_library_state *);
int m10v_library_remove(m10v_library_state *,uint32_t,m10v_library_store,void *);
int m10v_camera_library_remove(m10v_library_state *,uint32_t);
void m10v_library_init(m10v_library_state *);
int m10v_library_valid(const m10v_library_state *);
const char *m10v_library_name(uint32_t film);
int m10v_library_select(m10v_library_state *, uint32_t slot, uint32_t film,
                        m10v_library_store, void *);
int m10v_library_select_custom(m10v_library_state *,uint32_t slot,uint32_t film,uint32_t bank,m10v_library_store,void *);
int m10v_library_texture(m10v_library_state *, uint32_t slot, uint32_t grain, uint32_t soft,
                         m10v_library_store, void *);
int m10v_library_halation(m10v_library_state *, uint32_t slot, uint32_t gain, uint32_t spread, uint32_t threshold, uint32_t profile, m10v_library_store, void *);
int m10v_library_detail(m10v_library_state *, uint32_t slot, uint32_t gain, uint32_t spread, uint32_t threshold, uint32_t grain, uint32_t soft, m10v_library_store, void *);
int m10v_library_tables(uint32_t film, int16_t *, int16_t *, uint16_t *, uint16_t *);
int m10v_library_stamp(m10v_library_state *, uint32_t enabled, uint32_t format,
                       uint32_t corner, uint32_t color, m10v_library_store, void *);
int m10v_library_film_name_stamp(m10v_library_state *,uint32_t enabled,m10v_library_store,void *);
/* Upstream completion is per recipe; callers must validate generation and
 * frame identity before supplying this mask. These bits never disable an
 * effect that the native owner has not actually executed. */
enum { M10V_NATIVE_COLOR=1u, M10V_NATIVE_GRAIN=2u, M10V_NATIVE_SOFT=4u,
       M10V_NATIVE_HALO=8u, M10V_NATIVE_LEAK=16u, M10V_NATIVE_ALL=31u };
/* CPU residual plan after the recipe owner has authenticated completion.
 * No pixel access and no state mutation. A disabled halo has no spatial pass;
 * color retains its exact fallback. Grain is native-only and leak is retired. */
#define M10V_CPU_STAMP 32u
#define M10V_CPU_ANIME 64u
static inline uint32_t m10v_library_cpu_stages(const m10v_library_state *state,uint32_t slot,uint32_t completed){
    if(!state||slot>=M10V_SLOT_COUNT||!state->slots[slot].film)return 0;
    const m10v_slot *v=&state->slots[slot];
    uint32_t software_color=v->film==M10V_CHAR_ID||v->film==M10V_PIXEL_ID;
    uint32_t stages=(software_color||!(completed&M10V_NATIVE_COLOR))?M10V_NATIVE_COLOR:0;
    if(m10v_halo_enabled(v->film,v->halo_gain,v->halo_profile)&&!(completed&M10V_NATIVE_HALO))stages|=M10V_NATIVE_HALO;
    if(state->stamp||(state->reserved&1u))stages|=M10V_CPU_STAMP;
    return stages;
}
/* Transient per-exposure render context; serialized state and image ABI stay
 * unchanged. Direction follows official ShootingInfo+0xc8 (1/2/3 => EXIF8/3/6).
 * Out-of-range directions retain landscape layout. */
typedef struct {
    uint32_t direction,completed;
    const uint8_t *lut;
    const char *name;
} m10v_library_render_context;
int m10v_library_render_oriented(m10v_library_image *,const m10v_library_state *,uint32_t,
        const m10v_library_date *,uint32_t,uint8_t *,uint32_t,const m10v_library_render_context *);
int m10v_library_render_native(m10v_library_image *,const m10v_library_state *,uint32_t,
        const m10v_library_date *,uint32_t,uint8_t *,uint32_t,uint32_t completed);
int m10v_library_render_custom(m10v_library_image *,const m10v_library_state *,uint32_t,
        const m10v_library_date *,uint32_t,uint8_t *,uint32_t,uint32_t completed,const uint8_t *lut,const char *name);
int m10v_library_render(m10v_library_image *, const m10v_library_state *, uint32_t slot,
                        const m10v_library_date *, uint32_t seed, uint8_t *scratch,
                        uint32_t scratch_bytes);
/* Nonnegative load provenance: 0=new journal, 1=defaults, 2=v2 migration,
 * 3=v1 migration. All are usable validated states; negative is failure. */
int m10v_camera_library_preview(m10v_library_state *);
int m10v_camera_library_reconcile_legacy_selection(uint32_t model);
int m10v_camera_library_mutation_begin(void);
void m10v_camera_library_mutation_end(const m10v_library_state *);
int m10v_camera_library_mutation_busy(void);
void m10v_camera_library_preview_init(uint32_t);
void m10v_camera_library_preview_clear(uint32_t);
int m10v_camera_library_load(m10v_library_state *);
int m10v_camera_library_select(m10v_library_state *, uint32_t slot, uint32_t film);
int m10v_camera_library_select_custom(m10v_library_state *,uint32_t slot,uint32_t film,uint32_t bank);
int m10v_camera_library_texture(m10v_library_state *, uint32_t slot, uint32_t grain, uint32_t soft);
int m10v_camera_library_halation(m10v_library_state *, uint32_t slot, uint32_t gain, uint32_t spread, uint32_t threshold, uint32_t profile);
int m10v_camera_library_detail(m10v_library_state *, uint32_t slot, uint32_t gain, uint32_t spread, uint32_t threshold, uint32_t grain, uint32_t soft);
int m10v_camera_library_stamp(m10v_library_state *, uint32_t enabled, uint32_t format,
                             uint32_t corner, uint32_t color);
int m10v_camera_library_film_name_stamp(m10v_library_state *,uint32_t enabled);
#endif
