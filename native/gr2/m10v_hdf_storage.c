#include "m10v_hdf_storage.h"
#include "m10v_boot.h"
#include "m10v_hdf_layout.h"
#ifndef GR2_HDF_INITIAL_STRENGTH
#define GR2_HDF_INITIAL_STRENGTH 0u
#endif
_Static_assert(GR2_HDF_INITIAL_STRENGTH<=3u,"invalid GR II initial HDF strength");
#include "../../compat/gr2-v1/native/gr3/m10v_sd_library.h"
static const char names[2][16]={"H:/M10VHD0.BIN","H:/M10VHD1.BIN"};
typedef struct {uint32_t sequence,strength,bank;} record;
static int span(const void *p,uint32_t n){uintptr_t a=(uintptr_t)p;return a&&!(a&3u)&&a<=UINT32_MAX-n;}
static int disjoint(const void *a,uint32_t an,const void *b,uint32_t bn){
 uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x+an<=y||y+bn<=x;
}
static int decode(const uint8_t *bytes,record *out){
 if(m10v_sd_u32(bytes)!=0x31464448u||m10v_sd_u32(bytes+4)!=1u||
    m10v_sd_u32(bytes+12)>3u||m10v_sd_u32(bytes+16)||m10v_sd_crc(bytes,20)!=m10v_sd_u32(bytes+20))return 0;
 out->sequence=m10v_sd_u32(bytes+8);out->strength=m10v_sd_u32(bytes+12);return 1;
}
static int latest(const gr2_storage_io *io,record *out){
 uint8_t bytes[25];record candidates[2];uint32_t good[2]={0,0};
 for(uint32_t i=0;i<2;i++){
  if(io->read(names[i],bytes,sizeof(bytes))==24)good[i]=(uint32_t)decode(bytes,&candidates[i]);
  candidates[i].bank=i;
 }
 if(!good[0]&&!good[1])return 0;
 uint32_t i=!good[0]||(good[1]&&candidates[1].sequence>candidates[0].sequence);
 *out=candidates[i];return 1;
}
int gr2_hdf_journal_load(const gr2_storage_io *io,uint32_t *strength,uint32_t *sequence){
 if(!span(io,sizeof(*io))||!io->read||!span(strength,4)||!span(sequence,4)||
    !disjoint(strength,4,sequence,4)||!disjoint(io,sizeof(*io),strength,4)||!disjoint(io,sizeof(*io),sequence,4))return 0;
 record active;if(!latest(io,&active))return 0;
 *strength=active.strength;*sequence=active.sequence;return 1;
}
static void put32(uint8_t *out,uint32_t value){for(uint32_t i=0;i<4;i++)out[i]=(uint8_t)(value>>(8u*i));}
static int publish(const gr2_storage_io *io,uint32_t sequence,uint32_t strength,uint32_t bank){
 uint8_t bytes[24],back[25];record validated,active;
 put32(bytes,0x31464448u);put32(bytes+4,1);put32(bytes+8,sequence);put32(bytes+12,strength);put32(bytes+16,0);put32(bytes+20,m10v_sd_crc(bytes,20));
 if(io->write(names[bank],bytes,sizeof(bytes))!=24||io->read(names[bank],back,sizeof(back))!=24||!decode(back,&validated))return 0;
 for(uint32_t i=0;i<24;i++)if(back[i]!=bytes[i])return 0;
 return latest(io,&active)&&active.sequence==sequence&&active.strength==strength&&active.bank==bank;
}
int gr2_hdf_journal_store(const gr2_storage_io *io,uint32_t strength){
 if(strength>3u||!span(io,sizeof(*io))||!io->read||!io->write)return 0;
 record active;if(!latest(io,&active)||active.sequence==UINT32_MAX)return 0;
 /* Normally bank==sequence&1. Preserve the actual active bank even if a
  * manually moved valid file has the opposite parity. */
 return publish(io,active.sequence+1u,strength,1u-active.bank);
}

static const gr2_storage_io native_io={gr2_file_read,gr2_file_write};
int gr2_hdf_load_state(uint32_t *strength,uint32_t *sequence){
 return gr2_ui_storage_ready()&&gr2_hdf_journal_load(&native_io,strength,sequence);
}
int gr2_hdf_save_state(uint32_t strength){
 return gr2_ui_storage_ready()&&gr2_hdf_journal_store(&native_io,strength);
}
int gr2_hdf_initialize_state(void){
 if(!gr2_ui_storage_ready())return 0;
 uint32_t strength,sequence;
 if(gr2_hdf_journal_load(&native_io,&strength,&sequence))return 1;
 if(gr2_hdf_journals_absent()!=1)return 0;
 /* Preserve valid camera settings. Only a proven first use may consume the
  * compiled page default, after the original pool admits a nonzero grade. */
 if(GR2_HDF_INITIAL_STRENGTH&&!gr2_hdf_prepare_pool(GR2_HDF_INITIAL_STRENGTH))return 0;
 return publish(&native_io,1,GR2_HDF_INITIAL_STRENGTH,1);
}
