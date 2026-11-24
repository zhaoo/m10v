"""Build the R20 GR III controls diagnostic package; Live remains unavailable."""
import argparse, json, os, struct, tempfile, zipfile
from pathlib import Path
from package_gremote_connection import ROOT, _audit_elf, _candidate, _film_pack, build_service, need, sha
from package_gr3_roll_log import LOG_START, android_apk, diagnostic_startup

APK_SHA256 = '77965cf4fab8a79699d0a1df35d3f2da087db5e505a8f4ec34ddff2478c5b6fd'
R20_START = LOG_START.replace(b'R16', b'R20').replace(b'r16', b'r20')
R20_TTL = diagnostic_startup().replace(b'R16', b'R20').replace(b'r16', b'r20')
INSTRUCTIONS = '''M10V GR III 2.10 R20 ADJ/Fn 修复验证完整包
修复扩展 ADJ 第 6–9 格「影像控制」按 Fn 仍设置当前卷的问题：光标停在哪款已启用胶卷，就设置该卷；不用先按 OK 切换使用。保留 MENU 返回、R19 画幅修正和已有边框诊断。仅适用 GR III 官方 2.10 基线，尚待本候选真机验证。
Live 仍显示“暂不可用”，采集、缓存与传输关闭。本包仅显式打开原生日志和 SD 服务诊断。

安装
先关机并备份 SD 卡、原固件、SCRIPT/STARTUP.TTL、M10V 目录及自定义 LUT，不删除照片或个人配方。
1. 按原已确认升级流程使用 01_FIRMWARE/SD_ROOT/fwdc239b.bin，完成后关机并移走卡根目录升级 BIN。
2. 合并 02_SERVICE/SD_ROOT/SCRIPT 内容到卡中；已有其他插件时合并 STARTUP.TTL 启动命令，保留原启动顺序，不覆盖整个 SCRIPT。
3. 匹配胶卷与菜单资源分别在 03_FILMS 和 04_MENU，将对应 SD_ROOT/M10V 下单个文件放到卡中。保留自定义 LUT 和机身配置。
4. Android 可使用随包 05_ANDROID/GRemote.apk（正式 1.2.15）；离线复现优先不连接手机。
相机须已启用 SD 脚本，服务每次开机只启动一次，不在同次开机热重启。本包不自动写卡或刷机。

本次检查
1. 记录当前胶卷模式（拍摄中 / 已暂停 / 未开卷）。保留已有胶卷和设置，不新建或删除胶卷。
2. 在 ADJ 影像控制中高亮第一款胶卷，按 Fn，确认详情名称，修改一个参数并返回。再高亮第二款胶卷按 Fn，修改另一值；重新进入两款，确认各自保留独立设置。不要只按 OK 切换胶卷。
3. 退出 ADJ 后核对原拍摄卷未被这些参数操作切换；只有按 OK 确认选卷时才切换当前卷。原厂 ADJ 与扩展第 6–9 格的影像控制均可用上述方式检查。
4. 关机后取卡并尽快复制日志，避免反复开机覆盖尾窗。本次不要求重新测试此前所有功能。若另行复现边框黑屏，保留未编辑 JPG，黑屏后等待至少 6 秒再半按恢复。

回传文件
SD 卡根目录所有 M10VMN*.BIN、M10VCP*.BIN、M10VIO*.BIN、M10VAK*.BIN；如存在 M10VTO*.BIN 也一起保留。
M10V 目录中的 R20BOOT.TXT、R20WORK.TXT、R20FAULT.TXT、R20RAM.TXT、R20TTL.TXT：存在的全部回传；没有生成的请说明“未生成”，不要创建空文件。
同时保留本包 manifest.json / 构建来源.json，以及上述测试 JPG 或设置照片。日志不存在不能单独证明代码没有执行。
本包包含 360-383 胶卷选择与 Fn 交接、400-417 画幅相关日志；另由 Linux 服务将 JPEG 等待前后计数与 QuickView 状态写入 R20WORK.TXT 的 R20_REVIEW 行；拍摄回调不写 SD；R20_STAGE / R20_BANK 补充真实回显发布、接收、转换、显示、原生图像库释放和几何通知的标量记录。边框黑屏的机身根因尚未确认；不能将本包诊断能力当作黑屏修复结论。

恢复
关机后恢复备份的 STARTUP.TTL 和原固件，仅撤除本包 MCW1101 服务，保留其他插件、设置和照片。
'''


def package(candidate, apk, output):
    candidate, apk, output = Path(candidate), Path(apk), Path(output)
    need(not output.exists(), 'output already exists')
    receipt, firmware, native, identity = _candidate(candidate)
    need(native.get('roll_capture') and native.get('menu_hub'), 'R20 requires the native roll/menu bundle')
    need(native.get('debug_mode') is True and native.get('debug_log') and native['companion'].get('debug_mode') is True,
         'R20 requires explicit native and companion-owner debug mode')
    need(native.get('debug_scope') == 'controls' and native['debug_log'].get('adj_exit_trace') is True,
         'R20 requires focused controls diagnostics')
    need(native['companion']['extensions']['features'].get('live', False) is False,
         'R20 controls diagnostics must keep Live disabled')
    need(not any(name.startswith(('m10v_live_device_', 'm10v_live_camera_')) for name in native['symbols']),
         'Live producer or allocator remains linked')
    need(native['roll_capture'].get('review_diagnostic') == 'scalar-pre/post-JPEG-wait-v1',
         'R20 requires the read-only JPEG/review diagnostic suffix')
    need(native['roll_capture'].get('review_handoffs') == 'native-publication-playback-display-v2',
         'R20 requires real review publication/Playback/display checkpoints')
    need(sha(apk.read_bytes()) == APK_SHA256, 'R20 requires the frozen formal GRemote 1.2.15 APK')
    menu = (ROOT/'web/gr3/MENU-R8.M10').read_bytes()
    menu_meta = json.loads((ROOT/'web/gr3/MENU-R8.json').read_text())
    need(sha(menu) == menu_meta['sha256'] and struct.unpack_from('<4sIII', menu) ==
         (b'MNU8', 8, menu_meta['record_count'], len(menu)), 'menu archive differs')
    with tempfile.TemporaryDirectory(prefix='gr3-controls-r20-') as temporary:
        work = Path(temporary)
        service = build_service(work/'service', candidate_dir=candidate, hotspot_pairing=True,
            catalog_hash=identity['catalogHash'], renderer_hash=identity['rendererHash'], diagnostics=True)
        elf = (work/'service/m10v-companion.elf').read_bytes()
        _audit_elf(elf)
        need(service['firmwareSha256'] == sha(firmware) and service['serviceSha256'] == sha(elf), 'firmware/service identity differs')
        need(service['diagnosticsEnabled'] is True and service['liveEnabled'] is False and
             all(marker in elf for marker in (b'R20_ELF_ENTRY', b'R20WORK.TXT', b'R20FAULT.TXT', b'ROLL_DIAG', b'ROLL_SD', b'R20_REVIEW', b'R20_STAGE', b'R20_BANK')),
             'R20 diagnostics are not linked or Live is enabled')
        need(not (work/'service/pairing.json').exists(), 'retained pairing credentials are prohibited')
        need(service['reachableStackBoundBytes'] <= 4096 and service['stagingStaticBytes'] + 4096 <= 65536,
             'service memory budget exceeded')
        films, film_audit = _film_pack(work, identity)
        apk_bytes = android_apk(apk, identity, service)
    files = {'开始前必读.txt':INSTRUCTIONS.encode(),
        '01_FIRMWARE/SD_ROOT/fwdc239b.bin':firmware,
        '02_SERVICE/SD_ROOT/SCRIPT/STARTUP.TTL':R20_TTL,
        '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.SH':R20_START,
        '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.BIN':elf,
        '03_FILMS/SD_ROOT/M10V/FILMS.M10':films,
        '04_MENU/SD_ROOT/M10V/MENU.M10':menu,
        '05_ANDROID/GRemote.apk':apk_bytes,
        'provenance/firmware-receipt.json':json.dumps(receipt,indent=2).encode(),
        'provenance/runtime-manifest.json':json.dumps(native,indent=2).encode(),
        'provenance/service-receipt.json':json.dumps(service,indent=2).encode(),
        'provenance/film-pack-audit.json':json.dumps(film_audit,indent=2).encode()}
    provenance = {'label':'R20 controls diagnostics, Live unavailable', 'nativeDebug':True,
        'serviceDiagnostics':True,'debugScope':native['debug_scope'],'captureProfileEnabled':bool(native.get('capture_profile')),'liveAvailable':False,'cameraTested':False,'fixConfirmed':False,
        'identity':identity,'firmwareSha256':sha(firmware),'serviceSha256':sha(elf),
        'apkVersion':'1.2.15','apkSha256':sha(apk_bytes),'configurationSha256':receipt.get('configuration_sha256'),
        'nativeSourceFingerprint':receipt.get('runtime_source_sha256'),'serviceSourceFingerprint':service['sourceFingerprint'],
        'debugLog':native['debug_log'],'stackBoundBytes':service['reachableStackBoundBytes'],
        'staticStagingBytes':service['stagingStaticBytes']}
    files['构建来源.json']=(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n').encode()
    manifest={'schema':'m10v-gr3-controls-diagnostic-package/v1',**provenance,
              'files':{name:{'sha256':sha(data),'bytes':len(data)} for name,data in files.items()}}
    files['manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    files['SHA256SUMS']=''.join(f'{sha(data)}  {name}\n' for name,data in sorted(files.items())).encode()
    created=False
    try:
        with output.open('xb') as stream:
            created=True
            os.chmod(output,0o600)
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
                for name,data in files.items():archive.writestr(name,data)
        with zipfile.ZipFile(output) as archive:
            need(archive.testzip() is None and all(archive.read(name)==data for name,data in files.items()), 'ZIP readback differs')
    except BaseException:
        if created:output.unlink(missing_ok=True)
        raise
    return {'zip':str(output.resolve()),'sha256':sha(output.read_bytes()),'firmwareSha256':sha(firmware),
            'serviceSha256':sha(elf),'apkSha256':sha(apk_bytes),'verifiedHooks':receipt['verified_hooks'],
            'liveAvailable':False,'diagnosticsEnabled':True,'cameraTested':False,'fixConfirmed':False}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','apk','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(package(args.candidate,args.apk,args.output),ensure_ascii=False,indent=2))
