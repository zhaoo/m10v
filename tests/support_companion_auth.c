#include "auth.h"
#include "http_parser.h"
#include <stdio.h>
#include <string.h>
#define CHECK(condition) do {if(!(condition))return __LINE__;}while(0)
static int random_bytes(void*ctx,uint8_t*out,uint32_t bytes){unsigned *next=ctx;for(unsigned i=0;i<bytes;i++)out[i]=(uint8_t)((*next)++);return 1;}
static void sign(m10v_auth_state *state,m10v_http_request*r){
 uint8_t hash[32];char hex[65],canonical[512];m10v_sha256(0,0,hash);m10v_hex(hash,32,hex);
 int bytes=snprintf(canonical,sizeof(canonical),"%s\n%s\n%s\n%s\n%s\n%s\n%s",r->method,r->path,r->boot,r->session,r->sequence,r->nonce,hex);
 m10v_hmac256(state->key,32,canonical,(uint32_t)bytes,hash);m10v_hex(hash,32,r->signature);
}
static void request(m10v_auth_state*s,m10v_http_request*r,const char*session,unsigned seq,unsigned nonce){
 memset(r,0,sizeof(*r));strcpy(r->method,"GET");strcpy(r->path,seq?"/m10v/v1/state":"/m10v/v1/capabilities");strcpy(r->key_id,"fixture-key");
 if(seq){m10v_hex(s->boot,16,r->boot);strcpy(r->session,session);}snprintf(r->sequence,sizeof(r->sequence),"%u",seq);snprintf(r->nonce,sizeof(r->nonce),"%032x",nonce);r->fields=63;sign(s,r);
}
int m10v_test_auth_case(unsigned mode){
 m10v_auth_state state;uint8_t key[32]={0},boot[16]={1};unsigned rng=1;CHECK(m10v_auth_init(&state,key,"fixture-key",boot,random_bytes,&rng)==0);
 m10v_http_request r;char session[33],out[33];request(&state,&r,"",0,1);CHECK(m10v_auth_accept(&state,&r,0,0,session)==0);
 request(&state,&r,session,1,2);
 if(mode==1){r.signature[0]=r.signature[0]=='0'?'1':'0';CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);sign(&state,&r);}
 if(mode==2){r.boot[1]='0';CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);m10v_hex(state.boot,16,r.boot);sign(&state,&r);}
 if(mode==3){r.session[0]=r.session[0]=='0'?'1':'0';sign(&state,&r);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);strcpy(r.session,session);sign(&state,&r);}
 CHECK(m10v_auth_accept(&state,&r,0,0,out)==0);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);
 if(mode==4){request(&state,&r,session,2,2);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);request(&state,&r,session,2,3);CHECK(m10v_auth_accept(&state,&r,0,0,out)==0);}
 if(mode==5){for(unsigned seq=2;seq<=80;seq++){request(&state,&r,session,seq,seq+10);CHECK(m10v_auth_accept(&state,&r,0,0,out)==0);}request(&state,&r,session,1,999);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);request(&state,&r,session,1,999);strcpy(r.sequence,"0");sign(&state,&r);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);}
 if(mode==6){for(unsigned i=0;i<8;i++){request(&state,&r,"",0,100+i);CHECK(m10v_auth_accept(&state,&r,0,0,out)==0);}request(&state,&r,session,2,500);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);}
 if(mode==7){request(&state,&r,session,2,3);strcpy(r.sequence,"18446744073709551615");sign(&state,&r);CHECK(m10v_auth_accept(&state,&r,0,0,out)==0);strcpy(r.sequence,"18446744073709551616");sign(&state,&r);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);}
 if(mode==8){request(&state,&r,"",0,1);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);}
 if(mode==9){request(&state,&r,session,2,3);strcpy(r.sequence,"02");sign(&state,&r);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);request(&state,&r,session,2,3);r.nonce[0]='x';sign(&state,&r);CHECK(m10v_auth_accept(&state,&r,0,0,out)!=0);}
 char response_signature[65];CHECK(m10v_auth_sign_response(&state,&r,session,200,(const uint8_t*)"{}",2,response_signature)==0);CHECK(strlen(response_signature)==64);
 return 0;
}
int m10v_test_response_signature(char output[65]){
 m10v_auth_state state;uint8_t key[32],boot[16]={1};unsigned rng=1;for(unsigned i=0;i<32;i++)key[i]=(uint8_t)i;
 if(m10v_auth_init(&state,key,"fixture-key",boot,random_bytes,&rng))return 1;
 m10v_http_request r;request(&state,&r,"",0,1);
 return m10v_auth_sign_response(&state,&r,"000102030405060708090a0b0c0d0e0f",200,(const uint8_t*)"{}",2,output);
}
