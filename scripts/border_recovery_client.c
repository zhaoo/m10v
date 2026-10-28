/* Offline-only ARM ownership probe. No installed hook, task enqueue, or DMA. */
#include <stdint.h>
#define TAG 0x42524331u
#define COMPLETE 0x03050006u
typedef struct {uint32_t native[8];uint32_t tag;volatile uint32_t pending,inflight,completed;uint32_t worker,job;} border_recovery_client;
static void barrier(void){__asm__ volatile("dmb ish" ::: "memory");}
uint32_t border_recovery_notify(border_recovery_client *c,uint32_t event,uint32_t payload){
 c->inflight++;barrier();
 uint32_t r=((uint32_t(*)(void*,uint32_t,uint32_t))0x534aab0c)(c,event,payload);
 barrier();
 if(c->tag==TAG && c->pending==1 && event==COMPLETE){c->completed++;c->pending=0;}
 barrier();c->inflight--;barrier();return r;
}
static const uint32_t vtable[]={0x534ac164u,0x534ac18cu,(uint32_t)(uintptr_t)border_recovery_notify,0};
void border_recovery_construct(border_recovery_client *c){
 for(uint32_t i=0;i<sizeof(*c)/4;i++)((uint32_t*)c)[i]=0;
 ((void(*)(void*))0x534aacc8)(c);c->native[0]=(uint32_t)(uintptr_t)vtable;c->tag=TAG;
}
int border_recovery_prepare(border_recovery_client *c,uint32_t worker,uint32_t job){
 if(c->tag!=TAG || c->pending || c->inflight || !worker || !job)return 0;
 c->worker=worker;c->job=job;c->completed=0;barrier();c->pending=1;barrier();return 1;
}
int border_recovery_match(border_recovery_client *c,uint32_t worker,const uint32_t *job){
 return c->tag==TAG && c->pending==1 && c->worker==worker && c->job==(uint32_t)(uintptr_t)job && job[1]==(uint32_t)(uintptr_t)c;
}
int border_recovery_can_release(border_recovery_client *c){
 barrier();return c->tag==TAG && !c->pending && !c->inflight;
}
int border_recovery_destroy_if_done(border_recovery_client *c){
 if(!border_recovery_can_release(c))return 0;
 ((void(*)(void*))0x534ac164)(c);c->tag=0;return 1;
}
