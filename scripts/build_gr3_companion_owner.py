"""Optional GR III AppMain component; produces bytes only, never installs."""
import hashlib,json,os,re,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCES=['native/companion/runtime.c','native/companion/auth.c','native/companion/operations.c','native/companion/transaction.c','native/companion/extensions.c','native/companion/resident_bridge.c','native/gr3/m10v_companion_owner.c']
HEADERS=['native/companion/auth.h','native/companion/http_parser.h','native/companion/json.h','native/companion/operations.h','native/companion/transaction.h','native/companion/extensions.h','native/gr3/m10v_companion_extensions.inc','native/gr3/m10v_torn_overlay.h','native/gr3/m10v_zoom_camera.h','native/gr3/m10v_zoom.h','native/gr3/m10v_isp_effects_camera.h','native/gr3/m10v_isp_effects_state.h','native/companion/resident_bridge.h','native/companion/generated_contract.h','native/gr3/m10v_companion_owner.h','native/gr3/m10v_library.h','native/gr3/m10v_tone.h','native/gr3/m10v_sd_library.h','contracts/companion-v1.json','contracts/extensions-v1.json','scripts/build_gr3_companion_owner.py']
def identity_flags(identity):
 if not isinstance(identity,dict) or set(identity)!={'buildId','catalogHash','rendererHash'} or any(type(v)is not str or not re.fullmatch('[0-9a-f]{64}',v) or v=='0'*64 for v in identity.values()):raise ValueError('invalid companion build/catalog/renderer identity')
 return ['-DM10V_COMPANION_ENABLED=1',*[f'-DM10V_COMPANION_{label}_BYTES={{'+','.join(str(b) for b in bytes.fromhex(identity[key]))+'}' for label,key in [('BUILD','buildId'),('CATALOG','catalogHash'),('RENDERER','rendererHash')]]]
def build_companion_owner(base,imports,identity,folder,extensions=None):
 from scripts.build_gr3_m10v_library import FLAGS,link_object
 extensions=extensions or {}
 if set(extensions)-{'ab','hdf','border','isp','zoom','aspect','torn'} or any(type(v)is not bool for v in extensions.values()):raise ValueError('invalid companion feature flags')
 feature_flags=[f'-DM10V_COMPANION_EXT_{name.upper()}={int(extensions.get(name,False))}' for name in ['ab','hdf','border','isp','zoom','aspect']]
 flags=feature_flags+identity_flags(identity)+['-DM10V_COMPANION_RTOS_ONLY=1','-DM10V_LIVE_COLOR=1','-DM10V_APPENDED_SLOTS=1',f'-DM10V_TORN_ENABLED={int(extensions.get("torn",False))}']
 if base&15:raise ValueError('companion component must be aligned')
 compiler=os.environ.get('M10V_LLVM_CLANG') or shutil.which('clang');folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 image=bytearray();symbols=dict(imports);exports={}
 for index,name in enumerate(SOURCES):
  obj=folder/f'companion-{index}.o'
  subprocess.run([compiler,*FLAGS,*flags,'-c',str(ROOT/name),'-o',str(obj)],check=True,capture_output=True)
  at=(base+len(image)+15)&~15
  registry={
   'runtime.c':('__aeabi_',('memcpy','memset'),()),
   'auth.c':('m10v_auth_',('m10v_sha256_init','m10v_sha256_update','m10v_sha256_finish','m10v_sha256','m10v_hmac256','m10v_constant_equal','m10v_hex','m10v_unhex'),()),
   'operations.c':('m10v_operation_',('m10v_patch_size',),('m10v_operation_parse','m10v_operation_parse_tokens')),
   'transaction.c':('m10v_companion_',(),()),'extensions.c':('m10v_extensions_',(),()),'resident_bridge.c':('m10v_resident_',(),()),'m10v_companion_owner.c':('m10v_companion_ui_',(),())}
  prefix,extra,omitted=registry[Path(name).name]
  try:code,entries=link_object(obj.read_bytes(),at,symbols,prefix,additional_exports=extra,omitted_exports=omitted)
  except ValueError as error:raise ValueError(name+": "+str(error)) from error
  image+=bytes(at-base-len(image))+code;symbols.update(entries);exports.update(entries)
 available=((1<<17)-(1<<12)) | (7 if extensions.get('ab') else 0) | (1<<3 if extensions.get('hdf') else 0) | (1<<4 if extensions.get('border') else 0) | ((1<<12)-(1<<5) if extensions.get('isp') else 0) | (7<<21 if extensions.get('isp') else 0) | (7<<17 if extensions.get('zoom') else 0) | (1<<20 if extensions.get('aspect') else 0)
 if extensions.get('torn'):available|=1<<24
 report={'extensions':{'schema':'m10v.extensions/v1','available':available,'features':extensions,'powerImages':'firmwareBuildOnly'},'schema':'m10v-companion-owner/v2','enabled':True,'base':base,'bytes':len(image),'descriptor_offset':0x6400,'descriptor_bytes':64,'owner_bytes':0x6440,'per_owner_allocation_limit':16384,'mailbox_lifetime':'retainedUntilPoweroff','requestOffset':128,'payloadBytes':1024,'identity':identity,'symbols':exports,'camera_tested':False,'continuousCacheValidated':False,'sources':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES+HEADERS}}
 return bytes(image),report
