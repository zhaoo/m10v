#ifndef M10V_FILM_CARD_H
#define M10V_FILM_CARD_H
#include <stdint.h>
/* Square classic packaging with identifying labels inside the artwork. */
enum { M10V_CARD_WIDTH=128, M10V_CARD_HEIGHT=128, M10V_CARD_PIXELS=128*128,
       M10V_CARD_FIRST=749, M10V_CARD_COUNT=10,
       M10V_CARD_TILE_HEIGHT=172, M10V_CARD_TILE_PIXELS=128*172,
       M10V_CARD_DOTS_ID=857, M10V_CARD_MAX_PAGES=28,
       M10V_CARD_DOTS_WIDTH=16*M10V_CARD_MAX_PAGES, M10V_CARD_DOTS_HEIGHT=8 };
#define M10V_CARD_ID(i) ((i)<5?749u+(i):769u+(i)-5)
#define M10V_CARD_DOTS_OFFSET (M10V_CARD_COUNT*M10V_CARD_TILE_PIXELS*4u)
#define M10V_CARD_DESCRIPTOR_OFFSET (M10V_CARD_DOTS_OFFSET+M10V_CARD_DOTS_WIDTH*M10V_CARD_DOTS_HEIGHT*4u)
#define M10V_CARD_DIRECTORY_OFFSET (M10V_CARD_DESCRIPTOR_OFFSET+(M10V_CARD_COUNT+1u)*8u)
#define M10V_CARD_HEAP_BYTES (M10V_CARD_DIRECTORY_OFFSET+(M10V_CARD_DOTS_ID-M10V_CARD_FIRST+1u)*4u)
/* Caller supplies exactly M10V_CARD_PIXELS writable ARGB words. */
int m10v_film_card_render(uint32_t *,uint32_t film,uint32_t slot,uint32_t selected);
int m10v_film_card_custom(uint32_t *,const char *name,uint32_t slot,uint32_t selected);
/* Add a caption below the square artwork in a TILE_PIXELS buffer. */
void m10v_film_card_label(uint32_t *,const char *name,uint32_t focused);
void m10v_film_card_dots(uint32_t *,uint32_t current,uint32_t total);
#endif
