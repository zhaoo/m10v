"""Build GR III 2.10 roll capture observations and their freestanding helpers."""
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from scripts.build_gr3_menu_patches import assembly, branch
from scripts.build_gr3_m10v_library import FLAGS, ROOT, link_object

SHA = "8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67"
CAPTURE_API = tuple("m10v_roll_capture_" + name for name in (
    "arm", "revoke", "reserve", "copy_marker", "complete", "take_result",
))
SAVE_API = tuple("m10v_roll_save_" + name for name in ("begin", "output", "end"))
CAMERA_API = tuple("m10v_roll_camera_" + name for name in (
    "reserve", "group_start", "writer_start", "writer_finish", "writer_phases",
    "output", "group_finish", "insert_tag", "write_tag",
    "lcd_direct", "lcd_configured",
))
LIVE_API = tuple("m10v_live_camera_" + name for name in (
    "display", "shutter", "insert_tag", "write_tag",
))

# Replay native immediate branches with the original return PC and original
# outgoing SP. Everything else executes the displaced instruction in the shim.
SITES = (
    (0x5351eaa0, 0xe30d3440, "reserve", "mov r0,r1;", None),
    (0x5350c438, 0xeb067e3a, "group_start", "mov r0,r1;mov r1,r4;", 0x536abd28),
    (0x53599708, 0xebfffdf1, "writer_start", "mov r0,r4;", 0x53598ed4),
    (0x5359970c, 0xe5d43019, "writer_finish", "mov r0,r4;", None),
    (0x53598f80, 0xe0000005, "writer_phases", "mov r0,r6;", None),
    (0x53694b90, 0xe3500000, "output", "mov r3,r0;mov r0,r5;mov r2,r6;mov r1,r9;", None),
    (0x53694c64, 0xe12fff33, "group_finish", "mov r0,r2;", "r3"),
    (0x5345a2c8, 0xeb09aec3, "lcd_direct", "mov r0,r4;", 0x536c5ddc),
    (0x5345a3c0, 0xeb09ae4f, "lcd_configured", "mov r0,r4;", 0x536c5d04),
)

PUSH = ("push {r0-r12,lr};mrs ip,cpsr;.word 0xeef1ea10;push {ip,lr};"
        ".word 0xed2d0b20;.word 0xed6d0b20;")
POP = (".word 0xecfd0b20;.word 0xecbd0b20;pop {ip,lr};.word 0xeee1ea10;"
       "msr cpsr_f,ip;pop {r0-r12,lr};")
LIVE_ARGS = {
    "lcd_direct": "ldr r1,[sp,#264];ldr r2,[sp,#276];ldr r3,[sp,#320];",
    "lcd_configured": "ldr r1,[sp,#264];mov r2,r6;add r3,sl,r6;",
}


def _compile(source, prefix, base, api, imports=None, flags=()):
    compiler = os.environ.get("M10V_LLVM_CLANG") or "/opt/homebrew/opt/llvm/bin/clang"
    if not Path(compiler).is_file():
        compiler = shutil.which("clang")
    if not compiler:
        raise FileNotFoundError("clang required for GR III roll runtime")
    with tempfile.TemporaryDirectory(prefix="m10v-roll-capture-") as scratch:
        destination = Path(scratch) / "module.o"
        subprocess.run([compiler, *FLAGS, *flags, "-c", str(ROOT / "native/gr3" / source),
                        "-o", str(destination)], check=True, capture_output=True)
        return link_object(destination.read_bytes(), base, imports, prefix, additional_exports=api)


def build_channel(base):
    """Place the owner/producer mailbox ABI before linking either caller."""
    return _compile("m10v_roll_capture.c", "m10v_roll_capture_", base, CAPTURE_API)


def _replay(site, stock, target):
    if target is None:
        return f".word {stock:#x};b {site + 4:#x}"
    continuation = site + 4
    jump = f"b {target:#x}" if isinstance(target, int) else f"bx {target}"
    return f"movw lr,#{continuation & 0xffff};movt lr,#{continuation >> 16};{jump}"


def build_observers(rom, base, imports, live=False):
    """Require the exact original RTOS and an already-linked device channel."""
    if hashlib.sha256(rom).hexdigest() != SHA:
        raise ValueError("roll capture requires the exact GR III 2.10 RTOS")
    required = (*CAPTURE_API, "m10v_roll_device_capture_channel",
                *(("m10v_live_device_camera",) if live else ()))
    if any(type(imports.get(name)) is not int or imports[name] & 3 or
           not 0x540b6000 <= imports[name] < 0x55000000 for name in required):
        raise ValueError("missing checked roll device/capture exports")
    if live:
        # One translation unit shares the identical ShootingInfo ownership
        # validator and metadata allocator. No validator or feature is removed
        # to fit the fixed immutable-texture boundary. Local scalar helper
        # names are scoped so the original source files also build separately.
        with tempfile.TemporaryDirectory(prefix="m10v-roll-live-") as scratch:
            source = Path(scratch) / "roll-live.c"
            source.write_text("\n".join((
                "#define load live_load", "#define word live_word",
                '#include "' + str(ROOT / "native/gr3/m10v_live_camera.c") + '"',
                "#undef load", "#undef word",
                '#include "' + str(ROOT / "native/gr3/m10v_roll_save.c") + '"',
                '#include "' + str(ROOT / "native/gr3/m10v_roll_camera_capture.c") + '"',
            )))
            combined, exports = _compile(source, "m10v_roll_camera_", base,
                (*CAMERA_API, *LIVE_API, *SAVE_API),
                {**imports, "__aeabi_uidiv": 0x5313d850},
                flags=("-DM10V_LIVE_NATIVE_DEVICE=1", "-DM10V_ROLL_LIVE_AMALGAMATION=1", "-Oz"))
        save_symbols = {name: exports[name] for name in SAVE_API}
        live_symbols = {name: exports[name] for name in LIVE_API}
        camera_symbols = {name: exports[name] for name in CAMERA_API}
        code = bytearray(combined)
    else:
        save, save_symbols = _compile("m10v_roll_save.c", "m10v_roll_save_", base, SAVE_API)
        camera, camera_symbols = _compile(
            "m10v_roll_camera_capture.c", "m10v_roll_camera_", base + len(save),
            CAMERA_API, {**imports, **save_symbols, "__aeabi_uidiv": 0x5313d850})
        live_symbols = {}
        code = bytearray(save + camera)
    patches = []
    for site, expected, name, arguments, target in SITES:
        if struct.unpack_from("<I", rom, site - 0x53000000)[0] != expected:
            raise ValueError(f"roll capture stock instruction changed at {site:#x}")
        entry = base + len(code)
        if live:
            arguments += LIVE_ARGS.get(name, "")
        helper = camera_symbols["m10v_roll_camera_" + name]
        code += assembly(PUSH + arguments + f"bl {helper:#x};" + POP + _replay(site, expected, target), entry)
        patches.append(dict(address=site, expected=expected, replacement=branch(site, entry), entry=entry))
    return bytes(code), dict(schema="m10v-gr3-roll-capture/v1", base=base, bytes=len(code),
                             sha256=hashlib.sha256(code).hexdigest(), rtos_sha256=SHA,
                             exports={**save_symbols, **live_symbols, **camera_symbols}, patches=patches,
                             **({"live": "mono-nv12-192x128"} if live else {}),
                             camera_tested=False, scheduler_filesystem_calls=0)
