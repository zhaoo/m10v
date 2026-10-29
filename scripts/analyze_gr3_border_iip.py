"""Hash-pinned original ARM border primitives, without IIP pixels or firmware.

The fill probe executes FrameOperationPipeService::FillRectIip up to its
original IIP service boundary, recording requests instead of executing DMA.
Photo planes are deliberately UNMAPPED. This proves parameter propagation and
absence of CPU photo access in this scope, not hardware output or speed.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

BASE = 0x53000000
HASHES = {
    'gr3': '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67',
    'gr3x': '0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6',
}
CONTRACTS = {
    'native_descriptor': (0x5376bba0, 0x5376bc48),
    'loader': (0x536789f0, 0x53678b40),
    'store': (0x5368c3d8, 0x5368c5b4),
    'fill_pipe': (0x5365900c, 0x5365929c),
    'fill_iip_service': (0x53769a78, 0x5376a3b8),
    'copy_graph': (0x53681260, 0x536814b8),
    'release': (0x5376ed74, 0x5376f164),
    'jpeg_request': (0x53663a8c, 0x53663ba4),
    'jpeg_driver': (0x53791044, 0x537913e4),
    'jpeg_image_size_setter': (0x53791d8c, 0x53791dc8),
    'jpeg_dma_size_setter': (0x53792128, 0x53792164),
}


def validate(rom, model=None):
    digest = hashlib.sha256(rom).hexdigest()
    if model is None:
        if digest not in HASHES.values():
            raise ValueError('unrecognized official RTOS')
    elif model not in HASHES or digest != HASHES[model]:
        raise ValueError('model and official RTOS identity mismatch')
    return digest


class OriginalArm:
    def __init__(self, rom):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
        from unicorn import arm_const as A
        validate(rom)
        self.A = A
        self.u = u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        # The official divide helper uses UDIV, absent from Unicorn's A9
        # profile. A15 enables that instruction; this is an ISA fixture,
        # not an identification of the camera's CPU or a timing model.
        u.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A15)
        u.mem_map(BASE, (len(rom) + 4095) & ~4095)
        u.mem_write(BASE, rom)
        u.mem_protect(BASE, (len(rom) + 4095) & ~4095, UC_PROT_READ | UC_PROT_EXEC)
        u.mem_map(0x55000000, 0x1000000)
        u.mem_write(0x55000000, rom[0x107b540:0x107b540 + 0x3a080])
        u.reg_write(A.UC_ARM_REG_C1_C0_2, 0xf00000)
        u.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        self.assertions = []
        self.boundaries = {}
        u.hook_add(UC_HOOK_CODE, self.service)

    def words(self, address, *values):
        self.u.mem_write(address, struct.pack('<' + 'I' * len(values), *values))

    def read_words(self, address, count):
        return list(struct.unpack('<' + 'I' * count, self.u.mem_read(address, count * 4)))

    def service(self, u, pc, size, data):
        A = self.A
        if pc == 0x536b93d0:
            if not u.reg_read(A.UC_ARM_REG_R0):
                self.assertions.append({'caller': u.reg_read(A.UC_ARM_REG_LR),
                                        'line': u.reg_read(A.UC_ARM_REG_R3)})
            result = 0
        elif pc in self.boundaries:
            result = self.boundaries[pc]()
        else:
            return
        u.reg_write(A.UC_ARM_REG_R0, result or 0)
        u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))

    def call(self, address, *args):
        from unicorn import UcError
        A, u = self.A, self.u
        sp, stop = 0x55ffe000, 0x55fff000
        for n in range(13):
            u.reg_write(getattr(A, f'UC_ARM_REG_R{n}'), 0)
        u.mem_write(sp, bytes(128))
        for n, value in enumerate(args):
            if n < 4:
                u.reg_write(getattr(A, f'UC_ARM_REG_R{n}'), value)
            else:
                self.words(sp + 4 * (n - 4), value)
        u.reg_write(A.UC_ARM_REG_SP, sp)
        u.reg_write(A.UC_ARM_REG_LR, stop)
        try:
            u.emu_start(address, stop, count=500000)
        except UcError as error:
            raise AssertionError(f'{error}; PC={u.reg_read(A.UC_ARM_REG_PC):#x}, '
                                 f'LR={u.reg_read(A.UC_ARM_REG_LR):#x}') from error
        if u.reg_read(A.UC_ARM_REG_PC) != stop or u.reg_read(A.UC_ARM_REG_SP) != sp:
            raise AssertionError('original ARM did not return within budget with balanced stack')
        return u.reg_read(A.UC_ARM_REG_R0)


def probe_rectangle(rom, x, y, width, height):
    if not all(type(v) is int for v in (x, y, width, height)) or min(x, y) < 0 or min(width, height) < 1:
        raise ValueError('invalid rectangle')
    p = OriginalArm(rom)
    rectangle, loader, store = 0x55080000, 0x55081000, 0x55082000
    p.words(rectangle, x, y, width, height)
    p.call(0x536789f0, loader, 2, rectangle)
    p.call(0x5368c3d8, store, 8, rectangle)
    return {'loader': list(struct.unpack('<4H', p.u.mem_read(loader + 0xa0, 8))),
            'store': list(struct.unpack('<4H', p.u.mem_read(store + 0xa4, 8))),
            'assertions': p.assertions}


def probe_fill(rom, width, height, fmt=1, constants=(255, 128, 128)):
    if not (type(width) is int and type(height) is int and 1 <= width <= 65535 and
            1 <= height <= 65535 and fmt in (0, 1, 2) and len(constants) == 3 and
            all(type(v) is int and 0 <= v <= 65535 for v in constants)):
        raise ValueError('invalid native fill input')
    p = OriginalArm(rom)
    context, args, desc = 0x55080000, 0x55081000, 0x55082000
    requests, locks = [], []
    # Addresses are ABI tokens only. No actual image memory is mapped here.
    p.u.mem_write(desc, bytes([fmt]))
    p.words(desc + 4, 0x70000000, 0x74000000, 0)
    p.u.mem_write(desc + 0x10, struct.pack('<6H', width, height, width, height, 0, 0))
    p.words(args, desc)
    p.u.mem_write(args + 4, struct.pack('<3H', *constants))

    def record():
        packet = p.u.reg_read(p.A.UC_ARM_REG_R1)
        raw = bytes(p.u.mem_read(packet, 0x22))
        stride, rows, visible_width, visible_height, left, top, a, b, c = struct.unpack_from('<9H', raw, 0x10)
        requests.append({'format': raw[0], 'layout_code': raw[1],
                         'planes': list(struct.unpack_from('<3I', raw, 4)),
                         'stride': stride, 'height': rows, 'width': visible_width,
                         'visible_height': visible_height, 'left': left, 'top': top,
                         'constants': [a, b, c]})

    p.boundaries = {0x536a848c: lambda: locks.append('acquire'),
                    0x536a8544: lambda: locks.append('release'),
                    0x53769a78: record}
    p.call(0x5365900c, context, args)
    return {'requests': requests, 'locks': locks, 'assertions': p.assertions,
            'pixels_mapped': False, 'scope': 'original fill pipe; IIP service recorded, not executed'}


def analyze(rom, model):
    digest = validate(rom, model)
    spans = {name: {'start': start, 'end': end,
                    'sha256': hashlib.sha256(rom[start - BASE:end - BASE]).hexdigest()}
             for name, (start, end) in CONTRACTS.items()}
    contract = b''.join(rom[a - BASE:b - BASE] for a, b in CONTRACTS.values())
    return {'schema': 'm10v-border-iip-research/v1', 'model': model, 'rtos_sha256': digest,
            'analyzer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'contracts': spans, 'contract_sha256': hashlib.sha256(contract).hexdigest(),
            'firmware_emitted': False, 'hardware_pixels_executed': False,
            'camera_tested': False, 'activation_ready': False,
            'unproved': ['hardware_fill_and_copy_pixels', 'extended_jpeg_and_pool_allocation',
                         'failure_quiescence', 'capture_and_preview_integration', 'camera_latency'],
            'expanded_rectangle': probe_rectangle(rom, 0, 0, 6320, 4640),
            'expanded_fill': probe_fill(rom, 6320, 4640),
            'expanded_fill_driver': probe_fill_driver(rom, 6320, 4640, (255, 128, 128)),
            'failed_fill_driver_wait': probe_fill_driver(rom, 160, 120, (255, 128, 128), 0),
            'expanded_jpeg_request': probe_jpeg_request(rom, 6320, 4640),
            'expanded_jpeg_register_fixture': probe_jpeg_registers(rom, 6320, 4640)}


def probe_fill_driver(rom, width, height, constants, wait_result=1):
    """Execute original request construction, stop at unit-upload/OS services.

    No register uploads, IIP scheduler, event delivery or DMA is simulated.
    The recorded submit/wait/release order is control flow, not completion.
    """
    if not (1 <= width <= 65535 and 1 <= height <= 65535 and len(constants) == 3 and
            all(type(v) is int and 0 <= v <= 65535 for v in constants) and wait_result in (0, 1)):
        raise ValueError('invalid driver probe input')
    p = OriginalArm(rom)
    context, packet = 0x55080000, 0x55081000
    raw = bytearray(0x22)
    struct.pack_into('<3I', raw, 4, 0x70000000, 0x74000000, 0)
    struct.pack_into('<9H', raw, 0x10, width, height, width, height, 0, 0, *constants)
    p.u.mem_write(packet, bytes(raw))
    record = {'events': [], 'pixels_mapped': False, 'failure_quiescence_proven': False}

    def gpc():
        config = p.u.reg_read(p.A.UC_ARM_REG_R1)
        planes = [p.read_words(config + off, 1)[0] for off in (0x20, 0x30, 0x40)]
        record['constants'] = [p.read_words(plane + 0x44, 1)[0] for plane in planes]

    def store():
        config = p.u.reg_read(p.A.UC_ARM_REG_R1)
        record['store_size'] = list(struct.unpack('<2H', p.u.mem_read(config + 0x1c, 4)))
        record['store_origin'] = list(struct.unpack('<2H', p.u.mem_read(config + 0xa, 4)))

    def wait():
        record['events'].append('wait')
        return wait_result

    p.boundaries = {0x5377079c: lambda: p.u.reg_read(p.A.UC_ARM_REG_R0),
                    0x5376ebd0: lambda: 0, 0x5376eb14: lambda: 0,
                    0x5376b8bc: gpc, 0x5377448c: store, 0x5376eafc: lambda: 0,
                    0x536a9dd4: lambda: 0,
                    0x5376e55c: lambda: record['events'].append('submit'),
                    0x536a9e8c: wait,
                    0x5376ed74: lambda: record['events'].append('release'),
                    0x5377077c: lambda: 0}
    p.call(0x53769a78, context, packet)
    record['assertions'] = p.assertions
    return record


def probe_jpeg_request(rom, width, height):
    """Execute native request creation, recording the JPEG engine boundary.

    OS clear/wait and JPEG submit/release are test boundaries. No completion
    bytes or encoded image are synthesized. This does not prove codec limits.
    """
    if not (type(width) is int and type(height) is int and
            1 <= width <= 65535 and 1 <= height <= 65535):
        raise ValueError('invalid JPEG probe dimensions')
    p = OriginalArm(rom)
    context, desc, output = 0x55080000, 0x55081000, 0x55082000
    p.words(desc + 4, 0x70000000, 0x74000000, 0)
    p.u.mem_write(desc + 0x10, struct.pack('<4H', width, height, width, height))
    p.words(output, 0x78000000, 0, 32 * 1024 * 1024, 0)
    p.u.mem_write(output + 0x10, b'\x01')
    record = {'encoding_executed': False, 'pixels_mapped': False}

    def submit():
        packet = p.u.reg_read(p.A.UC_ARM_REG_R2)
        raw = bytes(p.u.mem_read(packet, 0x24))
        record['source_planes'] = list(struct.unpack_from('<2I', raw))
        record['stride'], record['width'], record['height'] = struct.unpack_from('<3H', raw, 0xc)

    p.boundaries = {0x536a9dd4: lambda: 0, 0x53791044: submit,
                    0x536a9e8c: lambda: 0, 0x53790f88: lambda: 0}
    p.call(0x53663a8c, context, desc, output, 0x3b6, 0, 0)
    record['assertions'] = p.assertions
    return record


def probe_jpeg_registers(rom, width, height):
    """Original JPEG driver arithmetic/setters, MMIO addresses backed by RAM.

    Control services and hardware start are substituted. Register writes are
    evidence of serialization ONLY: no silicon response/encoding is modeled.
    """
    if not (type(width) is int and type(height) is int and
            1 <= width <= 65535 and 1 <= height <= 65535):
        raise ValueError('invalid JPEG register probe dimensions')
    p = OriginalArm(rom)
    p.u.mem_map(0x298c0000, 0x10000)
    context, packet = 0x55080000, 0x55081000
    p.words(context + 0x24, 0x55082000)
    raw = bytearray(0x24)
    struct.pack_into('<3I', raw, 0, 0x70000000, 0x74000000, 0x78000000)
    struct.pack_into('<4H', raw, 0xc, width, width, height, 1)
    struct.pack_into('<I', raw, 0x14, 32 * 1024 * 1024)
    raw[0x22] = 1
    p.u.mem_write(packet, bytes(raw))
    p.boundaries = {address: (lambda: 0) for address in
                    (0x5356284c, 0x5377c450, 0x5378fecc, 0x53790e8c, 0x53790b30,
                     0x53784de0, 0x53783820, 0x53791ec4, 0x53791c20, 0x53791f44)}
    p.call(0x53791044, context, 0, packet)
    # Image size registers are V then H; DMA setter is H then V.
    h, w = p.read_words(0x298c0018, 2)
    dw, dh = p.read_words(0x298c0418, 2)
    return {'image_size': [w & 0xffff, h & 0xffff],
            'dma_size': [dw & 0xffff, dh & 0xffff],
            'assertions': p.assertions, 'hardware_executed': False,
            'scope': 'RAM register image; hardware start/control boundaries substituted'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtos', type=Path, required=True)
    parser.add_argument('--model', choices=tuple(HASHES), required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.rtos.read_bytes(), args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'model': args.model, 'out': str(args.out), 'activation_ready': False}))


if __name__ == '__main__':
    main()
