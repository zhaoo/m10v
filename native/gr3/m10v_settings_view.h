#ifndef M10V_SETTINGS_VIEW_H
#define M10V_SETTINGS_VIEW_H
#include "m10v_settings.h"
#include "m10v_zoom_menu.h"
#include "m10v_menu_detail_style.h"
/* GR III 2.10 only. Unintegrated view; caller owns route and root lifetime. */
enum { M10V_VIEW_CAPACITY=56, M10V_VIEW_COUNT=M10V_MENU_HUB?49:54, M10V_VIEW_HEAP=55 };
enum { M10V_FILM_GRID_X=24,M10V_FILM_GRID_Y=M10V_MENU_HUB?72:60,M10V_FILM_GRID_DX=136,M10V_FILM_GRID_DY=177 };
typedef struct { uint32_t widgets[M10V_VIEW_CAPACITY]; uint32_t count; } m10v_settings_view;
enum {
 M10V_VIEW_FILMS=937, M10V_VIEW_STAMP, M10V_VIEW_FILM_HELP,
 M10V_VIEW_CATALOG_HELP, M10V_VIEW_STAMP_HELP, M10V_VIEW_VALUE_HELP,
 M10V_VIEW_EMPTY, M10V_VIEW_CHANGED, M10V_VIEW_FAILED,
 M10V_VIEW_MODE, M10V_VIEW_FORMAT, M10V_VIEW_CORNER, M10V_VIEW_COLOR,
 M10V_VIEW_OFF, M10V_VIEW_DATE, M10V_VIEW_DATETIME,
 M10V_VIEW_YMD, M10V_VIEW_DMY, M10V_VIEW_YMD_DASH, M10V_VIEW_SHORT_YEAR,
 M10V_VIEW_TOP_LEFT, M10V_VIEW_TOP_RIGHT, M10V_VIEW_BOTTOM_LEFT, M10V_VIEW_BOTTOM_RIGHT,
 M10V_VIEW_WHITE, M10V_VIEW_ORANGE, M10V_VIEW_RED, M10V_VIEW_YELLOW,
 M10V_VIEW_EDIT_MODE, M10V_VIEW_EDIT_FORMAT, M10V_VIEW_EDIT_CORNER, M10V_VIEW_EDIT_COLOR,
 M10V_VIEW_CHOOSE_FILM, M10V_VIEW_NAME_OFF=988, M10V_VIEW_NAME_ON, M10V_VIEW_EDIT_NAME,
 M10V_VIEW_AB_TITLE, M10V_VIEW_AB_A, M10V_VIEW_AB_B, M10V_VIEW_AB_START, M10V_VIEW_AB_STOP, M10V_VIEW_AB_HELP
};
/* Initialize the entire struct to zero before first create. */
int m10v_settings_view_create(m10v_settings_view *);
#if M10V_MENU_HUB
enum { M10V_HUB_ROW_Y=86, M10V_HUB_ROW_HEIGHT=53, M10V_HUB_EFFECT_R6_HEIGHT=46,
 M10V_HUB_IMPRINT_HEIGHT=40, M10V_HUB_IMPRINT_THEME=4, M10V_HUB_LIVE_UNAVAILABLE=2 };
enum {
 M10V_HUB_DECK_EXTENDED=384,M10V_HUB_DECK_ROLL=385,M10V_HUB_ROLL_FRAME=386,
 M10V_HUB_ROLL_NEW=387,M10V_HUB_ROLL_PAUSED=388,M10V_HUB_ROLL_ACTIVE=389
};
#define M10V_HUB_BITMAP_ID 858u /* Retired icon slot, dedicated to this controller. */
#define M10V_THEME_BITMAP_ID 859u
uint32_t m10v_settings_view_theme(uint32_t, uint32_t, uint32_t, uint32_t);
uint32_t m10v_settings_view_theme_directory(uint32_t);
int m10v_settings_view_hub_create(m10v_settings_view *);
typedef struct {
 uint32_t frame,focus,patch[7],save_error;
 uint16_t marker_x,marker_y;
 uint32_t film,film_index;
} m10v_hub_paint;
uint32_t m10v_settings_view_hub(m10v_settings_view *,const m10v_hub_paint *);
uint32_t m10v_settings_view_hub_artwork(const m10v_settings_view *);
uint32_t m10v_settings_view_hub_directory(const m10v_settings_view *);
#endif
void m10v_settings_view_draw(m10v_settings_view *, const m10v_settings *, const m10v_settings_ops *);
void m10v_settings_view_zoom(m10v_settings_view *,const m10v_zoom_menu *);
#if M10V_SHUTDOWN_ALBUM
void m10v_settings_view_shutdown(m10v_settings_view *,const m10v_settings *,uint32_t);
#endif
#if M10V_ADJ_EXTRA_CAMERA
void m10v_settings_view_adj(m10v_settings_view *,const m10v_settings *);
#endif
/* Caller must unregister the shown root before destruction. */
void m10v_settings_view_destroy(m10v_settings_view *);
#endif
