#include "linux_io.h"
#include "linux_wifi.h"
#if defined(M10V_COMPANION_HOST_TEST)
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
static long input(int fd,void*out,unsigned size){return read(fd,out,size);}
static long output(int fd,const void*in,unsigned size){
#ifdef MSG_NOSIGNAL
 return send(fd,in,size,MSG_NOSIGNAL);
#else
 return send(fd,in,size,0);
#endif
}
static void close_fd(int fd){close(fd);}
int m10v_linux_random(void*ctx,uint8_t*out,uint32_t bytes){(void)ctx;int fd=open("/dev/urandom",O_RDONLY);if(fd<0)return 0;unsigned have=0;while(have<bytes){long n=read(fd,out+have,bytes-have);if(n<=0){close(fd);return 0;}have+=(unsigned)n;}close(fd);return 1;}
uint64_t m10v_linux_now_ms(void*ctx){(void)ctx;struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;}
int m10v_linux_prepare_wifi(m10v_companion_server_config*cfg){(void)cfg;return 0;}
int m10v_linux_pause_ms(unsigned ms){struct timespec t={(time_t)(ms/1000),(long)(ms%1000)*1000000};return !nanosleep(&t,0);}
static int listener(const m10v_companion_server_config*cfg){(void)cfg;int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0){perror("host fixture socket");return -1;}int one=1;setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one));struct sockaddr_in address={0};address.sin_family=AF_INET;address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);address.sin_port=0;if(bind(fd,(struct sockaddr*)&address,sizeof(address))||listen(fd,1)){perror("host fixture bind/listen");close(fd);return -1;}socklen_t n=sizeof(address);if(getsockname(fd,(struct sockaddr*)&address,&n)){perror("host fixture getsockname");close(fd);return -1;}printf("%u\n",ntohs(address.sin_port));fflush(stdout);return fd;}
static int accept_one(int fd){int peer=accept(fd,0,0);return peer<0&&errno==EINTR?-4:peer;}
static int timeout_socket(int fd){struct timeval timeout={0,500000};
#ifdef SO_NOSIGPIPE
 int one=1;if(setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one)))return 0;
#endif
 return !setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout))&&!setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));}
#else
#if !defined(__arm__)
#error Production companion I/O requires Linux ARM EABI
#endif
/* Linux ARM EABI syscall numbers checked against arch/arm/tools/syscall.tbl:
 * https://github.com/torvalds/linux/blob/master/arch/arm/tools/syscall.tbl
 * Actual camera kernel/interface support remains an explicit device gate. */
static long syscall6(unsigned number,unsigned a,unsigned b,unsigned c,unsigned d,unsigned e,unsigned f){register unsigned r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d,r4 __asm__("r4")=e,r5 __asm__("r5")=f,r7 __asm__("r7")=number;__asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7):"memory","cc");return (long)r0;}
static long input(int fd,void*out,unsigned size){return syscall6(3,(unsigned)fd,(unsigned)(uintptr_t)out,size,0,0,0);}
static long output(int fd,const void*in,unsigned size){return syscall6(289,(unsigned)fd,(unsigned)(uintptr_t)in,size,0x4000,0,0);}
static void close_fd(int fd){syscall6(6,(unsigned)fd,0,0,0,0,0);}
#if M10V_COMPANION_DIAGNOSTICS
/* Ordinary traces publish metadata by closing each append. The separate
 * preopened fault descriptor is used only by a fatal handler, then closed. */
static int diagnostic_fd = -1;
static unsigned diagnostic_lines;
static int diagnostic_stdout = 1;
static const char diagnostic_hex[] = "0123456789abcdef";

static void diagnostic_append(const char *path, const char *line, unsigned bytes,
 unsigned flags) {
 long fd = syscall6(5, (unsigned)(uintptr_t)path, flags, 0600, 0, 0, 0);
 if (fd < 0) return;
 syscall6(4, (unsigned)fd, (unsigned)(uintptr_t)line, bytes, 0, 0, 0);
 close_fd((int)fd);
}

void m10v_linux_trace(const char *event, const uint32_t *values, unsigned count) {
 char line[160];
 unsigned length = 0;
 if (diagnostic_lines >= 512u || count > 14u) return;
 while (*event && *event != '\n' && length < 32u) line[length++] = *event++;
 for (unsigned i = 0; i < count; i++) {
  line[length++] = ' ';
  for (unsigned shift = 32; shift; shift -= 4)
   line[length++] = diagnostic_hex[values[i] >> (shift - 4) & 15u];
 }
 line[length++] = '\n';
 diagnostic_lines++;
 /* A RAM copy distinguishes execution from SD publication or blocking.
  * Both sinks are bounded by diagnostic_lines; no request retries depend on IO. */
 diagnostic_append("/tmp/m10v-worker-1101.log", line, length, 0x441u);
 diagnostic_append("/media/storage1/M10V/R20WORK.TXT", line, length, 0x101441u);
 if (diagnostic_stdout) syscall6(4, 1, (unsigned)(uintptr_t)line, length, 0, 0, 0);
}

static void diagnostic_process(const char *event) {
 uint32_t values[] = {
  (uint32_t)syscall6(20, 0, 0, 0, 0, 0, 0),
  (uint32_t)syscall6(64, 0, 0, 0, 0, 0, 0),
  (uint32_t)syscall6(147, 0, 0, 0, 0, 0, 0)
 };
 m10v_linux_trace(event, values, 3);
}

/* ARM EABI siginfo fault address is word 3. The saved ARM PC is word 18
 * of sigcontext, after the five-word ucontext prefix. Never return through a
 * signal trampoline or depend on libc in the fault-reporting path. */
static __attribute__((noreturn)) void diagnostic_signal(unsigned signal,
 const uint32_t *info, const uint32_t *context) {
 char line[] = "WORKER_SIGNAL 00000000 00000000 00000000 00000000\n";
 uint32_t values[] = {signal, info ? info[2] : 0,
  info ? info[3] : 0, context ? context[23] : 0};
 for (unsigned i = 0; i < 4; i++)
  for (unsigned j = 0; j < 8; j++)
   line[14 + i * 9 + j] = diagnostic_hex[values[i] >> (28 - j * 4) & 15u];
 if (diagnostic_fd >= 0) {
  syscall6(4, (unsigned)diagnostic_fd, (unsigned)(uintptr_t)line, sizeof(line)-1, 0, 0, 0);
  close_fd(diagnostic_fd);
  diagnostic_fd = -1;
 }
 if (diagnostic_stdout) syscall6(4, 1, (unsigned)(uintptr_t)line, sizeof(line)-1, 0, 0, 0);
 syscall6(1, 128 + signal, 0, 0, 0, 0, 0);
 for (;;) {}
}

void m10v_linux_diagnostics_start(void) {
 static const char entry[] = "R20_ENTRY_BEFORE_SD\n";
 diagnostic_append("/tmp/m10v-worker-1101.log", entry, sizeof(entry)-1, 0x441u);
 diagnostic_fd = (int)syscall6(5,
  (unsigned)(uintptr_t)"/media/storage1/M10V/R20FAULT.TXT", 0x101441u, 0600, 0, 0, 0);
 /* Linux ARM kernel sigaction uses a 64-bit signal mask. SA_SIGINFO supplies
  * the fault information. Block other signals to bound handler nesting.
  * The handler exits, so no restorer is needed. */
 const unsigned signals[] = {1, 4, 6, 7, 11, 15};
 struct {unsigned handler, flags, restorer, mask[2];} action = {
  1, 0, 0, {~0u, ~0u}
 };
 /* A closed inherited lcmd pipe is a logging sink failure. Install SIG_IGN
  * before the first write, and skip stdout if the kernel rejects it. */
 diagnostic_stdout = syscall6(174, 13, (unsigned)(uintptr_t)&action, 0, 8, 0, 0) == 0;
 if (!diagnostic_stdout) m10v_linux_trace("SIGPIPE_IGNORE_FAILED", 0, 0);
 action.handler = (unsigned)(uintptr_t)diagnostic_signal;
 action.flags = 4;
 for (unsigned i = 0; i < sizeof(signals)/sizeof(signals[0]); i++) {
  long result = syscall6(174, signals[i], (unsigned)(uintptr_t)&action, 0, 8, 0, 0);
  if (result) {
   uint32_t failure[] = {signals[i], (uint32_t)result};
   m10v_linux_trace("SIGNAL_INSTALL_FAILED", failure, 2);
  }
 }
 diagnostic_process("PROCESS_START");
}

#endif

int m10v_linux_random(void*ctx,uint8_t*out,uint32_t bytes){(void)ctx;long fd=syscall6(5,(unsigned)(uintptr_t)"/dev/urandom",0,0,0,0,0);if(fd<0)return 0;unsigned have=0;while(have<bytes){long n=input((int)fd,out+have,bytes-have);if(n<=0){close_fd((int)fd);return 0;}have+=(unsigned)n;}close_fd((int)fd);return 1;}
uint64_t m10v_linux_now_ms(void*ctx){(void)ctx;int32_t t[2];if(syscall6(263,1,(unsigned)(uintptr_t)t,0,0,0,0)||t[0]<0||t[1]<0||t[1]>=1000000000)return 0;return (uint64_t)(uint32_t)t[0]*1000+(uint32_t)t[1]/1000000;}
#if M10V_COMPANION_DIAGNOSTICS
static unsigned wifi_attempts;
static int wifi_trace_enabled;
static void wifi_trace(const char *event, const uint32_t *values, unsigned count) {
 if (wifi_trace_enabled) m10v_linux_trace(event, values, count);
}
#else
#define wifi_trace(...) ((void)0)
#endif
static int wifi_query(void *ctx, unsigned command, void *out, unsigned bytes) {
 unsigned fd = *(unsigned *)ctx;
 wifi_trace("WIFI_IOCTL_BEGIN", (uint32_t[]){command, fd, bytes}, 3);
 long result;
 unsigned returned = bytes;
 if (command == 0x8912) {
  uint32_t conf[2] = {bytes, (unsigned)(uintptr_t)out};
  result = syscall6(54, fd, command, (unsigned)(uintptr_t)conf, 0, 0, 0);
  returned = conf[0];
 } else {
  if (bytes != 32) return -1;
  result = syscall6(54, fd, command, (unsigned)(uintptr_t)out, 0, 0, 0);
 }
 wifi_trace("WIFI_IOCTL_END", (uint32_t[]){command, (uint32_t)result, returned}, 3);
 if (result || returned > bytes) return -1;
 return command == 0x8912 ? (int)returned : 0;
}
int m10v_linux_prepare_wifi(m10v_companion_server_config *cfg) {
 if (!cfg) return 0;
 cfg->wifi_verified = 0;
#if M10V_COMPANION_DIAGNOSTICS
 wifi_trace_enabled = wifi_attempts < 4;
 if (wifi_trace_enabled) wifi_attempts++;
#endif
 wifi_trace("WIFI_SOCKET_BEGIN", 0, 0);
 long socket = syscall6(281, 2, 1, 0, 0, 0, 0);
 wifi_trace("WIFI_SOCKET_END", (uint32_t[]){(uint32_t)socket}, 1);
 if (socket < 0) return 0;
 unsigned fd = (unsigned)socket;
 int ok = m10v_linux_wifi_discover(&fd, wifi_query, cfg->wifi_interface, cfg->hotspot_pairing);
 wifi_trace("WIFI_CLOSE_BEGIN", (uint32_t[]){fd, (uint32_t)ok}, 2);
 close_fd((int)fd);
 wifi_trace("WIFI_CLOSE_END", 0, 0);
 if (ok) {
  cfg->wifi_address[0] = 192;
  cfg->wifi_address[1] = 168;
  cfg->wifi_address[2] = 0;
  cfg->wifi_address[3] = 1;
  cfg->wifi_verified = 1;
 }
 return ok;
}
int m10v_linux_pause_ms(unsigned ms){
 if(ms>1000)return 0;uint32_t t[2]={ms/1000,(ms%1000)*1000000};return !syscall6(162,(unsigned)(uintptr_t)t,0,0,0,0,0);
}
static int listener(const m10v_companion_server_config*cfg){
 if(!cfg->wifi_verified)return -1;unsigned length=0;while(length<16&&cfg->wifi_interface[length])length++;if(!length||length==16||!cfg->wifi_address[0]||cfg->wifi_address[0]>=224||cfg->wifi_address[0]==127)return -1;
 long fd=syscall6(281,2,1,0,0,0,0);if(fd<0)return -1;
 if(syscall6(294,(unsigned)fd,1,25,(unsigned)(uintptr_t)cfg->wifi_interface,length+1,0)){close_fd((int)fd);return -1;}
 struct {uint16_t family;uint8_t port[2],address[4],zero[8];} address={2,{(uint8_t)(18743>>8),(uint8_t)18743},{0},{0}};
 for(unsigned i=0;i<4;i++)address.address[i]=cfg->wifi_address[i];
 if(syscall6(282,(unsigned)fd,(unsigned)(uintptr_t)&address,sizeof(address),0,0,0)||syscall6(284,(unsigned)fd,1,0,0,0,0)){close_fd((int)fd);return -1;}return (int)fd;
}
static int accept_one(int fd){return (int)syscall6(285,(unsigned)fd,0,0,0,0,0);}
static int timeout_socket(int fd){int32_t timeout[2]={0,500000};return !syscall6(294,(unsigned)fd,1,20,(unsigned)(uintptr_t)timeout,sizeof(timeout),0)&&!syscall6(294,(unsigned)fd,1,21,(unsigned)(uintptr_t)timeout,sizeof(timeout),0);}
#if M10V_ROLL_LINUX_SERVICE
#include "linux_roll.h"
extern void m10v_linux_roll_tick_workspace(uint8_t *);
_Static_assert(M10V_ROLL_WORKSPACE_BYTES <= M10V_HTTP_MAX_BODY, "roll scratch fits idle HTTP input");
static int accept_ready(int fd) {
 struct {int32_t fd;int16_t events,revents;} entry={fd,1,0};
 #if M10V_COMPANION_LIVE_SOURCE
 const unsigned wait_ms=35;
#else
 const unsigned wait_ms=250;
#endif
 long n=syscall6(168,(unsigned)(uintptr_t)&entry,1,wait_ms,0,0,0);
 if(n<0&&n!=-4)return -1;
 return n>0&&!(entry.revents&1)?-1:(int)n;
}
#endif
#endif
static m10v_companion_server server;
#if M10V_ROLL_LINUX_SERVICE && !defined(M10V_COMPANION_HOST_TEST)
/* The synchronous server is between requests or has yet to open its socket. */
void m10v_linux_roll_idle(void){m10v_linux_roll_tick_workspace(server.input);}
#endif
static unsigned len(const char*p){unsigned n=0;while(p[n])n++;return n;}
static unsigned header_end(const uint8_t*p,unsigned bytes){for(unsigned i=3;i<bytes;i++)if(p[i-3]=='\r'&&p[i-2]=='\n'&&p[i-1]=='\r'&&p[i]=='\n')return i+1;return 0;}
static int within(m10v_companion_server*s,uint64_t start){uint64_t now=s->config->now_ms(s->config->clock_ctx);return now>=start&&now-start<1500;}
static int write_all(m10v_companion_server*s,int fd,const uint8_t*bytes,unsigned count){uint64_t start=s->config->now_ms(s->config->clock_ctx);unsigned done=0;while(done<count){if(!within(s,start))return 0;long n=output(fd,bytes+done,count-done);if(n<=0)return 0;done+=(unsigned)n;}return 1;}
static int append(uint8_t*out,unsigned*used,const char*text){unsigned n=len(text);if(*used+n>=M10V_HTTP_MAX_HEAD)return 0;for(unsigned i=0;i<n;i++)out[(*used)++]=(uint8_t)text[i];return 1;}
static void decimal(unsigned value,char*out){char reverse[11];unsigned n=0;do{reverse[n++]=(char)('0'+value%10);value/=10;}while(value);unsigned i=0;while(n)out[i++]=reverse[--n];out[i]=0;}
static void reply(m10v_companion_server*s,int fd){
 unsigned used=0;char value[12],boot[33];uint8_t*out=s->input;decimal(s->status,value);append(out,&used,"HTTP/1.1 ");append(out,&used,value);append(out,&used," Response\r\nConnection: close\r\nCache-Control: no-store\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ");decimal(s->output_bytes,value);append(out,&used,value);append(out,&used,"\r\n");
 if(s->authenticated){m10v_hex(s->auth.boot,16,boot);append(out,&used,"X-M10V-Boot: ");append(out,&used,boot);append(out,&used,"\r\nX-M10V-Session: ");append(out,&used,s->session);append(out,&used,"\r\nX-M10V-Response-Signature: ");append(out,&used,s->response_signature);append(out,&used,"\r\n");}
 append(out,&used,"\r\n");if(write_all(s,fd,out,used))write_all(s,fd,s->output.bytes,s->output_bytes);
}
static void connection(m10v_companion_server*s,int fd){
 if(!timeout_socket(fd))return;unsigned have=0,head=0;uint64_t start=s->config->now_ms(s->config->clock_ctx);
 while(!head){if(have>=M10V_HTTP_MAX_HEAD||!within(s,start))goto invalid;unsigned capacity=M10V_HTTP_MAX_HEAD-have;if(capacity>512)capacity=512;long n=input(fd,s->input+have,capacity);if(n<=0)goto invalid;have+=(unsigned)n;head=header_end(s->input,have);}
 if(m10v_http_parse_head((const char*)s->input,head,&s->request))goto invalid;
 unsigned body=have-head;if(body>s->request.content_length)goto invalid;for(unsigned i=0;i<body;i++)s->input[i]=s->input[head+i];
 while(body<s->request.content_length){if(!within(s,start))goto invalid;long n=input(fd,s->input+body,s->request.content_length-body);if(n<=0)goto invalid;body+=(unsigned)n;}
 if(m10v_companion_process_parsed(s,s->input,body)){m10v_companion_bad_request(s);}reply(s,fd);return;
 invalid:m10v_companion_bad_request(s);reply(s,fd);
}
int m10v_companion_serve(const m10v_companion_server_config*cfg,const m10v_companion_backend*backend){
#if !defined(M10V_COMPANION_HOST_TEST)
 if(!cfg||!cfg->wifi_verified)return M10V_ERROR_BRIDGE_UNAVAILABLE;
#endif
 if(m10v_companion_server_init(&server,cfg,backend))return M10V_ERROR_BRIDGE_UNAVAILABLE;int fd=listener(cfg);if(fd<0)return M10V_ERROR_BRIDGE_UNAVAILABLE;
 while(1){
#if M10V_ROLL_LINUX_SERVICE && !defined(M10V_COMPANION_HOST_TEST)
  m10v_linux_roll_idle();
  int ready=accept_ready(fd);if(ready==-4||!ready)continue;
  if(ready<0){close_fd(fd);return M10V_ERROR_BRIDGE_UNAVAILABLE;}
#endif
  int peer=accept_one(fd);if(peer==-4)continue;if(peer<0){close_fd(fd);return M10V_ERROR_BRIDGE_UNAVAILABLE;}
#if !defined(M10V_COMPANION_HOST_TEST)
 if(cfg->hotspot_pairing){
  m10v_companion_server_config current=*cfg;
  if(!m10v_linux_prepare_wifi(&current)||!m10v_constant_equal((const uint8_t*)current.wifi_interface,(const uint8_t*)cfg->wifi_interface,16)){close_fd(peer);continue;}
 }
#endif
 connection(&server,peer);close_fd(peer);}
}
