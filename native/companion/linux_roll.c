#include "linux_roll.h"
#include "roll_photo.h"
#include "linux_io.h"

#if !defined(__arm__)
#error Production SD scanner requires Linux ARM EABI
#endif

/* Linux arch/arm/tools/syscall.tbl and uapi/asm/fcntl.h. */
enum {
    OPEN = 5, CLOSE = 6, STAT_FS = 100, SEEK = 19, PREAD = 180,
    DIRENTS = 217, OPEN_AT = 322, MMAP2 = 192, MUNMAP = 91,
    DIRECTORY = 1 << 14, NOFOLLOW = 1 << 15, NONBLOCK = 1 << 11,
    PHOTO_LIMIT = 4096
};

static long call(unsigned n, unsigned a, unsigned b, unsigned c, unsigned d,
                 unsigned e, unsigned f) {
    register unsigned r0 __asm__("r0") = a, r1 __asm__("r1") = b, r2 __asm__("r2") = c,
        r3 __asm__("r3") = d, r4 __asm__("r4") = e, r5 __asm__("r5") = f, r7 __asm__("r7") = n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4),
                     "r"(r5), "r"(r7) : "memory", "cc");
    return (long)r0;
}

static unsigned address(const void *p) { return (unsigned)(uintptr_t)p; }
static void close_file(int fd) { (void)call(CLOSE, (unsigned)fd, 0, 0, 0, 0, 0); }
static int open_at(int fd, const char *name, unsigned flags) {
    return (int)call(OPEN_AT, (unsigned)fd, address(name), flags | NOFOLLOW | NONBLOCK, 0, 0, 0);
}

static int file_read(void *ctx, uint32_t offset, uint8_t *out, uint32_t bytes) {
    int fd = *(const int *)ctx;
    while (bytes) {
        long n = call(PREAD, (unsigned)fd, address(out), bytes, 0, offset, 0);
        if (n == -4) continue;
        if (n <= 0 || (uint32_t)n > bytes) return 0;
        bytes -= (uint32_t)n; offset += (uint32_t)n; out += n;
    }
    return 1;
}

static long size(int fd) {
    return call(SEEK, (unsigned)fd, 0, 2, 0, 0, 0);
}

static int read_pages(int root, m10v_roll_recovery *out) {
    for (unsigned i = 0; i < 2; ++i) {
        int fd = open_at(root, i ? "M10VRL1.BIN" : "M10VRL0.BIN", 0);
        if (fd == -2) { out->pages[i] = M10V_ROLL_SD_ABSENT; continue; }
        if (fd < 0) return 0;
        long n = size(fd);
        if (n == sizeof(m10v_roll_record)) {
            int ok = file_read(&fd, 0, (uint8_t *)&out->records[i], (uint32_t)n);
            close_file(fd);
            if (!ok) return 0;
            out->pages[i] = M10V_ROLL_SD_PRESENT;
        } else {
            close_file(fd);
            if (n < 0) return 0;
            out->pages[i] = M10V_ROLL_SD_DAMAGED;
        }
    }
    return 1;
}

static char upper(char c) { return c >= 'a' && c <= 'z' ? (char)(c - 32) : c; }
static int photo_format(const char *name, unsigned length) {
    if (length != 12 || name[8] != '.') return 0;
    if (upper(name[9]) == 'J' && upper(name[10]) == 'P' && upper(name[11]) == 'G') return 1;
    if (upper(name[9]) == 'D' && upper(name[10]) == 'N' && upper(name[11]) == 'G') return 2;
    return 0;
}

typedef struct {
    int fd;
    uint32_t prefix_bytes;
    const uint8_t *prefix;
    int *read_failed;
} cached_photo;

static int cached_read(void *ctx, uint32_t offset, uint8_t *out, uint32_t bytes) {
    const cached_photo *photo = ctx;
    if (offset <= photo->prefix_bytes && bytes <= photo->prefix_bytes - offset) {
        for (uint32_t i = 0; i < bytes; ++i) out[i] = photo->prefix[offset + i];
        return 1;
    }
    int ok = file_read((void *)&photo->fd, offset, out, bytes);
    if (!ok && photo->read_failed) *photo->read_failed = 1;
    return ok;
}

typedef struct {
    const m10v_roll_record *roll;
    uint32_t found[2][2];
    uint32_t checked;
} scan;

static int photograph(int folder, scan *s, const char *name, unsigned length, uint8_t *prefix) {
    int format = photo_format(name, length);
    if (!format) return 1;
    if (++s->checked > PHOTO_LIMIT) return 0;
    int fd = open_at(folder, name, 0);
    if (fd < 0) return 0;
    long n = size(fd);
    cached_photo source = {fd, n <= 0 ? 0 : n < M10V_ROLL_PREFIX_BYTES ? (uint32_t)n : M10V_ROLL_PREFIX_BYTES, prefix, 0};
    const m10v_roll_photo_reader photo = {&source, n > 0 ? (uint32_t)n : 0, cached_read};
    int frame = source.prefix_bytes && file_read(&fd, 0, prefix, source.prefix_bytes)
        ? m10v_roll_photo_frame(&photo, format == 1, s->roll) : -1;
    close_file(fd);
    if (frame < 0) return 0;
    if (frame > 0) {
        unsigned bit = (unsigned)frame - 1;
        s->found[format - 1][bit >> 5] |= 1u << (bit & 31);
    }
    return 1;
}

typedef struct {
    int folder;
    uint8_t *list;
    unsigned used, bytes;
} iterator;

/* 1 next entry, 0 EOF, -1 corrupt or inaccessible list. */
static int next_entry(iterator *it, const char **name, unsigned *length) {
    while (it->used == it->bytes) {
        long n = call(DIRENTS, (unsigned)it->folder, address(it->list), M10V_ROLL_LIST_BYTES, 0, 0, 0);
        if (n == -4) continue;
        if (n <= 0) return n == 0 ? 0 : -1;
        if ((unsigned)n > M10V_ROLL_LIST_BYTES) return -1;
        it->bytes = (unsigned)n;
        it->used = 0;
    }
    uint8_t *data = it->list + it->used;
    if (it->bytes - it->used < 20) return -1;
    unsigned end = data[16] | (unsigned)data[17] << 8;
    if (end < 20 || end > it->bytes - it->used) return -1;
    *name = (const char *)data + 19;
    *length = 0;
    while (*length < end - 19 && (*name)[*length]) ++*length;
    if (*length == end - 19) return -1;
    it->used += end;
    return 1;
}

static int photos(int dcim, scan *s, uint8_t *workspace) {
    iterator folders = {dcim, workspace, 0, 0};
    const char *name;
    unsigned length;
    int step;
    while ((step = next_entry(&folders, &name, &length)) > 0) {
        /* Stock DCF folders are three digits plus five characters. */
        if (length != 8 || name[0] < '1' || name[0] > '9' ||
            name[1] < '0' || name[1] > '9' || name[2] < '0' || name[2] > '9') continue;
        int folder = open_at(dcim, name, DIRECTORY);
        if (folder < 0) return 0;
        iterator files = {folder, workspace + M10V_ROLL_LIST_BYTES, 0, 0};
        int file_step;
        while ((file_step = next_entry(&files, &name, &length)) > 0) {
            if (!photograph(folder, s, name, length, workspace + 2 * M10V_ROLL_LIST_BYTES)) { file_step = -1; break; }
        }
        close_file(folder);
        if (file_step < 0) return 0;
    }
    return step == 0;
}

static int same_pages(const m10v_roll_recovery *a, const m10v_roll_recovery *b) {
    const uint8_t *x = (const uint8_t *)a, *y = (const uint8_t *)b;
    for (unsigned i = 0; i < sizeof(a->pages) + sizeof(a->records); ++i) {
        if (x[i] != y[i]) return 0;
    }
    return 1;
}

int m10v_linux_roll_scan(m10v_roll_recovery *out, uint8_t *workspace) {
    if (!out || !workspace) return 0;
    *out = (m10v_roll_recovery){0};
    int rt = (int)call(OPEN, address("/media/storage1"), DIRECTORY | NOFOLLOW, 0, 0, 0, 0);
    if (rt < 0) return 0;
    uint32_t fs[40];
    int ok = call(STAT_FS, (unsigned)rt, address(fs), 0, 0, 0, 0) == 0 &&
        (fs[0] == 0x4d44u || fs[0] == 0x2011bab0u) && read_pages(rt, out);
    if (!ok) goto done;
    const m10v_roll_record *even = out->pages[0] == M10V_ROLL_SD_PRESENT &&
        !(out->records[0].sequence & 1) ? &out->records[0] : 0;
    const m10v_roll_record *odd = out->pages[1] == M10V_ROLL_SD_PRESENT &&
        (out->records[1].sequence & 1) ? &out->records[1] : 0;
    int newest = m10v_roll_latest(even, odd);
    if (newest < 0) {
        ok = out->pages[0] == M10V_ROLL_SD_ABSENT && out->pages[1] == M10V_ROLL_SD_ABSENT;
        goto done;
    }
    if (out->records[newest].status != M10V_ROLL_ACTIVE) goto done;
    int dcim = open_at(rt, "DCIM", DIRECTORY);
    scan s = {.roll = &out->records[newest]};
    ok = dcim == -2 || (dcim >= 0 && photos(dcim, &s, workspace));
    if (dcim >= 0) close_file(dcim);
    if (!ok) goto done;
    m10v_roll_recovery after = {0};
    ok = read_pages(rt, &after) && same_pages(out, &after);
    if (ok) {
        for (unsigned format = 0; format < 2; ++format) {
            out->found[format][0] = s.found[format][0];
            out->found[format][1] = s.found[format][1];
        }
    }
done:
    close_file(rt);
    return ok;
}

/* Independent read-only archive reader. The two journal pages describe only
 * the latest roll; older identities come exclusively from completed JPEGs. */
static int index_latest(void *context, m10v_roll_record *record) {
    (void)context;
    m10v_roll_recovery journal = {0};
    int root = (int)call(OPEN, address("/media/storage1"), DIRECTORY | NOFOLLOW, 0, 0, 0, 0);
    if (root < 0) return -1;
    int ok = read_pages(root, &journal);
    close_file(root);
    if (!ok) return -1;
    const m10v_roll_record *a = journal.pages[0] == M10V_ROLL_SD_PRESENT && !(journal.records[0].sequence & 1) ? &journal.records[0] : 0;
    const m10v_roll_record *b = journal.pages[1] == M10V_ROLL_SD_PRESENT && (journal.records[1].sequence & 1) ? &journal.records[1] : 0;
    int latest = m10v_roll_latest(a, b);
    if (latest < 0) return journal.pages[0] == M10V_ROLL_SD_ABSENT && journal.pages[1] == M10V_ROLL_SD_ABSENT ? 0 : -1;
    *record = journal.records[latest];
    return 1;
}

typedef struct {
    int root, dcim, folder;
    iterator folders, files;
    uint8_t work[M10V_ROLL_WORKSPACE_BYTES];
    char directory[9];
    uint32_t cursor, checked, skipped;
    uint32_t entries, directories, opened, unmarked, malformed, failed, matched;
    uint32_t error_stage, error_code, names_logged;
    uint32_t first_folder[4], first_file[4];
} archive_scan;
/* One bounded, on-demand mapping keeps idle service staging below 64 KiB.
 * It is released on completion, restart, or any terminal scan error. */
static archive_scan *archive;
static uint32_t archive_generation;
static void index_trace(const char *event, const uint32_t *values, unsigned count) {
#if M10V_COMPANION_LIVE_SOURCE
    m10v_linux_trace(event, values, count);
#else
    (void)event; (void)values; (void)count;
#endif
}
static void index_open_error(uint32_t stage, int32_t error) {
    const uint32_t values[2] = {stage, (uint32_t)error};
    index_trace("ROLL_INDEX_OPEN", values, 2);
}
static void index_name(uint32_t out[4], const char *name, unsigned length) {
    if (out[0] || !length || name[0] == '.') return;
    out[0] = length;
    for (unsigned i = 0; i < 12 && i < length; ++i)
        out[1 + i / 4] |= (uint32_t)(uint8_t)name[i] << (8u * (i & 3u));
}
static void index_page_trace(uint32_t cursor, const m10v_roll_index_page *page) {
    const uint32_t values[14] = {cursor, page->next_cursor, archive->entries,
        archive->directories, archive->opened, archive->checked, archive->unmarked,
        archive->malformed, archive->failed, archive->matched, page->count,
        page->has_more, archive->error_stage, archive->error_code};
    index_trace("ROLL_INDEX_PAGE", values, 14);
    if (!(archive->names_logged & 1u) && archive->first_folder[0]) {
        index_trace("ROLL_INDEX_DIR", archive->first_folder, 4);
        archive->names_logged |= 1u;
    }
    if (!(archive->names_logged & 2u) && archive->first_file[0]) {
        index_trace("ROLL_INDEX_FILE", archive->first_file, 4);
        archive->names_logged |= 2u;
    }
}
static void index_failure(uint32_t stage, int32_t error) {
    ++archive->failed;
    archive->error_stage = stage; archive->error_code = (uint32_t)error;
}

static void archive_close(void) {
    if (!archive) return;
    if (archive->folder >= 0) close_file(archive->folder);
    if (archive->dcim >= 0) close_file(archive->dcim);
    if (archive->root >= 0) close_file(archive->root);
    (void)call(MUNMAP, address(archive), sizeof(*archive), 0, 0, 0, 0);
    archive = 0;
}
static int archive_start(void) {
    archive_close();
    unsigned mapped = (unsigned)call(MMAP2, 0, sizeof(*archive), 3, 0x22, (unsigned)-1, 0);
    if (!mapped || mapped >= 0xfffff000u) { index_open_error(1, (int32_t)mapped); return -1; }
    archive = (archive_scan *)(uintptr_t)mapped;
    archive->root = archive->dcim = archive->folder = -1;
    archive->root = (int)call(OPEN, address("/media/storage1"), DIRECTORY | NOFOLLOW, 0, 0, 0, 0);
    if (archive->root < 0) { index_open_error(2, archive->root); archive_close(); return -1; }
    archive->dcim = open_at(archive->root, "DCIM", DIRECTORY);
    if (archive->dcim == -2) { index_open_error(3, -2); archive_close(); return 0; }
    if (archive->dcim < 0) { index_open_error(3, archive->dcim); archive_close(); return -1; }
    archive->folders = (iterator){archive->dcim, archive->work, 0, 0};
    archive_generation = (archive_generation + 65536u) & 0x7fff0000u;
    if (!archive_generation) archive_generation = 65536u;
    archive->cursor = archive_generation;
    return 1;
}
static int index_photos(void *context, uint32_t cursor, m10v_roll_index_page *out) {
    (void)context;
    *out = (m10v_roll_index_page){0};
    if (!cursor) {
        int started = archive_start();
        if (started <= 0) return started < 0 ? -1 : 1;
    } else if (!archive || !archive->cursor || cursor != archive->cursor) return 0;
    unsigned budget = 0, entries = 0;
    int complete = 0;
    while (budget < 16 && entries < 128 && out->count < M10V_ROLL_INDEX_PAGE && archive->checked < PHOTO_LIMIT) {
        const char *name; unsigned length;
        if (archive->folder < 0) {
            int step = next_entry(&archive->folders, &name, &length);
            ++entries;
            if (step <= 0) { if (step < 0) { index_failure(4, step); index_page_trace(cursor, out); archive_close(); return -1; } complete = 1; break; }
            ++archive->entries;
            index_name(archive->first_folder, name, length);
            if (length != 8 || name[0] < '1' || name[0] > '9' || name[1] < '0' || name[1] > '9' || name[2] < '0' || name[2] > '9') continue;
            int safe = 1;
            for (unsigned i = 3; i < 8; ++i) if (!((name[i] >= 'A' && name[i] <= 'Z') || (name[i] >= 'a' && name[i] <= 'z') || (name[i] >= '0' && name[i] <= '9') || name[i] == '_')) safe = 0;
            if (!safe) continue;
            ++archive->directories;
            for (unsigned i = 0; i < 8; ++i) archive->directory[i] = name[i];
            archive->directory[8] = 0;
            archive->folder = open_at(archive->dcim, name, DIRECTORY);
            if (archive->folder < 0) { ++archive->skipped; index_failure(5, archive->folder); continue; }
            ++archive->opened;
            archive->files = (iterator){archive->folder, archive->work + M10V_ROLL_LIST_BYTES, 0, 0};
        }
        int step = next_entry(&archive->files, &name, &length);
        ++entries;
        if (step <= 0) {
            close_file(archive->folder); archive->folder = -1;
            if (step < 0) { ++archive->skipped; index_failure(6, step); }
            continue;
        }
        ++archive->entries;
        index_name(archive->first_file, name, length);
        int format = photo_format(name, length);
        if (!format) continue;
        int safe = 1;
        for (unsigned i = 0; i < 8; ++i) if (!((name[i] >= 'A' && name[i] <= 'Z') || (name[i] >= 'a' && name[i] <= 'z') || (name[i] >= '0' && name[i] <= '9') || name[i] == '_')) safe = 0;
        if (!safe) continue;
        ++budget; ++archive->checked;
        int fd = open_at(archive->folder, name, 0);
        if (fd < 0) { ++archive->skipped; index_failure(7, fd); continue; }
        long n = size(fd);
        uint8_t *prefix = archive->work + 2 * M10V_ROLL_LIST_BYTES;
        int read_failed = 0;
        cached_photo cache = {fd, n > 0 ? (n < M10V_ROLL_PREFIX_BYTES ? (uint32_t)n : M10V_ROLL_PREFIX_BYTES) : 0, prefix, &read_failed};
        m10v_roll_photo_reader reader = {&cache, n > 0 && n <= 64 * 1024 * 1024 ? (uint32_t)n : 0, cached_read};
        m10v_roll_index_photo photo = {0};
        int found = -1;
        if (!reader.bytes) index_failure(8, (int32_t)n);
        else if (!file_read(&fd, 0, prefix, cache.prefix_bytes)) index_failure(9, -1);
        else {
            found = m10v_roll_photo_index_format(&reader, format == 1, &photo.marker);
            if (read_failed) { index_failure(9, -1); found = -1; }
            else if (found < 0) { ++archive->malformed; archive->error_stage = 10; archive->error_code = (uint32_t)found; }
        }
        /* Detect concurrent append/truncate before exposing the reference. */
        if (size(fd) != n) { index_failure(11, -1); found = -1; }
        close_file(fd);
        if (found < 0) { ++archive->skipped; continue; }
        if (!found) { ++archive->unmarked; continue; }
        ++archive->matched;
        for (unsigned i = 0; i < 9; ++i) photo.directory[i] = archive->directory[i];
        for (unsigned i = 0; i < 12; ++i) photo.file[i] = name[i];
        photo.file[12] = 0;
        out->photos[out->count++] = photo;
    }
    out->checked = archive->checked; out->skipped = archive->skipped;
    out->truncated = archive->checked >= PHOTO_LIMIT;
    out->has_more = !complete && !out->truncated;
    if (out->has_more) out->next_cursor = ++archive->cursor;
    index_page_trace(cursor, out);
    if (!out->has_more) archive_close();
    return 1;
}
const m10v_roll_index_source m10v_linux_roll_index_source = {0, index_latest, index_photos};
