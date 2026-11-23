#include "roll_photo.h"
#include "../gr3/m10v_live_ingress.h"

#define PREFIX_LIMIT (256u * 1024u)

typedef struct {
    const m10v_roll_photo_reader *file;
    uint32_t base, bytes;
    int little;
} directory;

typedef struct { uint32_t at, count, type; } field;

static uint32_t word(const uint8_t *b, int little) {
    return little ? (uint32_t)b[0] | (uint32_t)b[1] << 8
                  : (uint32_t)b[0] << 8 | (uint32_t)b[1];
}

static uint32_t integer(const uint8_t *b, int little) {
    return little ? word(b, 1) | word(b + 2, 1) << 16
                  : word(b, 0) << 16 | word(b + 2, 0);
}

static __attribute__((noinline)) int photo_read_exact(const directory *d, uint32_t at, uint8_t *out, uint32_t n) {
    return at <= d->bytes && n <= d->bytes - at &&
        d->file->read(d->file->context, d->base + at, out, n);
}

static int field_of(const directory *d, uint32_t ifd, uint32_t tag, field *out) {
    uint8_t bytes[12];
    if (!photo_read_exact(d, ifd, bytes, 2)) return -1;
    uint32_t entries = word(bytes, d->little);
    if (entries > 512 || d->bytes - ifd < 2 + 12 * entries + 4) return -1;
    for (uint32_t i = 0; i < entries; ++i) {
        uint32_t at = ifd + 2 + 12 * i;
        if (!photo_read_exact(d, at, bytes, sizeof(bytes))) return -1;
        if (word(bytes, d->little) != tag) continue;
        uint32_t type = word(bytes + 2, d->little);
        uint32_t shift = type == 3 ? 1 : type == 4 || type == 13 ? 2 : 0;
        uint32_t count = integer(bytes + 4, d->little);
        if (!count || count > (UINT32_MAX >> shift)) return -1;
        uint32_t size = count << shift;
        uint32_t start = size <= 4 ? at + 8 : integer(bytes + 8, d->little);
        if (start > d->bytes || size > d->bytes - start) return -1;
        *out = (field){start, count, type};
        return 1;
    }
    return 0;
}

static int value(const directory *d, field f, uint32_t index, uint32_t *out) {
    uint8_t bytes[4];
    uint32_t width = f.type == 3 ? 2 : f.type == 4 || f.type == 13 ? 4 : 0;
    if (!width || index >= f.count || !photo_read_exact(d, f.at + index * width, bytes, width)) return 0;
    *out = width == 2 ? word(bytes, d->little) : integer(bytes, d->little);
    return 1;
}

static uint32_t marker_crc(const uint8_t marker[32]) {
    uint32_t crc = UINT32_MAX;
    for (uint32_t i = 0; i < 28; ++i) {
        crc ^= marker[i];
        for (uint32_t bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static int read_marker(directory note, const m10v_roll_record *roll, uint32_t *token, m10v_roll_photo_metadata *metadata) {
    uint8_t magic[8];
    if (!photo_read_exact(&note, 0, magic, sizeof(magic))) return -1;
    if (magic[0] != 'R' || magic[1] != 'I' || magic[2] != 'C' ||
        magic[3] != 'O' || magic[4] != 'H' || magic[5] != 0) return 0;
    if (magic[6] != magic[7] || (magic[6] != 'I' && magic[6] != 'M')) return -1;
    note.little = magic[6] == 'I';
    field entry;
    int found = field_of(&note, 8, (roll || metadata) ? M10V_ROLL_EXIF_TAG : M10V_LIVE_EXIF_TAG, &entry);
    if (found == 1 && !roll && !metadata) {
        uint8_t marker[M10V_LIVE_EXIF_WORDS * 4];
        if (entry.type != 7 || entry.count != sizeof(marker) ||
            !photo_read_exact(&note, entry.at, marker, sizeof(marker))) return -1;
        uint32_t filled = 0;
        for (unsigned i = 0; i < sizeof(marker); ++i) filled |= marker[i];
        if (!filled) return 0;
        if (integer(marker, 1) != M10V_LIVE_EXIF_MAGIC ||
            integer(marker + 4, 1) != M10V_LIVE_INGRESS_VERSION) return -1;
        uint32_t present = 0;
        for (unsigned i = 0; i < 4; ++i) {
            uint32_t value = integer(marker + 8 + i * 4, 1);
            if ((token[0] || token[1] || token[2] || token[3]) && value != token[i])
                return -1;
            present |= value;
        }
        if (!present) return -1;
        for (unsigned i = 0; i < 4; ++i) token[i] = integer(marker + 8 + i * 4, 1);
        return 1;
    }
    if (found <= 0) return found;
    uint8_t marker[M10V_ROLL_MARKER_BYTES];
    if (entry.type != 7 || entry.count != sizeof(marker) ||
        !photo_read_exact(&note, entry.at, marker, sizeof(marker))) return -1;
    /* Stock contexts retain this reserved slot for their lifetime. The writer
     * deliberately clears it for originals outside a matching roll lease. */
    uint32_t filled = 0;
    for (unsigned i = 0; i < sizeof(marker); ++i) filled |= marker[i];
    if (!filled) return 0;
    if (integer(marker, 1) != 0x5230314du ||
        integer(marker + 28, 1) != marker_crc(marker)) return -1;
    uint32_t present = 0;
    for (uint32_t i = 0; i < 16; ++i) present |= marker[4 + i];
    if (!present) return -1;
    if (roll) for (uint32_t i = 0; i < 16; ++i) if (marker[4 + i] != roll->id[i]) return 0;
    uint32_t frame = integer(marker + 20, 1);
    uint32_t target = integer(marker + 24, 1);
    if (!frame || !target || target > 64 || frame > target || (roll && target != roll->target)) return -1;
    if (metadata) {
        for (unsigned i = 0; i < 16; ++i) metadata->id[i] = marker[4 + i];
        metadata->frame = frame; metadata->target = target; metadata->film_code = 0;
        field tone; uint32_t code;
        if (field_of(&note, 8, 0x004f, &tone) == 1 && tone.type == 3 && tone.count == 1 &&
            value(&note, tone, 0, &code) &&
            ((code >= 0x1001 && code <= 0x104e) || (code >= 0x1121 && code <= 0x114e) ||
             (code >= 0x2000 && code < 0x2000 + 210 * 235))) metadata->film_code = code;
    }
    return (int)frame;
}

static int image_extents(const directory *tiff, uint32_t first) {
    field offsets, lengths;
    int found = field_of(tiff, first, 0x0111, &offsets);
    uint32_t length_tag = 0x0117;
    if (found == 0) {
        found = field_of(tiff, first, 0x0144, &offsets);
        length_tag = 0x0145;
    }
    if (found != 1 || field_of(tiff, first, length_tag, &lengths) != 1 ||
        offsets.count != lengths.count || offsets.count > 1024) return 0;
    for (uint32_t i = 0; i < offsets.count; ++i) {
        uint32_t offset, bytes;
        if (!value(tiff, offsets, i, &offset) || !value(tiff, lengths, i, &bytes) ||
            !offset || !bytes || offset > tiff->bytes || bytes > tiff->bytes - offset) return 0;
    }
    return 1;
}

static int raw_ifd(const directory *tiff, uint32_t at) {
    field photo;
    uint32_t interpretation;
    return field_of(tiff, at, 0x0106, &photo) == 1 &&
        value(tiff, photo, 0, &interpretation) &&
        (interpretation == 32803u || interpretation == 34892u) && image_extents(tiff, at);
}

static int complete_dng(const directory *tiff, uint32_t first) {
    if (raw_ifd(tiff, first)) return 1;
    field sub;
    if (field_of(tiff, first, 0x014a, &sub) != 1 || sub.count > 8) return 0;
    for (uint32_t i = 0; i < sub.count; ++i) {
        uint32_t at;
        if (!value(tiff, sub, i, &at)) return 0;
        if (raw_ifd(tiff, at)) return 1;
    }
    return 0;
}

static int read_tiff(directory tiff, int jpeg, const m10v_roll_record *roll, uint32_t *token, m10v_roll_photo_metadata *metadata) {
    uint8_t header[8];
    if (!photo_read_exact(&tiff, 0, header, sizeof(header)) || header[0] != header[1] ||
        (header[0] != 'I' && header[0] != 'M')) return -1;
    tiff.little = header[0] == 'I';
    if (word(header + 2, tiff.little) != 42) return -1;
    uint32_t first = integer(header + 4, tiff.little);
    uint32_t at = first;
    field entry;
    if (jpeg) {
        int found = field_of(&tiff, first, 0x8769, &entry);
        if (found <= 0) return found;
        if (entry.type != 4 || !value(&tiff, entry, 0, &at)) return -1;
    }
    int found = field_of(&tiff, at, jpeg ? 0x927c : 0xc634, &entry);
    if (found <= 0) return found;
    if (entry.type != (jpeg ? 7u : 1u)) return -1;
    directory note = {tiff.file, tiff.base + entry.at, entry.count, 0};
    int frame = read_marker(note, roll, token, metadata);
    return frame > 0 && !jpeg && !complete_dng(&tiff, first) ? -1 : frame;
}

static int read_jpeg(const directory *root, const m10v_roll_record *roll, uint32_t *token, m10v_roll_photo_metadata *metadata) {
    uint8_t bytes[6];
    if (root->bytes < 4 || !photo_read_exact(root, 0, bytes, 2) || word(bytes, 0) != 0xffd8) return -1;
    int frame = 0;
    uint32_t at = 2;
    while (at < PREFIX_LIMIT && photo_read_exact(root, at, bytes, 4)) {
        if (bytes[0] != 0xff) return -1;
        if (bytes[1] == 0xff) { ++at; continue; }
        if (bytes[1] == 0xda) {
            if (frame <= 0) return frame;
            return photo_read_exact(root, root->bytes - 2, bytes, 2) && word(bytes, 0) == 0xffd9 ? frame : -1;
        }
        uint32_t length = word(bytes + 2, 0);
        if (length < 2 || length > root->bytes - at - 2) return -1;
        if (bytes[1] == 0xe1 && length >= 8) {
            if (!photo_read_exact(root, at + 4, bytes, 6)) return -1;
            if (bytes[0] == 'E' && bytes[1] == 'x' && bytes[2] == 'i' && bytes[3] == 'f' &&
                bytes[4] == 0 && bytes[5] == 0) {
                m10v_roll_photo_metadata entry = {0};
                int candidate = read_tiff((directory){root->file, at + 10, length - 8, 0}, 1, roll, token, metadata ? &entry : 0);
                if (candidate < 0 || (candidate > 0 && frame && candidate != frame)) return -1;
                if (candidate > 0) {
                    if (metadata && frame) {
                        for (unsigned i = 0; i < 16; ++i) if (entry.id[i] != metadata->id[i]) return -1;
                        if (entry.target != metadata->target || entry.film_code != metadata->film_code) return -1;
                    }
                    if (metadata) *metadata = entry;
                    frame = candidate;
                }
            }
        }
        at += 2 + length;
    }
    return -1;
}

int m10v_roll_photo_frame(const m10v_roll_photo_reader *photo, int jpeg,
                           const m10v_roll_record *roll) {
    if (!photo || !photo->read || !roll || !photo->bytes) return -1;
    const directory root = {photo, 0, photo->bytes, 0};
    return jpeg ? read_jpeg(&root, roll, 0, 0) : read_tiff(root, 0, roll, 0, 0);
}


int m10v_live_photo_token(const m10v_roll_photo_reader *photo, uint32_t token[4]) {
    if (!photo || !photo->read || !photo->bytes || !token) return -1;
    for (unsigned i = 0; i < 4; ++i) token[i] = 0;
    const directory root = {photo, 0, photo->bytes, 0};
    return read_jpeg(&root, 0, token, 0);
}

int m10v_roll_photo_index_format(const m10v_roll_photo_reader *photo, int jpeg,
                                 m10v_roll_photo_metadata *out) {
    if (!photo || !photo->read || !photo->bytes || !out) return -1;
    *out = (m10v_roll_photo_metadata){0};
    const directory root = {photo, 0, photo->bytes, 0};
    return jpeg ? read_jpeg(&root, 0, 0, out) : read_tiff(root, 0, 0, 0, out);
}
int m10v_roll_photo_index(const m10v_roll_photo_reader *photo, m10v_roll_photo_metadata *out) {
    return m10v_roll_photo_index_format(photo, 1, out);
}
