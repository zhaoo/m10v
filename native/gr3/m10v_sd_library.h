#ifndef M10V_SD_LIBRARY_H
#define M10V_SD_LIBRARY_H
#include <stdint.h>
#include "m10v_library.h"
#include "m10v_film_directory.h"
/* Curated builtins followed by the compact list of custom records on SD. */
#define M10V_SD_DIRECTORY_LIMIT (M10V_DIRECTORY_COUNT+M10V_CUSTOM_MAX_ID-M10V_FILM_COUNT)
#define M10V_SD_HEADER_BYTES 4096u
#define M10V_SD_RECORD_BYTES 12288u
#define M10V_SD_MAX_FILMS 256u
#define M10V_SD_PAGE_ROWS 8u
/* Header caller must provide 4096 readable bytes; total is actual file size. */
uint32_t m10v_sd_header(const uint8_t *header,uint32_t total);
uint32_t m10v_sd_record(const uint8_t *record,uint32_t bytes,uint32_t expected_id);
uint32_t m10v_sd_u32(const uint8_t *p);
uint32_t m10v_sd_crc(const uint8_t *p,uint32_t bytes);
/* Camera operations return a stable film ID or zero; no SD calls from capture. */
uint32_t m10v_sd_camera_directory_extent(void);
uint32_t m10v_sd_camera_directory_item(uint32_t index);
int m10v_sd_camera_directory_install(uint32_t index,uint32_t expected_id,uint32_t slot);
uint32_t m10v_sd_camera_item(uint32_t page,uint32_t row);
int m10v_sd_camera_install(uint32_t page,uint32_t row,uint32_t expected_id,uint32_t slot);
int m10v_sd_camera_custom_record(const m10v_library_state *state,uint32_t slot,uint8_t *out,uint32_t bytes);
int m10v_sd_camera_custom_name(const m10v_library_state *state,uint32_t slot,char *out,uint32_t capacity);
int m10v_sd_camera_catalog_name(uint32_t index,uint32_t expected_id,char *out,uint32_t capacity);
#endif
