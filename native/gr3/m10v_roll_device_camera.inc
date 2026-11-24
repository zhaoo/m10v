/* Exact GR III 2.10. This is included by the permanent AppMain owner so
 * filesystem calls use the same native task and owner lifetime as settings. */
#include "m10v_debug.h"
typedef uint32_t (*roll_sd_get)(void);
typedef int (*roll_sd_open_fn)(uint32_t, const char *, uint32_t, uint32_t *, uint32_t *);
typedef int (*roll_sd_close_fn)(uint32_t, uint32_t, uint32_t *);
typedef int (*roll_sd_transfer_fn)(uint32_t, uint32_t, void *, uint32_t, uint32_t *);
typedef int (*roll_sd_position_fn)(uint32_t, uint32_t, uint32_t *, uint32_t *);

typedef int (*roll_sd_volume_fn)(uint32_t, const char *);

static ui_context *roll_context(void) {
    if (!(*(const volatile uint32_t *)0x55063910u & 1u)) return 0;
    ui_context *c = context(*(const volatile uint32_t *)0x55063988u);
    return c && current(c) ? c : 0;
}

static uint32_t roll_filesystem(void) {
    uint32_t manager = ((roll_sd_get)0x535847d8u)();
    /* The stock SD manager at 0x553497bc is below the resident mailbox heap.
     * Use the same static/object RAM bounds as the existing SD menu reader. */
    if ((manager&3u)||manager<0x55000000u||manager>0x80000000u-24u) return 0;
    uint32_t fs = ((const uint32_t *)(uintptr_t)manager)[5];
    return !(fs&3u)&&fs>=0x55000000u&&fs<=0x80000000u-32u&&
        *(const uint32_t *)(uintptr_t)fs==0x53d252d0u?fs:0;
}

static int roll_sd_ram(uint32_t addr, uint32_t bytes) {
    return !(addr&3u)&&addr>=0x55000000u&&addr<=0x80000000u-bytes;
}

static int roll_absent(uint32_t fs, const char *path) {
    const uint32_t *master = (const void *)(uintptr_t)fs;
    roll_sd_volume_fn volume = (roll_sd_volume_fn)0x535964c4u;
    if (!roll_sd_ram(master[2],36u)) return 0;
    unsigned drive = (unsigned)volume(master[2],path);
    uint32_t drivers = master[6], mutexes = master[7];
    if (drive >= 26u || !roll_sd_ram(drivers,4u*(drive+1u)) ||
        !roll_sd_ram(mutexes,4u*(drive+1u))) return 0;
    uint32_t master_lock = ((const uint32_t *)(uintptr_t)mutexes)[drive];
    fn2 lock = (fn2)0x536ae71cu;
    fn1 unlock = (fn1)0x536ae870u;
    if (!roll_sd_ram(master_lock,20u) || !lock(master_lock,0)) return 0;
    uint32_t driver = master[6]==drivers && master[7]==mutexes ?
        ((const uint32_t *)(uintptr_t)drivers)[drive] : 0;
    if (roll_sd_ram(driver,32u) &&
        *(const uint32_t *)(uintptr_t)driver==0x53d24f34u) {
        uint32_t info[8];
        /* Stock alternate filesystem has no backend mutex. Its native
         * file-info helper returns the original positive media error before
         * FileError translation. The directory search uses 5 for no entry
         * (0x53888c6c), while unrelated failures retain their distinct code. */
        int missing = ((fn2)0x5358e924u)(driver-4u,(uint32_t)(uintptr_t)path) &&
            ((fn3)0x5358ed2cu)(driver-4u,(uint32_t)(uintptr_t)path,
                (uint32_t)(uintptr_t)info)==5u;
        return unlock(master_lock) && missing;
    }
    /* The master calls the concrete FAT secondary vtable (open 0x535899ec).
     * Its thunk subtracts four from this, so the +0x18 mutex is at +0x14. */
    uint32_t backend_lock = roll_sd_ram(driver,40u) &&
        *(const uint32_t *)(uintptr_t)driver==0x53d2201cu ? driver+0x14u : 0;
    int missing = 0;
    if (backend_lock && lock(backend_lock,0)) {
        uint32_t volumes = *(const uint32_t *)0x55349b1cu;
        if (roll_sd_ram(volumes,36u)) {
            unsigned fat_drive = (unsigned)volume(volumes,path);
            uint32_t stat[16];
            /* The concrete driver resolves C: against its own volume
             * directory at 0x55349b1c (stock 0x53589940). */
            missing = fat_drive <= 1u &&
                ((int (*)(unsigned,const char *,void *))0x5389faf4u)(fat_drive,path+2,stat)==-15;
        }
        if (!unlock(backend_lock)) missing = 0;
    }
    return unlock(master_lock) && missing;
}

static int roll_page(ui_context *c, uint32_t page, m10v_roll_record *record, int write) {
    static const char paths[2][16] = {"C:\\M10VRL0.BIN", "C:\\M10VRL1.BIN"};
    c->roll.boot_stage = 20 + page * 10;
    uint32_t fs = roll_filesystem();
    if (!fs || !current(c) || page >= 2) return -1;
    c->roll.boot_stage++;
    /* Establish absence through the mounted FAT driver before opening.
     * FileMaster's mapped open error is not a file-existence predicate. */
    if (!write && roll_absent(fs,paths[page]))
        return current(c) && roll_filesystem()==fs ? 0 : -1;
    uint32_t handle = 0, error = 0;
    int opened = ((roll_sd_open_fn)0x53593e90u)(fs, paths[page], write ? 0 : 1, &handle, &error);
    if (!handle) {
        c->roll.boot_stage = 100u + (error < 100u ? error : 99u);
        return -1;
    }
    c->roll.boot_stage += 3;
    uint32_t length = 0, at = 0;
    int ok = -1;
    if (opened && !error) {
        if (!write && ((roll_sd_position_fn)0x535948c4u)(fs, handle, &length, &error) &&
            !error && length != sizeof(*record)) {
            zero(record, sizeof(*record));
            ok = 1; /* present but damaged, so the other page can win */
        } else if (!error && (write || length == sizeof(*record)) &&
            ((roll_sd_transfer_fn)(write ? 0x53592888u : 0x5359279cu))
                (fs, handle, record, sizeof(*record), &error) && !error &&
            ((roll_sd_position_fn)0x53592a60u)(fs, handle, &at, &error) &&
            !error && at == sizeof(*record)) {
            ok = 1;
        }
    }
    if (ok == 1) c->roll.boot_stage++;
    error = 0;
    if (!((roll_sd_close_fn)0x53593cecu)(fs, handle, &error) || error ||
        !current(c) || roll_filesystem() != fs) return -1;
    return ok;
}

static int roll_read(void *ctx, uint32_t page, m10v_roll_record *out) {
    return roll_page(ctx, page, out, 0);
}

static int roll_write(void *ctx, uint32_t page, const m10v_roll_record *record) {
    return roll_page(ctx, page, (m10v_roll_record *)record, 1) == 1;
}

static int roll_idle(ui_context *c) {
    return !c->roll.proof_failed && current(c) && !c->locked && !c->store_depth &&
        !c->transaction.pending.present && !c->extensions.pending.present;
}

static int roll_boot(ui_context *c) {
    if (c->roll.booted) return 1;
    c->roll.boot_stage = 10;
    if (!roll_idle(c)) return 0;
    c->roll.boot_stage++;
    uint32_t storage = m10v_companion_ui_storage_enter(0);
    if (!storage) return 0;
    const m10v_roll_journal journal = {c, roll_read, roll_write};
    m10v_roll_owner_init(&c->roll.owner, &journal, 0);
    c->roll.owner.loaded = m10v_roll_load(&journal, &c->roll.owner.current);
    c->roll.booted = m10v_companion_ui_storage_leave(storage) && c->roll.owner.loaded >= 0;
    if (c->roll.booted) c->roll.boot_stage = 0;
    return c->roll.booted;
}

void m10v_roll_device_prepare(void) {
    if (!(*(const volatile uint32_t *)0x55063910u & 1u)) return;
    uint32_t owner = *(const volatile uint32_t *)0x55063988u;
    /* Entering the roll page can happen before the A/B live-entry path has
     * started the owner timer. Ask AppMain to start it at this explicit entry. */
    m10v_companion_ui_start(owner);
    ui_context *c = roll_context();
    if (c) (void)roll_boot(c);
}

static int roll_commit_result(ui_context *c, int outputs) {
    uint32_t storage = m10v_companion_ui_storage_enter(0);
    if (!storage) return 0;
    m10v_roll_owner *owner = &c->roll.owner;
    int done;
    if (owner->armed) {
        done = m10v_roll_owner_finish(owner, c->roll.pending_ticket, c->roll.pending_marker, outputs) == 1;
    } else {
        /* Retry the same receipt if the first write or its readback failed. */
        done = m10v_roll_apply_saved(&owner->journal, c->roll.pending_marker, outputs) == 1;
        if (done) {
            owner->loaded = m10v_roll_load(&owner->journal, &owner->current);
            done = owner->loaded == 1;
        }
    }
    if (!m10v_companion_ui_storage_leave(storage) || !done) return 0;
    c->roll.pending_ticket = c->roll.ticket = 0;
    return 1;
}

static int roll_proof(ui_context *c, const m10v_roll_recovery *proof) {
    if (!roll_idle(c) || !c->session_bound) return M10V_ERROR_BUSY;
    if (!c->roll.pending_ticket) return 0;
    if (c->roll.pending_outputs > 0) return M10V_ERROR_BUSY;
    uint32_t frame = c->roll.pending_marker[20];
    if (!frame || frame > 36) return M10V_ERROR_INVALID_RECIPE;
    uint32_t bit = frame - 1;
    uint32_t outputs = ((proof->found[0][bit >> 5] >> (bit & 31u)) & 1u) |
        (((proof->found[1][bit >> 5] >> (bit & 31u)) & 1u) << 1);
    if (!outputs) return M10V_ERROR_BUSY;
    for (uint32_t page = 0; page < 2; ++page) {
        m10v_roll_record record;
        int read = roll_read(c, page, &record);
        if (proof->pages[page] > M10V_ROLL_SD_DAMAGED ||
            (proof->pages[page] == M10V_ROLL_SD_ABSENT ? read != 0 :
             read != 1 || !m10v_constant_equal((const uint8_t *)&record,
                (const uint8_t *)&proof->records[page], sizeof(record)))) return M10V_ERROR_BRIDGE_UNAVAILABLE;
    }
    return roll_commit_result(c, outputs) ? 0 : M10V_ERROR_BRIDGE_UNAVAILABLE;
}

static int roll_abort(ui_context *c, uint32_t ticket) {
    if (!ticket || ticket != c->roll.pending_ticket || c->roll.pending_outputs > 0) return M10V_ERROR_BUSY;
    c->roll.proof_failed = 1;
    return 0;
}

static int roll_take_pending(ui_context *c) {
    if (!c->roll.ticket) return 1;
    if (c->roll.pending_ticket || !m10v_roll_capture_revoke(&c->roll.channel, c->roll.ticket)) return 0;
    int settled = m10v_roll_owner_finish(&c->roll.owner, c->roll.ticket, c->roll.owner.marker, 0);
    if (settled != 1) return 0;
    c->roll.ticket = 0;
    return 1;
}

int m10v_roll_device_film_available(uint32_t film) {
    if (film == 0x10016u || (film >= 33u && M10V_BUILTIN(film) && !M10V_ANIME(film))) return 1;
    return M10V_CUSTOM(film) && m10v_camera_library_roll_prepare(film,0);
}

int m10v_roll_device_snapshot(m10v_roll_record *out) {
    if (!(*(const volatile uint32_t *)0x55063910u & 1u)) return -1;
    ui_context *c = context(*(const volatile uint32_t *)0x55063988u);
    if (!c) return -2;
    if (!current(c)) return -3;
    if (c->roll.proof_failed) return -4;
    if (!c->roll.booted) return c->roll.boot_stage ? -(int)c->roll.boot_stage : -5;
    return m10v_roll_owner_snapshot(&c->roll.owner, out);
}

int m10v_roll_device_locked(void) {
    ui_context *c = roll_context();
    return c && c->roll.booted && c->roll.owner.loaded == 1 &&
        c->roll.owner.current.status == M10V_ROLL_ACTIVE;
}

int m10v_roll_device_open(uint32_t film, uint32_t aspect, uint32_t target) {
    ui_context *c = roll_context();
    if (!c || !roll_idle(c) || !roll_boot(c) || !roll_take_pending(c) ||
        (aspect != 0 && aspect != 2 && aspect != 4 && aspect != 5) ||
        !m10v_roll_device_film_available(film)) return 0;
    uint32_t storage = m10v_companion_ui_storage_enter(0);
    if (!storage) return 0;
    uint32_t seed[8] = {0}, root = ((uint32_t (*)(void))0x5320ad88u)();
    uint32_t clock = ((fn1)0x5320b97cu)(root);
    if (!(clock & 3u) && clock >= 0x55000000u && clock <= 0x80000000u - 0x3ccu)
        (void)((int (*)(uint32_t, void *))0x532b36ccu)(clock, seed);
    (void)((int (*)(uint32_t *))0x53050b7cu)(seed + 3);
    seed[5] = c->roll.owner.loaded == 1 ? c->roll.owner.current.sequence : 0;
    seed[6] = c->wire.epoch;
    seed[7] = c->store_generation;
    uint8_t digest[32];
    m10v_sha256((const uint8_t *)seed, sizeof(seed), digest);
    int opened = m10v_roll_owner_open(&c->roll.owner, digest, film, aspect, target);
    return m10v_companion_ui_storage_leave(storage) && opened;
}

static int roll_drain(ui_context *c);

int m10v_roll_device_change(uint32_t status) {
    ui_context *c = roll_context();
    if (!c || !roll_idle(c) || !roll_boot(c)) return 0;
    /* A completion can arrive immediately before the user closes or pauses.
     * Settle its receipt on AppMain before trying to revoke the next frame. */
    (void)roll_drain(c);
    if (!roll_take_pending(c)) return 0;
    if (status == M10V_ROLL_ACTIVE &&
        (c->roll.owner.loaded != 1 || !m10v_roll_device_film_available(c->roll.owner.current.film))) return 0;
    uint32_t storage = m10v_companion_ui_storage_enter(0);
    if (!storage) return 0;
    int changed = m10v_roll_owner_change(&c->roll.owner, status);
    return m10v_companion_ui_storage_leave(storage) && changed;
}

m10v_roll_capture_channel *m10v_roll_device_capture_channel(void) {
    /* Capture may read the published mailbox. There is no filesystem call,
     * allocation or mutation of AppMain state in this path. */
    ui_context *c = roll_context();
    return c ? &c->roll.channel : 0;
}

static void roll_set_tone(uint32_t selected,uint32_t bank,uint32_t tone) {
    uint8_t *bytes = (void *)(uintptr_t)selected;
    uint8_t prior = bytes[0x1b]; bytes[0x1b] = 0;
    ((fn2)0x532bd61cu)(selected, bank);
    ((fn2)0x532c26c0u)(selected, tone);
    bytes[0x1b] = prior;
}

static void roll_clear(ui_context *c) {
    uint32_t selected=c->roll.previous_model;
    if(!selected)return;
    if(model()==selected){
        M10V_LOG(410,selected,c->roll.applied_aspect,c->roll.previous_aspect,c->roll.applied_tone);
        if(c->roll.applied_aspect!=c->roll.previous_aspect){
            uint32_t ratio;
#if M10V_DEBUG_MODE
            ratio=0xffffffffu;
#endif
            int read_status=m10v_settings_controller_remote_aspect_read(&ratio);
            M10V_LOG(411,selected,ratio,(uint32_t)read_status,c->roll.applied_aspect);
            if(!read_status&&ratio==c->roll.applied_aspect){
                int write_status=m10v_settings_controller_remote_aspect_write(c->roll.previous_aspect);
                M10V_LOG(412,selected,ratio,c->roll.previous_aspect,(uint32_t)write_status);
                (void)write_status;
            }
        }
        if((c->roll.applied_tone!=c->roll.previous_tone||c->roll.previous_bank) &&
           !((fn1)0x532bd6d4u)(selected) &&
           ((fn1)0x532bd6b4u)(selected)==c->roll.applied_tone)
            roll_set_tone(selected,c->roll.previous_bank,c->roll.previous_tone);
    }
    (void)m10v_camera_library_roll_prepare(0,1);
    c->roll.previous_model=0;
}

static int roll_apply(ui_context *c, uint32_t *tone_out, uint32_t *aspect_out, uint32_t *film_out) {
    m10v_roll_record roll;
    if (m10v_roll_owner_snapshot(&c->roll.owner, &roll) != 1 ||
        roll.status != M10V_ROLL_ACTIVE || m10v_settings_controller_remote_busy()) return 0;
    uint32_t selected = model(), ratio = 0;
    if (!selected || m10v_settings_controller_remote_aspect_read(&ratio)) return 0;
    uint32_t tone = roll.film == 0x10016u ? 22u : m10v_camera_library_roll_prepare(roll.film,1);
    if(!tone)return 0;
    if (!current(c) || model() != selected) return 0;
    if (c->roll.previous_model!=selected) {
        c->roll.previous_model=selected;
        c->roll.previous_tone=((fn1)0x532bd6b4u)(selected);
        c->roll.previous_bank=((fn1)0x532bd6d4u)(selected);
        c->roll.previous_aspect=ratio;
    }
    if (ratio != roll.aspect && m10v_settings_controller_remote_aspect_write(roll.aspect)) return 0;
    c->roll.applied_aspect=roll.aspect;
    if (((fn1)0x532bd6d4u)(selected) || ((fn1)0x532bd6b4u)(selected) != tone) roll_set_tone(selected,0,tone);
    c->roll.applied_tone=tone;
    if (!current(c) || model() != selected || ((fn1)0x532bd6d4u)(selected) ||
        ((fn1)0x532bd6b4u)(selected) != tone ||
        m10v_settings_controller_remote_aspect_read(&ratio) || ratio != roll.aspect) return 0;
    *tone_out = tone; *aspect_out = ratio; *film_out = roll.film;
    return 1;
}

static int roll_drain(ui_context *c) {
    uint32_t ticket;
    int32_t result;
    uint8_t marker[32];
    if (c->roll.pending_ticket) {
        if (c->roll.pending_outputs > 0) (void)roll_commit_result(c, c->roll.pending_outputs);
        return 1;
    }
    if (m10v_roll_capture_take_result(&c->roll.channel, &ticket, marker, &result)) {
        if (ticket != c->roll.ticket) return 1;
        if (result == 0) {
            if (m10v_roll_owner_finish(&c->roll.owner, ticket, marker, 0) == 1) c->roll.ticket = 0;
        } else {
            c->roll.pending_ticket = ticket;
            c->roll.pending_outputs = result;
            copy(c->roll.pending_marker, marker, sizeof(marker));
            if (result > 0) (void)roll_commit_result(c, result);
        }
        return 1;
    }
    return 0;
}

static void roll_tick(ui_context *c) {
    if (!c->roll.booted || !roll_idle(c)) return;
    if (c->roll.pending_ticket && c->roll.retry) { c->roll.retry--; return; }
    if (roll_drain(c)) {
        if (c->roll.pending_ticket) c->roll.retry = 9;
        return;
    }
    if (busy(c) || m10v_settings_controller_remote_busy()) return;
    if(c->roll.owner.loaded!=1||c->roll.owner.current.status!=M10V_ROLL_ACTIVE){
        if(roll_take_pending(c))roll_clear(c);
        return;
    }
    uint32_t tone, aspect, film;
    if (c->roll.ticket) {
        uint32_t selected = model();
        if (!selected || m10v_settings_controller_remote_aspect_read(&aspect)) return;
        m10v_library_state state;
        if (!((fn1)0x532bd6d4u)(selected) &&
            ((fn1)0x532bd6b4u)(selected) == c->roll.armed_tone &&
            aspect == c->roll.armed_aspect &&
            (c->roll.armed_tone==22u ||
             (m10v_camera_library_roll_preview(&state,c->roll.armed_tone) &&
              state.slots[m10v_tone_slot(c->roll.armed_tone)].film==c->roll.owner.current.film))) return;
        if (!roll_take_pending(c)) return;
    }
    if (!roll_apply(c, &tone, &aspect, &film)) return;
    uint8_t marker[32];
    uint32_t ticket = m10v_roll_owner_arm(&c->roll.owner, marker);
    if (!ticket) return;
    if (m10v_roll_capture_arm(&c->roll.channel, ticket, marker, tone, aspect, film)) {
        c->roll.armed_tone = tone; c->roll.armed_aspect = aspect;
        c->roll.ticket = ticket;
    } else (void)m10v_roll_owner_finish(&c->roll.owner, ticket, marker, -1);
}
