#include "linux_wifi.h"
int m10v_linux_wifi_discover(void*ctx,m10v_wifi_query query,char name[16],int require_ap){
 uint8_t entries[512],request[32];unsigned found=0;char selected[16];
 if(!query||!name)return 0;
 int bytes=query(ctx,0x8912,entries,sizeof(entries));
 if(bytes<0||(unsigned)bytes>sizeof(entries)||bytes%32)return 0;
 for(unsigned at=0;at<(unsigned)bytes;at+=32){
  const uint8_t*p=entries+at;
  if(p[16]!=2||p[17]||p[20]!=192||p[21]!=168||p[22]||p[23]!=1)continue;
  unsigned n=0;while(n<16&&p[n])n++;if(!n||n==16)continue;
  for(unsigned i=0;i<32;i++)request[i]=i<16?p[i]:0;
  if(query(ctx,0x8913,request,sizeof(request))||!(request[16]&1)||(request[16]&8))continue;
  for(unsigned i=16;i<32;i++)request[i]=0;
  if(query(ctx,0x8b01,request,sizeof(request))||!request[16])continue;
  if(require_ap){
   for(unsigned i=16;i<32;i++)request[i]=0;
   if(query(ctx,0x8b07,request,sizeof(request))||request[16]!=3||request[17]||request[18]||request[19])continue;
  }
  if(++found>1)return 0;
  for(unsigned i=0;i<16;i++)selected[i]=(char)p[i];
 }
 if(found!=1)return 0;
 for(unsigned i=0;i<16;i++)name[i]=selected[i];return 1;
}
