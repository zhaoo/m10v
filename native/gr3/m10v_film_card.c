/* Square packaging artwork. Bounded glyph coverage from OFL Noto Sans. */
#include "m10v_film_card.h"
#include "m10v_library.h"
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
/* Freestanding ARMv6 has no division service in the resource renderer. */
static uint32_t divide(uint32_t n,uint32_t d){uint32_t q=0,r=0;for(uint32_t b=32;b;b--){r=(r<<1)|((n>>(b-1))&1u);if(r>=d){r-=d;q|=1u<<(b-1);}}return q;}
/* Explicit line boxes keep the largest possible name clear of the speed. */
static void text(uint32_t *p,const char *s,uint32_t y,uint32_t height,uint32_t color){
 uint32_t width=0;for(uint32_t k=0;s[k];k++){uint32_t c=(uint8_t)s[k];if(c<32||c>126)return;width+=smooth_width[c-32];}
 if(!width)return;
 uint32_t w=width*height/20,h=height;if(w>112){w=112;h=divide(20*112,width);}if(!h)h=1;
 uint32_t x=8,offset=0,k=0,loaded=~0u,source=0,fraction=0;uint8_t pixels[320],row[40];
 for(uint32_t j=0,r=0,f=0;j<h;j++){row[j]=(uint8_t)r;f+=20;while(f>=h){f-=h;r++;}}
 for(uint32_t i=0;i<w;i++){
  while(s[k]&&source>=offset+smooth_width[(uint8_t)s[k]-32])offset+=smooth_width[(uint8_t)s[k++]-32];
  if(!s[k]||source-offset>=16)continue;
  if(loaded!=k){glyph(pixels,(uint8_t)s[k]-32);loaded=k;}
  for(uint32_t j=0;j<h&&y+j<M10V_CARD_HEIGHT;j++)blend(p,(y+j)*M10V_CARD_WIDTH+x+i,pixels[row[j]*16+source-offset],color);
  fraction+=width;while(fraction>=w){fraction-=w;source++;}
 }
}
static int render(uint32_t *p,const char *main,const char *sub,uint32_t c,uint32_t ink,const char *brand,uint32_t accent,uint32_t motif,uint32_t slot,uint32_t selected){
 if(!p||slot>=10)return -1;
 for(uint32_t y=0;y<128;y++)for(uint32_t x=0;x<128;x++){
  uint32_t v=c;int xx=(int)x,yy=(int)y;
  if(motif==0){if(y>=88||x+y>168)v=accent;if(x+y>205)v=0xffe96717u;}
  else if(motif==1||motif==2){int q=(xx+75)*(xx+75)+(yy+84)*(yy+84);if(q>47000)v=accent;if(q>55000)v=motif==1?0xffef762au:0xff733a63u;}
  else if(motif==3){if(y>87&&x>128-y&&x<y)v=0xff0d4051u;if(y>101&&((x+6*y)%47)<3)v=accent;if(y>108&&((x+6*y)%47)<2)v=0xff37e6e4u;}
  else if(motif==4){if(yy>=77+(90-xx)*51/65&&yy>=77+(xx-90)*30/38){v=accent;if(y<93)v=ink;}if(y>89&&yy>184-xx)v=0xff777c7bu;}
  else if(motif==5){if(y>104)v=0xff146485u;if(y>101&&y<108)v=0xff52aac0u;if(y>91&&(x<22||x>105)){int dx=xx-(x<22?8:121),dy=(yy-92)%12-5;if(dx*dx+dy*dy<95)v=accent;}}
  else if(motif==6){if(y>83&&((x+2*y)%26)<14)v=accent;}
  else if(motif==7){if(y>108-x/4)v=accent;if(y>116)v=0xff252d2du;if(y>120&&y<125&&x%13<6)v=c;}
  else if(motif==8){if(y>79&&((x+y)%25)<13)v=accent;}
  else if(motif==9){if(y>89&&y<124&&(y+x/12)%8<2)v=accent;}
  else if(motif==10){if(y>88&&((x/8+y/8)%3)==0)v=accent;}
  else if(motif==11){static const uint32_t rainbow[]={0xffd95155u,0xffed9d38u,0xffe9cb42u,0xff569c72u,0xff5089adu};if(y>101&&(y<107||x<8||x>119))v=rainbow[x/26];}
  p[y*128+x]=rgba(v);
 }
 /* Tiny motif details remain below the name and speed line boxes. */
 if(motif==1){for(uint32_t x=101;x<=117;x+=8){rect(p,x,108,1,20,0xff592a24u);rect(p,x-4,107,9,2,0xff592a24u);rect(p,x-2,104,5,2,0xff592a24u);}}
 if(motif==3){for(uint32_t x=5;x<128;x+=24){rect(p,x,94,1,25,0xff2a707eu);rect(p,x-1,92,3,3,0xff74f7edu);}}
 text(p,brand,7,15,motif==3?accent:ink);
 text(p,main,29,40,ink);text(p,sub,73,32,ink);
 if(selected)for(uint32_t y=0;y<12;y++)rect(p,116+y,y,12-y,1,0xffe9dc45u);
 return 0;
}
int m10v_film_card_render(uint32_t *p,uint32_t film,uint32_t slot,uint32_t selected){
 uint32_t i;if(film>=1&&film<=78)i=film-1;else if(film>=289&&film<=305)i=78+film-289;else if(film>=309&&film<=317)i=78+film-292;else if(film>=306&&film<=308)i=104+film-306;else if(M10V_FOUR_LOOKS(film))i=107+film-318;else return -1;
 return render(p,box_labels+box_label_offsets[box_cards[i].main],box_labels+box_label_offsets[box_cards[i].sub],box_palette[box_cards[i].color],box_palette[box_cards[i].ink],box_labels+box_label_offsets[box_cards[i].brand],box_palette[box_cards[i].accent],box_cards[i].motif,slot,selected);
}
int m10v_film_card_custom(uint32_t *p,const char *name,uint32_t slot,uint32_t selected){
 if(!p||!name||slot>=10)return -1;
 uint32_t hash=2166136261u,length=0;
 for(;length<24&&name[length];length++){uint32_t c=(uint8_t)name[length];if(c<32||c>126)return -1;hash=(hash^c)*16777619u;}
 if(!length||length==24)return -1;
 static const uint32_t colors[]={0xff508b9du,0xffa484adu,0xffc78d48u,0xff669c7au,0xffc94c47u,0xff667fa7u,0xffb47787u,0xff917b61u};
 return render(p,name,"LUT",0xffeee9d9u,0xff25363bu,"M10V",colors[hash&7],8,slot,selected);
}
