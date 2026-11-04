"""Check the exact halo primitives on the Cortex-A9 instruction set."""
import os
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn import arm_const as arm

from scripts.build_gr3_m10v_library import RENDER_FLAGS, link_object


ROOT = Path(__file__).resolve().parents[1]
BASE = 0x540b6000
Y, UV, OUT, SP, STOP = (0x55000000 + offset for offset in (0, 0x2000, 0x4000, 0x9000, 0xf000))


def energy(y, uv, x, gate):
    light = y[x]
    if uv is not None:
        red = light + ((359 * (uv[x | 1] - 128)) >> 8) - 24
        light = max(light, min(255, red))
    return max(0, light - gate) ** 2 * 8


class HalationNeonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clang = os.environ.get('M10V_LLVM_CLANG') or next(
            path for path in ('/opt/homebrew/opt/llvm/bin/clang', shutil.which('clang'))
            if path and Path(path).is_file())
        flags = [flag for flag in RENDER_FLAGS if not flag.startswith('-mfloat-abi=')]
        with tempfile.TemporaryDirectory() as folder:
            obj = Path(folder) / 'spatial.o'
            subprocess.run([clang, *flags, '-mfpu=neon', '-mfloat-abi=softfp',
                            '-c', str(ROOT / 'native/gr3/m10v_spatial_accel.c'),
                            '-o', str(obj)], check=True)
            cls.code, cls.symbols = link_object(obj.read_bytes(), BASE, prefix='m10v_spatial_')

    def setUp(self):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.cpu.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_A9)
        self.cpu.mem_map(BASE, 0x10000)
        self.cpu.mem_write(BASE, self.code)
        self.cpu.mem_map(Y, 0x10000)
        self.cpu.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xf00000)
        self.cpu.reg_write(arm.UC_ARM_REG_FPEXC, 0x40000000)
        self.rng = random.Random(80067)

    def call(self, symbol, *args):
        regs = (arm.UC_ARM_REG_R0, arm.UC_ARM_REG_R1, arm.UC_ARM_REG_R2, arm.UC_ARM_REG_R3)
        for reg, arg in zip(regs, args):
            self.cpu.reg_write(reg, arg)
        self.cpu.mem_write(SP, struct.pack(f'<{len(args)-4}I', *args[4:]))
        saved = [self.rng.getrandbits(64) for _ in range(8)]
        for i, value in enumerate(saved, 8):
            self.cpu.reg_write(getattr(arm, f'UC_ARM_REG_D{i}'), value)
        self.cpu.reg_write(arm.UC_ARM_REG_SP, SP)
        self.cpu.reg_write(arm.UC_ARM_REG_LR, STOP)
        self.cpu.emu_start(self.symbols[symbol], STOP, count=500_000)
        self.assertEqual(self.cpu.reg_read(arm.UC_ARM_REG_PC), STOP)
        self.assertEqual(self.cpu.reg_read(arm.UC_ARM_REG_SP), SP)
        self.assertEqual([self.cpu.reg_read(getattr(arm, f'UC_ARM_REG_D{i}'))
                          for i in range(8, 16)], saved)
        return self.cpu.reg_read(arm.UC_ARM_REG_R0)

    def test_cell_sum_and_peak_match_all_gates_and_partial_rows(self):
        stride = 27
        for width in (8, 16):
            for rows in (1, 7, 16):
                size = stride * rows
                for y, uv in ((self.rng.randbytes(size), self.rng.randbytes(size)),
                              (bytes([255]) * size, bytes([255]) * size),
                              (bytes([16]) * size, bytes([0]) * size)):
                    self.cpu.mem_write(Y + 1, y)
                    self.cpu.mem_write(UV + 1, uv)
                    for gate in range(176, 241, 8):
                        for chroma, peak in ((uv, 0), (None, OUT)):
                            want = [energy(y[at:], None if chroma is None else chroma[at:], x, gate)
                                    for at in range(0, size, stride) for x in range(width)]
                            got = self.call('m10v_spatial_halo_cell', Y + 1,
                                            UV + 1 if chroma is not None else 0,
                                            stride, width, rows, gate, peak)
                            self.assertEqual(got, sum(want))
                            if peak:
                                self.assertEqual(struct.unpack('<I', self.cpu.mem_read(peak, 4))[0],
                                                 max(want))

    def test_rolling_line_preserves_exact_taps_and_untouched_edges(self):
        for width in (2, 22, 24, 26, 32, 38, 6000):
            y = self.rng.randbytes(width)
            uv = self.rng.randbytes(width)
            self.cpu.mem_write(Y + 1, y)
            self.cpu.mem_write(UV + 1, uv)
            for distance in (1, 2, 4):
                for gate in (176, 200, 240):
                    guard = 0xabab
                    self.cpu.mem_write(OUT, bytes([0xab]) * (2 * width + 4))
                    end = self.call('m10v_spatial_halo_line', Y + 1, UV + 1, OUT + 2,
                                    width, gate, distance)
                    want_end = ((width - 8) // 8) * 8 if width >= 24 and distance != 1 else 0
                    self.assertEqual(end, want_end)
                    values = [energy(y, uv, x, gate) for x in range(width)]
                    want = [guard] + [
                        (values[x - distance] + 2 * values[x] + values[x + distance]) >> 2
                        if 8 <= x < end else guard for x in range(width)
                    ] + [guard]
                    self.assertEqual(struct.unpack(f'<{width+2}H', self.cpu.mem_read(OUT, 2 * width + 4)),
                                     tuple(want))
