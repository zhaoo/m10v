"""Characterize the pinned native AppMain timer callback route, without a device.

Only mutex/semaphore and AlarmTimer OS boundaries are mocked. Firmware getters,
start/cancel, timer-task enqueue, AppMain run, ring drain, event199 delivery and
expiry sweep execute original ARM. The tiny ARM callback is an observation sink
invoked by the native route; it can rearm through the native start function.
"""
import os
from pathlib import Path
import struct
import unittest

from scripts.analyze_gr3_settings import read_firmware
from scripts.build_gr3_menu_patches import assembly
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

BASE = 0x53000000
MODEL = 0x55063edc
QUEUE = 0x550645f0
LIST = 0x56000200
RECORD = 0x56000300
CALLBACK = 0x56000400
VTABLE = 0x56000500
ALARM = 0x56000600
RING = 0x56001000
CODE = 0x540c0000
STOP = 0x56010000
# Independent preimages, in addition to the whole-image SHA enforced by reader.
PREIMAGES = {
    0x5320b01c: '0dc0a0e118d82de9ac4504e3064545e3',
    0x5322b468: '0dc0a0e178d82de90040a0e104b04ce2',
    0x5322b1ec: '0dc0a0e118d82de904b04ce23c3090e5',
    0x5322b4b4: '402090e50dc0a0e178d82de904b04ce2',
    0x53207e88: '0dc0a0e100d82de904b04ce2bb0b00eb',
    0x53228b08: '0dc0a0e1cc3d0ee3f0df2de97c9705e3',
    0x53228ab4: 'b020d1e10dc0a0e118d82de9993100e3',
}


class TimerMachine:
    def __init__(self, firmware, callback_code):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        for address, size in ((BASE, 0x02000000), (0x55000000, 0x01000000), (0x56000000, 0x20000)):
            self.u.mem_map(address, size)
        self.u.mem_write(BASE, firmware)
        self.u.mem_write(CODE, callback_code)
        self.seen = set()
        self.locks = {}
        self.alarm_active = False
        self.callback_lock_state = []
        self.stop_at = None
        self.set(0x55063d80, 1)  # root already initialized
        self.set(0x55063e54, 1)  # AppModel queue already initialized
        self.set(0x550645ac, 1)  # AppTimerModel already initialized
        self.u.mem_write(0x55068228, b'\x01')  # AppMain startup already completed
        self.set(MODEL + 0x50, 1)
        self.set(MODEL + 0x3c, LIST)
        self.set(MODEL + 0x40, LIST + 4)
        self.set(LIST, RECORD)
        self.set(RECORD, ALARM)
        self.set(MODEL + 0x28, VTABLE + 0x20)
        self.set(VTABLE + 0x20, 0x5322b53c)  # actual model source callback thunk
        self.set(CALLBACK, VTABLE)
        self.set(CALLBACK + 12, RECORD)
        self.set(VTABLE + 8, CODE)
        self.set(QUEUE + 0x14, RING)
        self.u.mem_write(QUEUE + 0x18, struct.pack('<5H', 0, 64, 0, 0, 63))
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def set(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value))

    def word(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def hook(self, u, address, size, _):
        self.seen.add(address)
        if address == self.stop_at:
            u.emu_stop()
            return
        regs = [u.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        result = None
        if address == 0x536ae71c:  # Mutex::Lock
            self.locks[regs[0]] = self.locks.get(regs[0], 0) + 1
            result = 1
        elif address == 0x536ae870:  # Mutex::Unlock
            self.locks[regs[0]] = self.locks.get(regs[0], 0) - 1
            result = 1
        elif address in (0x536a9d1c, 0x536a9e8c, 0x536a9dd4):
            # Set, reset and wait. Wait supplies one externally completed alarm
            # or queue wake; no claim about RTOS scheduling or physical time.
            result = 1
        elif address == 0x536a848c:  # AlarmTimer::Start
            self.alarm_active = True
            result = 1
        elif address == 0x536a8544:  # AlarmTimer::Stop
            self.alarm_active = False
            result = 1
        elif address == 0x536a85f4:  # AlarmTimer::HasStarted
            result = int(self.alarm_active)
        elif address == CODE:
            self.callback_lock_state.append((self.locks.get(QUEUE + 0x38, 0), self.locks.get(QUEUE + 0x24, 0)))
        if result is not None:
            u.reg_write(UC_ARM_REG_R0, result)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def run(self, address, *args, stop=None):
        self.stop_at = stop
        self.u.reg_write(UC_ARM_REG_SP, 0x5600f000)
        self.u.reg_write(UC_ARM_REG_LR, STOP)
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            self.u.reg_write(reg, value)
        self.u.emu_start(address, STOP, count=100000)
        expected = stop if stop is not None else STOP
        if self.u.reg_read(UC_ARM_REG_PC) != expected:
            raise AssertionError(f'ARM did not reach boundary {expected:#x}')
        return self.u.reg_read(UC_ARM_REG_R0)

    def start(self):
        return self.run(0x5322b468, MODEL, 100, CALLBACK)

    def queue_timer_wakeup(self):
        # Execute the timer task, stop after its first native enqueue, before
        # it waits again. Its event source is the permanent model subobject.
        self.run(0x5322b17c, MODEL, stop=0x5322b1d4)

    def drain_on_appmain(self):
        # Execute real AppMain run, stop after the ring is drained, before
        # unrelated active-controller presentation/rendering begins.
        self.run(0x53207e88, stop=0x53228bf0)


class CompanionTimerArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(os.environ.get('M10V_GR3_ORIGINAL_RTOS', '/tmp/m10v-sd-research/rtos.bin'))
        if not path.exists():
            raise unittest.SkipTest('official GR III 2.10 decoded RTOS required')
        cls.firmware = read_firmware(path)
        for address, expected in PREIMAGES.items():
            if cls.firmware[address - BASE:address - BASE + 16].hex() != expected:
                raise AssertionError(f'preimage differs at {address:#x}')
        # Observer records the timer id and record state at callback entry.
        # The optional rearm is a real BL into native start, not a Python call.
        cls.callback_code = assembly(
            'push {r4,lr};mov r4,r0;str r1,[r4,#4];'
            'ldr r3,[r4,#12];ldr r2,[r3,#4];str r2,[r4,#16];'
            'ldr r2,[r3,#8];str r2,[r4,#20];'
            'ldr r2,[r4,#8];add r2,r2,#1;str r2,[r4,#8];'
            'ldr r2,[r4,#24];cmp r2,#0;beq done;'
            f'movw r0,#{MODEL & 65535};movt r0,#{MODEL >> 16};'
            'mov r1,#100;mov r2,r4;bl 0x5322b468;str r0,[r4,#28];'
            'done:;pop {r4,pc}', CODE)

    def machine(self):
        return TimerMachine(self.firmware, self.callback_code)

    def test_expiry_runs_callback_through_appmain_with_owner_lock(self):
        m = self.machine()
        timer_id = m.start()
        self.assertEqual(timer_id, 2)
        m.alarm_active = False  # OS reports one-shot expiry
        m.queue_timer_wakeup()
        self.assertEqual(m.word(RING) & 65535, 0x199)
        self.assertEqual(m.word(RING + 8), MODEL + 0x28)
        self.assertEqual(m.word(CALLBACK + 8), 0)
        m.drain_on_appmain()
        self.assertEqual(m.word(CALLBACK + 8), 1)
        self.assertEqual(m.word(CALLBACK + 4), timer_id)
        self.assertEqual(m.callback_lock_state, [(1, 0)])
        self.assertTrue({0x53207e88, 0x53228b08, 0x53228ab4, 0x5322b4b4, CODE}.issubset(m.seen))
        self.assertNotIn(0x5316d5dc, m.seen)

    def test_expiry_clears_record_before_callback_rearms_it(self):
        m = self.machine()
        m.set(CALLBACK + 24, 1)
        first = m.start()
        m.alarm_active = False
        m.queue_timer_wakeup()
        m.drain_on_appmain()
        self.assertEqual(m.word(CALLBACK + 16), 0)
        self.assertEqual(m.word(CALLBACK + 20), 0)
        self.assertEqual(m.word(CALLBACK + 28), first + 1)
        self.assertEqual(m.word(RECORD + 4), first + 1)
        self.assertEqual(m.word(RECORD + 8), CALLBACK)
        self.assertTrue(m.alarm_active)

    def test_cancel_clears_pointer_and_queued_sweep_cannot_call_dead_object(self):
        m = self.machine()
        timer_id = m.start()
        m.alarm_active = False
        m.queue_timer_wakeup()  # already queued when owner revokes callback
        self.assertEqual(m.run(0x5322b1ec, MODEL, timer_id), 1)
        self.assertEqual(m.word(RECORD + 4), 0)
        self.assertEqual(m.word(RECORD + 8), 0)
        m.set(CALLBACK, 0)  # represent invalidated/freed callback storage
        m.drain_on_appmain()
        self.assertEqual(m.word(CALLBACK + 8), 0)
        self.assertNotIn(CODE, m.seen)
        self.assertIn(0x5322b4b4, m.seen)

    def test_unexpired_alarm_wakeup_does_not_invoke_callback(self):
        m = self.machine()
        timer_id = m.start()
        m.queue_timer_wakeup()
        m.drain_on_appmain()
        self.assertEqual(m.word(CALLBACK + 8), 0)
        self.assertEqual(m.word(RECORD + 4), timer_id)
        self.assertEqual(m.word(RECORD + 8), CALLBACK)


if __name__ == '__main__':
    unittest.main()
