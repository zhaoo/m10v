"""Build a local GR III 2.10 self-test ZIP with boot-persistent diagnostics."""
import argparse
import json
import os
import struct
import tempfile
import zipfile
from pathlib import Path

from package_gremote_connection import (
    ROOT, STARTUP_TTL, _audit_elf, _candidate, _film_pack, build_service, need, sha,
)

LOG_START = b"""#!/bin/sh
base=/media/storage1/SCRIPT/MCW1101
lock=/tmp/m10v-companion-1101.lock
image="$base/SERVICE.BIN"
log=/media/storage1/M10V/R16BOOT.TXT
ram=/tmp/m10v-worker-1101.log
ram_copy=/media/storage1/M10V/R16RAM.TXT
snapshot_ram() {
 if [ -r "$ram" ]; then
  if cp "$ram" "$ram_copy" 2>/dev/null; then
   echo R16_RAM_COPIED >>"$log"
  fi
 fi
}
if ! mkdir "$lock" 2>/dev/null; then
 snapshot_ram
 exit 0
fi
if ! (echo R16_SHELL >>"$log") 2>/dev/null; then
 log=/tmp/m10v-r16-boot.log
 echo R16_SHELL >>"$log"
fi
read uptime _ </proc/uptime
echo "R16_UPTIME ${uptime:-unknown}" >>"$log"
if [ ! -r "$image" ]; then
 echo R16_IMAGE_UNREADABLE >>"$log"
 rmdir "$lock"
 exit 1
fi
echo R16_IMAGE_READABLE >>"$log"
if command -v sha256sum >/dev/null 2>&1; then
 digest=$(sha256sum "$image" 2>/dev/null)
 if [ -n "$digest" ]; then
  echo "R16_IMAGE_SHA256 $digest" >>"$log"
 else
  echo R16_IMAGE_SHA256_UNAVAILABLE >>"$log"
 fi
else
 echo R16_IMAGE_SHA256_UNAVAILABLE >>"$log"
fi
# Match the established service launch model: one foreground ELF inside a
# background shell supervisor. The ELF does not fork or acknowledge a parent.
(
 echo R16_EXEC_SD_BEGIN
 "$image"
 status=$?
 echo "R16_EXEC_SD_END_$status"
 case "$status" in
  126|127)
   copy="$lock/SERVICE.BIN"
   if cp "$image" "$copy" && chmod 700 "$copy"; then
    echo R16_EXEC_TMP_BEGIN
    "$copy"
    status=$?
    echo "R16_EXEC_TMP_END_$status"
   else
    status=1
    echo R16_COPY_FAILED
   fi
   rm -f "$copy"
   ;;
 esac
 echo "R16_SERVICE_EXIT_$status"
 # Retain the per-boot lock after exec: an uncertain RTOS operation must not
 # be replayed by another loader attempt in this same power cycle.
) </dev/null >>"$log" 2>&1 &
worker=$!
echo "R16_SPAWNED $worker" >>"$log"
snapshot_ram
exit 0
"""



def diagnostic_startup():
    marker = ("fileopen r16fh 'C:\\M10V\\R16TTL.TXT' 1\r\n"
              "if r16fh < 0 goto r6_launch\r\n"
              "filewriteln r16fh 'R16 TTL START'\r\nfileclose r16fh\r\n:r6_launch\r\n")
    delay, commands = STARTUP_TTL.split(b"\r\n", 1)
    return delay + b"\r\n" + marker.encode() + commands


def android_apk(apk, identity, service):
    with zipfile.ZipFile(apk) as archive:
        need(archive.testzip() is None and 'AndroidManifest.xml' in archive.namelist(),
             'invalid Android test APK')
        prefix = 'assets/flutter_assets/assets/films/'
        for profile in ('camera-', 'camera-profiles/leica-gr3-'):
            catalog = json.loads(archive.read(prefix + profile + 'catalog.json'))
            if catalog['hash'] == identity['catalogHash']:
                canonical = json.dumps({key: value for key, value in catalog.items() if key != 'hash'},
                                       sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
                contract = archive.read(prefix + profile + 'contract.json')
                need(sha(canonical) == identity['catalogHash'] and
                     catalog['rendererHash'] == identity['rendererHash'] and
                     sha(contract) == service['registrySha256'], 'APK protocol or renderer differs')
                return apk.read_bytes()
        raise ValueError('APK camera profile differs')


def package(candidate, apk, output):
    receipt, firmware, native, identity = _candidate(candidate)
    need(native.get('roll_capture') and native.get('menu_hub'), 'roll diagnostics require the roll firmware')
    need(native.get('roll_capture', {}).get('live') == 'mono-nv12-192x128' and
         native.get('companion', {}).get('extensions', {}).get('features', {}).get('live') is True,
         'the complete Live capture and transport feature is required')
    menu_path = ROOT / 'web/gr3/MENU-R8.M10'
    menu = menu_path.read_bytes()
    needs = json.loads(menu_path.with_suffix('.json').read_text())
    need(sha(menu) == needs['sha256'] and struct.unpack_from('<4sIII', menu) ==
         (b'MNU8', 8, needs['record_count'], len(menu)), 'menu archive differs')
    with tempfile.TemporaryDirectory(prefix='gr3-roll-log-build-') as temp:
        work = Path(temp)
        service_dir = work / 'service'
        service = build_service(service_dir, candidate_dir=candidate, hotspot_pairing=True,
                                catalog_hash=identity['catalogHash'], renderer_hash=identity['rendererHash'], diagnostics=True)
        elf = (service_dir / 'm10v-companion.elf').read_bytes()
        _audit_elf(elf)
        need(service['firmwareSha256'] == sha(firmware) and service['serviceSha256'] == sha(elf),
             'firmware and service differ')
        need(b'R16_ELF_ENTRY\n\0' in elf and b'ROLL_SD\0' in elf and b'ROLL_DIAG\0' in elf and b'LIVE_SD_OK\n\0' in elf and not (service_dir / 'pairing.json').exists(),
             'logging or hotspot policy differs')
        film_pack, film_audit = _film_pack(work, identity)
    instructions = (ROOT / 'docs/testing/2026-11-16-gr3-roll-log-package.txt').read_text()
    files = {
        '开始前必读.txt': (instructions + '\n固件 SHA-256 ' + sha(firmware) + '\n').encode(),
        '01_FIRMWARE/SD_ROOT/fwdc239b.bin': firmware,
        '02_SERVICE/SD_ROOT/SCRIPT/STARTUP.TTL': diagnostic_startup(),
        '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.SH': LOG_START,
        '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.BIN': elf,
        '03_FILMS/SD_ROOT/M10V/FILMS.M10': film_pack,
        '04_MENU/SD_ROOT/M10V/MENU.M10': menu,
        '05_ANDROID/GRemote.apk': android_apk(apk, identity, service),
        '06_OPTIONAL_ENABLE_SD_SCRIPT/00078350.588': b'[SCRIPT_EN_MODE EN]\r\n',
        '06_OPTIONAL_ENABLE_SD_SCRIPT/DEVELOP.MOD': bytes([7, 1, 44, 31, 16, 3, 30, 22, 5, 45]),
        '06_OPTIONAL_ENABLE_SD_SCRIPT/GRKit-LICENSE.txt': (ROOT / 'third_party/GRKIT-MIT.txt').read_bytes(),
        'evidence/firmware-receipt.json': json.dumps(receipt, indent=2).encode(),
        'evidence/runtime-manifest.json': json.dumps(native, indent=2).encode(),
        'evidence/service-receipt.json': json.dumps(service, indent=2).encode(),
        'evidence/film-pack-audit.json': json.dumps(film_audit, indent=2).encode(),
    }
    files['SHA256SUMS'] = ''.join(f'{sha(data)}  {name}\n'
                                  for name, data in sorted(files.items())).encode()
    created = False
    try:
        with output.open('xb') as stream:
            created = True
            os.chmod(output, 0o600)
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
        with zipfile.ZipFile(output) as archive:
            need(archive.testzip() is None and
                 all(sha(archive.read(name)) == sha(data) for name, data in files.items()), 'ZIP readback differs')
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    return {'zip': str(output.resolve()), 'sha256': sha(output.read_bytes()),
            'firmwareSha256': sha(firmware), 'apkSha256': sha(files['05_ANDROID/GRemote.apk']),
            'verifiedHooks': receipt['verified_hooks'], 'cameraTested': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('candidate', 'apk', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.candidate, args.apk, args.output), ensure_ascii=False))
