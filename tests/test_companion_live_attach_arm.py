"""Execute the production ARM Live storage setup and its failure/retry paths."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LiveAttachArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        objects = []
        fixture = directory / 'trace_fixture.c'
        fixture.write_text(r'''
#include "linux_target.h"
/* A fixture-only trap exposes trace arguments to the ARM emulator. */
void m10v_linux_trace(const char *event,const uint32_t *values,unsigned count){
 register unsigned r0 __asm__("r0")=(unsigned)event,r1 __asm__("r1")=(unsigned)values,
  r2 __asm__("r2")=count,r7 __asm__("r7")=0xfe00;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r7):"memory","cc");
}
static int read_probe(void*ctx,uint32_t address,void*out,uint32_t bytes){
 (void)ctx;for(uint32_t i=0;i<bytes;i++)((uint8_t*)out)[i]=((const uint8_t*)address)[i];return 1;
}
extern void m10v_linux_live_sample(m10v_linux_target*,uint64_t);
void sample_probe(uint32_t now){
 static m10v_linux_target target;
 target.epoch=0x56020000;target.io.read=read_probe;m10v_linux_live_sample(&target,now);
}
''')
        sources = [ROOT / 'native/companion' / (name + '.c')
                   for name in ('linux_live', 'live_clip', 'runtime', 'auth')]
        sources.append(fixture)
        for source in sources:
            output = directory / (source.stem + '.o')
            subprocess.run(['/opt/homebrew/opt/llvm/bin/clang', '--target=armv7-none-eabi',
                            '-mcpu=cortex-a9', '-marm', '-mfloat-abi=soft', '-Os',
                            '-std=c11', '-ffreestanding', '-fno-builtin', '-ffunction-sections',
                            '-fdata-sections', '-DM10V_COMPANION_LIVE_SOURCE=1', '-I', str(ROOT / 'native/companion'), '-Wall', '-Wextra', '-Werror', '-c',
                            str(source), '-o', str(output)],
                           check=True, capture_output=True)
            objects.append(str(output))
        executable = directory / 'attach.elf'
        subprocess.run(['/opt/homebrew/bin/ld.lld', '-m', 'armelf_linux_eabi',
                        '-Ttext=0x10000', '--gc-sections', '--entry=m10v_linux_live_attach', '--undefined=sample_probe',
                        *objects, '-o', str(executable)], check=True, capture_output=True)
        cls.binary = executable.read_bytes()
        output = subprocess.check_output(['/opt/homebrew/opt/llvm/bin/llvm-nm', executable], text=True)
        cls.sample = int(next(line.split()[0] for line in output.splitlines()
                             if line.endswith(' sample_probe')), 16)
        cls.entry = int(next(line.split()[0] for line in output.splitlines()
                            if line.endswith(' m10v_linux_live_attach')), 16)

    def test_unrestricted_filesystem_type_and_setup_failures_recover(self):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR
        from unicorn.arm_const import (
            UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
            UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R7, UC_ARM_REG_LR,
            UC_ARM_REG_SP, UC_ARM_REG_PC,
        )
        for failure in ('none', 'allocation', 'root', 'directory', 'mkdir', 'live'):
            with self.subTest(failure=failure):
                emulator = Uc(UC_ARCH_ARM, UC_MODE_ARM)
                emulator.mem_map(0x10000, 0x100000)
                emulator.mem_map(0x1000000, 0x200000)
                emulator.mem_map(0x56000000, 0x200000)
                offset = struct.unpack_from('<I', self.binary, 28)[0]
                size, count = struct.unpack_from('<HH', self.binary, 42)
                for index in range(count):
                    segment = struct.unpack_from('<8I', self.binary, offset + index * size)
                    if segment[0] == 1:
                        emulator.mem_write(segment[2], self.binary[segment[1]:segment[1] + segment[4]])
                emulator.mem_write(0x90000, struct.pack('<8I', 1, 0x56000000, 111232,
                                                     0x56020000, 3, 36992, 36864, 1))
                state = {'fail': failure, 'mappings': 0, 'logs': [], 'traces': []}
                registers = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                             UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5)

                def text_at(address):
                    data = bytearray()
                    while emulator.mem_read(address, 1) != b'\0':
                        data += emulator.mem_read(address, 1)
                        address += 1
                    return data.decode()

                def syscall(machine, interrupt, unused):
                    number = machine.reg_read(UC_ARM_REG_R7)
                    args = [machine.reg_read(register) for register in registers]
                    if number == 192:
                        self.assertEqual((args[2], args[3], args[4]), (3, 0x22, 0xffffffff))
                        state['mappings'] += 1
                        result = -12 if state['fail'] == 'allocation' else 0x1000000
                    elif number == 5:
                        self.assertEqual(text_at(args[0]), '/media/storage1')
                        self.assertEqual(args[1], 0xc000)
                        result = -13 if state['fail'] == 'root' else 10
                    elif number == 322:
                        name = text_at(args[1])
                        self.assertIn(name, ('M10V', 'LIVE'))
                        self.assertEqual(args[2], 0xc800)
                        failed = state['fail'] == ('directory' if name == 'M10V' else 'live')
                        result = -13 if failed else 11 if name == 'M10V' else 12
                    elif number == 323:
                        self.assertEqual(text_at(args[1]), 'LIVE')
                        result = -13 if state['fail'] == 'mkdir' else -17
                    elif number == 4:
                        state['logs'].append(bytes(machine.mem_read(args[1], args[2])).decode())
                        result = args[2]
                    elif number == 0xfe00:
                        event = text_at(args[0])
                        values = struct.unpack('<' + 'I' * args[2], machine.mem_read(args[1], args[2] * 4))
                        state['traces'].append((event, values))
                        result = 0
                    elif number == 6:
                        result = 0
                    else:
                        self.fail(f'unexpected syscall {number}, including filesystem-type probes')
                    machine.reg_write(UC_ARM_REG_R0, result & 0xffffffff)

                emulator.hook_add(UC_HOOK_INTR, syscall)

                def attach():
                    emulator.reg_write(UC_ARM_REG_R0, 0x90000)
                    emulator.reg_write(UC_ARM_REG_R1, 0x56020000)
                    emulator.reg_write(UC_ARM_REG_SP, 0xa0000)
                    emulator.reg_write(UC_ARM_REG_LR, 0x80000)
                    emulator.emu_start(self.entry, 0x80000, count=1000000)
                    self.assertEqual(emulator.reg_read(UC_ARM_REG_PC), 0x80000)
                    return emulator.reg_read(UC_ARM_REG_R0)

                self.assertEqual(attach(), int(failure == 'none'))
                if failure != 'none':
                    self.assertTrue(state['logs'][0].startswith('LIVE_ATTACH_ERROR '))
                    self.assertIn('fffffff4' if failure == 'allocation' else 'fffffff3', state['logs'][0])
                    state['fail'] = 'none'
                    self.assertEqual(attach(), 1)
                self.assertEqual(state['mappings'], 2 if failure == 'allocation' else 1)
                if failure == 'none':
                    control = struct.pack('<5I', 0x31494c4d, 1, 111232, 0x56020000, 1)
                    emulator.mem_write(0x56000000, control)
                    emulator.mem_write(0x56000100, struct.pack('<3I', 2, 1000, 1))
                    emulator.mem_write(0x56000180, bytes([42]) * 36864)

                    def sample(now):
                        emulator.reg_write(UC_ARM_REG_R0, now)
                        emulator.reg_write(UC_ARM_REG_SP, 0xa0000)
                        emulator.reg_write(UC_ARM_REG_LR, 0x80000)
                        emulator.emu_start(self.sample, 0x80000, count=1000000)

                    sample(1000)
                    progress = [values for event, values in state['traces'] if event == 'LIVE_PROGRESS']
                    self.assertEqual(len(progress), 1)
                    self.assertEqual(progress[0][:5], (1, 1, 2, 0, 0))
                    self.assertEqual(progress[0][7:10], (2, 1, 1))
                    sample(1035)
                    self.assertEqual(len(state['traces']), 1)
                    # Producer metadata uses the existing reserved control
                    # words. Ignore an in-progress odd snapshot.
                    diagnostic = [3, 1, 7, 0, 6, 0, 1, 0, 0, 5900, 5800, 1,
                                  17, 0x55020000, 0x55010000, 0x57000000, 0x571fe000,
                                  3, 0, *range(8)]
                    emulator.mem_write(0x56000014, struct.pack('<27I', *diagnostic))
                    sample(6000)
                    self.assertEqual(len(state['traces']), 2)
                    emulator.mem_write(0x56000014, struct.pack('<I', 4))
                    emulator.mem_write(0x56000010, struct.pack('<I', 8))
                    sample(6035)
                    progress = [values for event, values in state['traces'] if event == 'LIVE_PROGRESS']
                    self.assertEqual(progress[-1][:2], (8, 0))
                    producer = [values for event, values in state['traces'] if event == 'LIVE_PRODUCER']
                    source = [values for event, values in state['traces'] if event == 'LIVE_SOURCE']
                    self.assertEqual(producer, [tuple([4] + diagnostic[1:14])])
                    self.assertEqual(source, [tuple([4] + diagnostic[14:])])
                    self.assertEqual(len(state['traces']), 5)
                    sample(11035)
                    self.assertEqual(len(state['traces']), 5)
                    emulator.mem_write(0x56000018, struct.pack('<I', 2))
                    emulator.mem_write(0x56000010, struct.pack('<I', 9))
                    sample(11070)
                    producer = [values for event, values in state['traces'] if event == 'LIVE_PRODUCER']
                    self.assertEqual([values[1] for values in producer], [1, 2])
                    self.assertEqual(len(state['traces']), 8)



if __name__ == '__main__':
    unittest.main()
