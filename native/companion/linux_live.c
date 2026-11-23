#include "linux_live.h"
#include "live_clip.h"
#include "roll_photo.h"
#include "linux_io.h"
#include <stddef.h>

enum {
    OPEN = 5, CLOSE = 6, WRITE = 4, SEEK = 19, PREAD = 180, FSYNC = 118,
    MMAP2 = 192, MUNMAP = 91, OPEN_AT = 322, MKDIR_AT = 323, UNLINK_AT = 328,
    RENAME_AT = 329, GETDENTS64 = 217,
    DIRECTORY = 1 << 14, NOFOLLOW = 1 << 15, NONBLOCK = 1 << 11,
    WRITE_ONLY = 1, CREATE = 64, EXCLUSIVE = 128,
    FRAME_BYTES = M10V_LIVE_INGRESS_FRAME_BYTES,
    JPEG_LIMIT = 64 * 1024 * 1024,
};

typedef struct {
    m10v_live_clip clip;
    uint8_t frame[FRAME_BYTES];
    uint8_t ring[M10V_LIVE_FRAMES * FRAME_BYTES];
    uint8_t io[4096];
    m10v_live_pair cached;
    char jpeg_directory[17], jpeg_file[23];
    uint32_t jpeg_bytes;
    uint64_t diagnostic_next, shot_seen_at;
    uint32_t diagnostic_request, diagnostic_initialized, accepted_frames;
    uint32_t diagnostic_values[14];
    int32_t write_error;
} live_memory;

static live_memory *memory;
static uint32_t address, owner_epoch, request, sequence, shot_sequence, shot_token[4];
static uint64_t last_frame;
static int folder = -1;

static long call(unsigned n, unsigned a, unsigned b, unsigned c, unsigned d,
                 unsigned e, unsigned f) {
    register unsigned r0 __asm__("r0") = a, r1 __asm__("r1") = b, r2 __asm__("r2") = c,
        r3 __asm__("r3") = d, r4 __asm__("r4") = e, r5 __asm__("r5") = f, r7 __asm__("r7") = n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4),
                     "r"(r5), "r"(r7) : "memory", "cc");
    return (long)r0;
}

static unsigned ptr(const void *p) { return (unsigned)(uintptr_t)p; }
static void close_file(int fd) { if (fd >= 0) call(CLOSE, (unsigned)fd, 0, 0, 0, 0, 0); }

static int open_at(int fd, const char *name, unsigned flags) {
    return (int)call(OPEN_AT, (unsigned)fd, ptr(name), flags | NOFOLLOW | NONBLOCK, 0600, 0, 0);
}

static long size(int fd) { return call(SEEK, (unsigned)fd, 0, 2, 0, 0, 0); }

static int live_file_read(void *context, uint32_t offset, uint8_t *out, uint32_t bytes) {
    int fd = *(const int *)context;
    while (bytes) {
        long n = call(PREAD, (unsigned)fd, ptr(out), bytes, 0, offset, 0);
        if (n == -4) continue;
        if (n <= 0 || (uint32_t)n > bytes) return 0;
        bytes -= (uint32_t)n;
        offset += (uint32_t)n;
        out += n;
    }
    return 1;
}

static int live_file_write(void *context, const uint8_t *data, uint32_t bytes) {
    int fd = *(const int *)context;
    while (bytes) {
        long n = call(WRITE, (unsigned)fd, ptr(data), bytes, 0, 0, 0);
        if (n == -4) continue;
        if (n <= 0 || (uint32_t)n > bytes) {
            if (memory) memory->write_error = n < 0 ? (int32_t)n : -5;
            return 0;
        }
        data += n;
        bytes -= (uint32_t)n;
    }
    return 1;
}

static void log_live(const char *message) {
    unsigned len = 0;
    while (message[len]) ++len;
    (void)live_file_write(&(int){1}, (const uint8_t *)message, len);
}

static void attach_error(unsigned stage, long error) {
    static unsigned previous_stage;
    static long previous_error;
    static const char hex[] = "0123456789abcdef";
    if (stage == previous_stage && error == previous_error) return;
    previous_stage = stage;
    previous_error = error;
    char line[] = "LIVE_ATTACH_ERROR 0 00000000\n";
    line[18] = (char)('0' + stage);
    for (unsigned i = 0; i < 8; ++i)
        line[20 + i] = hex[(uint32_t)error >> (28u - i * 4u) & 15u];
    log_live(line);
}

static int sd_root(void) {
    int fd = (int)call(OPEN, ptr("/media/storage1"), DIRECTORY | NOFOLLOW, 0, 0, 0, 0);
    if (fd < 0) attach_error(3, fd);
    return fd;
}

static int open_live_folder(void) {
    int root = sd_root();
    if (root < 0) return -1;
    int m10v = open_at(root, "M10V", DIRECTORY);
    close_file(root);
    if (m10v < 0) { attach_error(4, m10v); return -1; }
    long created = call(MKDIR_AT, (unsigned)m10v, ptr("LIVE"), 0700, 0, 0, 0);
    int fd = created == 0 || created == -17 ? open_at(m10v, "LIVE", DIRECTORY) : -1;
    close_file(m10v);
    if (fd < 0) attach_error(created == 0 || created == -17 ? 6 : 5,
                             created == 0 || created == -17 ? fd : created);
    return fd;
}

static void token_filename(const uint32_t token[4], char name[38]) {
    m10v_hex((const uint8_t *)token, 16, name);
    for (unsigned i = 0; i < 6; ++i) name[32 + i] = ".M10L"[i];
}

static void trace_save_error(uint32_t stage, long result) {
    memory->diagnostic_values[0] = stage;
    memory->diagnostic_values[1] = (uint32_t)result;
    m10v_linux_trace("LIVE_SAVE_ERROR", memory->diagnostic_values, 2);
}

/* Preserve every token bit using only names accepted by the camera's 8.3
 * driver: aaaaaaaa/bbbbbbbb/cccccccc/dddddddd.M10. The HTTP identity remains
 * the original 16 + 16 hex split, independent of physical storage. */
static int token_folder(const char hex[33], int create) {
    int parent = folder;
    for (unsigned part = 0; part < 3; ++part) {
        char name[9];
        for (unsigned i = 0; i < 8; ++i) name[i] = hex[part * 8 + i];
        name[8] = 0;
        long made = create ? call(MKDIR_AT, (unsigned)parent, ptr(name), 0700, 0, 0, 0) : -17;
        int child = made == 0 || made == -17 ? open_at(parent, name, DIRECTORY) : (int)made;
        if (parent != folder) close_file(parent);
        if (child < 0) return child;
        parent = child;
    }
    return parent;
}

static void short_filename(const char hex[33], char name[13], const char *suffix) {
    for (unsigned i = 0; i < 8; ++i) name[i] = hex[24 + i];
    for (unsigned i = 0; i < 5; ++i) name[8 + i] = suffix[i];
}

static void sync_directory(int fd) {
    long result = call(FSYNC, (unsigned)fd, 0, 0, 0, 0, 0);
    if (!result) return;
    memory->diagnostic_values[0] = (uint32_t)result;
    m10v_linux_trace(result == -22 || result == -95 || result == -38 ?
        "LIVE_DIR_SYNC_UNSUPPORTED" : "LIVE_DIR_SYNC_ERROR", memory->diagnostic_values, 1);
}

static int save_clip(void) {
    char hex[33], name[13], temp[13];
    m10v_hex((const uint8_t *)shot_token, 16, hex);
    int parent = token_folder(hex, 1);
    if (parent < 0) { trace_save_error(8, parent); return 0; }
    short_filename(hex, name, ".M10");
    short_filename(hex, temp, ".TMP");
    int existing = open_at(parent, name, 0);
    if (existing != -2) {
        close_file(existing);
        close_file(parent);
        trace_save_error(1, existing);
        return 0;
    }
    int fd = open_at(parent, temp, WRITE_ONLY | CREATE | EXCLUSIVE);
    if (fd < 0) { close_file(parent); trace_save_error(2, fd); return 0; }
    memory->write_error = 0;
    int written = m10v_live_write_clip(&memory->clip, live_file_write, &fd);
    if (!written) trace_save_error(3, memory->write_error ? memory->write_error : -5);
    if (written) {
        long result = call(FSYNC, (unsigned)fd, 0, 0, 0, 0, 0);
        if (result) { trace_save_error(4, result); written = 0; }
    }
    long closed = call(CLOSE, (unsigned)fd, 0, 0, 0, 0, 0);
    if (closed) { trace_save_error(5, closed); written = 0; }
    if (written) {
        long renamed = call(RENAME_AT, (unsigned)parent, ptr(temp), (unsigned)parent, ptr(name), 0, 0);
        if (!renamed) {
            sync_directory(parent);
            close_file(parent);
            return 1;
        }
        trace_save_error(6, renamed);
    }
    (void)call(UNLINK_AT, (unsigned)parent, ptr(temp), 0, 0, 0, 0);
    close_file(parent);
    return 0;
}

int m10v_linux_live_attach(const m10v_live_ingress_offer *offer, uint32_t epoch) {
    if (offer->version != M10V_LIVE_INGRESS_VERSION || offer->epoch != epoch ||
        (offer->address & 127u) || offer->address < 0x55804374u ||
        offer->address > 0x60000000u - sizeof(m10v_live_ingress) ||
        offer->bytes != sizeof(m10v_live_ingress) ||
        offer->slot_count != M10V_LIVE_INGRESS_SLOTS ||
        offer->slot_stride != sizeof(m10v_live_ingress_frame) ||
        offer->frame_bytes != FRAME_BYTES || offer->format != M10V_LIVE_INGRESS_MONO_NV12) {
        attach_error(1, -22);
        return 0;
    }
    if (!memory) {
        unsigned mapped = (unsigned)call(MMAP2, 0, sizeof(*memory), 3, 0x22, (unsigned)-1, 0);
        if (!mapped || mapped >= 0xfffff000u) { attach_error(2, (long)mapped); return 0; }
        live_memory *allocated = (void *)(uintptr_t)mapped;
        if (!m10v_live_init_nv12(&allocated->clip, allocated->ring, sizeof(allocated->ring),
                                 M10V_LIVE_INGRESS_WIDTH, M10V_LIVE_INGRESS_HEIGHT)) {
            call(MUNMAP, mapped, sizeof(*allocated), 0, 0, 0, 0);
            attach_error(2, -22);
            return 0;
        }
        memory = allocated;
    }
    if (folder < 0) folder = open_live_folder();
    if (folder < 0) return 0;
    address = offer->address;
    owner_epoch = epoch;
    return 1;
}

/* The producer uses a wrapping millisecond clock. Extend solely from observed
 * adjacent frame timestamps, never from the unrelated Linux monotonic epoch. */
static uint64_t frame_time(uint32_t tick) {
    if (!last_frame) return (1ull << 32) + tick;
    return last_frame + (int32_t)(tick - (uint32_t)last_frame);
}

static int sequence_after(uint32_t a, uint32_t b) {
    return a && !(a & 1u) && (!b || (int32_t)(a - b) > 0);
}

static void trace_live_state(m10v_linux_target *target, uint64_t now,
                              const m10v_live_ingress_control *control,
                              const m10v_live_ingress_shutter *shot,
                              const uint32_t heads[M10V_LIVE_INGRESS_SLOTS][3]) {
    uint32_t mode = request & 3u;
    if (memory->diagnostic_initialized && memory->diagnostic_request == request &&
        (!mode || now < memory->diagnostic_next)) return;
    memory->diagnostic_initialized = 1;
    memory->diagnostic_request = request;
    memory->diagnostic_next = now + 5000u;
    uint32_t *values = memory->diagnostic_values;
    values[0] = request;
    values[1] = mode;
    for (unsigned i = 0; i < M10V_LIVE_INGRESS_SLOTS; ++i)
        values[2 + i] = heads ? heads[i][0] : 0;
    values[5] = shot ? shot->seq : 0;
    values[6] = shot ? shot->request : 0;
    values[7] = sequence;
    values[8] = memory->accepted_frames;
    values[9] = memory->clip.count;
    values[10] = memory->clip.pending;
    values[11] = memory->clip.failed;
    values[12] = (uint32_t)last_frame;
    values[13] = (uint32_t)now;
    m10v_linux_trace("LIVE_PROGRESS", values, 14);
    const m10v_live_ingress_diagnostic *d = &control->diagnostic;
    uint32_t confirmed;
    /* Diagnostics are observational. Older producers, an in-flight cache
     * publication or an unreadable snapshot never block clip consumption. */
    if ((d->version != 1 && d->version != 2) || !d->seq || (d->seq & 1u) ||
        !target->io.read(target->io.ctx,
            address + offsetof(m10v_live_ingress_control, diagnostic), &confirmed, 4) ||
        confirmed != d->seq) return;
    const uint32_t *words = (const void *)d;
    m10v_linux_trace("LIVE_PRODUCER", words, 14);
    values[0] = d->seq;
    for (unsigned i = 1; i < 14; ++i) values[i] = words[i + 13];
    m10v_linux_trace("LIVE_SOURCE", values, 14);
}

static void window_trace(const char *event) {
    const m10v_live_clip *clip = &memory->clip;
    uint32_t *v = memory->diagnostic_values;
    v[0] = clip->rejection;
    v[1] = (uint32_t)clip->shutter;
    v[2] = clip->count ? (uint32_t)clip->frames[clip->head].time : 0;
    v[3] = clip->post_start == UINT64_MAX ? 0 : (uint32_t)clip->post_start;
    v[4] = clip->count ? (uint32_t)clip->frames[(clip->head + clip->count - 1u) % M10V_LIVE_FRAMES].time : 0;
    v[5] = (uint32_t)clip->end;
    v[6] = clip->post_start == UINT64_MAX ? 0 : (uint32_t)(clip->post_start - clip->shutter);
    v[7] = clip->count;
    m10v_linux_trace(event, v, 8);
}

static void begin_shot(const m10v_live_ingress_shutter *shot, uint32_t mode, uint64_t now) {
    shot_sequence = shot->seq;
    uint32_t *v = memory->diagnostic_values;
    const m10v_live_clip *clip = &memory->clip;
    v[0] = shot->seq; v[1] = request; v[2] = shot->tick;
    v[3] = clip->count;
    v[4] = clip->count ? (uint32_t)clip->frames[clip->head].time : 0;
    v[5] = clip->count ? (uint32_t)clip->frames[
        (clip->head + clip->count - 1u) % M10V_LIVE_FRAMES].time : 0;
    v[6] = clip->pending; v[7] = clip->failed;
    if (m10v_live_shutter(&memory->clip, frame_time(shot->tick), mode == 1)) {
        for (unsigned i = 0; i < 4; ++i) shot_token[i] = shot->token[i];
        memory->shot_seen_at = now;
        log_live("LIVE_SHUTTER\n");
        window_trace("LIVE_WINDOW_START");
    } else {
        m10v_linux_trace("LIVE_WINDOW_REJECT", v, 8);
        memory->diagnostic_values[0] = memory->clip.rejection;
        m10v_linux_trace("LIVE_WINDOW_REASON", memory->diagnostic_values, 1);
        log_live("LIVE_SKIPPED_PREBUFFER_OR_BUSY\n");
    }
}

void m10v_linux_live_sample(m10v_linux_target *target, uint64_t now) {
    static uint64_t checked, last_progress;
    if (!address || owner_epoch != target->epoch || now < checked + 34u) return;
    checked = now;
    m10v_live_ingress_control control;
    if (!target->io.read(target->io.ctx, address, &control, sizeof(control)) ||
        control.magic != M10V_LIVE_INGRESS_MAGIC || control.epoch != owner_epoch ||
        control.version != M10V_LIVE_INGRESS_VERSION || control.bytes != sizeof(m10v_live_ingress))
        return;
    if (request != control.request) {
        request = control.request;
        sequence = shot_sequence = 0;
        last_frame = last_progress = 0;
        memory->accepted_frames = 0;
        m10v_live_reset(&memory->clip);
    }
    uint32_t mode = request & 3;
    if (mode != 1 && mode != 2) {
        trace_live_state(target, now, &control, 0, 0);
        return;
    }

    uint32_t heads[M10V_LIVE_INGRESS_SLOTS][3];
    uint32_t start = address + offsetof(m10v_live_ingress, frames);
    for (unsigned i = 0; i < M10V_LIVE_INGRESS_SLOTS; ++i) {
        if (!target->io.read(target->io.ctx, start + i * sizeof(m10v_live_ingress_frame), heads[i], 12))
            heads[i][0] = 0;
    }
    /* Snapshot frame headers before the shutter. Otherwise a shutter published
     * between these reads lets a post-exposure frame enter the rolling buffer
     * before its event; the next sample then rejects newest > shutter. An
     * in-flight event defers this batch until its token/timestamp are stable. */
    m10v_live_ingress_shutter shot;
    uint32_t shutter = address + offsetof(m10v_live_ingress, shutter), confirmed_shot;
    if (!target->io.read(target->io.ctx, shutter, &shot, sizeof(shot)) || (shot.seq & 1u) ||
        !target->io.read(target->io.ctx, shutter, &confirmed_shot, 4) || confirmed_shot != shot.seq)
        return;
    int has_shot = shot.request == request && sequence_after(shot.seq, shot_sequence) &&
        (shot.token[0] || shot.token[1] || shot.token[2] || shot.token[3]);
    for (unsigned pass = 0; pass < M10V_LIVE_INGRESS_SLOTS; ++pass) {
        unsigned selected = M10V_LIVE_INGRESS_SLOTS;
        for (unsigned i = 0; i < M10V_LIVE_INGRESS_SLOTS; ++i) {
            if (heads[i][2] == request && sequence_after(heads[i][0], sequence) &&
                (selected == M10V_LIVE_INGRESS_SLOTS || sequence_after(heads[selected][0], heads[i][0])))
                selected = i;
        }
        if (selected == M10V_LIVE_INGRESS_SLOTS) break;
        uint32_t *head = heads[selected];
        uint32_t frame = start + selected * sizeof(m10v_live_ingress_frame);
        uint32_t confirmed;
        sequence = head[0];
        if (!target->io.read(target->io.ctx, frame + offsetof(m10v_live_ingress_frame, data),
                             memory->frame, FRAME_BYTES) ||
            !target->io.read(target->io.ctx, frame, &confirmed, 4) || confirmed != sequence)
            continue;
        uint64_t time = frame_time(head[1]);
        if (has_shot && (int32_t)(head[1] - shot.tick) >= 0) {
            has_shot = 0;
            begin_shot(&shot, mode, now);
        }
        last_frame = time;
        last_progress = now;
        uint64_t previous_post = memory->clip.post_start;
        if ((mode == 1 || memory->clip.pending) &&
            m10v_live_push(&memory->clip, time, memory->frame, FRAME_BYTES)) {
            memory->accepted_frames++;
            if (memory->clip.pending && previous_post == UINT64_MAX &&
                memory->clip.post_start != UINT64_MAX) window_trace("LIVE_POST_START");
        }
    }
    /* Arm a stable event even while the display source is blacked out.
     * All stable pre-event frame headers from this batch have been consumed. */
    if (has_shot) begin_shot(&shot, mode, now);
    uint64_t estimated = last_frame + (last_progress ? now - last_progress : 0);
    if (memory->clip.pending) {
        uint64_t event_clock = memory->clip.shutter + (now - memory->shot_seen_at);
        if (estimated < event_clock) estimated = event_clock;
        if (memory->clip.failed || estimated >= memory->clip.end + 80u) {
            if (m10v_live_complete(&memory->clip, estimated)) {
                window_trace("LIVE_WINDOW_COMPLETE");
                log_live(save_clip() ? "LIVE_SD_OK\n" : "LIVE_SD_ERROR\n");
            } else {
                window_trace("LIVE_WINDOW_FAILED");
                log_live("LIVE_INCOMPLETE\n");
            }
            m10v_live_reset(&memory->clip);
        }
    }
    if (!memory->clip.pending && last_progress && now - last_progress > 1800u) {
        m10v_live_reset(&memory->clip);
        last_progress = 0;
    }
    trace_live_state(target, now, &control, &shot, heads);
}

static int same(const char *a, const char *b) {
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}

static void label(char *out, const char *in, unsigned limit) {
    unsigned i = 0;
    while (i < limit && in[i]) { out[i] = in[i]; ++i; }
    out[i] = 0;
}

static int digest(int fd, uint32_t bytes, uint8_t sha[32]) {
    m10v_sha256_context hash;
    m10v_sha256_init(&hash);
    for (uint32_t at = 0; at < bytes;) {
        uint32_t count = bytes - at;
        if (count > sizeof(memory->io)) count = sizeof(memory->io);
        if (!live_file_read(&fd, at, memory->io, count)) return 0;
        m10v_sha256_update(&hash, memory->io, count);
        at += count;
    }
    m10v_sha256_finish(&hash, sha);
    return size(fd) == (long)bytes;
}

static int open_jpeg(const char *directory, const char *name) {
    int root = sd_root();
    if (root < 0) return -1;
    int dcim = open_at(root, "DCIM", DIRECTORY);
    close_file(root);
    if (dcim < 0) return dcim;
    int dir = open_at(dcim, directory, DIRECTORY);
    close_file(dcim);
    if (dir < 0) return dir;
    int fd = open_at(dir, name, 0);
    close_file(dir);
    return fd;
}

static uint32_t le32(const uint8_t *b) {
    return (uint32_t)b[0] | (uint32_t)b[1] << 8 | (uint32_t)b[2] << 16 | (uint32_t)b[3] << 24;
}

/* A successful long-name open is insufficient on this camera: its driver
 * silently truncates components. Only an exact directory entry proves that a
 * legacy 32-hex .M10L file retains the complete identity. Never try 8.3 aliases. */
static int legacy_entry(const char *name) {
    long result = call(SEEK, (unsigned)folder, 0, 0, 0, 0, 0);
    if (result < 0) return result == -22 || result == -38 || result == -95 ? 0 : -1;
    for (;;) {
        result = call(GETDENTS64, (unsigned)folder, ptr(memory->io), sizeof(memory->io), 0, 0, 0);
        if (result <= 0) return result == 0 || result == -22 || result == -38 || result == -95 ? 0 : -1;
        if ((unsigned)result > sizeof(memory->io)) return -1;
        for (unsigned at = 0; at < (unsigned)result;) {
            if ((unsigned)result - at < 20) return -1;
            unsigned length = memory->io[at + 16] | (unsigned)memory->io[at + 17] << 8;
            if (length < 20 || length > (unsigned)result - at) return -1;
            unsigned i = 0;
            while (i < 38 && 19 + i < length) {
                unsigned c = memory->io[at + 19 + i];
                if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
                unsigned expected = (unsigned char)name[i];
                if (expected >= 'A' && expected <= 'Z') expected += 'a' - 'A';
                if (c != expected) break;
                if (!c) return 1;
                ++i;
            }
            at += length;
        }
    }
}

static int open_clip(const char hex[33]) {
    int parent = token_folder(hex, 0);
    int fd = parent;
    if (parent >= 0) {
        char shortname[13];
        short_filename(hex, shortname, ".M10");
        fd = open_at(parent, shortname, 0);
        close_file(parent);
    }
    if (fd != -2) return fd;
    char legacy[38];
    for (unsigned i = 0; i < 32; ++i) legacy[i] = hex[i];
    for (unsigned i = 0; i < 6; ++i) legacy[32 + i] = ".M10L"[i];
    int found = legacy_entry(legacy);
    if (found != 1) return found == 0 ? -2 : -5;
    fd = open_at(folder, legacy, 0);
    return fd == -36 || fd == -22 ? -2 : fd;
}

static int live_lookup(void *context, const char *directory, const char *name, m10v_live_pair *out) {
    (void)context;
    if (!memory || folder < 0) return 0;
    int jpeg = open_jpeg(directory, name);
    if (jpeg < 0) return jpeg == -2 ? 0 : -1;
    long jpeg_bytes = size(jpeg);
    uint32_t token[4];
    const m10v_roll_photo_reader reader = {&jpeg, jpeg_bytes > 0 ? (uint32_t)jpeg_bytes : 0, live_file_read};
    int matched = jpeg_bytes > 0 && jpeg_bytes <= JPEG_LIMIT ? m10v_live_photo_token(&reader, token) : -1;
    if (matched != 1) { close_file(jpeg); return matched; }
    char filename[38];
    token_filename(token, filename);
    m10v_live_pair pair = {0};
    label(pair.clip_file, filename + 16, 21);
    label(pair.clip_directory, filename, 16);
    int clip = open_clip(filename);
    if (clip < 0) { close_file(jpeg); return clip == -2 ? 0 : -1; }
    long clip_bytes = size(clip);
    int ok = clip_bytes > 24 && clip_bytes <= M10V_LIVE_HTTP_BYTES;
    if (ok && memory->cached.bytes == (uint32_t)clip_bytes && memory->jpeg_bytes == (uint32_t)jpeg_bytes &&
        same(memory->cached.clip_file, pair.clip_file) && same(memory->cached.clip_directory, pair.clip_directory) &&
        same(memory->jpeg_directory, directory) && same(memory->jpeg_file, name)) {
        *out = memory->cached;
    } else if (ok) {
        uint8_t header[24];
        ok = live_file_read(&clip, 0, header, sizeof(header)) &&
            le32(header) == M10V_LIVE_EXIF_MAGIC && header[4] == 2 && header[5] == 0 &&
            le32(header + 12) <= le32(header + 16) && le32(header + 16) <= M10V_LIVE_MAX_SPAN_MS &&
            le32(header + 20) == 1;
        if (ok) ok = digest(jpeg, (uint32_t)jpeg_bytes, pair.jpeg_sha256) &&
            digest(clip, (uint32_t)clip_bytes, pair.clip_sha256);
        if (ok) {
            pair.kind = 1;
            pair.bytes = (uint32_t)clip_bytes;
            pair.presentation_us = le32(header + 12) * 1000u;
            memory->cached = *out = pair;
            memory->jpeg_bytes = (uint32_t)jpeg_bytes;
            label(memory->jpeg_directory, directory, 16);
            label(memory->jpeg_file, name, 22);
        }
    }
    close_file(clip);
    close_file(jpeg);
    return ok ? 1 : -1;
}

static int live_read(void *context, const m10v_live_pair *pair, uint32_t offset, uint8_t *out, uint32_t bytes) {
    (void)context;
    if (offset > pair->bytes || bytes > pair->bytes - offset) return 0;
    char hex[33];
    if (pair->clip_directory[16] || !same(pair->clip_file + 16, ".M10L")) return 0;
    for (unsigned i = 0; i < 32; ++i) {
        char c = i < 16 ? pair->clip_directory[i] : pair->clip_file[i - 16];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return 0;
        hex[i] = c;
    }
    hex[32] = 0;
    int fd = open_clip(hex);
    if (fd < 0) return 0;
    int ok = size(fd) == (long)pair->bytes && live_file_read(&fd, offset, out, bytes);
    close_file(fd);
    return ok;
}

const m10v_live_source m10v_linux_live_source = {0, live_lookup, live_read};
