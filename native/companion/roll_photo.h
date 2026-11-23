#ifndef M10V_ROLL_PHOTO_H
#define M10V_ROLL_PHOTO_H

#include "../gr3/m10v_roll.h"

typedef struct {
    void *context;
    uint32_t bytes;
    int (*read)(void *, uint32_t offset, uint8_t *, uint32_t count);
} m10v_roll_photo_reader;

/* >0 is a complete original's frame for this roll; 0 is a structurally
 * readable original with no relevant marker; -1 prevents proving absence. */
int m10v_roll_photo_frame(const m10v_roll_photo_reader *, int jpeg,
                           const m10v_roll_record *);

typedef struct {
    uint8_t id[16];
    uint32_t frame, target, film_code;
} m10v_roll_photo_metadata;
/* Reads a CRC-valid marker only from a JPEG with SOS and terminal EOI. */
int m10v_roll_photo_index(const m10v_roll_photo_reader *, m10v_roll_photo_metadata *);
/* jpeg=0 requires valid TIFF RAW image extents; never infers a sibling file. */
int m10v_roll_photo_index_format(const m10v_roll_photo_reader *, int jpeg,
                                m10v_roll_photo_metadata *);

int m10v_live_photo_token(const m10v_roll_photo_reader *, uint32_t token[4]);

#endif
