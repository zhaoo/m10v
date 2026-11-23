"""Compile the actual native Live owner and check configuration vs readiness."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
#include "m10v_live_camera.h"
typedef void (*cache_fn)(void *,uint32_t);
typedef uint32_t (*fn1)(uint32_t);
typedef struct {
 m10v_live_camera live;
 uint32_t live_alloc_tried;
 struct {uint32_t epoch;} wire;
 struct {struct {uint8_t boot_id[16];} metadata;} services;
} ui_context;
static ui_context *roll_context(void){return (ui_context*)0x56000000u;}
static int ram(uint32_t a,uint32_t n){return a>=0x55000000u&&a<=0x60000000u-n;}
static void zero(void*p,uint32_t n){for(uint32_t i=0;i<n;i++)((uint8_t*)p)[i]=0;}
static void copy(void*d,const void*s,uint32_t n){for(uint32_t i=0;i<n;i++)((uint8_t*)d)[i]=((const uint8_t*)s)[i];}
#define M10V_ERROR_BRIDGE_UNAVAILABLE 10
#include "m10v_live_device_camera.inc"
'''


class LiveModeArmTests(unittest.TestCase):
    def test_configured_mode_survives_stale_recorder_and_off_is_always_allowed(self):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
        from unicorn.arm_const import (
            UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR, UC_ARM_REG_SP,
            UC_ARM_REG_PC,
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, obj, executable = [directory / name for name in ('fixture.c', 'fixture.o', 'mode.elf')]
            source.write_text(FIXTURE)
            subprocess.run(['/opt/homebrew/opt/llvm/bin/clang', '--target=armv7-none-eabi',
                            '-mcpu=cortex-a9', '-marm', '-mfloat-abi=soft', '-Os',
                            '-std=c11', '-ffreestanding', '-fno-builtin', '-ffunction-sections',
                            '-fdata-sections', '-I', str(ROOT / 'native/gr3'), '-c', str(source),
                            '-o', str(obj)], check=True, capture_output=True)
            subprocess.run(['/opt/homebrew/bin/ld.lld', '-m', 'armelf_linux_eabi', '-Ttext=0x10000',
                            '--entry=m10v_live_device_mode', str(obj), '-o', str(executable)],
                           check=True, capture_output=True)
            binary = executable.read_bytes()
            output = subprocess.check_output(['/opt/homebrew/opt/llvm/bin/llvm-nm', executable], text=True)
            symbols = {line.split()[2]: int(line.split()[0], 16) for line in output.splitlines()
                       if len(line.split()) == 3}
        self.assertIn('m10v_live_device_configured_mode', symbols)
        emulator = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        emulator.mem_map(0x10000, 0x100000)
        emulator.mem_map(0x53000000, 0x100000)
        emulator.mem_map(0x53800000, 0x100000)
        emulator.mem_map(0x56000000, 0x100000)
        offset = struct.unpack_from('<I', binary, 28)[0]
        size, count = struct.unpack_from('<HH', binary, 42)
        for index in range(count):
            segment = struct.unpack_from('<8I', binary, offset + index * size)
            if segment[0] == 1:
                emulator.mem_write(segment[2], binary[segment[1]:segment[1] + segment[4]])
        writes = []

        def word(address, value):
            emulator.mem_write(address, struct.pack('<I', value))

        def hook(machine, address, size, unused):
            if address == 0x53050b7c:
                destination = machine.reg_read(UC_ARM_REG_R0)
                machine.mem_write(destination, struct.pack('<II', 0, 10000))
                machine.reg_write(UC_ARM_REG_R0, 0)
                machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
            elif address == 0x5383c870:
                writes.append((machine.reg_read(UC_ARM_REG_R0), machine.reg_read(UC_ARM_REG_R1)))
                machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))

        emulator.hook_add(UC_HOOK_CODE, hook)

        def call(name, value=0):
            emulator.reg_write(UC_ARM_REG_R0, value)
            emulator.reg_write(UC_ARM_REG_SP, 0x80000)
            emulator.reg_write(UC_ARM_REG_LR, 0x90000)
            emulator.emu_start(symbols[name], 0x90000, count=100000)
            return struct.unpack('<i', struct.pack('<I', emulator.reg_read(UC_ARM_REG_R0)))[0]

        self.assertEqual(call('m10v_live_device_configured_mode'), 0)
        self.assertEqual(call('m10v_live_device_mode'), -2)
        self.assertEqual(call('m10v_live_device_set_mode', 0), 1)
        self.assertEqual(call('m10v_live_device_set_mode', 1), 0)
        arena = 0x56010000
        word(0x56000000, arena)
        word(arena + 16, 9)  # Mode 1 with sequence bits.
        self.assertEqual(call('m10v_live_device_configured_mode'), 1)
        self.assertEqual(call('m10v_live_device_mode'), -3)
        self.assertEqual(call('m10v_live_device_set_mode', 2), 0)
        self.assertEqual(call('m10v_live_device_set_mode', 0), 1)
        self.assertEqual(call('m10v_live_device_configured_mode'), 0)
        word(0x56000000 + 36, 9000)  # consumer_tick in native camera.
        self.assertEqual(call('m10v_live_device_set_mode', 2), 1)
        self.assertEqual(call('m10v_live_device_configured_mode'), 2)
        self.assertEqual(call('m10v_live_device_mode'), 2)
        self.assertEqual(call('m10v_live_device_set_mode', 3), 0)
        self.assertEqual(len(writes), 2)


if __name__ == '__main__':
    unittest.main()
