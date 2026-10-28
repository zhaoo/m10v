#include "m10v_border.h"

static uint32_t border_up(uint32_t value) { return (value + 7u) & ~7u; }
static uint32_t at_least_two(uint32_t value) { return value < 2u ? 2u : value; }
static void publish_words(void *out,const void *in,uint32_t words) {
    volatile uint32_t *d=out;const uint32_t *s=in;
    for(uint32_t i=0;i<words;++i)d[i]=s[i];
}

int m10v_border_layout(uint32_t style, uint32_t width, uint32_t height,
                       m10v_border_layout_info *out) {
    if (!out || style > M10V_BORDER_FILM || width < 2u || height < 2u ||
        width > 65534u || height > 65534u || ((width | height) & 1u)) return -1;
    m10v_border_layout_info result;
    for(uint32_t i=0;i<sizeof(result)/4u;++i)((volatile uint32_t *)&result)[i]=0;
    result.style = style;
    result.inner.width = result.outer.width = width;
    result.inner.height = result.outer.height = height;
    if (style != M10V_BORDER_OFF) {
        uint32_t short_side = width < height ? width : height;
        uint32_t margin = style == M10V_BORDER_POLAROID ?
            border_up((short_side + 24u) / 25u) :
            border_up((short_side * 3u + 49u) / 50u);
        result.inner.x = result.inner.y = margin;
        result.outer.width = width + margin * 2u;
        result.outer.height = height + margin * (style == M10V_BORDER_POLAROID ? 4u : 2u);
        if (style == M10V_BORDER_FILM) {
            uint32_t hole_width = at_least_two((margin / 2u) & ~1u);
            uint32_t hole_height = at_least_two((margin * 3u / 4u) & ~1u);
            uint32_t gap = at_least_two((margin / 2u) & ~1u);
            uint32_t pitch = hole_height + gap;
            uint32_t usable = result.outer.height - margin;
            /* At most 63 bounded control steps; no freestanding variable
             * divide helper and no work proportional to photo pixels. */
            uint32_t count = 1;
            while (count < 64u && (count + 1u) * pitch <= usable + gap) ++count;
            m10v_border_holes left;
            left.first.x = ((margin - hole_width) / 2u) & ~1u;
            left.first.y = ((result.outer.height - ((count - 1u) * pitch + hole_height)) / 2u) & ~1u;
            left.first.width = hole_width;
            left.first.height = hole_height;
            left.pitch = pitch;
            left.count = count;
            result.holes[0] = result.holes[1] = left;
            result.holes[1].first.x = result.outer.width - left.first.x - hole_width;
        }
    }
    publish_words(out,&result,sizeof(result)/4u);
    return 0;
}

static m10v_border_rect stored_rect(m10v_border_rect r, uint32_t width,
                                   uint32_t height, uint32_t orientation) {
    m10v_border_rect s = r;
    if (orientation >= 5u) {
        s.x = r.y; s.y = r.x; s.width = r.height; s.height = r.width;
    }
    if (orientation == 2u || orientation == 3u || orientation == 7u || orientation == 8u)
        s.x = width - s.x - s.width;
    if (orientation == 3u || orientation == 4u || orientation == 6u || orientation == 7u)
        s.y = height - s.y - s.height;
    return s;
}

int m10v_border_storage_layout(uint32_t style, uint32_t width, uint32_t height,
                               uint32_t orientation, uint32_t format,
                               m10v_border_storage_info *out) {
    if (!out || orientation < 1u || orientation > 8u || (format != 1u && format != 2u)) return -1;
    m10v_border_layout_info display;
    if (m10v_border_layout(style, orientation >= 5u ? height : width,
                          orientation >= 5u ? width : height, &display)) return -1;
    m10v_border_storage_info result;
    for(uint32_t i=0;i<sizeof(result)/4u;++i)((volatile uint32_t *)&result)[i]=0;
    result.style = style; result.format = format;
    result.outer.width = orientation >= 5u ? display.outer.height : display.outer.width;
    result.outer.height = orientation >= 5u ? display.outer.width : display.outer.height;
    if (result.outer.width > 16384u || result.outer.height > 16384u) return -1;
    result.inner = stored_rect(display.inner, result.outer.width, result.outer.height, orientation);
    if (style != M10V_BORDER_OFF) {
        result.stride = (result.outer.width + 63u) & ~63u;
        result.allocated_height = (result.outer.height + 7u) & ~7u;
        result.y_bytes = result.stride * result.allocated_height;
        result.chroma_bytes = format == 2u ? result.y_bytes / 2u : result.y_bytes;
        result.total_bytes = result.y_bytes + result.chroma_bytes;
        for (uint32_t i = 0; i < 2u; ++i) if (display.holes[i].count) {
            m10v_border_storage_holes *s = &result.holes[i];
            s->first = stored_rect(display.holes[i].first, result.outer.width, result.outer.height, orientation);
            s->count = display.holes[i].count;
            int32_t step = (int32_t)display.holes[i].pitch;
            if (orientation == 3u || orientation == 4u || orientation == 7u || orientation == 8u) step = -step;
            if (orientation >= 5u) s->dx = step; else s->dy = step;
        }
    }
    publish_words(out,&result,sizeof(result)/4u);
    return 0;
}

/* Largest even ratio result below numerator/denominator. Bounded binary
 * search avoids a freestanding ARM division helper or a pixel-sized loop. */
static uint32_t even_ratio(uint32_t numerator,uint32_t denominator,uint32_t bound){
    uint32_t low=0,high=bound/2u;
    while(low<high){
        uint32_t middle=(low+high+1u)/2u;
        if(2u*middle*denominator<=numerator)low=middle;else high=middle-1u;
    }
    return 2u*low;
}

int m10v_border_preview_fit(uint32_t width,uint32_t height,
                            uint32_t bound_width,uint32_t bound_height,
                            m10v_border_rect *out){
    if(!out||width<2u||height<2u||bound_width<2u||bound_height<2u||
       width>16384u||height>16384u||bound_width>16384u||bound_height>16384u||
       ((width|height|bound_width|bound_height)&1u))return -1;
    m10v_border_rect r={0,0,bound_width,bound_height};
    if(width*bound_height>height*bound_width)
        r.height=even_ratio(bound_width*height,width,bound_height);
    else r.width=even_ratio(bound_height*width,height,bound_width);
    if(r.width<2u||r.height<2u)return -1;
    publish_words(out,&r,sizeof(r)/4u);
    return 0;
}
