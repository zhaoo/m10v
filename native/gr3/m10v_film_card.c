/* Portrait artwork. Bounded glyph coverage generated from OFL Noto Sans. */
#include "m10v_film_card.h"
#include "m10v_film_card_data.h"
static uint32_t rgba(uint32_t c){return (c&0xff00ff00u)|((c&255u)<<16)|((c>>16)&255u);}
static void glyph(uint8_t *pixels,uint32_t ch){
 uint32_t at=0,i=glyph_offsets[ch],end=glyph_offsets[ch+1];
 while(i<end&&at<320){
  uint32_t token=glyph_data[i++],run=(token&127u)+1u;
  uint32_t repeated=token&128u,value=repeated?glyph_data[i++]:0;
  for(uint32_t n=0;n<run&&at<320;n++)pixels[at++]=(uint8_t)(repeated?value:glyph_data[i++]);
 }
}
static void blend(uint32_t *p,uint32_t at,uint32_t a,uint32_t color){
 if(!a)return;
 uint32_t old=rgba(p[at]),out=0xff000000u;
 for(uint32_t shift=0;shift<24;shift+=8)out|=((((color>>shift)&255)*a+((old>>shift)&255)*(255-a)+127)/255)<<shift;
 p[at]=rgba(out);
}
static void rect(uint32_t *p,uint32_t x,uint32_t y,uint32_t w,uint32_t h,uint32_t c){
 for(uint32_t j=y;j<y+h&&j<M10V_CARD_HEIGHT;j++)for(uint32_t i=x;i<x+w&&i<M10V_CARD_WIDTH;i++)p[j*M10V_CARD_WIDTH+i]=rgba(c);
}
/* Fit every label inside the 96px paper area, never into another card. */
static void text(uint32_t *p,const char *s,uint32_t y,uint32_t color){
 uint32_t width=0;for(uint32_t k=0;s[k];k++){uint32_t c=(uint8_t)s[k];if(c<32||c>126)return;width+=smooth_width[c-32];}
 if(!width)return;
 uint32_t scale=width>96?width:96,w=width>96?96:width,h=0;
 while((h+1)*scale<=20*96)h++;
 if(!h)h=1;
 uint32_t x=(120-w)/2,offset=0,k=0,loaded=~0u;uint8_t pixels[320];
 for(uint32_t i=0;i<w;i++){
  uint32_t source=i*scale/96;
  while(s[k]&&source>=offset+smooth_width[(uint8_t)s[k]-32])offset+=smooth_width[(uint8_t)s[k++]-32];
  if(!s[k]||source-offset>=16)continue;
  if(loaded!=k){glyph(pixels,(uint8_t)s[k]-32);loaded=k;}
  for(uint32_t j=0;j<h&&y+j<142;j++)blend(p,(y+j)*120+x+i,pixels[(j*scale/96)*16+source-offset],color);
 }
}
static int render(uint32_t *p,const char *main,const char *sub,uint32_t c,uint32_t ink,const char *brand,uint32_t header,uint32_t accent,uint32_t slot,uint32_t selected){
 if(!p||slot>=10)return -1;
 for(uint32_t i=0;i<M10V_CARD_PIXELS;i++)p[i]=rgba(0xff20271fu);
 rect(p,6,5,108,138,0xff92968bu);rect(p,8,7,104,134,c);
 rect(p,8,7,104,30,header);rect(p,8,37,104,1,0xfff3eedcu);
 text(p,brand,16,header==0xffffcf32u?0xffae2636u:0xfffff8e5u);
 text(p,main,60,ink);text(p,sub,92,ink);rect(p,8,133,104,8,accent);
 if(selected)for(uint32_t y=0;y<16;y++)rect(p,102+y,2+y,16-y,1,0xffe9dc45u);
 return 0;
}
int m10v_film_card_render(uint32_t *p,uint32_t film,uint32_t slot,uint32_t selected){
 uint32_t i;if(film>=1&&film<=78)i=film-1;else if(film>=289&&film<=305)i=78+film-289;else if(film>=309&&film<=316)i=78+film-292;else return -1;
 return render(p,box_labels+box_label_offsets[box_cards[i].main],box_labels+box_label_offsets[box_cards[i].sub],box_palette[box_cards[i].color],box_palette[box_cards[i].ink],box_labels+box_label_offsets[box_cards[i].brand],box_palette[box_cards[i].header],box_palette[box_cards[i].accent],slot,selected);
}
int m10v_film_card_custom(uint32_t *p,const char *name,uint32_t slot,uint32_t selected){
 if(!p||!name||slot>=10)return -1;
 uint32_t hash=2166136261u,length=0;
 for(;length<24&&name[length];length++){uint32_t c=(uint8_t)name[length];if(c<32||c>126)return -1;hash=(hash^c)*16777619u;}
 if(!length||length==24)return -1;
 static const uint32_t colors[]={0xff508b9du,0xffa484adu,0xffc78d48u,0xff669c7au,0xffc94c47u,0xff667fa7u,0xffb47787u,0xff917b61u};
 return render(p,name,"LUT",0xffeee9d9u,0xff25363bu,"M10V",colors[hash&7],colors[hash&7],slot,selected);
}
