"""Read-only ARM research: new official updater -> minimal bridge -> old official.

No update BIN is built or emitted. Package metadata and one RTOS branch are
changed in emulator memory only. Version getters and logging are substituted;
Flash writes, complete parsing, camera boot and settings migration do not run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_SP

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'gr3': {
        'new_sha': '5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e',
        'old_sha': 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4',
        'new_version': 0x0214141c, 'project': 588,
    },
    'gr3x': {
        'new_sha': 'aa8e3ae1349d94e83be381c20530e41d5e57b75c27ef24ba81c7b017d6c11592',
        'old_sha': '708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7',
        'new_version': 0x01461412, 'project': 609,
    },
}
KINDS = (0, 1, 2, 3, 4, 6)
LOAD, ENTRY, GATE, SUCCESS = 0x53000000, 0x536285d0, 0x536286cc, 0x5362866c
STOP = 0x550ffff0


def require(condition, message):
    if not condition:
        raise ValueError(message)


def version(word):
    return '.'.join(str((word >> shift) & 255) for shift in (24, 16, 8, 0))


def read_source(file, expected):
    file = Path(file).resolve()
    raw = file.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'official source SHA-256 differs')
    script = """import{readFileSync}from'node:fs';
import{inspectFirmwareImport}from'./node/firmware.mjs';
import{decodeFrameMap}from'./node/gr3-frames.mjs';
const b=readFileSync(process.argv[1]);process.stdout.write(JSON.stringify(inspectFirmwareImport(b))+'\\n');
process.stdout.write(decodeFrameMap(b).decoded);"""
    output = subprocess.check_output(['node', '--input-type=module', '-e', script, str(file)], cwd=ROOT, timeout=60)
    header, decoded = output.split(b'\n', 1)
    report = json.loads(header)
    require(report['sha256'] == expected, 'decoder source differs')
    sections, at = {}, 0
    for row in report['sections']:
        end = at + row['size']
        require(end <= len(decoded)-4, 'section bounds differ')
        require(decoded[at:at+8].split(b'\0')[0].decode() == row['name'], 'section order differs')
        sections[row['name']] = decoded[at+16:end]
        at = end
    require(at + 4 == len(decoded), 'decoded trailer differs')
    return raw, sections


def machine(rom, dsp, cpu):
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    u.mem_map(LOAD, (len(rom)+65535) & ~65535)
    u.mem_write(LOAD, rom)
    u.mem_map(0x55000000, 0x100000)
    def service(u, pc, size, data):
        if pc in (0x53547c9c, 0x53547ce0, 0x536b83c4):
            value = dsp if pc == 0x53547c9c else cpu if pc == 0x53547ce0 else 0
            u.reg_write(UC_ARM_REG_R0, value)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE, service)
    return u


def call(u, entry, obj):
    u.reg_write(UC_ARM_REG_R0, obj)
    u.reg_write(UC_ARM_REG_SP, 0x550ff000)
    u.reg_write(UC_ARM_REG_LR, STOP)
    u.emu_start(entry, STOP, count=2000000)
    require(u.reg_read(UC_ARM_REG_PC) == STOP, 'ARM probe did not return')
    return u.reg_read(UC_ARM_REG_R0)


def gate(rom, dsp, cpu, header, payload, kind):
    u = machine(rom, dsp, cpu)
    obj, buf, parser = 0x55001000, 0x55010000, 0x55002000
    for at, value in ((obj+8, 0x55003000), (obj+0x1c, parser), (obj+0x20, parser),
                      (obj+0x24, parser), (parser+0xc, 0x55004000), (obj+0x2c, kind), (obj+0x38, buf)):
        u.mem_write(at, struct.pack('<I', value))
    u.mem_write(buf, bytes(header[:128]))
    u.mem_write(buf+0x90, bytes(payload[0x90:0x94]))
    return bool(call(u, ENTRY, obj))


def probe(new_file, old_file, model):
    require(model in PROFILES, 'unsupported model')
    p = PROFILES[model]
    new_raw, new_sections = read_source(new_file, p['new_sha'])
    old_raw, old_sections = read_source(old_file, p['old_sha'])
    rom, cpu = new_sections['RTOS'], new_sections['CPU']
    current, proposed = p['new_version'], p['new_version']+256
    require(rom[GATE-LOAD:GATE-LOAD+4] == bytes.fromhex('e42103e3'), 'new updater patch preimage differs')
    require(rom[0x628664:0x62866c] == bytes.fromhex('000055e11700003a'), 'new updater comparison differs')
    patched = bytearray(rom)
    struct.pack_into('<I', patched, GATE-LOAD, 0xea000000 | (((SUCCESS-GATE-8)//4) & 0xffffff))
    require(patched[GATE-LOAD:GATE-LOAD+4] == bytes.fromhex('e6ffffea'), 'branch encoding differs')
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    md.detail = True
    instruction = list(md.disasm(bytes(patched[GATE-LOAD:GATE-LOAD+4]), GATE))
    require(len(instruction) == 1 and instruction[0].mnemonic == 'b' and instruction[0].operands[0].imm == SUCCESS, 'independent branch decoding differs')
    require(patched[:GATE-LOAD] == rom[:GATE-LOAD] and patched[GATE-LOAD+4:] == rom[GATE-LOAD+4:], 'non-target RTOS changed')
    patched = bytes(patched)

    # This is a proposed header/CPU in memory, NOT a valid full update package.
    header, proposed_cpu = bytearray(new_raw[:128]), bytearray(cpu)
    for off in (0x38, 0x50):
        struct.pack_into('>I', header, off, proposed)
    struct.pack_into('>I', proposed_cpu, 0x90, proposed)
    struct.pack_into('>I', proposed_cpu, 0x7c, 0)
    struct.pack_into('>I', proposed_cpu, 0x7c, -sum(struct.unpack('>32768I', proposed_cpu)) & 0xffffffff)

    first, historical, second, validators = [], [], [], []
    old_bridge = bytearray(old_raw[:128])
    old_bridge_cpu = bytearray(old_sections['CPU'])
    for off in (0x38, 0x50):
        struct.pack_into('>I', old_bridge, off, 0x020a161b)
    struct.pack_into('>I', old_bridge_cpu, 0x90, 0x020a161b)
    for kind in KINDS:
        cases = [(current, current, True), (proposed, proposed, True), (proposed+1, proposed+1, False),
                 (proposed+1, current, kind == 6), (current, proposed+1, kind in (0, 1))]
        for dsp, current_cpu, wanted in cases:
            accepted = gate(rom, dsp, current_cpu, header, proposed_cpu, kind)
            require(accepted == wanted, f'first-stage comparison differs: {kind}')
            first.append(dict(kind=kind, current_dsp=version(dsp), current_cpu=version(current_cpu), accepted=accepted))
        if model == 'gr3':
            accepted = gate(rom, current, current, old_bridge, old_bridge_cpu, kind)
            require(not accepted, 'historical 2.10.22.27 bridge unexpectedly admitted by official 2.20')
            historical.append(dict(kind=kind, accepted=accepted))
        for changed in (False, True):
            accepted = gate(patched if changed else rom, proposed, proposed, old_raw, old_sections['CPU'], kind)
            require(accepted == changed, f'second-stage comparison differs: {kind}')
            second.append(dict(kind=kind, patched=changed, accepted=accepted))
    for changed in (False, True):
        actual_rom = patched if changed else rom
        require(call(machine(actual_rom, current, current), ENTRY, 0x55001000) == 0, 'empty candidate admitted')
        for mode in ('new_official', 'old_official', 'proposed_cpu', 'bad_checksum', 'wrong_model'):
            payload = bytearray(old_sections['CPU'] if mode == 'old_official' else proposed_cpu if mode == 'proposed_cpu' else cpu)
            if mode == 'bad_checksum':
                payload[0x93] ^= 1
            if mode == 'wrong_model':
                struct.pack_into('<I', payload, 0x80, 609 if model == 'gr3' else 588)
                struct.pack_into('>I', payload, 0x7c, 0)
                struct.pack_into('>I', payload, 0x7c, -sum(struct.unpack('>32768I', payload)) & 0xffffffff)
            u = machine(actual_rom, current, current)
            obj, buf = 0x55001000, 0x55010000
            u.mem_write(buf, bytes(payload))
            u.mem_write(obj+0xc, struct.pack('<I', buf))
            u.mem_write(obj+0x14, struct.pack('<I', p['project']))
            accepted = bool(call(u, 0x536291b8, obj))
            require(accepted == (mode not in ('bad_checksum', 'wrong_model')), f'CPU validator differs: {mode}')
            validators.append(dict(patched=changed, mode=mode, accepted=accepted))
    return dict(schema='m10v-anniversary-downgrade-research/v1', model=model,
                source_sha256=p['new_sha'], restore_sha256=p['old_sha'],
                stage_one_package_version=version(proposed),
                strategy='new-official-runtime-minimal-bridge-then-exact-old-official',
                patch=dict(address=hex(GATE), before='e42103e3', after='e6ffffea', destination=hex(SUCCESS)),
                first_stage=first, historical_bridge_rejection=historical, second_stage=second,
                cpu_validation=validators, null_candidate_rejected=True,
                scenario_count=len(first)+len(historical)+len(second)+len(validators)+2,
                bin_emitted=False, installation_allowed=False, camera_verified=False,
                scope='ARM local version gate and CPU validator only; getters/logging substituted; synthetic package metadata',
                remaining_blockers=['full_package_not_built_or_parsed', 'flash_writes_not_executed',
                                    'minimal_bridge_boot_not_verified', 'persistent_settings_downgrade_not_verified',
                                    'old_official_boot_and_hardware_recovery_not_verified',
                                    'shop_service_firmware_versions_and_updater_unknown'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new', required=True, type=Path)
    parser.add_argument('--old', required=True, type=Path)
    parser.add_argument('--model', required=True, choices=PROFILES)
    parser.add_argument('--report', type=Path, help='optional new JSON report; existing files are never overwritten')
    args = parser.parse_args()
    try:
        result = probe(args.new, args.old, args.model)
        output = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
        if args.report:
            require(args.report.suffix.lower() == '.json', 'research output must be a JSON report, never a firmware BIN')
            with args.report.open('x') as file:
                file.write(output)
        print(output, end='')
        return 2  # Research passed, installation remains blocked.
    except Exception as error:
        print(json.dumps(dict(status='rejected', installation_allowed=False, bin_emitted=False, reason=str(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
