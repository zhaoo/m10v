#include "operations.h"
#include "auth.h"
uint32_t m10v_patch_size(void){return sizeof(m10v_companion_patch);}
const char*m10v_error_name(unsigned code){static const char*names[]={"none","unauthorized","unsupportedProtocol","unsupportedModel","incompatibleRenderer","invalidRecipe","busy","revisionConflict","storeFailed","readbackMismatch","bridgeUnavailable","resultUnknown"};return code<=M10V_ERROR_RESULT_UNKNOWN?names[code]:"bridgeUnavailable";}
static int name(const uint8_t*text,const m10v_json_token*t,const char*key){if(t->type!=M10V_JSON_STRING)return 0;unsigned i=0;for(;i<(unsigned)(t->end-t->start);i++)if(!key[i]||(uint8_t)key[i]!=text[t->start+i])return 0;return !key[i];}
static int hex(const uint8_t*text,const m10v_json_token*t,unsigned bytes,uint8_t*out){if(t->type!=M10V_JSON_STRING||t->end-t->start!=bytes*2)return 0;return m10v_unhex((const char*)text+t->start,bytes,out);}
int m10v_operation_parse_tokens(const uint8_t*text,uint32_t bytes,m10v_json_token*t,m10v_companion_patch*out){
 if(!out||!t)return M10V_ERROR_INVALID_RECIPE;uint16_t count;if(m10v_json_parse(text,bytes,t,&count)||t[0].type!=M10V_JSON_OBJECT)return M10V_ERROR_INVALID_RECIPE;
 for(unsigned i=0;i<sizeof(*out);i++)((uint8_t*)out)[i]=0;out->activate_slot=-1;
 static const char*keys[]={"protocol","requestId","bootId","baseRevision","catalogHash","rendererHash","patch","activateSlot"};uint16_t index[8];for(unsigned i=0;i<8;i++)index[i]=M10V_JSON_MISSING;
 unsigned seen=0;uint16_t at=1;for(unsigned i=0;i<t[0].count;i++){unsigned k;for(k=0;k<8;k++)if(name(text,&t[at],keys[k]))break;if(k==8)return M10V_ERROR_INVALID_RECIPE;seen|=1u<<k;index[k]=at+1;at=t[at+1].next;}
 if((seen&127)!=127)return M10V_ERROR_INVALID_RECIPE;uint32_t protocol;if(!m10v_json_uint(text,&t[index[0]],&protocol)||protocol!=1)return M10V_ERROR_UNSUPPORTED_PROTOCOL;
 if(!hex(text,&t[index[1]],16,out->request_id)||!hex(text,&t[index[2]],16,out->boot_id)||!hex(text,&t[index[3]],32,out->base_revision)||!hex(text,&t[index[4]],32,out->catalog_hash)||!hex(text,&t[index[5]],32,out->renderer_hash))return M10V_ERROR_INVALID_RECIPE;
 if(index[7]!=M10V_JSON_MISSING&&t[index[7]].type!=M10V_JSON_NULL){uint32_t slot;if(!m10v_json_uint(text,&t[index[7]],&slot)||slot>=M10V_SLOT_COUNT)return M10V_ERROR_INVALID_RECIPE;out->activate_slot=(int8_t)slot;}
 uint16_t array=index[6];if(t[array].type!=M10V_JSON_ARRAY||t[array].count>M10V_SLOT_COUNT)return M10V_ERROR_INVALID_RECIPE;
 at=array+1;for(unsigned i=0;i<t[array].count;i++){
  if(t[at].type!=M10V_JSON_OBJECT)return M10V_ERROR_INVALID_RECIPE;uint16_t slot_token=m10v_json_get(text,t,at,"slot");uint32_t slot;
  if(slot_token==M10V_JSON_MISSING||!m10v_json_uint(text,&t[slot_token],&slot)||slot>=M10V_SLOT_COUNT||(out->slots_mask&(1u<<slot)))return M10V_ERROR_INVALID_RECIPE;out->slots_mask|=(uint16_t)(1u<<slot);
  uint16_t key=at+1;for(unsigned j=0;j<t[at].count;j++){
   if(name(text,&t[key],"slot")){key=t[key+1].next;continue;}
   if(name(text,&t[key],"customHash")){if(!hex(text,&t[key+1],32,out->custom_hashes[slot]))return M10V_ERROR_INVALID_RECIPE;out->fields[slot]|=M10V_CUSTOM_HASH_FIELD;key=t[key+1].next;continue;}
   unsigned field;for(field=0;field<M10V_FIELD_COUNT;field++)if(name(text,&t[key],m10v_field_names[field]))break;uint32_t value;
   if(field==M10V_FIELD_COUNT||!m10v_json_uint(text,&t[key+1],&value)||value>m10v_field_max(field,0)||(field==M10V_FIELD_FILMID&&!value))return M10V_ERROR_INVALID_RECIPE;
   out->fields[slot]|=(uint16_t)(1u<<field);out->values[slot][field]=(uint16_t)value;key=t[key+1].next;
  }
  if(!out->fields[slot])return M10V_ERROR_INVALID_RECIPE;at=t[at].next;
 }
 if((!out->slots_mask&&out->activate_slot<0)||(out->slots_mask&&out->activate_slot>=0))return M10V_ERROR_INVALID_RECIPE;
 return M10V_ERROR_NONE;
}
int m10v_operation_parse(const uint8_t*text,uint32_t bytes,m10v_companion_patch*out){m10v_json_token tokens[M10V_JSON_TOKENS];return m10v_operation_parse_tokens(text,bytes,tokens,out);}
void m10v_operation_digest(const m10v_companion_patch*p,uint8_t out[32]){
 uint8_t data[1024];unsigned n=0;const uint8_t*identity[]={p->request_id,p->boot_id,p->base_revision,p->catalog_hash,p->renderer_hash};const unsigned lengths[]={16,16,32,32,32};
 for(unsigned k=0;k<5;k++)for(unsigned i=0;i<lengths[k];i++)data[n++]=identity[k][i];
 for(unsigned slot=0;slot<M10V_SLOT_COUNT;slot++){data[n++]=(uint8_t)p->fields[slot];data[n++]=(uint8_t)(p->fields[slot]>>8);for(unsigned f=0;f<M10V_FIELD_COUNT;f++){data[n++]=(uint8_t)p->values[slot][f];data[n++]=(uint8_t)(p->values[slot][f]>>8);}for(unsigned i=0;i<32;i++)data[n++]=p->custom_hashes[slot][i];}
 data[n++]=(uint8_t)p->activate_slot;data[n++]=(uint8_t)p->slots_mask;data[n++]=(uint8_t)(p->slots_mask>>8);m10v_sha256(data,n,out);
}
