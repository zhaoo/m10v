"""RAW development request-to-recipe transport for the two pinned GR III images."""
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from scripts.build_gr3_m10v_library import ROOT, FLAGS, link_object
from scripts.build_gr3_menu_patches import assembly, branch, movw

ROM = 0x53000000
RTOS_HASHES = {
    '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67': 'gr3',
    '0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6': 'gr3x',
}
COPY_SITE = 0x53510830
SNAPSHOT = 'm10v_isp_frame_raw_snapshot'
# A32 helpers at inline boundaries preserve CPSR, all GPR and VFP state.
SAVE = ('push {r0-r12,lr};mrs ip,cpsr;.word 0xeef1ea10;push {ip,lr};'
        '.word 0xed2d0b20;.word 0xed6d0b20;')
RESTORE = ('.word 0xecfd0b20;.word 0xecbd0b20;pop {ip,lr};'
           '.word 0xeee1ea10;msr cpsr_f,ip;pop {r0-r12,lr};')


def build_raw_ingress(base, stock, symbols, identity_copy):
    digest = hashlib.sha256(stock).hexdigest()
    if digest not in RTOS_HASHES:
        raise ValueError('RAW ingress requires a pinned official RTOS')
    for address in (base, identity_copy, symbols.get(SNAPSHOT)):
        if type(address) is not int or address & 3 or not ROM <= address < 0x54fe0000:
            raise ValueError('invalid RAW ingress code address')
    compiler = os.environ.get('M10V_LLVM_CLANG') or '/opt/homebrew/opt/llvm/bin/clang'
    if not Path(compiler).is_file():
        compiler = shutil.which('clang')
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / 'raw-ingress.o'
        subprocess.run([compiler, *FLAGS, '-c', str(ROOT / 'native/gr3/m10v_raw_ingress.c'),
                        '-o', str(obj)], check=True, capture_output=True)
        code, exports = link_object(obj.read_bytes(), base, externals={SNAPSHOT: symbols[SNAPSHOT]},
                                    prefix='m10v_raw_ingress_')
    code = bytearray(code)
    patches = []

    def patch(site, expected, replacement, name):
        if struct.unpack_from('<I', stock, site - ROM)[0] != expected:
            raise ValueError(f'RAW ingress {name} preimage differs at {site:#x}')
        patches.append(dict(address=site, expected=expected, replacement=replacement, name=name))

    def hook(site, expected, body, name, link=False, condition=14):
        entry = base + len(code)
        code.extend(assembly(body, entry))
        patch(site, expected, branch(site, entry, link, condition), name)

    patch(0x534bf1d4, 0xe3040270, movw(0, 0x4280), 'raw_source_extent')
    hook(0x534bf1e4, branch(0x534bf1e4, 0x5355e87c, True),
         'push {r4,lr};bl 0x5355e87c;push {r0-r3,ip,lr};'
         'movw ip,#0x4270;movt ip,#7;add ip,r5,ip;'
         'mov r3,#0;str r3,[ip];str r3,[ip,#4];str r3,[ip,#8];str r3,[ip,#12];'
         'pop {r0-r3,ip,lr};pop {r4,pc}', 'raw_source_init', link=True)

    stage = exports['m10v_raw_ingress_stage']
    unstage = exports['m10v_raw_ingress_unstage']
    for name, offset, clone, original, emit, finish, finish_word, frame_offset, operation in (
        ('preview', 0x83c, 0x534a47ac, 0x534bffe4, 0x534c1128, 0x534c112c, 0xe1a08000, 0x8c0, 1),
        ('save', 0x82c, 0x534a5530, 0x534d6ab8, 0x534c17fc, 0x534c1800, 0xe16f6f10, 0x868, 2),
    ):
        clone_word = 0xe2870c07 if name == 'preview' else 0xe5c43828
        hook(clone, clone_word,
             f'push {{ip}};ldr ip,[r7,#{offset}];str ip,[r4,#{offset}];pop {{ip}};'
             f'.word {clone_word:#x};b {clone + 4:#x}', f'raw_{name}_clone')
        hook(emit, branch(emit, original, True),
             SAVE + f'mov r0,r7;ldr r1,[fp,#-{frame_offset}];mov r3,#{operation};bl {stage:#x};'
             + RESTORE + f'b {original:#x}', f'raw_{name}_stage', link=True)
        hook(finish, finish_word,
             SAVE + f'mov r0,r7;bl {unstage:#x};' + RESTORE +
             f'.word {finish_word:#x};b {finish + 4:#x}', f'raw_{name}_unstage')

    # Preserve the existing capture identity-clear adapter, then run the RAW
    # helper with the original source only after the entire stock copy.
    consumer = exports['m10v_raw_ingress_after_copy']
    hook(COPY_SITE, branch(COPY_SITE, 0x5313fd80, True),
         f'push {{r1,lr}};bl {identity_copy:#x};' + SAVE +
         f'mov r0,r4;mov r1,r5;ldr r2,[sp,#320];bl {consumer:#x};' + RESTORE +
         'add sp,sp,#4;ldr lr,[sp],#4;bx lr', 'raw_recipe_copy', link=True)
    # Native recipes can skip the copy entirely. Clear any earlier RAW
    # snapshot on that branch while preserving the original join and flags.
    hook(0x5351081c, branch(0x5351081c, 0x53510834, condition=0),
         SAVE + f'mov r0,r4;mov r1,r5;mov r2,#0;bl {consumer:#x};' + RESTORE +
         'b 0x53510834', 'raw_recipe_no_source', condition=0)
    return bytes(code), dict(schema='m10v-gr3-raw-ingress/v1', base=base, bytes=len(code),
                             exports=exports, patches=patches, source_bytes=0x74280,
                             copy_site=COPY_SITE, chained_identity_copy=identity_copy,
                             camera_model=RTOS_HASHES[digest], required_rtos_sha256=digest)
