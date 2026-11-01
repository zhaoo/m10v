/* Minimal memory intrinsics required by freestanding ARM structure copies. */
#include <stddef.h>
void *memcpy(void*to,const void*from,size_t bytes){unsigned char*d=to;const unsigned char*s=from;for(size_t i=0;i<bytes;i++)d[i]=s[i];return to;}
void *memset(void*to,int value,size_t bytes){unsigned char*d=to;for(size_t i=0;i<bytes;i++)d[i]=(unsigned char)value;return to;}
void __aeabi_memcpy(void*d,const void*s,size_t n){memcpy(d,s,n);}
void __aeabi_memcpy4(void*d,const void*s,size_t n){memcpy(d,s,n);}
void __aeabi_memcpy8(void*d,const void*s,size_t n){memcpy(d,s,n);}
void __aeabi_memset(void*d,size_t n,int c){memset(d,c,n);}
void __aeabi_memset4(void*d,size_t n,int c){memset(d,c,n);}
void __aeabi_memclr(void*d,size_t n){memset(d,0,n);}
void __aeabi_memclr4(void*d,size_t n){memset(d,0,n);}

void __aeabi_memclr8(void*d,size_t n){memset(d,0,n);}
