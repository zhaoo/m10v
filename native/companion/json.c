#include "json.h"
typedef struct {const uint8_t *text;uint32_t bytes,pos;uint16_t count;m10v_json_token *tokens;} parser;
static void space(parser*p){while(p->pos<p->bytes&&(p->text[p->pos]==' '||p->text[p->pos]=='\t'||p->text[p->pos]=='\r'||p->text[p->pos]=='\n'))p->pos++;}
static int same_token(parser*p,unsigned a,unsigned b){const m10v_json_token*x=&p->tokens[a],*y=&p->tokens[b];if(x->end-x->start!=y->end-y->start)return 0;for(unsigned i=0;i<(unsigned)(x->end-x->start);i++)if(p->text[x->start+i]!=p->text[y->start+i])return 0;return 1;}
static int value(parser*p,unsigned depth){
 space(p);if(p->pos>=p->bytes||p->count>=M10V_JSON_TOKENS||depth>10)return -1;unsigned index=p->count++;m10v_json_token*t=&p->tokens[index];t->start=(uint16_t)p->pos;t->count=0;uint8_t c=p->text[p->pos++];
 if(c=='{'||c=='['){t->type=c=='{'?M10V_JSON_OBJECT:M10V_JSON_ARRAY;space(p);uint8_t close=c=='{'?'}':']';
  if(p->pos<p->bytes&&p->text[p->pos]==close)p->pos++;
  else while(1){
   if(c=='{'){space(p);if(p->pos>=p->bytes||p->text[p->pos]!='"')return -1;int key=value(p,depth+1);if(key<0)return -1;unsigned old=index+1;for(unsigned i=0;i<t->count;i++){if(same_token(p,old,(unsigned)key))return -1;old=p->tokens[old+1].next;}space(p);if(p->pos>=p->bytes||p->text[p->pos++]!=':')return -1;}
   if(value(p,depth+1)<0||t->count==255)return -1;t->count++;space(p);if(p->pos>=p->bytes)return -1;uint8_t separator=p->text[p->pos++];if(separator==close)break;if(separator!=',')return -1;
  }
 }else if(c=='"'){
  t->type=M10V_JSON_STRING;t->start=(uint16_t)p->pos;while(p->pos<p->bytes&&p->text[p->pos]!='"'){uint8_t ch=p->text[p->pos++];if(ch<32||ch>126||ch=='\\')return -1;}if(p->pos>=p->bytes)return -1;t->end=(uint16_t)p->pos;p->pos++;t->next=p->count;return (int)index;
 }else if(c=='-'||(c>='0'&&c<='9')){
  t->type=M10V_JSON_NUMBER;if(c=='-'){if(p->pos>=p->bytes)return -1;c=p->text[p->pos++];if(c<'0'||c>'9')return -1;}
  if(c=='0'){if(p->pos<p->bytes&&p->text[p->pos]>='0'&&p->text[p->pos]<='9')return -1;}
  else while(p->pos<p->bytes&&p->text[p->pos]>='0'&&p->text[p->pos]<='9')p->pos++;
 }else{
  const char*literal=c=='t'?"true":c=='f'?"false":c=='n'?"null":0;if(!literal)return -1;t->type=c=='t'?M10V_JSON_TRUE:c=='f'?M10V_JSON_FALSE:M10V_JSON_NULL;unsigned i=1;while(literal[i]){if(p->pos>=p->bytes||p->text[p->pos++]!=(uint8_t)literal[i++])return -1;}
 }
 t->end=(uint16_t)p->pos;t->next=p->count;return (int)index;
}
int m10v_json_parse(const uint8_t*text,uint32_t bytes,m10v_json_token*tokens,uint16_t*count){if(!text||!tokens||!count||!bytes||bytes>16384)return 1;parser p={text,bytes,0,0,tokens};if(value(&p,0)<0)return 1;space(&p);if(p.pos!=bytes)return 1;*count=p.count;return 0;}
static int name(const uint8_t*text,const m10v_json_token*t,const char*key){if(t->type!=M10V_JSON_STRING)return 0;unsigned n=t->end-t->start;for(unsigned i=0;i<n;i++)if(!key[i]||text[t->start+i]!=(uint8_t)key[i])return 0;return !key[n];}
uint16_t m10v_json_get(const uint8_t*text,const m10v_json_token*tokens,uint16_t object,const char*key){if(tokens[object].type!=M10V_JSON_OBJECT)return M10V_JSON_MISSING;uint16_t at=object+1;for(unsigned i=0;i<tokens[object].count;i++){if(name(text,&tokens[at],key))return at+1;at=tokens[at+1].next;}return M10V_JSON_MISSING;}
int m10v_json_string(const uint8_t*text,const m10v_json_token*t,char*out,uint32_t capacity){if(t->type!=M10V_JSON_STRING||t->end-t->start>=capacity)return 0;unsigned n=t->end-t->start;for(unsigned i=0;i<n;i++)out[i]=(char)text[t->start+i];out[n]=0;return 1;}
int m10v_json_uint(const uint8_t*text,const m10v_json_token*t,uint32_t*out){if(t->type!=M10V_JSON_NUMBER)return 0;uint32_t value=0;for(unsigned i=t->start;i<t->end;i++){uint8_t c=text[i];if(c<'0'||c>'9'||value>(UINT32_MAX-(c-'0'))/10)return 0;value=value*10+(c-'0');}*out=value;return 1;}
