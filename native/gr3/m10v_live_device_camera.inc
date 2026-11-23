/* Included by the permanent GR III AppMain owner; no capture-side allocation. */
static uint32_t live_tick_now(void) {
 uint32_t tick[2];
 return ((int(*)(uint32_t *))0x53050b7cu)(tick)?0:tick[1];
}

static int live_fresh(const m10v_live_camera *camera) {
 uint32_t lease=__atomic_load_n(&camera->consumer_tick,__ATOMIC_ACQUIRE),now=live_tick_now();
 return lease&&now&&now-lease<=M10V_LIVE_INGRESS_LEASE_MS;
}

m10v_live_camera *m10v_live_device_camera(void) {
 ui_context *c=roll_context();
 return c?&c->live:0;
}

int m10v_live_device_mode(void) {
 m10v_live_camera *camera=m10v_live_device_camera();
 if(!camera)return -1;
 if(!camera->arena)return -2;
 if(!live_fresh(camera))return -3;
 return (int)(camera->arena->control.request&3u);
}

int m10v_live_device_configured_mode(void) {
 m10v_live_camera *camera=m10v_live_device_camera();
 return camera&&camera->arena?(int)(camera->arena->control.request&3u):0;
}

int m10v_live_device_set_mode(uint32_t mode) {
 m10v_live_camera *camera=m10v_live_device_camera();
 if(mode>2)return 0;
 if(!camera||!camera->arena)return mode==0;
 if(mode&&!live_fresh(camera))return 0;
 m10v_live_ingress_control *control=&camera->arena->control;
 uint32_t request=control->request;
 if((request&3u)==mode)return 1;
 if(request>0xfffffffbu)return 0;
 __atomic_store_n(&control->request,((request&~3u)+4u)|mode,__ATOMIC_RELEASE);
 ((cache_fn)0x5383c870u)(control,sizeof(*control));
 return 1;
}

static int live_describe(ui_context *c,uint8_t *out,uint32_t *length) {
 m10v_live_ingress *arena=c->live.arena;
 if(!arena){
  if(c->live_alloc_tried)return M10V_ERROR_BRIDGE_UNAVAILABLE;
  c->live_alloc_tried=1;
  uint32_t a=((fn1)0x536af2a8u)(sizeof(*arena)+127u);
  if(!a||a>0xffffff80u||!ram((a+127u)&~127u,sizeof(*arena))){
   if(a)((void(*)(uint32_t))0x536af2e4u)(a);
   return M10V_ERROR_BRIDGE_UNAVAILABLE;
  }
  arena=(void *)(uintptr_t)((a+127u)&~127u);
  zero(arena,sizeof(*arena));
  for(uint32_t index=0;index<M10V_LIVE_INGRESS_SLOTS;index++)
   for(uint32_t p=M10V_LIVE_INGRESS_Y_BYTES;p<M10V_LIVE_INGRESS_FRAME_BYTES;p++)
    arena->frames[index].data[p]=128;
  arena->control.magic=M10V_LIVE_INGRESS_MAGIC;
  arena->control.version=M10V_LIVE_INGRESS_VERSION;
  arena->control.bytes=sizeof(*arena);
  arena->control.epoch=c->wire.epoch;
  arena->control.diagnostic.version=2;
  arena->control.diagnostic.seq=2;
  copy(c->live.nonce,c->services.metadata.boot_id,sizeof(c->live.nonce));
  ((cache_fn)0x5383c870u)(arena,sizeof(*arena));
  __atomic_store_n(&c->live.arena,arena,__ATOMIC_RELEASE);
 }
 const m10v_live_ingress_offer offer={
  M10V_LIVE_INGRESS_VERSION,(uint32_t)(uintptr_t)arena,sizeof(*arena),c->wire.epoch,
  M10V_LIVE_INGRESS_SLOTS,sizeof(m10v_live_ingress_frame),M10V_LIVE_INGRESS_FRAME_BYTES,
  M10V_LIVE_INGRESS_MONO_NV12
 };
 copy(out,&offer,sizeof(offer));*length=sizeof(offer);return 0;
}
