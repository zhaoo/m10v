"""Create a private per-download GR III GRemote ZIP. Never install or publish it."""
import argparse,hashlib,importlib.util,json,os,re,subprocess,tempfile,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def _load(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
_builder=_load('build_companion_service');build_service=_builder.build_service;_audit_elf=_builder._audit_elf
_extension_info=_load('package_companion_debug')._extension_info
MAX_BYTES=70*1024*1024
OFFICIAL_SHA='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'
SERVICE_SH=b'''#!/bin/sh
base=/media/storage1/SCRIPT/MCW1101
# One process per boot; never replay an old mailbox after process restart.
if mkdir /tmp/m10v-companion-1101.lock 2>/dev/null; then
 ( "$base/SERVICE.BIN"; status=$?; echo M10V_SERVICE_EXIT_$status ) </dev/null >/tmp/m10v-companion-1101.log 2>&1 &
fi
exit 0
'''
STARTUP_TTL=("mpause 2000\r\nsendln 'lcmd_resp on'\r\nmcw_boot = 0\r\n:mcw_retry\r\nsendln 'lcmd sh /media/storage1/SCRIPT/MCW1101/SERVICE.SH'\r\nmpause 1000\r\nmcw_boot = mcw_boot + 1\r\nif mcw_boot < 8 goto mcw_retry\r\nend\r\n").encode()

def sha(data):return hashlib.sha256(data).hexdigest()
def need(ok,message):
 if not ok:raise ValueError(message)
def identity(value):
 need(type(value)is dict and set(value)=={'buildId','catalogHash','rendererHash'} and all(type(v)is str and re.fullmatch('[a-f0-9]{64}',v) and v!='0'*64 for v in value.values()),'invalid companion identity')
 return value

def _candidate(folder):
 receipt=json.loads((folder/'M10V-build-receipt.json').read_text())
 need(receipt.get('model')=='GR III' and receipt.get('camera_model')=='gr3' and receipt.get('public_version')=='2.10' and receipt.get('filename')=='fwdc239b.bin' and receipt.get('source_sha256')==OFFICIAL_SHA,'GRemote connection supports exact GR III 2.10 only; IIIx is unsupported')
 firmware_path=folder/'fwdc239b.bin'
 need(0<firmware_path.stat().st_size<=MAX_BYTES,'firmware size exceeds 70 MiB limit')
 firmware=firmware_path.read_bytes()
 need(0<len(firmware)<=MAX_BYTES and len(firmware)==receipt.get('candidate_bytes') and sha(firmware)==receipt.get('candidate_sha256'),'firmware hash or size differs')
 command="import{readFileSync}from'node:fs';import{inspectFirmwareImport}from'./node/firmware.mjs';const r=inspectFirmwareImport(readFileSync(process.argv[1]));process.stdout.write(JSON.stringify({model:r.model,public_version:r.public_version,internal_version:r.internal_version}));"
 checked=subprocess.run([os.environ.get('M10V_NODE','node'),'--input-type=module','-e',command,str(firmware_path.resolve())],cwd=ROOT,capture_output=True,text=True)
 need(checked.returncode==0,'firmware independent decode failed')
 decoded=json.loads(checked.stdout)
 need(decoded=={'model':'GR III','public_version':'2.10','internal_version':'2.10.21.27'},'firmware requires exact GR III 2.10; IIIx is unsupported')
 native=json.loads((folder/'M10V-runtime-manifest.json').read_text())
 component=native.get('companion',{});ident=identity(component.get('identity'))
 need(native.get('camera_model')=='gr3' and component.get('enabled')is True and component.get('schema')=='m10v-companion-owner/v2','GR III 2.10 resident companion is required')
 need(identity(receipt.get('companion_identity'))==ident,'receipt and runtime companion identity differ')
 need(component.get('camera_tested')is False and component.get('continuousCacheValidated')is False,'camera validation status must remain unverified')
 return receipt,firmware,native,ident

def _instructions(ident,has_films):
 films=('本包附匹配的 03_FILMS/SD_ROOT/M10V/FILMS.M10。先备份原文件和自定义 LUT，仅在确认采用本包胶卷库后替换单个文件。' if has_films else '本包不含 FILMS.M10；保留卡上的胶卷库与自定义 LUT。')
 return ('''M10V × GRemote 连接包（个人下载）
仅适用于精确官方 GR III 2.10 基线；GR IIIx / GR II / GR IV 等其他机型不支持。
本候选仅完成离线检查，尚未通过本包真机验收，不代表允许安装。请等待当前候选的明确设备验证安排，不要直接刷机。
首次连接时，相机热点内的 GRemote 会自动建立会话。App 请从 GRemote 官方发布页单独获取：https://github.com/zhaoo/gremote/releases/latest 。本包不含 APK。

准备与人工安装边界
1. 在获得本候选的明确验证安排后，先关机，备份固件、现有 SCRIPT/STARTUP.TTL、机身设置、M10V/FILMS.M10、自定义 LUT、个人配方与照片。
2. 固件位于 01_FIRMWARE/SD_ROOT/fwdc239b.bin。仅按已确认的 GR III 2.10 机身流程操作；完成后关机并移走卡根目录的 BIN。本包不自动刷机、不自动写 SD 卡，不添加 ModeSet / DEVELOP.MOD，不写入持久脚本模式开关。
3. 服务位于 02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.BIN 与 SERVICE.SH。只有已确认 SD 脚本启动方式后才人工放置服务。
4. 本包提供 SCRIPT/STARTUP.TTL 参考启动脚本。不要直接覆盖已有自定义脚本；有其他插件时先合并并保留启动顺序。不要删除整个 SCRIPT，不覆盖机身设置或照片。
5. 使用支持自动连接的 GRemote Android 版本。连上相机自身的 Wi-Fi 后打开 App，无需导入配对文件。
6. 服务每次开机只启动一次；失败后先关机再开机，不在同一开机周期热重启服务。手机连接相机 Wi-Fi 后先读取状态，再修改单项并等待回执和机身读回。
7. '''+films+'''

能力与恢复
是否能读写以实际机身能力和匹配身份为准；无线整库上传关闭，不自动触发拍照或对焦。遇到未知结果不要重放原写入，先读取和手动核对机身状态。
回退：先关机，恢复备份的 STARTUP.TTL，仅撤除本包 SCRIPT/MCW1101，保留其他插件、设置与照片；固件回退使用原备份及已确认的机身流程。
真实缓存一致性、连接与拍摄性能、画质、掉电恢复均待设备验证。离线编译、ELF/哈希检查不能替代真机结果。

固件标识：'''+ident['buildId']+'\n').encode()

def _film_pack(folder,ident):
 target=folder/'FILMS.M10'
 command="import{writeFileSync}from'node:fs';import{buildSdFilmPack,auditSdFilmPack}from'./node/gr3-sd-film-pack.mjs';const b=buildSdFilmPack();writeFileSync(process.argv[1],b,{mode:0o600});process.stdout.write(JSON.stringify(auditSdFilmPack(b)));"
 result=subprocess.run([os.environ.get('M10V_NODE','node'),'--input-type=module','-e',command,str(target)],cwd=ROOT,capture_output=True,text=True)
 need(result.returncode==0,'canonical film generation or audit failed')
 audit=json.loads(result.stdout);film=target.read_bytes()
 need(audit.get('renderer_sha256')==ident['rendererHash'] and audit.get('sha256')==sha(film),'canonical film renderer identity differs')
 return film,audit

def package_connection(candidate_dir,out,*,include_films=True):
 candidate_dir,out=Path(candidate_dir),Path(out)
 if out.exists():raise FileExistsError(out)
 receipt,firmware,native,ident=_candidate(candidate_dir)
 extensions=_extension_info(native)
 with tempfile.TemporaryDirectory(prefix='gremote-package-',dir=candidate_dir) as temp:
  temp=Path(temp);os.chmod(temp,0o700)
  service=temp/'service'
  # No caller-provided key/instance or retained pairing path is accepted.
  meta=build_service(service,catalog_hash=ident['catalogHash'],renderer_hash=ident['rendererHash'],candidate_dir=candidate_dir,hotspot_pairing=True)
  elf=(service/'m10v-companion.elf').read_bytes();_audit_elf(elf)
  need(meta.get('installable')is True and meta.get('cameraPassed')is False and meta.get('firmwareSha256')==sha(firmware) and meta.get('serviceSha256')==sha(elf),'service firmware identity differs')
  need(all(meta.get(k)==ident[k] for k in ['buildId','catalogHash','rendererHash']),'service companion identity differs')
  need(meta.get('pairingPolicy')=='camera-hotspot-per-boot' and not (service/'pairing.json').exists(),'service must use a boot-local hotspot credential')
  files={
   '01_FIRMWARE/SD_ROOT/fwdc239b.bin':firmware,
   '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.BIN':elf,
   '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.SH':SERVICE_SH,
   '02_SERVICE/SD_ROOT/SCRIPT/STARTUP.TTL':STARTUP_TTL,
   'evidence/firmware-receipt.json':(candidate_dir/'M10V-build-receipt.json').read_bytes(),
   'evidence/runtime-manifest.json':(candidate_dir/'M10V-runtime-manifest.json').read_bytes(),
   'evidence/service-receipt.json':(service/'service-receipt.json').read_bytes(),
  }
  if extensions:files['evidence/extensions-contract.json']=(ROOT/'contracts/extensions-v1.json').read_bytes()
  film_audit=None
  if include_films:
   film,film_audit=_film_pack(temp,ident);files['03_FILMS/SD_ROOT/M10V/FILMS.M10']=film
   files['evidence/film-pack-audit.json']=(json.dumps(film_audit,indent=2)+'\n').encode()
  files['开始前必读.txt']=_instructions(ident,include_films)
  manifest={'schema':'m10v-gremote-connection-package/v1','model':'GR III','public_version':'2.10','status':'offline_verified_camera_unverified','camera_tested':False,'installation_allowed':False,'wireless_ready':False,'companion_identity':ident,'firmware_sha256':sha(firmware),'service_sha256':sha(elf),'pairing_policy':'camera-hotspot-per-boot','apk_included':False,'files':{name:{'sha256':sha(data),'bytes':len(data)} for name,data in files.items()}}
  files['manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
  files['SHA256SUMS']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode()
  need(sum(map(len,files.values()))<=MAX_BYTES,'package exceeds 70 MiB unpacked size limit')
  created=False
  try:
   # Exclusive private file creation; no partial ZIP survives an exception.
   with out.open('xb') as handle:
    created=True
    os.chmod(out,0o600)
    with zipfile.ZipFile(handle,'w',zipfile.ZIP_DEFLATED) as archive:
     for name,data in files.items():
      info=zipfile.ZipInfo(name);info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(0o100600<<16)
      archive.writestr(info,data)
   need(out.stat().st_size<=MAX_BYTES,'package exceeds 70 MiB download size limit')
  except BaseException:
   if created:out.unlink(missing_ok=True)
   raise
  return {'schema':manifest['schema'],'model':'GR III','public_version':'2.10','status':manifest['status'],'camera_tested':False,'installation_allowed':False,'sha256':sha(out.read_bytes()),'bytes':out.stat().st_size,'firmware_sha256':sha(firmware),'service_sha256':sha(elf),'companion_identity':ident,'pairing_policy':'camera-hotspot-per-boot','apk_included':False,'film_pack_included':include_films,'files':{name:{'sha256':sha(data),'bytes':len(data)} for name,data in files.items()}}

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate-dir',required=True);parser.add_argument('--out',required=True);parser.add_argument('--without-films',action='store_true');args=parser.parse_args()
 try:print(json.dumps(package_connection(args.candidate_dir,args.out,include_films=not args.without_films)))
 except Exception:raise SystemExit('GRemote package failed independent validation or service build; no package was issued')
