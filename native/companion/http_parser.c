#include "http_parser.h"
static unsigned length(const char*s){unsigned n=0;while(s[n])n++;return n;}
static int equal(const char*a,unsigned size,const char*b){if(length(b)!=size)return 0;for(unsigned i=0;i<size;i++)if(a[i]!=b[i])return 0;return 1;}
static int lower_equal(const char*a,unsigned size,const char*b){if(length(b)!=size)return 0;for(unsigned i=0;i<size;i++){char c=a[i];if(c>='A'&&c<='Z')c+='a'-'A';if(c!=b[i])return 0;}return 1;}
static int copy(char*out,unsigned capacity,const char*p,unsigned size){if(size>=capacity)return 0;for(unsigned i=0;i<size;i++)out[i]=p[i];out[size]=0;return 1;}
static int token(char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='-';}
int m10v_http_parse_head(const char*p,uint32_t bytes,m10v_http_request*out){
 if(!p||!out||bytes<4||bytes>M10V_HTTP_MAX_HEAD||p[bytes-4]!='\r'||p[bytes-3]!='\n'||p[bytes-2]!='\r'||p[bytes-1]!='\n')return 1;
 for(unsigned i=0;i<sizeof(*out);i++)((uint8_t*)out)[i]=0;
 for(unsigned i=0;i<bytes;i++){if(!p[i]||(p[i]=='\n'&&(i==0||p[i-1]!='\r'))||(p[i]=='\r'&&(i+1==bytes||p[i+1]!='\n')))return 1;}
 unsigned end=0;while(end+1<bytes&&p[end]!='\r')end++;unsigned first=0;while(first<end&&p[first]!=' ')first++;
 if(!first||!copy(out->method,sizeof(out->method),p,first)||!(equal(out->method,first,"GET")||equal(out->method,first,"POST")||equal(out->method,first,"PUT")))return 1;
 unsigned path=first+1,after=path;while(after<end&&p[after]!=' ')after++;
 if(after==path||!copy(out->path,sizeof(out->path),p+path,after-path)||!equal(p+after,end-after," HTTP/1.1"))return 1;
 if(after-path<9)return 1;const char *prefix="/m10v/v1/";for(unsigned i=0;i<9;i++)if(out->path[i]!=prefix[i])return 1;
 for(unsigned i=0;i<after-path;i++){char c=out->path[i];if((unsigned char)c<33||(unsigned char)c>126||c=='%'||c=='?'||c=='#'||c=='\\'||c=='.'||(c=='/'&&i&&out->path[i-1]=='/'))return 1;}
 unsigned seen_host=0,seen_length=0,at=end+2;
 while(at<bytes-2){end=at;while(end+1<bytes&&p[end]!='\r')end++;if(end==at||p[at]==' '||p[at]=='\t')return 1;unsigned colon=at;while(colon<end&&p[colon]!=':'){if(!token(p[colon]))return 1;colon++;}if(colon==at||colon==end)return 1;
  unsigned start=colon+1,stop=end;while(start<stop&&(p[start]==' '||p[start]=='\t'))start++;while(stop>start&&(p[stop-1]==' '||p[stop-1]=='\t'))stop--;
  for(unsigned i=start;i<stop;i++)if((unsigned char)p[i]<32||(unsigned char)p[i]>126)return 1;
  if(lower_equal(p+at,colon-at,"transfer-encoding")||lower_equal(p+at,colon-at,"expect"))return 1;
  if(lower_equal(p+at,colon-at,"host")){if(seen_host++||start==stop||stop-start>80)return 1;out->hotspot_host=equal(p+start,stop-start,"192.168.0.1:18743");}
  else if(lower_equal(p+at,colon-at,"origin"))out->browser_origin=1;
  else if(lower_equal(p+at,colon-at,"x-m10v-hotspot")){if(out->hotspot_client||!equal(p+start,stop-start,"1"))return 1;out->hotspot_client=1;}
  else if(lower_equal(p+at,colon-at,"content-length")){if(seen_length++||start==stop||(stop-start>1&&p[start]=='0'))return 1;uint32_t value=0;for(unsigned i=start;i<stop;i++){if(p[i]<'0'||p[i]>'9'||value>1638)return 1;value=value*10+(unsigned)(p[i]-'0');if(value>M10V_HTTP_MAX_BODY)return 1;}out->content_length=value;}
  else if(lower_equal(p+at,colon-at,"x-m10v-chunk-hash")){if(out->chunk_hash[0]||stop-start!=64||!copy(out->chunk_hash,sizeof(out->chunk_hash),p+start,stop-start))return 1;}
  else {
   static const char *names[6]={"x-m10v-keyid","x-m10v-nonce","x-m10v-boot","x-m10v-session","x-m10v-seq","x-m10v-signature"};
   char *dest[6]={out->key_id,out->nonce,out->boot,out->session,out->sequence,out->signature};unsigned capacities[6]={33,33,33,33,21,65};
   for(unsigned i=0;i<6;i++)if(lower_equal(p+at,colon-at,names[i])){if((out->fields&(1u<<i))||!copy(dest[i],capacities[i],p+start,stop-start))return 1;out->fields|=1u<<i;}
  }
  at=end+2;
 }
 if(!seen_host||at!=bytes-2||(!equal(out->method,length(out->method),"GET")&&!seen_length)||((out->method[0]=='G')&&out->content_length))return 1;
 return 0;
}
int m10v_http_validate_head(const char*p,uint32_t bytes){m10v_http_request request;return m10v_http_parse_head(p,bytes,&request);}
