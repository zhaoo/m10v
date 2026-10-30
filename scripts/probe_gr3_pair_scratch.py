"""Bounded original-GR3 ImageMemory metadata probes; no photo memory or hardware.

Run from the repository root with the existing Unicorn environment.
The actual pool backend is a named double: success tokens prove ABI, not capacity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_gr3_border_iip import OriginalArm, validate

OBJECT = 0x55260000
MANAGER = 0x55270000
TOKEN = 0x70000003  # unmapped, intentionally unaligned backing token
INIT, ALLOC, FREE, GET = 0x534aa810, 0x534aa994, 0x534aa868, 0x534aa800
SPANS = {'image_memory': (0x534aa7f0, 0x534aab0c),
         'alignment_helper': (0x534a22b8, 0x534a22d0)}


def run_case(rom, name, bytes_requested, alignment=16, failures=0, preallocated=False):
    p = OriginalArm(rom)
    p.u.mem_write(OBJECT - 16, b'\xa5' * 64)
    before = bytes(p.u.mem_read(OBJECT - 16, 64))
    p.call(INIT, OBJECT)
    initial = bytes(p.u.mem_read(OBJECT, 32))
    assert struct.unpack_from('<IIH', initial) == (0, 0, 16)
    assert initial[0xc:0x1c] == bytes(16)
    assert initial[0x1c:0x1f] == bytes([5, 5, 0])
    assert initial[0x1f] == 0xa5
    assert bytes(p.u.mem_read(OBJECT - 16, 16)) == before[:16]
    assert bytes(p.u.mem_read(OBJECT + 32, 16)) == before[48:]
    allocations, frees = [], []

    def allocate():
        r = [p.u.reg_read(getattr(p.A, f'UC_ARM_REG_R{i}')) for i in range(4)]
        allocations.append(r)
        assert r[0] == MANAGER and r[1] == bytes_requested + alignment - 1 and r[2] == 2
        return 0 if len(allocations) <= failures else TOKEN

    def release():
        r = [p.u.reg_read(getattr(p.A, f'UC_ARM_REG_R{i}')) for i in range(3)]
        frees.append(r)
        assert r[:2] == [MANAGER, TOKEN]
        return 0  # pool dispatch return does not prove physical release

    def report():
        if not p.u.reg_read(p.A.UC_ARM_REG_R0):
            p.assertions.append({'caller': p.u.reg_read(p.A.UC_ARM_REG_LR),
                                 'line': p.u.reg_read(p.A.UC_ARM_REG_R3),
                                 'boundary': 'original report/assert 536b9f1c replaced'})
        return 0

    p.boundaries = {0x536b9f1c: report, 0x536a2424: lambda: MANAGER, 0x536a27e8: allocate, 0x536a248c: release}
    if preallocated:
        p.words(OBJECT, TOKEN, 123)
    result = p.call(ALLOC, OBJECT, bytes_requested, alignment)
    post = bytes(p.u.mem_read(OBJECT, 32))
    if preallocated:
        assert result == 0 and not allocations
        assert p.read_words(OBJECT, 2) == [TOKEN, 123]
    elif not bytes_requested:
        assert result == 0 and not allocations and p.read_words(OBJECT, 2) == [0, 0]
    else:
        success = failures < 5
        assert result == int(success)
        assert len(allocations) == min(failures + 1, 5)
        assert p.read_words(OBJECT, 2) == [TOKEN if success else 0, bytes_requested]
        assert struct.unpack_from('<H', post, 8)[0] == alignment
        if success:
            assert p.call(GET, OBJECT) == (TOKEN + alignment - 1) & ~(alignment - 1)
            p.call(FREE, OBJECT)
            assert len(frees) == 1 and bytes(p.u.mem_read(OBJECT, 31)) == initial[:31]
        else:
            # Call the optional cleanup wrapper, which checks backing before free.
            p.call(0x534aa89c, OBJECT)
            assert not frees
    assert bytes(p.u.mem_read(OBJECT - 16, 16)) == before[:16]
    assert bytes(p.u.mem_read(OBJECT + 32, 16)) == before[48:]
    assert bytes(p.u.mem_read(OBJECT + 31, 1)) == b'\xa5'
    assert len(p.assertions) == (1 if preallocated or not bytes_requested or failures >= 5 else 0)
    return {'name': name, 'requested': bytes_requested, 'alignment': alignment,
            'allocator_attempts': len(allocations), 'returned_bool': result,
            'allocator_args': allocations, 'free_args': frees,
            'assertions': p.assertions, 'object_extent_bytes': 32,
            'highest_initialized_byte': 30, 'photo_memory_mapped': False}


def run_direct_case(rom, name, e_available, f_available, e_result, f_result):
    p = OriginalArm(rom)
    size = 4 * 2992 * 4000
    requested = size + 15
    e, f, vt = 0x55280000, 0x55281000, 0x55282000
    info_leaf, alloc_leaf, member_leaf, free_leaf = [0x55e00000 + 4*i for i in range(4)]
    p.words(e, vt); p.words(f, vt)
    p.words(vt+8, alloc_leaf, free_leaf, info_leaf, 0, member_leaf)
    # Explicit already-initialized singleton fixture: execute real fast getter.
    p.words(0x5536c520, 1)
    manager = p.call(0x536a2424)
    assert manager == 0x5536c51c
    events = []
    def pool():
        ident = p.u.reg_read(p.A.UC_ARM_REG_R0)
        assert ident in (14,15)
        events.append(['pool',ident])
        return e if ident==14 else f
    def info():
        owner = p.u.reg_read(p.A.UC_ARM_REG_R0)
        p.words(p.u.reg_read(p.A.UC_ARM_REG_R1), 0x10000000)
        p.words(p.u.reg_read(p.A.UC_ARM_REG_R2), e_available if owner==e else f_available)
        events.append(['info',owner])
        return 1
    def allocate():
        args=[p.u.reg_read(getattr(p.A,f'UC_ARM_REG_R{i}')) for i in range(4)]
        assert args[0] in (e,f) and args[1:]==[requested,0,0]
        events.append(['allocate',*args])
        return e_result if args[0]==e else f_result
    token = e_result or f_result
    chosen = e if e_result else f
    def member():
        owner = p.u.reg_read(p.A.UC_ARM_REG_R0)
        assert p.u.reg_read(p.A.UC_ARM_REG_R1)==token
        events.append(['member',owner,token])
        return int(owner==chosen)
    def free():
        args=[p.u.reg_read(getattr(p.A,f'UC_ARM_REG_R{i}')) for i in range(3)]
        assert args==[chosen,token,0]
        events.append(['free',*args])
        return 0 # exact dispatch return, not release-success assertion
    p.boundaries={0x536abf18:pool,info_leaf:info,alloc_leaf:allocate,member_leaf:member,free_leaf:free}
    raw=p.call(0x536a27e8,manager,requested,2,0)
    if token:
        assert raw==token
        aligned=(raw+15)&~15
        assert raw<=aligned and aligned+size<=raw+requested
        p.call(0x536a248c,manager,raw,0)
        assert sum(v[0]=='free' for v in events)==1
    else:
        assert raw==0 and not any(v[0] in ('member','free') for v in events)
    assert not p.assertions
    return dict(name=name,requested_pool_bytes=requested,usable_bytes=size,manager=manager,returned_raw=raw,
                aligned_data=((raw+15)&~15) if raw else 0,events=events,assertions=p.assertions,
                boundaries='pool lookup and pool virtual leaves only; manager getter/policy/precheck/membership dispatch/free are original ARM')


def probe(rom):
    digest = validate(rom, 'gr3')
    cases = [run_case(rom, 'pair_2992x4000', 4 * 2992 * 4000),
             run_case(rom, 'pair_2400x3200_align64', 4 * 2400 * 3200, 64),
             run_case(rom, 'pair_1680x2240_third_attempt', 4 * 1680 * 2240, failures=2),
             run_case(rom, 'pair_960x1280_all_five_fail', 4 * 960 * 1280, failures=5),
             run_case(rom, 'zero_size_refused', 0),
             run_case(rom, 'existing_owner_refused', 64, preallocated=True)]
    return {'schema': 'm10v-gr3-pair-scratch-research/v1', 'rtos_sha256': digest,
            'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'spans': {name: {'start': a, 'end': z, 'sha256': hashlib.sha256(rom[a-0x53000000:z-0x53000000]).hexdigest()} for name, (a, z) in SPANS.items()},
            'cases': cases, 'direct_policy2_cases': [
                run_direct_case(rom,'poolE_success',0x10000000,0x10000000,TOKEN,0),
                run_direct_case(rom,'poolE_leaf_fails_poolF_success',0x10000000,0x10000000,0,TOKEN),
                run_direct_case(rom,'poolE_exact_available_skipped_poolF_success',4*2992*4000+15,0x10000000,0,TOKEN),
                run_direct_case(rom,'both_pools_insufficient',0,0,0,0),
                run_direct_case(rom,'both_allocation_leaves_return_NULL',0x10000000,0x10000000,0,0)],
            'hardware_executed': False, 'pool_backend_executed': False,
            'limitations': ['Allocator/free backend and manager getter are explicit doubles; no physical capacity or pool locking is proved.',
                           'ImageMemory initializes only through byte30 of its 32-byte object; caller must initialize byte31 if needed.',
                           'Policy2 tries original pools E then F; capacity, fragmentation and execution latency are not bounded here.',
                           'Free dispatch return is not a success boolean; retain exact original backing token, not aligned getter pointer.',
                           'Scratch failure must occur before JPEG descriptor or source-pixel mutation to preserve stock JPEG fallback.',
                           'All-five failure, zero size and preexisting ownership call original report/assert 536b9f1c; false-return probes replace it. It logs, mutates diagnostic state and calls RTOS-dependent helpers; this is not a clean fallible production allocator.',
                           'Use checked direct policy2 allocator 536a27e8 for optional scratch rather than assuming ImageMemory Alloc OOM has no side effects.',
                           'Private SD file and filesystem service admission from capture task are separate contracts.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtos', type=Path, default=Path('builds/gr3-extension-validation/official-rtos.bin'))
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = probe(args.rtos.read_bytes())
    encoded = json.dumps(result, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded)
    print(f"PASS: {len(result['cases'])} ImageMemory cases and {len(result['direct_policy2_cases'])} direct fallible policy2 cases; no pixels, pool leaves or hardware executed.")


if __name__ == '__main__':
    main()
