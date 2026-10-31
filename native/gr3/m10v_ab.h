#ifndef M10V_AB_H
#define M10V_AB_H
#include "m10v_tone.h"
#include <stdint.h>
#include "m10v_library.h"
/* Lives in the first explicitly owned settings controller, UI thread only.
 * Pair persists separately; enabled never persists. LiveView owns no A/B UI. */
typedef struct {
 uint32_t a,b,enabled,down,selected,film_a,film_b;
 uint32_t reserved[4]; /* Retired overlay fields: keep the 44-byte ABI. */
} m10v_ab;
/* Exact stock ImageControl ordering, including stock Hi-Contrast BW (tone16).
 * The five installed films occupy their existing real carrier positions. */
static inline uint32_t m10v_ab_tone(uint32_t choice){
 static const uint8_t tones[12]={11,12,13,14,15,16,22,17,18,19,20,21};
 if(M10V_APPENDED_SLOTS&&choice>=12&&choice<22)return 25+choice-12;
 return choice<12?tones[choice]:0;
}
static inline uint32_t m10v_ab_slot(uint32_t choice){
 return m10v_tone_slot(m10v_ab_tone(choice));
}
static inline const char *m10v_ab_stock_name(uint32_t choice){
 static const char names[12][20]={"Standard","Film","Monotone","Soft Monotone",
  "Hard Monotone","Hi-Contrast B&W","Negative Film","Positive Film","Film","Film","Film","Film"};
 if(M10V_APPENDED_SLOTS){
  static const char restored[5][20]={"Vivid","Bleach Bypass","Retro","HDR Tone","Cross Processing"};
  if(choice==1)return restored[0];if(choice>=8&&choice<12)return restored[choice-7];
 }
 return choice<12?names[choice]:"Film";
}
static inline uint32_t m10v_ab_caption(uint32_t choice,uint32_t film){
 static const uint16_t stock[12]={4,268,269,270,271,272,273,274,275,276,277,278};
 if(choice>=M10V_TONE_CHOICES)return 4;
 if(m10v_ab_slot(choice)>=M10V_SLOT_COUNT)return choice<12?stock[choice]:4;
 if(M10V_FOUR_LOOKS(film))return M10V_FOUR_LOOKS_NAME(film);
 if(M10V_EXTRA_FILM(film))return M10V_EXTRA_FILM_NAME(film);
 if(M10V_C41(film))return M10V_C41_NAME_FIRST+film-312;
 if(M10V_ANIME_E6(film))return 1142+film-M10V_ANIME_FIRST;
 if(M10V_D76(film))return 1130+film-M10V_D76_FIRST;
 if(film==M10V_5213_ID)return 1128;
 if(M10V_STYLE(film))return 1104+film-M10V_STYLE_FIRST;
 if(film==M10V_PIXEL_ID)return 1023;
 if(film==M10V_CHAR_ID)return 1012;
 if(film>=1&&film<=32)return 785+film;
 if(film==33)return 860;
 if(film>=34&&film<=65)return 879+film-34;
 if(film==66)return 911;
 if(film>=67&&film<=68)return 930+film-67;
 if(film>=69&&film<=78)return 978+film-69;
 return 997+m10v_ab_slot(choice);
}
static inline int m10v_ab_start(m10v_ab *s,uint32_t a,uint32_t b,uint32_t current,uint32_t fa,uint32_t fb){
 if(a>=M10V_TONE_CHOICES||b>=M10V_TONE_CHOICES||a==b||(m10v_ab_slot(a)<M10V_SLOT_COUNT&&!fa)||(m10v_ab_slot(b)<M10V_SLOT_COUNT&&!fb)){s->enabled=0;return -1;}
 s->a=a;s->b=b;s->film_a=fa;s->film_b=fb;
 s->selected=current==b?b:a;s->down=0;s->enabled=1;return 0;
}
/* Returns destination+1. Caller commits only after stock setter readback. */
static inline uint32_t m10v_ab_key(m10v_ab *s,uint32_t key,uint32_t current){
 if(!s->enabled)return 0;
 if(current!=s->selected){s->enabled=0;s->down=0;return 0;}
 if(key==0x36){s->down=0;return 0;}
 if(key!=0x37||s->down)return 0;
 s->down=1;return (s->selected==s->a?s->b:s->a)+1;
}
static inline void m10v_ab_commit(m10v_ab *s,uint32_t slot){s->selected=slot;}
#endif
