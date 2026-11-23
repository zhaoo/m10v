"""Assemble the GR III formal offline roll release, with Live unavailable and no logs."""
import argparse, json, os, re, struct, tempfile, zipfile
from pathlib import Path
from package_gremote_connection import ROOT, STARTUP_TTL, _audit_elf, _candidate, _film_pack, build_service, need, sha
from package_gr3_roll_log import android_apk

SERVICE_SH = b'''#!/bin/sh
base=/media/storage1/SCRIPT/MCW1101
if mkdir /tmp/m10v-companion-1101.lock 2>/dev/null; then
 ( "$base/SERVICE.BIN" ) </dev/null >/dev/null 2>&1 &
fi
exit 0
'''
FORBIDDEN = (b'R16WORK.TXT', b'R16FAULT.TXT', b'm10v-worker-1101.log', b'R16_ELF_ENTRY', b'ROLL_DIAG', b'ROLL_SD')

def package(candidate, apk, output):
    candidate, apk, output = Path(candidate), Path(apk), Path(output)
    need(not output.exists(), 'output already exists')
    receipt, firmware, native, identity = _candidate(candidate)
    need(native.get('roll_capture') and native.get('menu_hub'), 'formal release requires offline roll and menu')
    need(native['companion']['extensions']['features'].get('live', False) is False,
         'formal release must disable native Live')
    need(not any(name.startswith('m10v_live_device_') or name.startswith('m10v_live_camera_') for name in native['symbols']),
         'Live producer or allocator remains linked')
    need(native.get('debug_mode') is False, 'debug firmware is prohibited')
    menu = (ROOT/'web/gr3/MENU-R8.M10').read_bytes()
    menu_meta = json.loads((ROOT/'web/gr3/MENU-R8.json').read_text())
    need(sha(menu) == menu_meta['sha256'] and struct.unpack_from('<4sIII', menu) ==
         (b'MNU8', 8, menu_meta['record_count'], len(menu)), 'menu resource differs')
    with tempfile.TemporaryDirectory(prefix='gr3-formal-') as temporary:
        work = Path(temporary)
        service = build_service(work/'service', candidate_dir=candidate, hotspot_pairing=True,
            catalog_hash=identity['catalogHash'], renderer_hash=identity['rendererHash'], diagnostics=False)
        elf = (work/'service/m10v-companion.elf').read_bytes()
        _audit_elf(elf)
        need(service['firmwareSha256'] == sha(firmware) and service['serviceSha256'] == sha(elf), 'service identity differs')
        need(service['diagnosticsEnabled'] is False and service['liveEnabled'] is False and
             not any(marker in elf for marker in FORBIDDEN), 'diagnostic or Live service is prohibited')
        need(service['reachableStackBoundBytes'] <= 4096 and service['stagingStaticBytes'] + 4096 <= 65536,
             'service memory budget exceeded')
        films, film_audit = _film_pack(work, identity)
        apk_bytes = android_apk(apk, identity, service)
    instructions = '''M10V GR III 2.10 正式完整包
仅适用于 GR III 官方 2.10 基线，不适用于 IIIx、IV 或其他机型。
Live 暂不可用，已关闭采集、缓存分配与接口；历史 Live 配置保留但不生效。胶卷模式、离线计数及锁定继续保留。

安装前关机，备份 SD 卡、原固件、SCRIPT/STARTUP.TTL、M10V 目录及自定义 LUT。
1. 按 GR III 固件升级流程使用 01_FIRMWARE/SD_ROOT/fwdc239b.bin，完成后关机并移走卡根目录的升级 BIN。
2. 将 02_SERVICE/SD_ROOT 的 SCRIPT 内容合并到卡中。已有 STARTUP.TTL 或插件时保留原配置并合并启动命令，不覆盖整个 SCRIPT。
3. 将 03_FILMS/SD_ROOT/M10V/FILMS.M10 和 04_MENU/SD_ROOT/M10V/MENU.M10 放到卡的 M10V 目录；保留自定义 LUT 和个人配置。
4. Android 安装 05_ANDROID/GRemote.apk。相机开机后连接相机 Wi-Fi，再打开 App。
相机须已启用 SD 脚本；服务每次开机只启动一次。异常时关机重开，勿在同次开机热重启。
本包默认不生成启动、工作、故障、RAM 或 TTL 诊断日志，不自动写卡或刷机。
恢复：关机后恢复备份的 STARTUP.TTL 和固件，仅撤除本包 MCW1101 服务；保留其他插件、设置和照片。
真机适用范围沿用已反馈的胶卷和连接结果；本次正式产物的离线验证不替代新增真机性能结论。
'''
    files = {'开始前必读.txt': instructions.encode(),
        '01_FIRMWARE/SD_ROOT/fwdc239b.bin':firmware,
        '02_SERVICE/SD_ROOT/SCRIPT/STARTUP.TTL':STARTUP_TTL,
        '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.SH':SERVICE_SH,
        '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.BIN':elf,
        '03_FILMS/SD_ROOT/M10V/FILMS.M10':films,
        '04_MENU/SD_ROOT/M10V/MENU.M10':menu,
        '05_ANDROID/GRemote.apk':apk_bytes}
    manifest = {'schema':'m10v-gr3-formal-package/v1','model':'GR III','firmwareVersion':'2.10',
        'liveAvailable':False,'diagnosticsEnabled':False,'identity':identity,
        'sourceFingerprint':service['sourceFingerprint'],'firmwareSha256':sha(firmware),
        'serviceSha256':sha(elf),'stackBoundBytes':service['reachableStackBoundBytes'],
        'staticStagingBytes':service['stagingStaticBytes'],'cameraTested':False,
        'files':{name:{'sha256':sha(data),'bytes':len(data)} for name,data in files.items()}}
    files['manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    files['SHA256SUMS']=''.join(f'{sha(data)}  {name}\n' for name,data in sorted(files.items())).encode()
    try:
        with output.open('xb') as stream:
            os.chmod(output,0o600)
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
                for name,data in files.items():archive.writestr(name,data)
        with zipfile.ZipFile(output) as archive:
            need(archive.testzip() is None, 'archive CRC failed')
            for name,data in files.items():need(archive.read(name)==data,'archive readback failed')
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {'path':str(output.resolve()),'sha256':sha(output.read_bytes()),'bytes':output.stat().st_size,
            'firmwareSha256':sha(firmware),'serviceSha256':sha(elf),'identity':identity,
            'stackBoundBytes':service['reachableStackBoundBytes'],'staticStagingBytes':service['stagingStaticBytes']}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--apk',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(package(args.candidate,args.apk,args.out),ensure_ascii=False,indent=2))
