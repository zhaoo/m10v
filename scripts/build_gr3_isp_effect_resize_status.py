"""Optional hash-pinned inline observation of native Resize error metadata.

Emits one shim and patch plan only. Requires the complete private guard
component; does not change its default eighteen-patch installation plan.
"""
import hashlib
import struct

from scripts import build_gr3_border_wait_guard as guard
from scripts.build_gr3_menu_patches import assembly, branch

SITE = 0x53771620
RESUME = 0x53771624
EXPECTED = 0xE51B12D4  # ldr r1,[fp,#-0x2d4], from both exact official images
HELPER = 'm10v_border_effect_resize_status'


def build(base=0x54170000, stock=None, guard_manifest=None, *, enabled=False,
          camera_model='gr3'):
    if type(enabled) is not bool:
        raise ValueError('Resize status hook option must be an explicit boolean')
    disabled = {'schema': 'm10v-isp-effect-resize-status/v1', 'enabled': False,
                'patches': [], 'code_bytes': 0, 'firmware_emitted': False,
                'hardware_completion_proven': False, 'failure_quiescence_proven': False}
    if not enabled:
        return b'', disabled
    if camera_model not in guard.MODELS:
        raise ValueError('Resize status hook requires pinned GR III/IIIx input')
    model = guard.MODELS[camera_model]
    if not isinstance(stock, bytes) or hashlib.sha256(stock).hexdigest() != model['rtos_sha256']:
        raise ValueError('Resize status hook requires exact model-locked official RTOS')
    if type(base) is not int or base & 15 or not 0x540B6000 <= base <= 0x54EF0000:
        raise ValueError('invalid Resize status hook code base')
    if not isinstance(guard_manifest, dict):
        raise ValueError('complete private guard manifest required')
    g = guard_manifest
    if (g.get('enabled') is not True or g.get('camera_model') != camera_model or
            g.get('original_rtos_sha256') != model['rtos_sha256']):
        raise ValueError('matching enabled private guard required')
    symbols = g.get('symbols', {})
    patches = g.get('patches', [])
    if not isinstance(symbols, dict) or not isinstance(patches, list) or len(patches) != len(guard.HOOKS):
        raise ValueError('all eighteen private guard patches required')
    by_address = {p.get('address'): p for p in patches if isinstance(p, dict)}
    if len(by_address) != len(guard.HOOKS):
        raise ValueError('duplicate or malformed private guard patch')
    for at, expected, target, role in guard.HOOKS:
        p = by_address.get(at, {})
        address = symbols.get(target) if isinstance(target, str) else None
        if isinstance(target, str) and (type(address) is not int or address & 3):
            raise ValueError('missing private guard export ' + target)
        replacement = guard.arm_bl(at, address) if isinstance(target, str) else target
        if p.get('expected') != expected or p.get('replacement') != replacement or p.get('role') != role:
            raise ValueError('private guard patch contract differs at ' + hex(at))
    helper = symbols.get(HELPER)
    guard_base, guard_bytes = g.get('base'), g.get('code_bytes')
    if (type(helper) is not int or helper & 3 or type(guard_base) is not int or
            type(guard_bytes) is not int or not 0 < guard_bytes <= 65536 or
            not 0x540B6000 <= guard_base <= 0x54EF0000 or
            not guard_base <= helper < guard_base + guard_bytes):
        raise ValueError('bound private Resize status helper export required')
    spans = []
    for name, start, end, expected_hash in guard.ABI_SPANS:
        if name not in ('resize_body', 'resize_iip_lower'):
            continue
        if hashlib.sha256(stock[start - guard.RTOS_BASE:end - guard.RTOS_BASE]).hexdigest() != expected_hash:
            raise ValueError('native Resize ABI span differs: ' + name)
        spans.append({'name': name, 'start': start, 'end': end, 'sha256': expected_hash})
    if struct.unpack_from('<I', stock, SITE - guard.RTOS_BASE)[0] != EXPECTED:
        raise ValueError('native Resize status instruction preimage differs')
    # 56 GPR + 8 status + 256 VFP bytes preserves native 8-byte alignment.
    # Save both VFP register banks with raw A32 encodings (soft-float build).
    code = assembly(
        'push {r0-r12,lr};mrs ip,cpsr;.word 0xeef1ea10;push {ip,lr};'
        '.word 0xed2d0b20;.word 0xed6d0b20;'
        'ldr r0,[fp,#-0x2d0];mov r1,fp;bl ' + hex(helper) + ';'
        '.word 0xecfd0b20;.word 0xecbd0b20;pop {ip,lr};'
        '.word 0xeee1ea10;msr cpsr_f,ip;pop {r0-r12,lr};'
        '.word ' + hex(EXPECTED) + ';b ' + hex(RESUME), base)
    if len(code) > 65536 or base < guard_base + guard_bytes and guard_base < base + len(code):
        raise ValueError('Resize status shim overlaps private guard component')
    patch = {'address': SITE, 'expected': EXPECTED,
             'replacement': branch(SITE, base), 'target': base,
             'role': 'effect_resize_error_observation', 'kind': 'INLINE'}
    manifest = dict(disabled, enabled=True, base=base, code_bytes=len(code),
        code_sha256=hashlib.sha256(code).hexdigest(), patches=[patch],
        camera_model=camera_model, original_rtos_sha256=model['rtos_sha256'],
        helper=helper, helper_symbol=HELPER, required_guard_patches=18,
        verified_abi_spans=spans, resume=RESUME,
        displaced_instruction='ldr r1,[fp,#-0x2d4]',
        original_instruction_correction={
            'requested_site': SITE,
            'requested_description': 'ldr r2,[fp,#-0x2d0]',
            'actual_previous_site': SITE - 4,
            'actual_previous_word': 0xE51B22D0,
            'actual_site_word': EXPECTED,
            'reason': 'Exact original bytes place context load four bytes before hook; replay actual hook instruction.'},
        preserves=['r0-r12', 'sp', 'lr', 'NZCV', 'd0-d31', 'FPSCR'],
        status_observation_only=True, pixel_access=False, allocator_calls=0,
        filesystem_calls=0, camera_tested=False,
        ownership_prerequisite='Original immutable lower frame, enlarged Resize worker and private client remain alive.',
        integration='Append shim and merge its one optional exact-preimage patch only with the complete private guard component.')
    return code, manifest
