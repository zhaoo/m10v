"""Independent extension schema and portable owner transaction contracts."""
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Extensions(unittest.TestCase):
 def test_independent_contract_has_stable_fields_and_hash(self):
  path=ROOT/'contracts/extensions-v1.json'
  self.assertTrue(path.exists(),'extension contract must be independent of film renderer')
  value=json.loads(path.read_text());self.assertEqual(value['schema'],'m10v.extensions/v1')
  self.assertEqual(len(value['fields']),25)
  self.assertEqual([f['id'] for f in value['fields']],list(range(25)))
  self.assertEqual(value['fields'][24],dict(id=24,key='tornSession',min=0,max=4,writeMax=1,persistence='runtime'))
  self.assertEqual([f['persistence'] for f in value['fields'] if f['key'] in ('quickSwitch','focalSlot','aspect')],['runtime']*3)
  header=(ROOT/'native/companion/extensions.h').read_text()
  canonical=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
  self.assertIn(hashlib.sha256(canonical).hexdigest(),header)

 def test_owner_cas_dedup_busy_and_uncertain_write_never_replays(self):
  self.assertTrue((ROOT/'native/companion/extensions.c').exists(),'portable extension transaction is missing')
  with tempfile.TemporaryDirectory() as d:
   exe=Path(d)/'extensions'
   result=subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'native/companion'),str(ROOT/'tests/support_companion_extensions.c'),str(ROOT/'native/companion/extensions.c'),str(ROOT/'native/companion/auth.c'),'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   subprocess.run([str(exe)],check=True)
 def test_json_envelope_rejects_unknown_fields_ranges_and_wrong_types(self):
  self.assertTrue((ROOT/'native/companion/extensions_json.c').exists(),'extension parser is missing')
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'parse.c';exe=Path(d)/'parse'
   body={'requestId':'01'*16,'bootId':'02'*16,'contractHash':'03'*32,'baseRevision':'04'*32,'field':'aspect','value':6}
   cases=[(body,0),({**body,'field':'leakPosition','value':4},5),({**body,'field':'leakPosition','value':5},5),({**body,'field':'imprint','value':7},0),({**body,'field':'imprint','value':8},5),({**body,'extra':1},5),({**body,'value':7},5),({**body,'value':True},5),({**body,'field':'unknown'},5),({**body,'value':-1},5)]
   cases.extend([({**body,'field':'tornSession','value':v},0 if v<2 else 5) for v in range(5)])
   calls=''.join('assert(m10v_extensions_parse((const uint8_t*)'+json.dumps(json.dumps(b))+',strlen('+json.dumps(json.dumps(b))+'),tokens,&p)=='+str(code)+');' for b,code in cases)
   src.write_text('#include "extensions.h"\n#include <assert.h>\n#include <string.h>\nint main(void){m10v_extension_patch p;m10v_json_token tokens[M10V_JSON_TOKENS];'+calls+'return 0;}')
   run=subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'native/companion'),str(src),*[str(ROOT/'native/companion'/f) for f in ['extensions_json.c','extensions.c','auth.c','json.c']],'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(run.returncode,0,run.stderr);subprocess.run([str(exe)],check=True)
