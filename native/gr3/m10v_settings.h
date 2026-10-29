#ifndef M10V_SETTINGS_H
#define M10V_SETTINGS_H
#include "m10v_library.h"
/* Owned page state: no dependency on ImageControl model, IDs or padding.
 * Backend load must provide a validated journal (including compiled defaults).
 * Backend install must recheck expected ID and commit before returning zero. */
enum { M10V_SETTINGS_CLOSED, M10V_SETTINGS_FILMS, M10V_SETTINGS_CATALOG,
       M10V_SETTINGS_STAMP, M10V_SETTINGS_VALUE, M10V_SETTINGS_NAME, M10V_SETTINGS_AB, M10V_SETTINGS_WATERMARK=9 };
enum { M10V_KEY_LEFT, M10V_KEY_RIGHT, M10V_KEY_UP, M10V_KEY_DOWN,
       M10V_KEY_OK, M10V_KEY_BACK, M10V_KEY_PREVIOUS, M10V_KEY_NEXT, M10V_KEY_DISP, M10V_KEY_CLEAN };
enum { M10V_SETTINGS_NO_ERROR, M10V_SETTINGS_EMPTY, M10V_SETTINGS_CHANGED,
       M10V_SETTINGS_SAVE_FAILED, M10V_SETTINGS_FULL };
typedef struct {
 void *context;
 int (*load)(void *, m10v_library_state *);
 uint32_t (*item)(void *, uint32_t index);
 int (*install)(void *, uint32_t index,uint32_t expected,uint32_t slot);
 int (*remove)(void *,uint32_t slot);
 int (*stamp)(void *,uint32_t mode,uint32_t format,uint32_t corner,uint32_t color);
 int (*film_name_stamp)(void *,uint32_t enabled);
 /* Validated directory extent; zero is a read failure. Optional for old adapters. */
 uint32_t (*extent)(void *);
} m10v_settings_ops;
typedef struct {
 m10v_library_state saved;
 uint32_t screen, focus, slot, index, expected, value, error, group;
} m10v_settings;
int m10v_settings_open(m10v_settings *,const m10v_settings_ops *,uint32_t screen);
void m10v_settings_key(m10v_settings *,const m10v_settings_ops *,uint32_t key);
#endif
