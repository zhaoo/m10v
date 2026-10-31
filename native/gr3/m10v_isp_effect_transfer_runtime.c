#include "m10v_isp_effect_transfer_runtime.h"
#include "m10v_border_wait_guard.h"
#include "m10v_isp_effect_memory.h"

#if defined(__arm__)
extern void border_recovery_transfer_body_hook(void),border_recovery_transfer_wait_hook(void);
extern void border_recovery_fill_body_hook(void),border_recovery_fill_wait_hook(void);
extern void border_recovery_resize_body_hook(void),border_recovery_resize_wait_hook(void);
extern void border_recovery_resize_dma_wait_hook(void),border_recovery_fill_release_hook(void);
extern void border_recovery_resize_release_hook(void),m10v_isp_effect_resize_status_hook(void);
#define U(p) ((uint32_t)(uintptr_t)(p))
#define EFFECT_MARKER 0x31584645u
static uint32_t word(uint32_t p){return *(const volatile uint32_t *)(uintptr_t)p;}
static int ram(uint32_t p,uint32_t bytes){return !(p&3u)&&p>=0x55000000u&&bytes<=0x80000000u&&p<=0x80000000u-bytes;}
static int overlap(uint32_t a,uint32_t an,uint32_t b,uint32_t bn){return a<b+bn&&b<a+an;}
static void hold(void){for(;;)((void(*)(uint32_t))0x536b0a74u)(1);}
static __attribute__((noinline)) int branch_opcode(uint32_t at,uint32_t target,uint32_t opcode){
 int32_t delta=(int32_t)(target-at-8u);
 return !(target&3u)&&delta>=-(1<<25)&&delta<(1<<25)&&
   word(at)==(opcode|(((uint32_t)delta>>2)&0xffffffu));
}
static int branch(uint32_t at,uint32_t target){return branch_opcode(at,target,0xeb000000u);}
static int ready(void){
 if(word(0x5369a010u)!=0xe3a00058u||word(0x536589fcu)!=0xe3a00068u||word(0x53672bacu)!=0xe3a00058u)return 0;
 /* Direct expressions preserve checked ARM MOVW/MOVT relocations. */
 if(!branch(0x5369a01cu,U(m10v_border_transfer_construct))||
    !branch(0x5369ac4cu,U(border_recovery_transfer_body_hook))||
    !branch(0x5369a478u,U(border_recovery_transfer_wait_hook))||
    !branch(0x534aae28u,U(m10v_border_client_wait))||
    !branch(0x53658a08u,U(m10v_border_fill_construct))||
    !branch(0x536594a0u,U(border_recovery_fill_body_hook))||
    !branch(0x5376a370u,U(border_recovery_fill_wait_hook))||
    !branch(0x53672bb8u,U(m10v_border_resize_construct))||
    !branch(0x53674014u,U(border_recovery_resize_body_hook))||
    !branch(0x5377160cu,U(border_recovery_resize_wait_hook))||
    !branch(0x53673244u,U(border_recovery_resize_dma_wait_hook))||
    !branch(0x5367331cu,U(border_recovery_resize_dma_wait_hook))||
    !branch(0x53673384u,U(border_recovery_resize_dma_wait_hook))||
    !branch(0x5376a38cu,U(border_recovery_fill_release_hook))||
    !branch(0x53771968u,U(border_recovery_resize_release_hook))||
    /* Inline displaced LDR trampoline must preserve the original LR. */
    !branch_opcode(0x53771620u,U(m10v_isp_effect_resize_status_hook),0xea000000u))return 0;
 static const uint32_t factories[3][5]={
   {0x5369a0e8u,4,0x44,0x42575431u,0x58},
   {0x53658a68u,4,0x58,0x42465731u,0x68},
   {0x53672c48u,12,0x48,0x42525731u,0x58}};
 for(uint32_t i=0;i<3u;++i){
  const uint32_t *f=factories[i];uint32_t factory=((uint32_t(*)(void))(uintptr_t)f[0])();
  if(!ram(factory,16u))return 0;
  uint32_t worker=word(factory+f[1]);
  if(!ram(worker,f[4])||word(worker+f[2])!=f[3])return 0;
 }
 return 1;
}
static int descriptors(const m10v_isp_effect_transfer *p){
 const uint32_t *s=p->source,*d=p->destination;
 uint32_t sw=s[4]&65535u,sh=s[4]>>16,ss=s[5]&65535u,sr=s[5]>>16;
 uint32_t sx=s[6]&65535u,sy=s[6]>>16;
 uint32_t dw=d[4]&65535u,dh=d[4]>>16,ds=d[5]&65535u,dr=d[5]>>16;
 if(s[0]!=2u||(d[0]!=1u&&d[0]!=2u)||s[3]||d[3]||s[7]!=2u||d[7]!=2u||d[6]||
    !sw||!sh||!dw||!dh||((sw|sh|sr|sx|sy|dw|dh)&1u)||
    ss>3072u||sr>2048u||!ss||!sr||(ss&63u)||sw>ss||sh>sr||sx>ss-sw||sy>sr-sh||
    dw>6144u||dh>6144u||ds!=((dw+15u)&~15u)||dr!=dh||(s[1]&63u)||(d[1]&15u))return 0;
 uint32_t source_y=ss*sr,source_bytes=source_y+source_y/2u;
 uint32_t dest_y=ds*dr,dest_bytes=dest_y+(d[0]==1u?dest_y:dest_y/2u);
 if(s[1]<0x540b6000u||s[1]>=0x55000000u||source_bytes>0x55000000u-s[1]||
    s[2]!=s[1]+source_y||!m10v_isp_effect_buffer_span(d[1],dest_bytes)||d[2]!=d[1]+dest_y||
    p->workspace_bytes!=dest_bytes||overlap(s[1],source_bytes,d[1],dest_bytes))return 0;
 return 1;
}
int m10v_isp_effect_transfer_execute(const m10v_isp_effect_transfer *plan,uint32_t frame_token){
 if(!frame_token||!ram(U(plan),sizeof(*plan)))return -1;
 /* Native callbacks may outlive an event wake, but never this retained stack.
  * Snapshot caller metadata before admission; never dereference pixel planes. */
 m10v_isp_effect_transfer frozen;
 const volatile uint32_t *in=(const volatile uint32_t *)plan;
 uint32_t *out=(uint32_t *)&frozen;
 for(uint32_t i=0;i<sizeof(frozen)/4u;++i)out[i]=in[i];
 if(!descriptors(&frozen)||overlap(U(plan),sizeof(*plan),frozen.destination[1],frozen.workspace_bytes))return -1;
 m10v_border_native_client client;
 if(overlap(U(&frozen),sizeof(frozen),frozen.destination[1],frozen.workspace_bytes)||
    overlap(U(&client),sizeof(client),frozen.destination[1],frozen.workspace_bytes)||!ready())return -1;
 uint32_t gate=m10v_border_stage_enter(frame_token);
 if(!gate)return -1;
 m10v_border_client_construct(&client);
 if(!m10v_border_client_prepare(&client,0x03020002u,0x40u)){
  if(!m10v_border_client_destroy_if_done(&client)||!m10v_border_stage_leave(gate,frame_token))hold();
  return -1;
 }
 /* prepare clears this marker; set only on the freshly prepared private job. */
 client.fill_bundle=EFFECT_MARKER;
 /* prepared=1 bypasses public pre/post ownership maintenance. Clarity can
  * leave CPU-dirty coefficient lines in this reused native workspace: retire
  * them BEFORE the ISP overwrites either real plane. Original 5383c8a8 is
  * mode2 clean+invalidate (large-span native DSB/remote-ACK path), whereas
  * Granulation's later 536bbcac is invalidate only. No CPU pixels are read. */
 ((void(*)(uint32_t,uint32_t))0x5383c8a8u)(frozen.destination[1],frozen.workspace_bytes);
 __asm__ volatile("dmb ish" ::: "memory");
 ((void(*)(void*,const void*,const void*,uint32_t))0x534ab6b8u)(&client,frozen.source,frozen.destination,1u);
 if(!m10v_border_client_done(&client)||client.tag!=M10V_BORDER_CLIENT_TAG||
    client.pending||client.inflight||client.completed!=1u||
    client.expected_event!=0x03020002u||client.expected_mask!=0x40u||client.fill_bundle!=EFFECT_MARKER)hold();
 uint32_t error=client.bundle_error;
 if(!m10v_border_client_destroy_if_done(&client)||!m10v_border_stage_leave(gate,frame_token))hold();
 return error?-4:1;
}
#else
int m10v_isp_effect_transfer_execute(const m10v_isp_effect_transfer *plan,uint32_t frame_token){
 (void)plan;(void)frame_token;return -3;
}
#endif
