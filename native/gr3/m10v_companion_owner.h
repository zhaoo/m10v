#ifndef M10V_COMPANION_UI_OWNER_H
#define M10V_COMPANION_UI_OWNER_H
#include <stdint.h>
#include "m10v_library.h"
int m10v_camera_library_read_current(m10v_library_state *);
int m10v_camera_library_commit_snapshot(const m10v_library_state *);
#define M10V_COMPANION_DESCRIPTOR_OFFSET 0x6400u
#define M10V_COMPANION_DESCRIPTOR_BYTES 64u
#define M10V_COMPANION_DESCRIPTOR_MAGIC 0x3244494du
typedef struct {uint32_t magic,version,bytes,context,wire,wire_bytes,epoch,reserved[9];} m10v_companion_ui_descriptor;
uint32_t m10v_companion_ui_storage_enter(uint32_t remote);
uint32_t m10v_companion_ui_storage_current(uint32_t token);
uint32_t m10v_companion_ui_storage_leave(uint32_t token);
void m10v_companion_ui_init(uint32_t owner);
void m10v_companion_ui_start(uint32_t owner);
void m10v_companion_ui_stop(uint32_t owner);
uint32_t m10v_companion_ui_timer(uint32_t context,uint32_t timer,uint32_t ignored);
#endif
