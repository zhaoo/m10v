/* Included by the permanent AppMain owner. All calls execute on that owner;
 * Linux only exchanges bounded mailbox records. No capture path is changed. */
#include "m10v_zoom_camera.h"
#include "m10v_isp_effects_camera.h"
extern uint32_t m10v_settings_controller_remote_busy(void);
extern int m10v_settings_controller_remote_ab_read(uint32_t *,uint32_t *);
extern int m10v_settings_controller_remote_ab_write(uint32_t,uint32_t);
extern int m10v_settings_controller_remote_aspect_read(uint32_t *);
extern int m10v_settings_controller_remote_aspect_write(uint32_t);
#if M10V_COMPANION_EXT_HDF
extern int m10v_hdf_remote_snapshot(uint32_t *,uint32_t *);
extern int m10v_hdf_save(uint32_t);
#endif
#if M10V_COMPANION_EXT_BORDER
extern int m10v_border_camera_snapshot(uint32_t *);
extern int m10v_border_camera_sequence(uint32_t *);
extern int m10v_border_camera_save(uint32_t,uint32_t);
#endif
#if M10V_COMPANION_EXT_ZOOM
extern int m10v_zoom_camera_snapshot(m10v_zoom_state *);
extern uint32_t m10v_zoom_live_slot(void);
extern int m10v_zoom_live_apply(uint32_t);
#endif
static int extension_busy(void*v){return busy(v)||m10v_settings_controller_remote_busy();}
static int extension_blocked(void*v){return ((ui_context*)v)->transaction.pending.present!=0;}
static int extension_read(void*v,m10v_extension_snapshot*out){
 ui_context*c=v;if(!current(c)||c->store_depth)return M10V_ERROR_BRIDGE_UNAVAILABLE;
 m10v_companion_snapshot film;int code=snapshot(c,&film);if(code)return code;
 zero(out,sizeof(*out));uint32_t generations[5]={0};
 out->available=((1u<<17)-(1u<<12));
 out->values[12]=film.state.stamp;out->values[13]=film.state.format;
 out->values[14]=film.state.corner;out->values[15]=film.state.color;out->values[16]=film.state.reserved&1u;
#if M10V_COMPANION_EXT_AB
 if(m10v_settings_controller_remote_ab_read(out->values,&generations[0]))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 out->available|=7u;
#endif
#if M10V_COMPANION_EXT_HDF
 if(m10v_hdf_remote_snapshot(&out->values[3],&generations[1]))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 out->available|=1u<<3;
#endif
#if M10V_COMPANION_EXT_BORDER
 if(!m10v_border_camera_snapshot(&out->values[4])||m10v_border_camera_sequence(&generations[2]))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 out->available|=1u<<4;
#endif
#if M10V_COMPANION_EXT_ISP
 m10v_isp_effects_settings fx;
 if(!m10v_isp_effects_camera_snapshot(&fx,&generations[3]))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 out->values[5]=fx.grain_mode;out->values[6]=fx.grain_size;out->values[7]=fx.leak_gain;
 out->values[8]=fx.leak_position;out->values[9]=fx.leak_spread;out->values[10]=fx.blur_gain;out->values[11]=fx.blur_range;
 out->available|=((1u<<12)-(1u<<5));
#endif
#if M10V_COMPANION_EXT_ZOOM
 m10v_zoom_state zoom;if(m10v_zoom_camera_snapshot(&zoom))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 out->values[17]=zoom.mm[0];out->values[18]=zoom.mm[1];out->values[19]=m10v_zoom_live_slot();generations[4]=zoom.sequence;
 out->available|=7u<<17;
#endif
#if M10V_COMPANION_EXT_ASPECT
 if(m10v_settings_controller_remote_aspect_read(&out->values[20]))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 out->available|=1u<<20;
#endif
 out->busy=(uint32_t)extension_busy(c);
 /* Bind every film byte/hash/sequence and all known extension generations.
  * A local change followed by restoring the value still invalidates CAS. */
 m10v_sha256_context hash;m10v_sha256_init(&hash);
 const uint8_t prefix[]="m10v-native-extensions/v1";
 m10v_sha256_update(&hash,prefix,sizeof(prefix));m10v_sha256_update(&hash,film.revision,32);
 m10v_sha256_update(&hash,(const uint8_t*)&film.state,sizeof(film.state));
 m10v_sha256_update(&hash,(const uint8_t*)generations,sizeof(generations));
 m10v_sha256_update(&hash,(const uint8_t*)out,offsetof(m10v_extension_snapshot,revision));
 m10v_sha256_finish(&hash,out->revision);
 return current(c)?0:M10V_ERROR_BRIDGE_UNAVAILABLE;
}
static int extension_write(void*v,uint32_t field,uint32_t value){
 ui_context*c=v;if(!current(c)||!c->locked||extension_busy(c)||extension_blocked(c))return M10V_IO_NOT_WRITTEN;
#if M10V_COMPANION_EXT_AB
 if(field<3)return m10v_settings_controller_remote_ab_write(field,value);
#endif
#if M10V_COMPANION_EXT_HDF
 if(field==3)return m10v_hdf_save(value)?M10V_IO_UNCERTAIN:M10V_IO_OK;
#endif
#if M10V_COMPANION_EXT_BORDER
 if(field==4)return m10v_border_camera_save(c->ui_owner,value)?M10V_IO_UNCERTAIN:M10V_IO_OK;
#endif
#if M10V_COMPANION_EXT_ISP
 if(field>=5&&field<=11){
  m10v_isp_effects_settings fx;uint32_t sequence;
  if(!m10v_isp_effects_camera_snapshot(&fx,&sequence))return M10V_IO_NOT_WRITTEN;
  switch(field){case 5:if(value==1u){if(!m10v_isp_effects_set_enabled(&fx,1,0))return M10V_IO_NOT_WRITTEN;}else if(!m10v_isp_effects_set_strength(&fx,1,value)||!m10v_isp_effects_set_enabled(&fx,1,1))return M10V_IO_NOT_WRITTEN;break;case 6:fx.grain_size=value;break;case 7:if(value&&!m10v_isp_effects_set_strength(&fx,0,value))return M10V_IO_NOT_WRITTEN;if(!m10v_isp_effects_set_enabled(&fx,0,value!=0))return M10V_IO_NOT_WRITTEN;break;case 8:fx.leak_position=value;break;case 9:fx.leak_spread=value;break;case 10:if(value&&!m10v_isp_effects_set_strength(&fx,2,value))return M10V_IO_NOT_WRITTEN;if(!m10v_isp_effects_set_enabled(&fx,2,value!=0))return M10V_IO_NOT_WRITTEN;break;default:fx.blur_range=value;break;}
  return m10v_isp_effects_camera_save(c->ui_owner,&fx)?M10V_IO_UNCERTAIN:M10V_IO_OK;
 }
#endif
 if(field>=12&&field<=16){
  m10v_library_state next;if(m10v_camera_library_read_current(&next)||next.sequence==UINT32_MAX)return M10V_IO_NOT_WRITTEN;
  switch(field){case 12:next.stamp=(uint8_t)value;break;case 13:next.format=(uint8_t)value;break;case 14:next.corner=(uint8_t)value;break;case 15:next.color=(uint8_t)value;break;default:next.reserved=(next.reserved&~1u)|value;break;}
  m10v_companion_state_seal(&next,next.sequence+1);
  return m10v_camera_library_commit_snapshot(&next)?M10V_IO_UNCERTAIN:M10V_IO_OK;
 }
#if M10V_COMPANION_EXT_ZOOM
 if(field==17||field==18){
  m10v_zoom_state zoom;if(m10v_zoom_camera_snapshot(&zoom))return M10V_IO_NOT_WRITTEN;
  m10v_zoom_editor editor={zoom.sequence,field-17,value};
  int result=m10v_zoom_camera_save(&zoom,&editor);
  return result==M10V_ZOOM_STALE?M10V_IO_NOT_WRITTEN:result?M10V_IO_UNCERTAIN:M10V_IO_OK;
 }
 if(field==19)return m10v_zoom_live_apply(value)?M10V_IO_UNCERTAIN:M10V_IO_OK;
#endif
#if M10V_COMPANION_EXT_ASPECT
 if(field==20)return m10v_settings_controller_remote_aspect_write(value);
#endif
 return M10V_IO_NOT_WRITTEN;
}
static m10v_extension_services extension_services(ui_context*c){
 m10v_extension_services s={0};s.ctx=c;s.owner=&c->extensions;
 copy(s.boot_id,c->services.metadata.boot_id,16);s.is_current=current;s.enter=enter;s.leave=leave;
 s.is_busy=extension_busy;s.blocked=extension_blocked;s.read=extension_read;s.write=extension_write;return s;
}
