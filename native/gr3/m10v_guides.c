#include "m10v_guides.h"

typedef struct {
    uint16_t x, y;
} spiral_point;

/* A logarithmic spiral whose radius decreases by the golden ratio each
 * quarter turn, sampled every pi/16 for 2.25 turns. The fixed-point points
 * span the path's bounding box, which is fitted to the current photo box. */
static const spiral_point spiral[] = {
    {65535, 18113}, {61950, 31641}, {57058, 43099}, {51199, 52270},
    {44716, 59048}, {37937, 63438}, {31162, 65535}, {24660, 65517},
    {18657, 63624}, {13335, 60144}, { 8827, 55394}, { 5219, 49706},
    { 2552, 43413}, {  825, 36830}, {    0, 30253}, {    7, 23941},
    {  752, 18113}, { 2121, 12946}, { 3990,  8570}, { 6228,  5067},
    { 8704,  2478}, {11293,   801}, {13881,     0}, {16365,     7},
    {18657,   730}, {20690,  2059}, {22412,  3874}, {23790,  6046},
    {24809,  8450}, {25469, 10964}, {25784, 13476}, {25781, 15888},
    {25497, 18113}, {24974, 20087}, {24260, 21759}, {23405, 23097},
    {22459, 24086}, {21470, 24726}, {20482, 25032}, {19533, 25030},
    {18657, 24753}, {17881, 24246}, {17223, 23553}, {16697, 22723},
    {16308, 21805}, {16056, 20844}, {15935, 19885}, {15936, 18964},
    {16045, 18113}, {16245, 17360}, {16517, 16721}, {16844, 16210},
    {17205, 15832}, {17583, 15588}, {17961, 15471}, {18323, 15472},
    {18657, 15577}, {18954, 15771}, {19205, 16036}, {19406, 16353},
    {19555, 16704}, {19651, 17070}, {19697, 17437}, {19697, 17789},
    {19655, 18113}, {19579, 18401}, {19475, 18645}, {19350, 18840},
    {19212, 18985}, {19068, 19078}, {18924, 19123}, {18785, 19122},
    {18657, 19082},
};

static uint32_t minimum(uint32_t a, uint32_t b)
{
    return a < b ? a : b;
}

static uint32_t maximum(uint32_t a, uint32_t b)
{
    return a > b ? a : b;
}

/* Spans fit in 16 bits, so the Q16 multiply and rounding fit in one word. */
static uint32_t scale(uint32_t span, uint32_t fraction)
{
    return (span * fraction + 32768u) >> 16;
}

static void fill(const m10v_guides_surface *surface, m10v_guides_rect clip,
                 uint32_t left, uint32_t top, uint32_t right, uint32_t bottom,
                 uint32_t rgba)
{
    left = maximum(left, clip.left);
    top = maximum(top, clip.top);
    right = minimum(right, clip.right);
    bottom = minimum(bottom, clip.bottom);
    if (left >= right || top >= bottom)
        return;

    for (uint32_t y = top; y < bottom; ++y) {
        volatile uint32_t *row = surface->pixels + y * surface->stride_pixels;
        for (uint32_t x = left; x < right; ++x)
            row[x] = rgba;
    }
}

static void golden_grid(const m10v_guides_surface *surface, m10v_guides_rect clip,
                        uint32_t rgba)
{
    const m10v_guides_rect photo = surface->photo;
    const uint32_t width = photo.right - photo.left;
    const uint32_t height = photo.bottom - photo.top;
    static const uint16_t sections[] = {25033u, 40503u};
    for (unsigned i = 0; i < sizeof(sections) / sizeof(sections[0]); ++i) {
        uint32_t x = photo.left + scale(width, sections[i]);
        uint32_t y = photo.top + scale(height, sections[i]);
        fill(surface, clip, x - 1, photo.top, x + 1, photo.bottom, rgba);
        fill(surface, clip, photo.left, y - 1, photo.right, y + 1, rgba);
    }
}

static void spiral_segment(const m10v_guides_surface *surface, m10v_guides_rect clip,
                           int x, int y, int end_x, int end_y, uint32_t rgba)
{
    const int dx = x < end_x ? end_x - x : x - end_x;
    const int dy = y < end_y ? y - end_y : end_y - y;
    const int step_x = x < end_x ? 1 : -1;
    const int step_y = y < end_y ? 1 : -1;
    int error = dx + dy;

    for (;;) {
        fill(surface, clip, (uint32_t)x, (uint32_t)y, (uint32_t)x + 2,
             (uint32_t)y + 2, rgba);
        if (x == end_x && y == end_y)
            return;
        int twice = 2 * error;
        if (twice >= dy) {
            error += dy;
            x += step_x;
        }
        if (twice <= dx) {
            error += dx;
            y += step_y;
        }
    }
}

static void golden_spiral(const m10v_guides_surface *surface, m10v_guides_rect clip,
                          uint32_t mode, uint32_t rgba)
{
    const m10v_guides_rect photo = surface->photo;
    const uint32_t width = photo.right - photo.left - 2;
    const uint32_t height = photo.bottom - photo.top - 2;
    const uint32_t orientation = mode - M10V_GUIDES_SPIRAL_TOP_LEFT;
    const int x_direction = orientation & 1 ? -1 : 1;
    const int y_direction = orientation & 2 ? -1 : 1;
    const int x_origin = x_direction > 0 ? (int)photo.left : (int)photo.right - 2;
    const int y_origin = y_direction > 0 ? (int)photo.top : (int)photo.bottom - 2;
    int x = x_origin + x_direction * (int)scale(width, spiral[0].x);
    int y = y_origin + y_direction * (int)scale(height, spiral[0].y);

    for (unsigned i = 1; i < sizeof(spiral) / sizeof(spiral[0]); ++i) {
        int next_x = x_origin + x_direction * (int)scale(width, spiral[i].x);
        int next_y = y_origin + y_direction * (int)scale(height, spiral[i].y);
        spiral_segment(surface, clip, x, y, next_x, next_y, rgba);
        x = next_x;
        y = next_y;
    }
}

void m10v_guides_draw(const m10v_guides_surface *surface, uint32_t mode, uint32_t rgba)
{
    if (!mode || mode >= M10V_GUIDES_MODE_COUNT || !surface)
        return;
    if (!surface->pixels || ((uintptr_t)surface->pixels & 3u) ||
        !surface->width || !surface->height || surface->width > UINT16_MAX ||
        surface->height > UINT16_MAX || surface->stride_pixels < surface->width)
        return;

    uint64_t extent = (uint64_t)(surface->height - 1) * surface->stride_pixels
                    + surface->width;
    if (extent > surface->capacity_pixels ||
        extent > (UINTPTR_MAX - (uintptr_t)surface->pixels) / sizeof(uint32_t))
        return;

    const m10v_guides_rect photo = surface->photo;
    if (photo.right > surface->width || photo.bottom > surface->height ||
        photo.left >= photo.right || photo.top >= photo.bottom ||
        photo.right - photo.left < 2 || photo.bottom - photo.top < 2)
        return;

    const m10v_guides_rect clip = {
        maximum(photo.left, surface->clip.left),
        maximum(photo.top, surface->clip.top),
        minimum(photo.right, surface->clip.right),
        minimum(photo.bottom, surface->clip.bottom),
    };
    if (clip.left >= clip.right || clip.top >= clip.bottom)
        return;

    if (mode == M10V_GUIDES_GOLDEN_GRID)
        golden_grid(surface, clip, rgba);
    else
        golden_spiral(surface, clip, mode, rgba);
}
