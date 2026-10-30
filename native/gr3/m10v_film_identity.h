#ifndef M10V_FILM_IDENTITY_H
#define M10V_FILM_IDENTITY_H
#include <stdint.h>
/* Dedicated ProcessingManager ShootingInfo pool only. Other stock config
 * constructors retain their original extent and must never expose this tail. */
#define M10V_FILM_SI_BYTES 0x74270u
#define M10V_FILM_SI_EXTENT (M10V_FILM_SI_BYTES+16u)
#define M10V_FILM_IDENTITY_MAGIC 0x31444946u
typedef struct {uint32_t magic,generation,code,check;} m10v_film_identity;
static inline m10v_film_identity *m10v_film_identity_owned(uint32_t si){
 uint32_t manager=*(const volatile uint32_t *)0x55345328u;
 if((manager&3)||manager<0x55000000u||manager>0x80000000u-0x218u||
    *(const volatile uint32_t *)(uintptr_t)(manager+0x20)!=M10V_FILM_SI_EXTENT||
    (si&3)||si<0x55000000u||si>0x80000000u-M10V_FILM_SI_EXTENT)return 0;
 for(uint32_t i=0;i<100;i++)if(*(const volatile uint32_t *)(uintptr_t)(manager+0x88+i*4)==si){
  if(*(const volatile uint8_t *)(uintptr_t)(manager+0x24+i))return 0;
  return (m10v_film_identity *)(uintptr_t)(si+M10V_FILM_SI_BYTES);
 }
 return 0;
}
static inline uint32_t m10v_film_identity_read(uint32_t si){
 m10v_film_identity *p=m10v_film_identity_owned(si);if(!p)return 0;
 uint32_t magic=__atomic_load_n(&p->magic,__ATOMIC_ACQUIRE),generation=p->generation,code=p->code,check=p->check;
 __atomic_thread_fence(__ATOMIC_ACQUIRE);
 return magic==M10V_FILM_IDENTITY_MAGIC&&check==(~code^generation)&&
  magic==p->magic&&generation==p->generation?code:0;
}
#endif
