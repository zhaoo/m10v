"""Bundle a private, manually installed GR III companion debug package.
Never writes SD, starts service, installs APK, or publishes artifacts.
"""
import argparse,hashlib,json,os,re,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def need(ok,message):
 if not ok:raise ValueError(message)
def _extension_info(native):
 marker=native.get('companion',{}).get('extensions')
 if marker is None:return None
 need(isinstance(marker,dict) and marker.get('schema')=='m10v.extensions/v1','extension schema differs')
 need(type(marker.get('available'))is int and 0<=marker['available']<(1<<21),'extension availability differs')
 need(isinstance(marker.get('features'),dict) and set(marker['features'])=={'ab','hdf','border','isp','zoom','aspect'} and all(type(v)is bool for v in marker['features'].values()),'extension features differ')
 need(marker.get('powerImages')=='firmwareBuildOnly','extension power images boundary differs')
 contract=(ROOT/'contracts/extensions-v1.json').read_bytes()
 need(native.get('companion',{}).get('sources',{}).get('contracts/extensions-v1.json')==sha(contract),'extension contract source differs')
 value=json.loads(contract);canonical=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
 digest=sha(canonical)
 need(value.get('schema')==marker['schema'] and digest=='9df047418574e23fd399a0c59491aecc9ea212dbf119a79ff29532aec6493628','extension contract identity differs')
 return {**marker,'contractHash':digest}

def _extensions_readme(identity,extensions,retained,has_film):
 pairing=('本包已核验沿用旧 v2 的相同配对密钥和相机身份；App 已导入该配对时无需重新导入。'
          if retained else '首次使用时导入 private/pairing.json；沿用旧 v2 相同配对且 App 已导入时无需重新导入。')
 film=('本包附匹配的 M10V/FILMS.M10。先备份旧文件，仅在确认使用本包胶卷库时替换该单个文件；不要删除机身设置、个人配方和照片。'
       if has_film else '本包不覆盖 M10V/FILMS.M10；保留卡上已有胶卷库、个人配方与照片。')
 return ('''M10V × GRemote 相机扩展测试包
仅用于 GR III 2.10，尚未通过本包真机验收。不得用于其他机型。
本包含个人配对密钥，请勿公开分享。

安装与更新
1. 相机关机，用手机读卡器备份现有 SCRIPT/STARTUP.TTL、机身设置、胶卷库与照片。电脑不写卡。
2. 仅将 01_FIRMWARE/SD_ROOT/fwdc239b.bin 复制到卡根目录，按之前的机身升级流程安装；保留旧固件备份。
3. 升级结束关机后移走卡根目录 fwdc239b.bin；不要从其他研究包添加 ModeSet 或 DEVELOP.MOD。
4. 服务沿用旧 v2 的 SCRIPT/MCW1101 路径（SERVICE.BIN 和 SERVICE.SH），每次开机只启动一次。关机后替换此目录中的两个服务文件。
5. 仅当现有 STARTUP.TTL 就是旧 v2 启动脚本时，才用本包 STARTUP.TTL 替换。若用户添加了其他插件，必须先合并启动逻辑并保留插件启动顺序；不要直接覆盖自定义启动脚本。
6. 不要删除整个 SCRIPT，不覆盖其他插件、个人设置或照片。本包不写入持久模式开关，不更改已启用的 SD 脚本模式。
7. 安装 GRemote.apk，保留应用数据。'''+pairing+'\n8. '+film+'''
9. 装回卡并正常开机，手机连接相机 Wi-Fi。在 App「相机 → 扩展」先读取机身状态，再修改一项并等待机身读回确认。

21 项扩展设置（是否可用以本包已安装组件及 App 读取的机身可用项为准）
功能：快切开关、快切 A、快切 B。
效果：HDF、边框、颗粒模式、颗粒尺寸、漏光强度、漏光位置、漏光范围、模糊强度、模糊范围。
水印：时间水印、日期格式、水印位置、水印颜色、胶卷名称。
焦距：第一档焦距、第二档焦距、当前焦距档；GR III 两档范围均为 28–50 mm。
画幅：3:2、1:1、4:3、16:9、XPan、6×7、Half 3:4。

每次仅修改一个数值字段；不同设置使用独立存档，不承诺跨存档原子保存。只有持久保存/运行状态读回与原请求相符才显示成功。
快切开启时，快切 A/B 配对只读；先关闭快切再修改配对。快切重启后默认关闭，已保存配对保留。
Half 3:4 使用两次拍摄完成双格合成；离开 Half 会取消尚未完成的配对。合成、回放与连续拍摄的真实表现仍需机身验证。
开机画面与关机画面仅支持固件构建时替换（firmwareBuildOnly），本无线接口不上传或即时更换图片。

结果待核对与恢复
遇到「结果待核对」不要重复提交，也不要自动重放原写入。先核对原请求回执；若断连、重启或回执无法确认，重新读取并手动复核机身实际状态后，再决定后续操作。
服务失败后需要关机重启，不在同一开机周期热重启服务。撤除服务时先关机，恢复已备份的 STARTUP.TTL，仅撤除本包 SCRIPT/MCW1101；不要删除其他脚本、设置或照片。回退固件使用原备份并按机身更新流程操作。
本包不会以拍照替代对焦，也不自动触发拍摄。离线测试、构建与 ARM 模拟结果不能替代真机性能、缓存一致性、成片质量或设备兼容性验收。
'''+ '\n固件标识：'+identity['buildId']+'\n扩展协议：'+extensions['schema']+'\n扩展合同：'+extensions['contractHash']+'\n')

def package_debug(candidate,service,apk,out,*,prior_pairing=None,film_pack=None):
 candidate,service,apk,out=map(Path,(candidate,service,apk,out))
 if out.exists():raise FileExistsError(out)
 receipt=json.loads((candidate/'M10V-build-receipt.json').read_text());need(receipt.get('filename')=='fwdc239b.bin','candidate filename differs')
 firmware=(candidate/'fwdc239b.bin').read_bytes();need(sha(firmware)==receipt['candidate_sha256'],'candidate hash differs')
 native=json.loads((candidate/'M10V-runtime-manifest.json').read_text());identity=native['companion']['identity'];extensions=_extension_info(native)
 meta=json.loads((service/'service-receipt.json').read_text());elf=(service/'m10v-companion.elf').read_bytes()
 need(meta.get('installable')is True and meta.get('cameraPassed')is False and meta.get('firmwareSha256')==sha(firmware),'service is not matching debug candidate')
 need(meta['buildId']==identity['buildId'] and meta['catalogHash']==identity['catalogHash'] and meta['rendererHash']==identity['rendererHash'] and sha(elf)==meta['serviceSha256'],'service identity differs')
 pair=(service/'pairing.json').read_bytes();pairing=json.loads(pair)
 need(pairing.get('schema')=='m10v.companion-pairing/v1' and pairing.get('model')=='GR III' and re.fullmatch('[a-f0-9]{64}',pairing.get('keyHex','')) is not None,'invalid private pairing')
 key=bytes.fromhex(pairing['keyHex']);need(sha(key)[:32]==pairing['keyId'] and key in elf and bytes.fromhex(pairing['instanceId']) in elf,'pairing differs from executable')
 retained=False
 if prior_pairing is not None:
  need(json.loads(Path(prior_pairing).read_bytes())==pairing,'prior pairing differs; refusing identity rotation');retained=True
 film=None;film_audit=None
 if film_pack is not None:
  film=Path(film_pack).read_bytes()
  command="import{readFileSync}from'node:fs';import{auditSdFilmPack}from'./node/gr3-sd-film-pack.mjs';process.stdout.write(JSON.stringify(auditSdFilmPack(readFileSync(process.argv[1]))));"
  try:film_audit=json.loads(subprocess.check_output(['node','--input-type=module','-e',command,str(Path(film_pack).resolve())],cwd=ROOT,text=True,stderr=subprocess.PIPE))
  except subprocess.CalledProcessError as error:raise ValueError('film pack audit failed')from error
  need(film_audit.get('renderer_sha256')==identity['rendererHash'] and film_audit.get('sha256')==sha(film),'film pack identity differs')
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
  if extensions:
   payloads=[n for n in names if n=='assets/flutter_assets/kernel_blob.bin' or re.fullmatch(r'lib/[^/]+/libapp\.so',n)]
   need(any(extensions['schema'].encode()in z.read(n) and extensions['contractHash'].encode()in z.read(n) for n in payloads),'APK extension identity differs')
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
 if extensions:
  files['手机安装说明.txt']=_extensions_readme(identity,extensions,retained,film is not None).encode()
  files['evidence/extensions-contract.json']=(ROOT/'contracts/extensions-v1.json').read_bytes()
 if film is not None:
  files['03_FILMS/SD_ROOT/M10V/FILMS.M10']=film
  files['evidence/film-pack-audit.json']=(json.dumps(film_audit,indent=2)+'\n').encode()
 manifest={'schema':'m10v-companion-debug-delivery/v2','buildId':identity['buildId'],'model':'GR III','cameraPassed':False,'wirelessReady':False,'validation':'host-and-arm-only','catalogHash':identity['catalogHash'],'rendererHash':identity['rendererHash'],'firmwareSha256':sha(firmware),'apkSha256':sha(files['GRemote.apk']),'sourceRevision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'sourceDirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),'files':{name:{'sha256':sha(data),'bytes':len(data)}for name,data in files.items()}}
 if extensions:manifest['extensions']={**extensions,'pairingRetained':retained}
 if film is not None:manifest['filmPackSha256']=sha(film)
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
 p.add_argument('--prior-pairing',help='Verify exact previous pairing without exposing the key');p.add_argument('--film-pack',help='Optional matching FILMS.M10, audited before packaging')
 a=p.parse_args();m=package_debug(a.candidate,a.service,a.apk,a.out,prior_pairing=a.prior_pairing,film_pack=a.film_pack);print(json.dumps({k:m[k]for k in ['buildId','cameraPassed','firmwareSha256','apkSha256']}))
