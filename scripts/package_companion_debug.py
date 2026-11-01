"""Bundle a private, manually installed GR III companion debug package.
Never writes SD, starts service, installs APK, or publishes artifacts.
"""
import argparse,hashlib,json,os,re,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def need(ok,message):
 if not ok:raise ValueError(message)
def package_debug(candidate,service,apk,out):
 candidate,service,apk,out=map(Path,(candidate,service,apk,out))
 if out.exists():raise FileExistsError(out)
 receipt=json.loads((candidate/'M10V-build-receipt.json').read_text());need(receipt.get('filename')=='fwdc239b.bin','candidate filename differs')
 firmware=(candidate/'fwdc239b.bin').read_bytes();need(sha(firmware)==receipt['candidate_sha256'],'candidate hash differs')
 native=json.loads((candidate/'M10V-runtime-manifest.json').read_text());identity=native['companion']['identity']
 meta=json.loads((service/'service-receipt.json').read_text());elf=(service/'m10v-companion.elf').read_bytes()
 need(meta.get('installable')is True and meta.get('cameraPassed')is False and meta.get('firmwareSha256')==sha(firmware),'service is not matching debug candidate')
 need(meta['buildId']==identity['buildId'] and meta['catalogHash']==identity['catalogHash'] and meta['rendererHash']==identity['rendererHash'] and sha(elf)==meta['serviceSha256'],'service identity differs')
 pair=(service/'pairing.json').read_bytes();pairing=json.loads(pair)
 need(pairing.get('schema')=='m10v.companion-pairing/v1' and pairing.get('model')=='GR III' and re.fullmatch('[a-f0-9]{64}',pairing.get('keyHex','')) is not None,'invalid private pairing')
 key=bytes.fromhex(pairing['keyHex']);need(sha(key)[:32]==pairing['keyId'] and key in elf and bytes.fromhex(pairing['instanceId']) in elf,'pairing differs from executable')
 with zipfile.ZipFile(apk)as z:
  names=z.namelist();need(len(names)==len(set(names)),'duplicate APK entries')
  prefix='assets/flutter_assets/assets/films/'
  catalog=json.loads(z.read(prefix+'camera-catalog.json'));contract=z.read(prefix+'camera-contract.json')
  canonical=json.dumps({k:v for k,v in catalog.items()if k!='hash'},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
  need(sha(canonical)==catalog['hash']==identity['catalogHash'] and catalog['rendererHash']==identity['rendererHash'],'APK camera catalog differs')
  need(sha(contract)==meta['registrySha256'],'APK camera contract differs')
  # The separate camera contract must not replace the local imaging engine.
  local=json.loads(z.read(prefix+'catalog.json'));source=z.read(prefix+'source-manifest.json');local_source=json.loads(source)
  marker=('GREMOTE_FILM_V1:'+local['rendererHash']+':'+local['hash']+':'+sha(source)).encode()
  libs=[name for name in names if re.fullmatch(r'lib/[^/]+/libgremote_imaging\.so',name)]
  need(libs and all(re.findall(rb'GREMOTE_FILM_V1:[a-f0-9]{64}:[a-f0-9]{64}:[a-f0-9]{64}',z.read(name))==[marker] for name in libs),'APK local renderer identity differs')
  need(local_source['catalogHash']==local['hash'] and local_source['rendererHash']==local['rendererHash'],'APK local source identity differs')
 files={
  '01_FIRMWARE/SD_ROOT/fwdc239b.bin':firmware,
  '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.BIN':elf,
  '02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.SH':b'''#!/bin/sh
base=/media/storage1/SCRIPT/MCW1101
# One process per boot; never replay an old mailbox after process restart.
if mkdir /tmp/m10v-companion-1101.lock 2>/dev/null; then
 ( "$base/SERVICE.BIN"; status=$?; echo M10V_SERVICE_EXIT_$status ) </dev/null >/tmp/m10v-companion-1101.log 2>&1 &
fi
exit 0
''',
  '02_SERVICE/SD_ROOT/SCRIPT/STARTUP.TTL':("mpause 2000\r\nsendln 'lcmd_resp on'\r\nmcw_boot = 0\r\n:mcw_retry\r\nsendln 'lcmd sh /media/storage1/SCRIPT/MCW1101/SERVICE.SH'\r\nmpause 1000\r\nmcw_boot = mcw_boot + 1\r\nif mcw_boot < 8 goto mcw_retry\r\nend\r\n").encode(),
  'private/pairing.json':pair,
  'GRemote.apk':apk.read_bytes(),
  'evidence/firmware-receipt.json':(candidate/'M10V-build-receipt.json').read_bytes(),
  'evidence/runtime-manifest.json':(candidate/'M10V-runtime-manifest.json').read_bytes(),
  'evidence/service-receipt.json':(service/'service-receipt.json').read_bytes(),
 }
 files['手机安装说明.txt']=('''M10V × GRemote 十槽位联调包
仅用于 GR III 2.10，尚未通过本包真机验收。不得用于其他机型。
本包包含个人配对密钥，请勿公开分享。

1. 先将相机关机。用手机读写 SD 卡，备份现有 SCRIPT/STARTUP.TTL 与机身胶卷存档；电脑不写卡。
2. 仅将 01_FIRMWARE/SD_ROOT/fwdc239b.bin 复制到卡根目录，按此前相同的机身升级步骤安装。保留旧版固件备份。
3. 升级完成关机后，移走卡根目录 fwdc239b.bin；卡上不要留下 ModeSet 或 DEVELOP.MOD。
4. 将 02_SERVICE/SD_ROOT 中两个文件路径复制到卡上，替换本次已核对的旧探针 STARTUP.TTL；不要删除整个 SCRIPT，也不覆盖 M10V/FILMS.M10、个人配方或其他插件。
5. 安装 GRemote.apk，保留应用数据。把 private/pairing.json 放在手机下载目录，通过 App 相机胶卷页面导入配对文件。
6. 将卡装回相机，正常开机，手机连接相机 Wi-Fi，再接 USB 调试。启动后约一分钟内读取机身配置；本服务每次开机只启动一次，失败后需要关机重启，不热重装。
7. 先读取确认十个槽位、胶卷和当前启用槽，再修改一项已支持参数并读回。装卷是先保存再单独切换启用槽；未读回确认的写入不能视为成功。

当前范围：内置胶卷参数、十槽位读取、保存与正式切换；自定义 LUT 无线上传关闭。旧颗粒尺寸、漏光参数仅保留读取，不通过此路径写入。
本包不触发拍照或自动对焦，不改变原有照片文件。真实缓存一致性、连续拍摄性能和设备兼容性需要另行实测。

撤除/恢复：关机后恢复备份的 STARTUP.TTL，仅撤除 SCRIPT/MCW1101；需要回退固件时使用此前备份并按机身更新流程操作。SD 脚本开关原已启用，本包不再写开关。
'''+ '\n固件标识：'+identity['buildId']+'\n').encode()
 manifest={'schema':'m10v-companion-debug-delivery/v2','buildId':identity['buildId'],'model':'GR III','cameraPassed':False,'wirelessReady':False,'validation':'host-and-arm-only','catalogHash':identity['catalogHash'],'rendererHash':identity['rendererHash'],'firmwareSha256':sha(firmware),'apkSha256':sha(files['GRemote.apk']),'sourceRevision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'sourceDirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),'files':{name:{'sha256':sha(data),'bytes':len(data)}for name,data in files.items()}}
 files['manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
 files['SHA256SUMS']=''.join(sha(data)+'  '+name+'\n'for name,data in sorted(files.items())).encode()
 out.mkdir(parents=True,mode=0o700)
 for name,data in files.items():
  target=out/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);target.write_bytes(data);os.chmod(target,0o600)
 with zipfile.ZipFile(out.with_suffix('.zip'),'x',zipfile.ZIP_DEFLATED)as z:
  for name in files:z.write(out/name,name)
 os.chmod(out.with_suffix('.zip'),0o600)
 return manifest
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['candidate','service','apk','out']:p.add_argument('--'+key,required=True)
 a=p.parse_args();m=package_debug(a.candidate,a.service,a.apk,a.out);print(json.dumps({k:m[k]for k in ['buildId','cameraPassed','firmwareSha256','apkSha256']}))
