#include "extensions.h"
#include "auth.h"
static int name(const uint8_t*b,const m10v_json_token*t,const char*s){if(t->type!=M10V_JSON_STRING)return 0;unsigned n=(unsigned)(t->end-t->start),i=0;for(;i<n;i++)if(!s[i]||b[t->start+i]!=(uint8_t)s[i])return 0;return !s[i];}
static int hex(const uint8_t*b,const m10v_json_token*t,unsigned n,uint8_t*out){return t->type==M10V_JSON_STRING&&(unsigned)(t->end-t->start)==n*2&&m10v_unhex((const char*)b+t->start,n,out);}
int m10v_extensions_parse(const uint8_t*b,uint32_t n,m10v_json_token*t,m10v_extension_patch*out){
 if(!out||!t)return M10V_ERROR_INVALID_RECIPE;uint16_t count;if(m10v_json_parse(b,n,t,&count)||t[0].type!=M10V_JSON_OBJECT||t[0].count!=6)return M10V_ERROR_INVALID_RECIPE;
 static const char*keys[]={"requestId","bootId","contractHash","baseRevision","field","value"};uint16_t indices[6];unsigned seen=0,at=1;
 for(unsigned i=0;i<6;i++){unsigned k=0;for(;k<6;k++)if(name(b,&t[at],keys[k]))break;if(k==6)return M10V_ERROR_INVALID_RECIPE;seen|=1u<<k;indices[k]=(uint16_t)(at+1);at=t[at+1].next;}
 if(seen!=63)return M10V_ERROR_INVALID_RECIPE;for(unsigned i=0;i<sizeof(*out);i++)((uint8_t*)out)[i]=0;
 if(!hex(b,&t[indices[0]],16,out->request_id)||!hex(b,&t[indices[1]],16,out->boot_id)||!hex(b,&t[indices[2]],32,out->contract_hash)||!hex(b,&t[indices[3]],32,out->base_revision))return M10V_ERROR_INVALID_RECIPE;
 for(out->field=0;out->field<M10V_EXTENSION_FIELDS;out->field++)if(name(b,&t[indices[4]],m10v_extension_names[out->field]))break;
 if(out->field==M10V_EXTENSION_FIELDS||!m10v_json_uint(b,&t[indices[5]],&out->value)||!m10v_extensions_writable(out->field,out->value))return M10V_ERROR_INVALID_RECIPE;return 0;
}
