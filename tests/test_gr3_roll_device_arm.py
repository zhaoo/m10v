"""Execute exported GR III roll admission and the original static SD getter."""
import hashlib
import json
import os
from pathlib import Path
import struct
import unittest
import zlib

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1,
    UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP,
)

from tests.test_gr3_companion_timer_arm import TimerMachine


OWNER = 0x55860000
STATIC_SD_MANAGER = 0x553497BC
STATIC_SD_FILESYSTEM = 0x55349800
FAT_VOLUMES = 0x55349900
MASTER_VOLUMES = 0x55349A00
MASTER_BACKENDS = 0x55349A80
MASTER_LOCKS = 0x55349AC0
FAT_BACKEND = 0x5534A000
MASTER_LOCK = 0x5534A080
PROCESS = 0x55810000
SCRATCH = 0x56002000


class RollDevice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = os.environ.get("M10V_ROLL_DEVICE_CANDIDATE")
        stock = os.environ.get("M10V_GR3_ORIGINAL_RTOS")
        if not folder or not stock:
            raise unittest.SkipTest("verified roll candidate and official stock RTOS required")
        folder = Path(folder)
        cls.manifest = json.loads((folder / "M10V-runtime-manifest.json").read_text())
        cls.symbols = cls.manifest["symbols"]
        cls.image = (folder / "M10V-runtime-arm.bin").read_bytes()
        cls.stock = Path(stock).read_bytes()
        assert hashlib.sha256(cls.stock).hexdigest() == (
            "8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67")

    def machine(self):
        m = TimerMachine(self.stock, b"")
        m.instruction_budget = 1000000
        m.u.mem_write(self.manifest["base"], self.image)
        m.set(0x55063910, 1)
        m.set(0x55063988, OWNER)
        return m

    def card_machine(self, files, absent=-15, start_timer=True, original_stat=False, open_error=12,
                     alternate=False, model_address=0x55820000):
        m = self.machine()
        m.set(STATIC_SD_MANAGER - 4, 1)  # Initialized flag read by original getter.
        m.set(STATIC_SD_MANAGER + 20, STATIC_SD_FILESYSTEM)
        m.set(STATIC_SD_FILESYSTEM, 0x53D252D0)
        m.set(STATIC_SD_FILESYSTEM + 8, MASTER_VOLUMES)
        m.set(STATIC_SD_FILESYSTEM + 24, MASTER_BACKENDS)
        m.set(STATIC_SD_FILESYSTEM + 28, MASTER_LOCKS)
        m.set(MASTER_BACKENDS + 8, FAT_BACKEND)
        m.set(MASTER_LOCKS + 8, MASTER_LOCK)
        m.set(FAT_BACKEND, 0x53D24F34 if alternate else 0x53D2201C)
        m.set(0x55349B1C, FAT_VOLUMES)
        if alternate:
            m.set(0x55376058, 0x5534B900)  # Alternate native filesystem initialized.
        m.u.mem_write(0x5537A750, b"\\")
        m.set(0x55063DCC, 1)  # Image control model initialized.
        m.set(0x55064398, 1)  # System model initialized.
        m.set(0x55063ECC, 1)  # Shoot state model initialized.
        m.u.mem_write(0x55067958 + 0x880, b"\x03")
        model = model_address
        opened = {}
        raw_allocation = 0x55400000

        def service(u, address, _size, _context):
            nonlocal raw_allocation
            args = [u.reg_read(reg) for reg in (
                UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
            r0, r1, r2, r3 = args
            if address == 0x536AF2A8:
                result = PROCESS
            elif address in (0x5383C834, 0x5383C870):
                result = 0
            elif address in (0x5320AD88, 0x5320B01C):
                result = PROCESS
            elif address == 0x5322B468:
                result = 42
            elif address in (0x5322B1EC, 0x5320B97C, 0x53050B7C):
                result = 0
            elif address == 0x5320BA9C:
                result = model
            elif address in (0x532BD61C, 0x532C26C0):
                m.set(r0 + (4 if address == 0x532BD61C else 8), r1)
                result = 0
            elif address in (0x532BD6D4, 0x532BD6B4):
                result = m.word(r0 + (4 if address == 0x532BD6D4 else 8))
            elif address == self.symbols["m10v_settings_controller_remote_busy"]:
                result = 0
            elif address == self.symbols["m10v_settings_controller_remote_aspect_read"]:
                m.set(r0, 0)
                result = 0
            elif address == 0x535964C4:
                # The master can have other driver types and a different table order.
                result = 0 if r0 == FAT_VOLUMES else 2
            elif address == 0x5389FAF4:
                if original_stat:
                    return
                self.assertEqual(r0, 0)
                self.assertEqual(m.locks.get(MASTER_LOCK), 1)
                self.assertEqual(m.locks.get(FAT_BACKEND + 0x14), 1)
                name = bytes(u.mem_read(r1, 12)).split(b"\0", 1)[0]
                result = (absent if b"C:" + name not in files else 0) & 0xFFFFFFFF
            elif original_stat and address == 0x5358BA30:
                result = raw_allocation
                raw_allocation += 0x1000
            elif original_stat and address == 0x5358BA68:
                result = 0
            elif original_stat and address == 0x538A8794:
                m.set(r0, 0x5534B800)
                result = 0
            elif original_stat and address in (0x538A8570,0x538A85A4,0x538A8654,0x538A8688):
                result = 0
            elif original_stat and address == 0x538A5B94:
                result = 0
            elif original_stat and address == 0x538A5580:
                result = -2 & 0xFFFFFFFF  # Stock FAT directory lookup did not find the filename.
            elif alternate and address == 0x5358E924:
                result = 1  # The alternate native volume is already mounted.
            elif alternate and address == 0x5388DD18:
                result = 0x5534B800  # Native task-local filesystem context.
            elif alternate and address == 0x53888174:
                result = 0  # Native volume number acquired.
            elif alternate and address == 0x538882A8:
                result = 1  # Native volume lock released.
            elif alternate and address == 0x53888EB4:
                self.assertEqual(m.locks.get(MASTER_LOCK), 1)
                self.assertEqual(bytes(u.mem_read(r0,16)).split(b"\0",1)[0][:3], b"C:\\")
                m.set(0x5534B804, absent)
                result = 0  # Directory lookup reached EOF with task-local status.
            elif address == 0x53593E90:
                self.assertEqual(r0, STATIC_SD_FILESYSTEM)
                name = bytes(u.mem_read(r1, 16)).split(b"\0", 1)[0]
                err = m.word(u.reg_read(UC_ARM_REG_SP))
                if r2 == 1 and name not in files:
                    m.set(err, open_error)
                    result = 0
                else:
                    if r2 == 0:
                        files[name] = b""
                    opened[101] = [name, 0]
                    m.set(r3, 101)
                    m.set(err, 0)
                    result = 1
            elif address in (0x535948C4, 0x53592A60):
                name, cursor = opened[r1]
                m.set(r2, len(files[name]) if address == 0x535948C4 else cursor)
                m.set(r3, 0)
                result = 1
            elif address == 0x5359279C:
                name, cursor = opened[r1]
                u.mem_write(r2, files[name][cursor:cursor+r3])
                opened[r1][1] += r3
                result = 1
            elif address == 0x53592888:
                name, cursor = opened[r1]
                self.assertEqual(cursor, 0)
                files[name] = bytes(u.mem_read(r2, r3))
                opened[r1][1] += r3
                result = 1
            elif address == 0x53593CEC:
                del opened[r1]
                m.set(r2, 0)
                result = 1
            else:
                return
            u.reg_write(UC_ARM_REG_R0, result)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

        m.u.hook_add(UC_HOOK_CODE, service)
        m.run(self.symbols["m10v_companion_ui_init"], OWNER)
        if start_timer:
            m.run(self.symbols["m10v_companion_ui_start"], OWNER)
        return m

    def tick(self, m):
        m.run(self.symbols["m10v_companion_ui_timer"], PROCESS, 42, 0)

    def prepare(self, m):
        m.run(self.symbols["m10v_roll_device_prepare"])

    def test_active_roll_blocks_menu_and_adj_until_it_is_paused(self):
        files = {}
        m = self.card_machine(files, start_timer=False, model_address=0x55068200)
        self.prepare(m)
        self.assertEqual(m.run(self.symbols["m10v_roll_device_open"], 326, 0, 24), 1)
        self.assertEqual(m.run(self.symbols["m10v_roll_device_locked"]), 1)
        original = {self.manifest["base"] + 0xa0: 0x75,
                    self.manifest["base"] + 0xe0: 0x76}
        called = []

        def native(u, address, _size, _context):
            if address in original:
                called.append(address)
                u.reg_write(UC_ARM_REG_R0, original[address])
                u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

        m.u.hook_add(UC_HOOK_CODE, native)
        for symbol, args in (
                ("m10v_menu_focus", (SCRATCH, 0)),
                ("m10v_menu_confirm", (SCRATCH,)),
                ("m10v_tone_menu_adj_select", (SCRATCH, 0))):
            self.assertEqual(m.run(self.symbols[symbol], *args), 0)
        self.assertEqual(called, [])
        self.assertEqual(m.run(self.symbols["m10v_roll_device_change"], 2), 1)
        self.assertEqual(m.run(self.symbols["m10v_roll_device_locked"]), 0)
        self.assertEqual(m.run(self.symbols["m10v_menu_focus"], SCRATCH, 0), 0x75)
        self.assertEqual(m.run(self.symbols["m10v_tone_menu_adj_select"], SCRATCH, 0), 0x76)
        self.assertEqual(called, list(original))

    def test_static_sd_manager_allows_native_empty_journal_and_new_roll(self):
        files = {}
        m = self.card_machine(files, start_timer=False)
        self.prepare(m)
        self.assertTrue(0x535847D8 in m.seen, "native journal did not call the stock SD manager")
        self.assertTrue(0x5389FAF4 in m.seen, "native journal did not establish the files' absence")
        self.assertEqual(m.run(self.symbols["m10v_roll_device_open"], 326, 0, 24), 1)
        self.assertEqual(len(files[b"C:\\M10VRL1.BIN"]), 48)
        self.assertEqual(m.run(self.symbols["m10v_roll_device_snapshot"], SCRATCH), 1)
        self.assertEqual(m.word(SCRATCH + 24), 326)
        self.assertEqual(files[b"C:\\M10VRL1.BIN"], bytes(m.u.mem_read(SCRATCH, 48)))
        self.assertEqual(m.locks[MASTER_LOCK], 0)
        self.assertEqual(m.locks[FAT_BACKEND + 0x14], 0)

    def test_dormant_appmain_timer_does_not_probe_card(self):
        m = self.card_machine({})
        self.tick(m)
        self.tick(m)
        self.assertTrue(0x535847D8 not in m.seen, "dormant roll must not probe SD")
        self.prepare(m)
        self.assertEqual(m.run(self.symbols["m10v_roll_device_snapshot"], SCRATCH), 0)

    def test_native_absence_through_original_fat_stat_chain(self):
        m = self.card_machine({}, original_stat=True, open_error=2)
        self.prepare(m)
        self.assertTrue(0x5389FAF4 in m.seen)
        self.assertTrue(0x538A6470 in m.seen)
        self.assertTrue(0x538A5580 in m.seen)
        self.assertEqual(m.run(self.symbols["m10v_roll_device_snapshot"], SCRATCH), 0)

    def test_alternate_filesystem_missing_and_io_failure_keep_distinct_native_status(self):
        for raw_error, expected in [(5,0), (9,102)]:
            with self.subTest(raw_error=raw_error):
                files = {}
                m = self.card_machine(files, absent=raw_error, alternate=True, open_error=2)
                self.prepare(m)
                self.assertTrue(0x5358ED2C in m.seen)
                self.assertTrue(0x53886634 in m.seen)
                self.assertTrue(0x53888EB4 in m.seen)
                self.assertEqual(m.run(self.symbols["m10v_roll_device_snapshot"],SCRATCH),
                                 (-expected) & 0xffffffff)
                self.assertEqual(files,{})
                self.assertEqual(m.locks[MASTER_LOCK],0)

    def test_suspect_fat_error_and_corrupt_journal_never_start_blank(self):
        corrupt = {b"C:\\M10VRL1.BIN": bytes(48)}
        for files, absent in [({}, -7), (corrupt.copy(), -15)]:
            with self.subTest(absent=absent):
                before = files.copy()
                m = self.card_machine(files, absent=absent)
                self.prepare(m)
                stage = 112 if absent == -7 else 35
                self.assertEqual(m.run(self.symbols["m10v_roll_device_snapshot"], SCRATCH), (-stage) & 0xffffffff)
                self.assertEqual(m.run(self.symbols["m10v_roll_device_open"], 326, 0, 24), 0)
                self.assertEqual(files, before)

    def test_store_receipt_and_shutdown_recover_without_any_mailbox_request(self):
        files = {}
        m = self.card_machine(files)
        self.prepare(m)
        negative = 0x10016
        self.assertEqual(m.run(self.symbols["m10v_roll_device_open"], negative, 0, 24), 1)
        channel = m.run(self.symbols["m10v_roll_device_capture_channel"])

        def save():
            self.tick(m)
            # A completed Store job published its per-exposure outcome.
            si, generation = 0x55830000, 41
            m.u.mem_write(0x5600F000, struct.pack("<II", 0, negative))
            self.assertEqual(m.run(self.symbols["m10v_roll_capture_reserve"], channel, si, generation, 22), 1)
            self.assertEqual(m.run(self.symbols["m10v_roll_capture_complete"], channel, si, generation, 1), 1)

        save()
        self.tick(m)
        self.assertEqual(m.run(self.symbols["m10v_roll_device_snapshot"], SCRATCH), 1)
        self.assertEqual(m.word(SCRATCH + 36), 1)
        roll_id = bytes(m.u.mem_read(SCRATCH + 8, 16))
        save()
        m.run(self.symbols["m10v_companion_ui_stop"], OWNER)

        restarted = self.card_machine(files)
        self.prepare(restarted)
        self.assertEqual(restarted.run(self.symbols["m10v_roll_device_snapshot"], SCRATCH), 1)
        self.assertEqual(restarted.word(SCRATCH + 36), 2)
        self.assertEqual(bytes(restarted.u.mem_read(SCRATCH + 8, 16)), roll_id)

    def test_native_store_uses_frozen_descriptor_when_r4_is_completion_holder(self):
        files = {}
        m = self.card_machine(files)
        self.prepare(m)
        self.assertEqual(m.run(self.symbols["m10v_roll_device_open"],0x10016,0,24),1)
        self.tick(m)
        channel = m.run(self.symbols["m10v_roll_device_capture_channel"])
        si, group = 0x55830000, 0x55840000
        lease, manager = si+0x74270, 0x55450000
        request, holder, setter, entry, tag = 0x55844000, 0x55844100, 0x55844200, 0x55844300, 0x55844400
        m.set(0x55345328,manager)
        m.set(manager+0x20,0x74280)
        m.set(manager+0x88,si)
        m.set(lease+4,17)

        def native_metadata(u,address,_size,_context):
            args = [u.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)]
            if address==0x535D02F4:
                u.mem_write(m.word(args[0]+16),bytes(32))
                result=0
            elif address==0x535D034C:
                u.mem_write(m.word(args[0]+16),bytes(u.mem_read(args[1],args[2])))
                result=0
            else:
                return
            u.reg_write(UC_ARM_REG_R0,result)
            u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))

        m.u.hook_add(UC_HOOK_CODE,native_metadata)
        m.u.mem_write(0x5600F000,struct.pack("<II",0,0x10016))
        self.assertEqual(m.run(self.symbols["m10v_roll_capture_reserve"],channel,si,17,22),1)
        m.set(request+8,group)
        m.set(request+12,0x800001)
        m.u.mem_write(group,b"\x01")  # JPEG in stream zero.
        descriptor=group+0x14
        writer=descriptor+0x45C
        m.set(descriptor+0x134,si+4)
        m.run(self.symbols["m10v_roll_camera_group_start"],request,holder)
        self.assertEqual(m.word(channel+16),0)
        m.set(descriptor+0x134,si)
        m.set(writer+4,descriptor+0x478)
        m.set(writer+8,descriptor+0x3F0)
        m.set(writer+0x10,descriptor)
        # Execute the original register assignment immediately preceding the enqueue.
        # 5350c3c0 and 5350c590 both replace r4 with fp-0x38.
        self.assertEqual(self.stock[0x50C590:0x50C594],bytes.fromhex("38404be2"))
        m.run(self.symbols["m10v_roll_camera_group_start"],request,holder)
        m.run(self.symbols["m10v_roll_camera_writer_start"],writer)
        m.set(setter+24,si)
        m.set(entry+4,(7<<16)|0xC7F2)
        m.set(entry+8,32)
        m.set(entry+16,tag)
        m.run(self.symbols["m10v_roll_camera_write_tag"],setter,entry)
        m.run(self.symbols["m10v_roll_camera_writer_phases"],descriptor+0x478)
        m.run(self.symbols["m10v_roll_camera_output"],writer,descriptor,group,1)
        m.run(self.symbols["m10v_roll_camera_group_finish"],group,0x800001)
        # Closing immediately after a native completion must drain the receipt,
        # even when the periodic AppMain callback has not run yet.
        self.assertEqual(m.run(self.symbols["m10v_roll_device_change"],3),1)
        self.assertEqual(m.run(self.symbols["m10v_roll_device_snapshot"],SCRATCH),1)
        self.assertEqual(m.word(SCRATCH+36),1)

    def test_stock_fat_distinguishes_missing_file_from_lookup_io_failure(self):
        m = self.machine()
        raw_error = -2

        def filesystem_subcalls(u, address, _size, _context):
            if address in (0x538A8654, 0x538A8688):
                result = 0  # The FAT volume opened and released normally.
            elif address == 0x538A5B94:
                result = 0  # The record name passed stock directory parsing.
            elif address == 0x538A5580:
                result = raw_error  # The media lookup is the only simulated error.
            else:
                return
            u.reg_write(UC_ARM_REG_R0, result & 0xFFFFFFFF)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

        m.u.hook_add(UC_HOOK_CODE, filesystem_subcalls)
        m.u.mem_write(0x5600F000, struct.pack("<III", 2, 7, SCRATCH + 64))
        self.assertEqual(m.run(0x538A6470, 0, SCRATCH, 0, 1), (-15) & 0xFFFFFFFF)
        raw_error = -7
        self.assertEqual(m.run(0x538A6470, 0, SCRATCH, 0, 1), (-7) & 0xFFFFFFFF)

    def test_original_master_open_retains_real_error_mapping(self):
        m = self.machine()
        fs = STATIC_SD_FILESYSTEM
        master_entries, fat_entries = 0x5534A100, 0x5534A140
        m.set(fs, 0x53D252D0)
        m.set(fs + 8, MASTER_VOLUMES)
        m.set(fs + 24, MASTER_BACKENDS)
        m.set(fs + 28, MASTER_LOCKS)
        m.set(MASTER_VOLUMES + 20, master_entries)
        m.set(MASTER_VOLUMES + 32, 1)
        m.set(master_entries + 4, ord("C"))
        m.set(MASTER_BACKENDS, FAT_BACKEND)
        m.set(MASTER_LOCKS, MASTER_LOCK)
        m.set(FAT_BACKEND, 0x53D2201C)
        m.set(0x55349B1C, FAT_VOLUMES)
        m.set(FAT_VOLUMES + 20, fat_entries)
        m.set(FAT_VOLUMES + 32, 1)
        m.set(fat_entries + 4, ord("C"))
        m.u.mem_write(SCRATCH, b"C:\\M10VRL1.BIN\0")
        raw_result = -2
        observed = []

        def media(u, address, _size, _context):
            if address == 0x536B93D0:
                result = 0  # Stock assertion/logging leaf.
            elif address == 0x5389E36C:
                args = [u.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)]
                observed.append((args[0], bytes(u.mem_read(args[1], 14)).split(b"\0",1)[0], args[2]))
                self.assertEqual(m.locks.get(MASTER_LOCK), 1)
                self.assertEqual(m.locks.get(FAT_BACKEND + 0x14), 1)
                result = raw_result
            else:
                return
            u.reg_write(UC_ARM_REG_R0, result & 0xFFFFFFFF)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

        m.u.hook_add(UC_HOOK_CODE, media)
        for raw_result, expected in [(-2,12), (-4,2), (-10,5), (-16,7)]:
            m.set(SCRATCH + 32, 0)
            m.set(SCRATCH + 36, 0)
            m.set(0x5600F000, SCRATCH + 36)
            self.assertEqual(m.run(0x53593E90, fs, SCRATCH, 1, SCRATCH + 32), 0)
            self.assertEqual(m.word(SCRATCH + 32), 0)
            self.assertEqual(m.word(SCRATCH + 36), expected)
        self.assertEqual(observed, [(0, b"\\M10VRL1.BIN",1)] * 4)

    def test_stock_alternate_directory_eof_has_unique_missing_code(self):
        m = self.machine()
        directory, volume, task = 0x55420000, 0x55421000, 0x55422000
        m.set(directory,volume)
        m.set(volume+0x60,1)
        leaf_error = 0

        def media(u,address,_size,_context):
            if address==0x5388DD18:
                result=task
            elif address==0x53888500:
                m.set(task+4,leaf_error)
                result=0  # The underlying directory cluster chain ended.
            else:
                return
            u.reg_write(UC_ARM_REG_R0,result)
            u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))

        m.u.hook_add(UC_HOOK_CODE,media)
        for leaf_error,expected in [(0,5),(9,9)]:
            m.set(directory+0x10,0)
            m.set(task+4,0)
            self.assertEqual(m.run(0x53888B78,directory,0,0,0),0)
            self.assertEqual(m.word(task+4),expected)
            self.assertEqual(m.run(0x5358D970,0,expected),2)

    def test_new_film_with_ten_slots_changes_only_the_render_snapshot(self):
        m = self.machine()
        state = bytearray.fromhex(self.manifest["initial_state_hex"])
        for i, film in enumerate((33, 34, 35, 36, 37, 56, 58, 62, 66, 69)):
            struct.pack_into("<HBBBBBB", state, 12 + 8 * i, film, 0, 0, 0, 3, 5, 6)
            state[96 + 8*i:104 + 8*i] = bytes(8)
        struct.pack_into("<I", state, 180, zlib.crc32(state[:180]))
        m.u.mem_write(SCRATCH, bytes(state))
        m.run(self.symbols["m10v_camera_library_preview_init"], OWNER)
        self.assertEqual(m.run(self.symbols["m10v_camera_library_mutation_begin"]), 1)
        m.run(self.symbols["m10v_camera_library_mutation_end"], SCRATCH)
        self.assertEqual(m.run(self.symbols["m10v_camera_library_roll_prepare"], 326, 1), 25)
        self.assertEqual(m.run(self.symbols["m10v_camera_library_preview"], SCRATCH), 1)
        self.assertEqual(bytes(m.u.mem_read(SCRATCH, 184)), bytes(state))
        self.assertEqual(m.run(self.symbols["m10v_camera_library_roll_preview"], SCRATCH, 25), 1)
        effective = bytes(m.u.mem_read(SCRATCH, 184))
        self.assertEqual(struct.unpack_from("<H", effective, 12)[0], 326)
        self.assertEqual(effective[20:96], bytes(state[20:96]))
        self.assertEqual(zlib.crc32(effective[:180]), m.word(SCRATCH + 180))
        self.assertEqual(m.run(self.symbols["m10v_camera_library_roll_prepare"], 0, 1), 1)
        self.assertEqual(m.run(self.symbols["m10v_camera_library_roll_preview"], SCRATCH, 25), 1)
        self.assertEqual(bytes(m.u.mem_read(SCRATCH, 184)), bytes(state))
