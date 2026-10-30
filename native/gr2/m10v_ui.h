#ifndef M10V_GR2_UI_H
#define M10V_GR2_UI_H
#include <stdint.h>
/* Original loaded UTF-16 strings; caller never owns or frees these pointers. */
const uint16_t *gr2_original_text(uint32_t text_id,uint32_t language);
/* Fresh detached storage only; this is not menu open/registration. */
int gr2_effect_view_init(void *storage,uint32_t capacity);
int gr2_film_card_rgba(uint8_t *,uint32_t capacity,uint32_t film,uint32_t slot,uint32_t selected);
/* UI thread only, initialized stock 640x480 logical context. Rectangle is
 * left/top/right/bottom, count excludes the required UTF-16 terminator. */
int gr2_text_draw(const uint16_t *,uint32_t,const int16_t rectangle[4],uint32_t color);
/* UI owner only; physical x/y packed in low/high16, one 128x128 card. */
int gr2_card_draw(uint32_t film,uint32_t slot,uint32_t selected,uint32_t position);
/* Fresh caller-owned storage. Only the UI owner may attach/detach; callbacks
 * remain alive until detach completes. destroy may release its owner and must
 * return nonzero to request redrawing the preserved camera root. */
typedef struct {
    uint32_t (*event)(void *,const uint32_t *);
    const uint32_t *event_table;
    void **children;
    uint16_t count,reserved;
    int (*destroy)(void *,uint32_t);
    uint32_t dirty,parameter,tick,flags;
} gr2_overlay;
int gr2_overlay_attach(gr2_overlay *);
int gr2_overlay_detach(gr2_overlay *);
/* Original full-resolution 8-bit (0) or RGBA4444 (1) surface fill. */
int gr2_fill_rect(uint32_t index,const int16_t rectangle[4],uint32_t color);
/* Same bounded font bridge on the full 720x480 original context. */
int gr2_text_draw_full(const uint16_t *,uint32_t,const int16_t rectangle[4],uint32_t color);
#endif
