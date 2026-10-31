/* Data-only format validator. SHA-256 binds complete records to the unchanged
 * renderer's supported recipe revision, including captions and artwork. */
#include "m10v_sd_library.h"
#include "m10v_sd_contract.h"
#include "m10v_custom_isp.h"
uint32_t m10v_sd_u32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
uint32_t m10v_sd_crc(const uint8_t *p,uint32_t n){uint32_t c=0xffffffffu;for(uint32_t i=0;i<n;++i){c^=p[i];for(uint32_t k=0;k<8;++k)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return ~c;}
static uint32_t rotr(uint32_t v,uint32_t n){return (v>>n)|(v<<(32-n));}
static void block(uint32_t *h,const uint8_t *p){
 static const uint32_t k[64]={
 0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
 0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
 0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
 0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
 0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
 0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
 0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
 0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
 uint32_t w[64];for(uint32_t i=0;i<16;++i)w[i]=((uint32_t)p[i*4]<<24)|((uint32_t)p[i*4+1]<<16)|((uint32_t)p[i*4+2]<<8)|p[i*4+3];
 for(uint32_t i=16;i<64;++i){uint32_t a=w[i-15],b=w[i-2];w[i]=w[i-16]+(rotr(a,7)^rotr(a,18)^(a>>3))+w[i-7]+(rotr(b,17)^rotr(b,19)^(b>>10));}
 uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],v=h[7];
 for(uint32_t i=0;i<64;++i){uint32_t t=v+(rotr(e,6)^rotr(e,11)^rotr(e,25))+((e&f)^(~e&g))+k[i]+w[i];uint32_t q=(rotr(a,2)^rotr(a,13)^rotr(a,22))+((a&b)^(a&c)^(b&c));v=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+q;}
 h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=v;
}
uint32_t m10v_sd_header(const uint8_t *p,uint32_t total){
 if(!p)return 0;
 uint32_t version=m10v_sd_u32(p+8);
 static const uint8_t magic[8]={'M','1','0','V','S','D','1',0};
 for(uint32_t i=0;i<8;++i)if(p[i]!=(i==6&&version==2?'2':magic[i]))return 0;
 uint32_t count=m10v_sd_u32(p+16);
 if((version!=1&&version!=2)||!count||count>M10V_SD_MAX_FILMS||m10v_sd_u32(p+20)!=M10V_SD_RECORD_BYTES||
 m10v_sd_u32(p+24)!=239||m10v_sd_u32(p+28)!=1||total!=4096+count*M10V_SD_RECORD_BYTES||m10v_sd_u32(p+12)!=total||
 m10v_sd_crc(p,4092)!=m10v_sd_u32(p+4092))return 0;
 for(uint32_t i=32;i<64;++i)if(p[i])return 0;
 for(uint32_t i=0;i<count;++i){uint32_t id=m10v_sd_u32(p+64+12*i);if(id<33||(id>(version==2?288u:M10V_FILM_COUNT)&&!M10V_BUILTIN(id))||m10v_sd_u32(p+72+12*i)!=1)return 0;
  for(uint32_t j=0;j<i;++j)if(m10v_sd_u32(p+64+12*j)==id)return 0;}
 for(uint32_t i=64+count*12;i<4092;++i)if(p[i])return 0;
 return count;
}
/* Direct constant references avoid an absolute .rodata pointer table; the
 * bounded runtime relocator intentionally rejects such pointer relocations. */
static __attribute__((noinline)) int renderer_matches(const uint8_t *p,const uint8_t *expected){
 for(uint32_t i=0;i<32;i++)if(p[i]!=expected[i])return 0;
 return 1;
}
static uint32_t custom_record(const uint8_t *p,uint32_t id){
 static const uint8_t magic[8]={'M','1','0','V','R','E','C','2'};
 if(id<79||id>288||m10v_sd_u32(p+12)!=4)return 0;
 for(uint32_t i=0;i<8;++i)if(p[i]!=magic[i])return 0;
 uint32_t name=0;for(;name<24&&p[16+name];++name)if(p[16+name]<32||p[16+name]>126)return 0;
 if(!name||name>23)return 0;
 for(uint32_t i=16+name;i<40;++i)if(p[i])return 0;
 static const uint8_t mark[4]={'M','1','0','V'};for(uint32_t i=0;i<4;++i)if(p[40+i]!=mark[i])return 0;
 for(uint32_t i=44;i<64;++i)if(p[i])return 0;
 if(p[6655])return 0;
 if(!m10v_custom_isp_valid(p))return 0;
 if(!renderer_matches(p+8448,m10v_sd_renderer_hash)&&
    !renderer_matches(p+8448,m10v_sd_pre_c41_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_d76_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_anime_e6_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_orientation_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_retired_anime_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_mono_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_isp_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_halo_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_aerocolor_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_directory_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_multiselect_renderer)&&
    !renderer_matches(p+8448,m10v_sd_texture_prior_renderer)&&
    !renderer_matches(p+8448,m10v_sd_prior_renderer)&&
    !renderer_matches(p+8448,m10v_sd_previous_renderer)&&
    !renderer_matches(p+8448,m10v_sd_recent_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_styles_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_instax_renderer)&&
    !renderer_matches(p+8448,m10v_sd_pre_four_looks_renderer))return 0;
 for(uint32_t i=8480;i<M10V_SD_RECORD_BYTES-4;++i)if(p[i])return 0;
 uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
 uint8_t buf[64];uint32_t used=0,bytes=0;
 for(uint32_t i=0;i<name+1+6591;++i){uint8_t v=i<name?p[16+i]:i==name?0:p[64+i-name-1];buf[used++]=v;++bytes;
  if(used==64){block(h,buf);used=0;}}
 buf[used++]=128;if(used>56){for(uint32_t i=used;i<64;++i)buf[i]=0;block(h,buf);used=0;}
 for(uint32_t i=used;i<56;++i)buf[i]=0;
 uint32_t bits=bytes*8;for(uint32_t i=56;i<64;++i)buf[i]=0;for(uint32_t i=0;i<4;++i)buf[63-i]=(uint8_t)(bits>>(8*i));block(h,buf);
 for(uint32_t i=0;i<32;++i)if((uint8_t)(h[i>>2]>>(24-8*(i&3)))!=p[6656+i])return 0;
 return id;
}
uint32_t m10v_sd_record(const uint8_t *p,uint32_t n,uint32_t id){
 if(!p||n!=M10V_SD_RECORD_BYTES||id<33||(id>288&&!M10V_BUILTIN(id))||m10v_sd_u32(p+8)!=id||m10v_sd_crc(p,n-4)!=m10v_sd_u32(p+n-4))return 0;
 if(M10V_CUSTOM(id))return custom_record(p,id);
 uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
 for(uint32_t i=0;i<n;i+=64)block(h,p+i);
 uint8_t tail[64];for(uint32_t i=0;i<64;++i)tail[i]=0;tail[0]=128;
 uint32_t bits=n*8;for(uint32_t i=0;i<4;++i)tail[63-i]=(uint8_t)(bits>>(8*i));block(h,tail);
 uint32_t current=1,legacy=1,prior=1,previous=1,recent=1,pre_styles=1,texture_prior=1,pre_multiselect=1,pre_directory=1,pre_aerocolor=1,pre_d76=1,pre_isp=1,pre_halo=1,pre_anime_e6=1,pre_mono=1,pre_c41=1,pre_instax=1,pre_orientation=1,pre_retired_anime=1,pre_square_art=1,pre_four_looks=1;
 for(uint32_t i=0;i<32;++i){uint8_t v=(uint8_t)(h[i>>2]>>(24-8*(i&3)));
  if(id>317||v!=m10v_sd_pre_square_art_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_square_art=0;
  if(id>317||v!=m10v_sd_pre_four_looks_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_four_looks=0;
  if(id>297||v!=m10v_sd_pre_multiselect_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_multiselect=0;
  if(id>297||v!=m10v_sd_texture_prior_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])texture_prior=0;
  if(id>297||v!=m10v_sd_pre_directory_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_directory=0;
  if(id>298||v!=m10v_sd_pre_d76_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_d76=0;
  if(id>298||v!=m10v_sd_pre_aerocolor_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_aerocolor=0;
  if(id>305||v!=m10v_sd_pre_isp_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_isp=0;
  if(id>305||v!=m10v_sd_pre_halo_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_halo=0;
  if(id>305||v!=m10v_sd_pre_anime_e6_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_anime_e6=0;
  if(id>316||v!=m10v_sd_pre_instax_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_instax=0;
  if(id>316||v!=m10v_sd_pre_orientation_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_orientation=0;
  if(id>313||v!=m10v_sd_pre_retired_anime_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_retired_anime=0;
  if(id>311||v!=m10v_sd_pre_c41_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_c41=0;
  if(id>311||v!=m10v_sd_pre_mono_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_mono=0;
  if(v!=m10v_sd_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])current=0;
  if(id>=M10V_PIXEL_ID||v!=m10v_sd_previous_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])previous=0;
  if(id>=M10V_PIXEL_ID||v!=m10v_sd_recent_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])recent=0;
  if(id>290||v!=m10v_sd_pre_styles_hashes[id>=M10V_CHAR_ID?id-243:id-33][i])pre_styles=0;
  if(id>72||v!=m10v_sd_legacy_hashes[id-33][i])legacy=0;
  if(id>78||v!=m10v_sd_prior_hashes[id-33][i])prior=0;}
 if(!current&&!legacy&&!prior&&!previous&&!recent&&!pre_styles&&!texture_prior&&!pre_multiselect&&!pre_directory&&!pre_aerocolor&&!pre_d76&&!pre_halo&&!pre_isp&&!pre_anime_e6&&!pre_mono&&!pre_c41&&!pre_retired_anime&&!pre_orientation&&!pre_instax&&!pre_square_art&&!pre_four_looks)return 0;
 return id;
}
