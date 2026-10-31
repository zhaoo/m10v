/* Generated from web/gr3/film-directory.json. Display order is not identity. */
#ifndef M10V_FILM_DIRECTORY_H
#define M10V_FILM_DIRECTORY_H
#include <stdint.h>
#define M10V_DIRECTORY_COUNT 51u
#define M10V_DIRECTORY_GROUPS 6u
#define M10V_DIRECTORY_GROUP_RESOURCE 1129u
static const struct {uint16_t id;uint8_t group;char name[24];} m10v_directory[]={
{33,0,"800T"},
{66,0,"5207"},
{62,0,"5219"},
{78,0,"5203"},
{298,0,"5213"},
{77,0,"2460"},
{318,0,"2383"},
{69,1,"Portra 160"},
{37,1,"Portra 400"},
{70,1,"Fuji Industrial 100"},
{73,1,"Fuji C200"},
{56,1,"Fuji Superia 200"},
{36,1,"Fuji Pro 400H"},
{35,1,"Kodak Gold 200"},
{58,1,"Kodak UltraMax 400"},
{74,1,"ProImage 100"},
{34,1,"Ektar 100"},
{71,1,"Lucky C200"},
{67,1,"Harman Phoenix II"},
{68,1,"Harman Red"},
{292,1,"Lomography"},
{312,1,"OptiColour 200"},
{313,1,"NC500"},
{294,2,"Fuji Velvia 50"},
{309,2,"Fuji Provia 100F"},
{310,2,"Kodak Ektachrome E100"},
{311,2,"5294"},
{75,3,"T-Max 100"},
{299,3,"Tri-X 400"},
{300,3,"Ilford Delta 100"},
{301,3,"Ilford Pan 400"},
{302,3,"Rollei Infrared 400"},
{303,3,"Ilford SFX 200"},
{304,3,"Fomapan 400"},
{305,3,"CatLABS X Film 80"},
{314,3,"ACROS II 100"},
{315,3,"Double-X 5222"},
{289,4,"Kodak Charmera"},
{72,4,"CCD"},
{293,4,"Polaroid"},
{296,4,"Cyanotype"},
{290,4,"Pixel Worlds"},
{76,4,"Aerochrome"},
{316,4,"LomoChrome Turquoise"},
{317,4,"Instax Color"},
{321,4,"LomoChrome Purple"},
{291,5,"Leica Monochrome"},
{297,5,"German Cool"},
{65,5,"GR2"},
{319,5,"Classic Negative"},
{320,5,"Classic Chrome"},
};
static const uint8_t m10v_directory_first[7]={0,7,23,27,37,46,51};
static inline const char *m10v_directory_name(uint32_t id){for(uint32_t i=0;i<M10V_DIRECTORY_COUNT;i++)if(m10v_directory[i].id==id)return m10v_directory[i].name;return 0;}
#endif
