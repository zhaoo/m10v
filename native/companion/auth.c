/* SHA-256 (FIPS 180-4) and HMAC (RFC 2104), scalar freestanding core.
 * Constants are the specified fractional prime roots. No camera ABI calls.
 * https://doi.org/10.6028/NIST.FIPS.180-4
 * https://www.rfc-editor.org/rfc/rfc2104.html */
#include "auth.h"
typedef m10v_sha256_context sha_context;
static const uint32_t rounds[64]={0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
static uint32_t rotate(uint32_t v,unsigned n){return (v>>n)|(v<<(32-n));}
static void block(sha_context*s,const uint8_t *p){
 uint32_t w[64];for(unsigned i=0;i<16;i++)w[i]=((uint32_t)p[4*i]<<24)|((uint32_t)p[4*i+1]<<16)|((uint32_t)p[4*i+2]<<8)|p[4*i+3];
 for(unsigned i=16;i<64;i++){uint32_t x=w[i-15],y=w[i-2];w[i]=w[i-16]+(rotate(x,7)^rotate(x,18)^(x>>3))+w[i-7]+(rotate(y,17)^rotate(y,19)^(y>>10));}
 uint32_t a=s->h[0],b=s->h[1],c=s->h[2],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
 for(unsigned i=0;i<64;i++){uint32_t t=h+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^(~e&g))+rounds[i]+w[i];uint32_t u=(rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&b)^(a&c)^(b&c));h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u;}
 s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void init(sha_context*s){static const uint32_t initial[8]={0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};for(unsigned i=0;i<8;i++)s->h[i]=initial[i];s->used=0;s->total=0;}
static void update(sha_context*s,const uint8_t*data,uint32_t bytes){s->total+=bytes;while(bytes){uint32_t n=64-s->used;if(n>bytes)n=bytes;for(uint32_t i=0;i<n;i++)s->block[s->used+i]=data[i];data+=n;bytes-=n;s->used+=n;if(s->used==64){block(s,s->block);s->used=0;}}}
static void finish(sha_context*s,uint8_t out[32]){uint64_t bits=s->total*8;s->block[s->used++]=0x80;if(s->used>56){while(s->used<64)s->block[s->used++]=0;block(s,s->block);s->used=0;}while(s->used<56)s->block[s->used++]=0;for(unsigned i=0;i<8;i++)s->block[63-i]=(uint8_t)(bits>>(8*i));block(s,s->block);for(unsigned i=0;i<32;i++)out[i]=(uint8_t)(s->h[i/4]>>(24-8*(i%4)));}
static void wipe(void*p,uint32_t bytes){volatile uint8_t*v=p;for(uint32_t i=0;i<bytes;i++)v[i]=0;}
void m10v_sha256(const void *data,uint32_t bytes,uint8_t out[32]){sha_context s;init(&s);update(&s,data,bytes);finish(&s,out);wipe(&s,sizeof(s));}
void m10v_hmac256(const void *key,uint32_t key_bytes,const void *data,uint32_t bytes,uint8_t out[32]){
 uint8_t pad[64],digest[32];for(unsigned i=0;i<64;i++)pad[i]=0;if(key_bytes>64)m10v_sha256(key,key_bytes,pad);else for(uint32_t i=0;i<key_bytes;i++)pad[i]=((const uint8_t*)key)[i];
 for(unsigned i=0;i<64;i++)pad[i]^=0x36;sha_context s;init(&s);update(&s,pad,64);update(&s,data,bytes);finish(&s,digest);
 for(unsigned i=0;i<64;i++)pad[i]^=0x36^0x5c;init(&s);update(&s,pad,64);update(&s,digest,32);finish(&s,out);wipe(pad,sizeof(pad));wipe(digest,sizeof(digest));wipe(&s,sizeof(s));
}
int m10v_constant_equal(const uint8_t*a,const uint8_t*b,uint32_t bytes){uint32_t diff=0;for(uint32_t i=0;i<bytes;i++)diff|=a[i]^b[i];return diff==0;}

_Static_assert(sizeof(m10v_auth_state)<=5000,"bounded authentication state");
static unsigned bounded(const char*s,unsigned capacity){unsigned n=0;while(n<capacity&&s[n])n++;return n;}
static int same(const char*a,const char*b){unsigned i=0;while(a[i]&&b[i]&&a[i]==b[i])i++;return a[i]==b[i];}
void m10v_hex(const uint8_t*bytes,uint32_t length,char*out){static const char digits[]="0123456789abcdef";for(uint32_t i=0;i<length;i++){out[2*i]=digits[bytes[i]>>4];out[2*i+1]=digits[bytes[i]&15];}out[2*length]=0;}
int m10v_unhex(const char*text,uint32_t length,uint8_t*out){for(uint32_t i=0;i<length;i++){unsigned value=0;for(unsigned j=0;j<2;j++){char c=text[2*i+j];unsigned digit;if(c>='0'&&c<='9')digit=(unsigned)(c-'0');else if(c>='a'&&c<='f')digit=(unsigned)(c-'a'+10);else return 0;value=value*16+digit;}out[i]=(uint8_t)value;}return 1;}
int m10v_auth_init(m10v_auth_state*s,const uint8_t key[32],const char*id,const uint8_t boot[16],m10v_random_bytes random,void*ctx){
 if(!s||!key||!id||!boot||!random)return 1;unsigned bytes=bounded(id,33);if(!bytes||bytes>32)return 1;
 for(unsigned i=0;i<bytes;i++)if(!((id[i]>='a'&&id[i]<='z')||(id[i]>='A'&&id[i]<='Z')||(id[i]>='0'&&id[i]<='9')||id[i]=='-'||id[i]=='_'))return 1;
 for(unsigned i=0;i<sizeof(*s);i++)((uint8_t*)s)[i]=0;
 for(unsigned i=0;i<32;i++)s->key[i]=key[i];for(unsigned i=0;i<16;i++)s->boot[i]=boot[i];for(unsigned i=0;i<bytes;i++)s->key_id[i]=id[i];s->random=random;s->random_context=ctx;return 0;
}
static int append(char*out,unsigned*used,const char*text,unsigned capacity){unsigned i=0;while(text[i]){if(*used+1>=capacity)return 0;out[(*used)++]=text[i++];}out[*used]=0;return 1;}
static int sequence(const char*text,uint64_t*out){unsigned count=bounded(text,21);if(!count||count>20||(count>1&&text[0]=='0'))return 0;uint64_t value=0;for(unsigned i=0;i<count;i++){if(text[i]<'0'||text[i]>'9')return 0;unsigned digit=(unsigned)(text[i]-'0');if(value>UINT64_C(1844674407370955161)||(value==UINT64_C(1844674407370955161)&&digit>5))return 0;value=value*10+digit;}*out=value;return 1;}
int m10v_auth_accept(m10v_auth_state*s,const m10v_http_request*r,const uint8_t*body,uint32_t bytes,char*out_session){
 if(!s||!r||!out_session||bytes>M10V_HTTP_MAX_BODY||(bytes&&!body)||r->fields!=63||r->content_length!=bytes)return 1;
 const char *fields[8]={r->method,r->path,r->key_id,r->nonce,r->boot,r->session,r->sequence,r->signature};const unsigned sizes[8]={8,sizeof(r->path),33,33,33,33,21,65};
 for(unsigned i=0;i<8;i++)if(bounded(fields[i],sizes[i])==sizes[i])return 1;
 if(!same(s->key_id,r->key_id)||bounded(r->nonce,33)!=32||bounded(r->signature,65)!=64)return 1;
 uint8_t nonce[16],signature[32];if(!m10v_unhex(r->nonce,16,nonce)||!m10v_unhex(r->signature,32,signature))return 1;
 uint64_t seq;if(!sequence(r->sequence,&seq))return 1;
 int bootstrap=!seq&&!r->boot[0]&&!r->session[0]&&same(r->method,"GET")&&same(r->path,"/m10v/v1/capabilities")&&!bytes;
 char boot_hex[33];m10v_hex(s->boot,16,boot_hex);m10v_auth_session *session=0;
 if(!bootstrap){
  if(!seq||!same(boot_hex,r->boot)||bounded(r->session,33)!=32)return 1;uint8_t id[16];if(!m10v_unhex(r->session,16,id))return 1;
  for(unsigned i=0;i<8;i++)if(s->sessions[i].valid&&m10v_constant_equal(s->sessions[i].id,id,16)){session=&s->sessions[i];break;}if(!session)return 1;
 }
 char canonical[512]={0},hash_hex[65];uint8_t hash[32];m10v_sha256(body,bytes,hash);m10v_hex(hash,32,hash_hex);unsigned used=0;
 const char *lines[7]={r->method,r->path,r->boot,r->session,r->sequence,r->nonce,hash_hex};
 for(unsigned i=0;i<7;i++){if(!append(canonical,&used,lines[i],sizeof(canonical)))return 1;if(i<6&&!append(canonical,&used,"\n",sizeof(canonical)))return 1;}
 m10v_hmac256(s->key,32,canonical,used,hash);if(!m10v_constant_equal(signature,hash,32))return 1;
 if(bootstrap){
  unsigned count=s->bootstrap_count<128?s->bootstrap_count:128;for(unsigned i=0;i<count;i++)if(m10v_constant_equal(s->bootstrap_nonces[i],nonce,16))return 1;
  uint8_t id[16];unsigned attempt;for(attempt=0;attempt<8;attempt++){
   if(!s->random(s->random_context,id,16))return 1;unsigned collision=0;for(unsigned i=0;i<8;i++)if(s->sessions[i].valid&&m10v_constant_equal(s->sessions[i].id,id,16))collision=1;if(!collision)break;
  }if(attempt==8||s->bootstrap_count==UINT32_MAX)return 1;
  unsigned index=s->bootstrap_count%128;for(unsigned i=0;i<16;i++)s->bootstrap_nonces[index][i]=nonce[i];
  session=&s->sessions[s->bootstrap_count%8];s->bootstrap_count++;
  for(unsigned i=0;i<sizeof(*session);i++)((uint8_t*)session)[i]=0;for(unsigned i=0;i<16;i++)session->id[i]=id[i];session->valid=1;
 }else{
  m10v_sha256(nonce,16,hash);uint32_t fingerprint=(uint32_t)hash[0]|((uint32_t)hash[1]<<8)|((uint32_t)hash[2]<<16)|((uint32_t)hash[3]<<24);
  /* Fingerprint collisions only reject a request; they can never authorize one. */
  for(unsigned i=0;i<session->nonce_count;i++)if(session->nonce_hashes[i]==fingerprint)return 1;
  if(seq>session->highwater){uint64_t delta=seq-session->highwater;session->window=delta>=64?1:(session->window<<delta)|1;session->highwater=seq;}
  else {uint64_t delta=session->highwater-seq;if(delta>=64||(session->window&(UINT64_C(1)<<delta)))return 1;session->window|=UINT64_C(1)<<delta;}
  session->nonce_hashes[session->nonce_cursor]=fingerprint;session->nonce_cursor=(session->nonce_cursor+1)%64;if(session->nonce_count<64)session->nonce_count++;
 }
 m10v_hex(session->id,16,out_session);return 0;
}

int m10v_auth_sign_response(const m10v_auth_state*s,const m10v_http_request*r,const char*session,unsigned status,const uint8_t*body,uint32_t bytes,char signature[65]){
 if(!s||!r||!session||!signature||status<100||status>599||bytes>M10V_HTTP_MAX_BODY||(bytes&&!body)||bounded(session,33)!=32||bounded(r->method,8)==8||bounded(r->path,sizeof(r->path))==sizeof(r->path)||bounded(r->sequence,21)==21||bounded(r->nonce,33)==33)return 1;
 char canonical[512]={0},boot[33],hash_hex[65],code[4];uint8_t hash[32];m10v_hex(s->boot,16,boot);m10v_sha256(body,bytes,hash);m10v_hex(hash,32,hash_hex);
 code[0]=(char)('0'+status/100);code[1]=(char)('0'+(status/10)%10);code[2]=(char)('0'+status%10);code[3]=0;
 const char *lines[9]={"RESPONSE",r->method,r->path,boot,session,r->sequence,r->nonce,code,hash_hex};unsigned used=0;
 for(unsigned i=0;i<9;i++){if(!append(canonical,&used,lines[i],sizeof(canonical)))return 1;if(i<8&&!append(canonical,&used,"\n",sizeof(canonical)))return 1;}
 m10v_hmac256(s->key,32,canonical,used,hash);m10v_hex(hash,32,signature);return 0;
}

void m10v_sha256_init(m10v_sha256_context*s){init(s);}
void m10v_sha256_update(m10v_sha256_context*s,const uint8_t*p,uint32_t n){update(s,p,n);}
void m10v_sha256_finish(m10v_sha256_context*s,uint8_t out[32]){finish(s,out);wipe(s,sizeof(*s));}
