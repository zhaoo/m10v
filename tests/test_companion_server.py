"""Use real sockets against the compiled C service with an explicit host backend."""
import hashlib,hmac,http.client,json,os,subprocess,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
KEY=bytes(range(32)) # Public fixture only; never a package key.
class Server(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name);cls.exe=d/'server'
  result=subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-DM10V_COMPANION_HOST_TEST','-I',str(ROOT/'native/companion'),*[str(ROOT/'native/companion'/f) for f in ['auth.c','http_parser.c','json.c','operations.c','http_server.c','linux_io.c','transaction.c','film_upload.c','extensions.c','extensions_json.c']],*[str(ROOT/'native/gr3'/f) for f in ['m10v_library.c','halation_core.c','film_5207.c','film_harman.c','film_curated.c','film_newstocks.c','film_style_filters_0.c','film_style_filters_1.c','film_d76_0.c','film_d76_1.c','m10v_sd_library.c']],str(ROOT/'tests/support_companion_server.c'),'-o',str(cls.exe)],capture_output=True,text=True)
  if result.returncode:raise AssertionError(result.stderr)
 def setUp(self):
  env=dict(os.environ);self.key=KEY;self.key_id='fixture-key'
  if self._testMethodName=='test_hotspot_bootstrap_reads_and_signs_with_boot_key':env['M10V_TEST_HOTSPOT']='1'
  if self._testMethodName=='test_upload_chunks_verified_then_install_is_separate':env['M10V_TEST_UPLOAD']='1'
  if self._testMethodName=='test_full_ten_slot_snapshot_and_receipt_fit_response_budget':env['M10V_TEST_FULL_TEN']='1'
  if self._testMethodName=='test_async_read_busy_and_submit_waits_for_read_turn':env['M10V_TEST_ASYNC_READ']='1'
  if self._testMethodName=='test_timeout_keeps_unknown_write_locked_but_reads_remain_available':env['M10V_TEST_STALL']='1'
  if self._testMethodName=='test_per_film_state_stays_wire_compatible':env['M10V_TEST_PER_FILM']='1'
  if 'mismatch' in self._testMethodName:env['M10V_TEST_MISMATCH']='1'
  if self._testMethodName=='test_extensions_unknown_write_blocks_all_mutations':env['M10V_TEST_EXT_UNKNOWN']='1'
  self.process=subprocess.Popen([str(self.exe)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);self.addCleanup(self.stop)
  line=self.process.stdout.readline()
  if not line:
   diagnostic=self.process.stderr.read();self.fail(f'host service exited before listen: returncode={self.process.wait()} stderr={diagnostic}')
  self.port=int(line);self.boot='';self.session='';self.sequence=0;self.nonce=0
  if 'M10V_TEST_HOTSPOT' in env:
   code,pair,headers=self.hotspot({'Host':'192.168.0.1:18743','X-M10V-Hotspot':'1'})
   self.assertEqual(code,200)
   self.assertEqual(headers['cache-control'],'no-store')
   self.assertEqual(pair['schema'],'m10v.companion-pairing/v1')
   self.key=bytes.fromhex(pair['keyHex']);self.key_id=pair['keyId']
   self.assertNotEqual(self.key,KEY)
   self.assertEqual(hashlib.sha256(self.key).hexdigest()[:32],self.key_id)
  response=self.request('GET','/m10v/v1/capabilities');self.assertEqual(response[0],200);self.boot=response[1]['bootId'];self.session=response[1]['sessionId']
 def stop(self):
  self.process.terminate()
  try:self.process.wait(timeout=3)
  except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
  self.process.stdout.close();self.process.stderr.close()
 def request(self,method,path,payload=None,*,bad_signature=False):
  body=b'' if payload is None else payload if isinstance(payload,bytes) else json.dumps(payload,separators=(',',':')).encode();self.nonce+=1
  if self.session:self.sequence+=1
  nonce=f'{self.nonce:032x}';canonical='\n'.join([method,path,self.boot,self.session,str(self.sequence),nonce,hashlib.sha256(body).hexdigest()]);signature=hmac.digest(self.key,canonical.encode(),'sha256').hex()
  if bad_signature:signature='0'*64
  headers={'X-M10V-KeyId':self.key_id,'X-M10V-Boot':self.boot,'X-M10V-Session':self.session,'X-M10V-Seq':str(self.sequence),'X-M10V-Nonce':nonce,'X-M10V-Signature':signature,'Content-Length':str(len(body))}
  if isinstance(payload,bytes):headers['X-M10V-Chunk-Hash']=hashlib.sha256(body).hexdigest()
  self.last_wire=(method,path,body,headers)
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3);connection.request(method,path,body,headers);response=connection.getresponse();raw=response.read();status=response.status;out_headers={k.lower():v for k,v in response.getheaders()};connection.close()
  if status!=401:
   signed='\n'.join(['RESPONSE',method,path,out_headers['x-m10v-boot'],out_headers['x-m10v-session'],str(self.sequence),nonce,str(status),hashlib.sha256(raw).hexdigest()]);self.assertEqual(out_headers['x-m10v-response-signature'],hmac.digest(self.key,signed.encode(),'sha256').hex())
  return status,json.loads(raw)
 def hotspot(self,headers,method='GET'):
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
  connection.request(method,'/m10v/v1/hotspot',headers=headers)
  response=connection.getresponse()
  result=response.status,json.loads(response.read()),dict((k.lower(),v) for k,v in response.getheaders())
  connection.close()
  return result
 def test_hotspot_bootstrap_reads_and_signs_with_boot_key(self):
  host={'Host':'192.168.0.1:18743'};native={**host,'X-M10V-Hotspot':'1'}
  for headers in [host,{**native,'Origin':'https://example.com'},{**native,'Host':'example.com'}]:
   code,value,_=self.hotspot(headers);self.assertEqual(code,401);self.assertNotIn('keyHex',value)
  self.assertEqual(self.hotspot(native,'POST')[0],401)
  status,state=self.request('GET','/m10v/v1/state');self.assertEqual(status,200)
  self.assertEqual(self.request('POST','/m10v/v1/operations',self.envelope(state),bad_signature=True)[0],401)
  self.assertEqual(self.request('POST','/m10v/v1/operations',self.envelope(state))[0],202)
  for _ in range(8):
   _,receipt=self.request('GET','/m10v/v1/operations/'+'a'*32)
   if receipt['status']=='committed':break
  self.assertEqual(receipt['status'],'committed')
 def test_legacy_service_never_releases_its_pairing_key(self):
  self.assertEqual(self.hotspot({'Host':'192.168.0.1:18743','X-M10V-Hotspot':'1'})[0],401)
 def envelope(self,state,request_id='a'*32):return {'protocol':1,'requestId':request_id,'bootId':self.boot,'baseRevision':state['revision'],'catalogHash':state['catalogHash'],'rendererHash':state['rendererHash'],'patch':[{'slot':0,'grain':2}],'activateSlot':None}
 def test_extensions_independent_discovery_and_verified_commit(self):
  status,caps=self.request('GET','/m10v/v1/extensions/capabilities');self.assertEqual(status,200)
  self.assertEqual(caps['schema'],'m10v.extensions/v1');self.assertEqual(len(caps['fields']),22)
  contract=json.loads((ROOT/'contracts/extensions-v1.json').read_text())
  self.assertEqual([{k:v for k,v in f.items() if k!='supported'} for f in caps['fields']],[{k:v for k,v in f.items() if k!='id'} for f in contract['fields']])
  self.assertEqual(caps['powerImages'],{'supported':False,'reason':'firmwareBuildRequired'})
  status,state=self.request('GET','/m10v/v1/extensions/state');self.assertEqual(status,200)
  self.assertEqual(set(state['values']),set(state['supported']))
  payload={'requestId':'b'*32,'bootId':self.boot,'contractHash':caps['contractHash'],'baseRevision':state['revision'],'field':'hdf','value':2}
  status,r=self.request('POST','/m10v/v1/extensions/operations',payload);self.assertEqual(status,202)
  for _ in range(8):
   status,r=self.request('GET','/m10v/v1/extensions/operations/'+'b'*32)
   if r['status']=='committed':break
  self.assertEqual(r['status'],'committed');self.assertEqual(r['snapshot']['values']['hdf'],2)
  self.assertEqual(self.request('GET','/m10v/v1/extensions/state')[1],r['snapshot'])
  self.assertEqual(self.request('POST','/m10v/v1/extensions/operations',payload)[1]['status'],'committed')
  self.assertEqual(self.request('POST','/m10v/v1/extensions/operations',{**payload,'value':1})[0],409)
  self.assertEqual(self.request('POST','/m10v/v1/extensions/operations',{**payload,'requestId':'c'*32})[0],202)
  self.assertEqual(self.request('GET','/m10v/v1/extensions/operations/'+'c'*32)[1]['status'],'rejected')
  self.assertEqual(self.request('GET','/m10v/v1/extensions/state',bad_signature=True)[0],401)
  legacy=self.request('GET','/m10v/v1/capabilities')[1];self.assertNotIn('extensions',legacy);self.assertNotIn('extensions',legacy['capabilities'])
 def test_extensions_unknown_write_blocks_all_mutations(self):
  status,state=self.request('GET','/m10v/v1/extensions/state');self.assertEqual(status,200)
  payload={'requestId':'d'*32,'bootId':self.boot,'contractHash':state['contractHash'],'baseRevision':state['revision'],'field':'hdf','value':2}
  self.assertEqual(self.request('POST','/m10v/v1/extensions/operations',payload)[0],202)
  status,r=self.request('GET','/m10v/v1/extensions/operations/'+'d'*32)
  self.assertEqual(r['status'],'unknown');self.assertEqual(r['code'],'resultUnknown')
  self.assertEqual(self.request('POST','/m10v/v1/extensions/operations',payload)[1]['status'],'unknown')
  self.assertEqual(self.request('POST','/m10v/v1/extensions/operations',{**payload,'requestId':'e'*32})[0],409)
  film=self.request('GET','/m10v/v1/state')[1]
  self.assertEqual(self.request('POST','/m10v/v1/operations',self.envelope(film,'f'*32))[0],409)
 def test_extensions_bad_contract_unknown_fields_and_shared_pending_lock(self):
  status,state=self.request('GET','/m10v/v1/extensions/state');self.assertEqual(status,200)
  payload={'requestId':'b'*32,'bootId':self.boot,'contractHash':state['contractHash'],'baseRevision':state['revision'],'field':'aspect','value':6}
  self.assertEqual(self.request('POST','/m10v/v1/extensions/operations',{**payload,'extra':1})[0],400)
  self.assertEqual(self.request('POST','/m10v/v1/extensions/operations',{**payload,'contractHash':'0'*64})[0],409)
  self.assertEqual(self.request('POST','/m10v/v1/extensions/operations',payload)[0],202)
  film=self.request('GET','/m10v/v1/state')[1]
  # Fixture completes extension requests immediately; exercise other-domain ID isolation.
  self.assertEqual(self.request('GET','/m10v/v1/operations/'+'b'*32)[0],404)
  self.assertEqual(self.request('POST','/m10v/v1/operations',self.envelope(film,'b'*32))[0],409)
 def test_capabilities_publish_ten_slot_state_and_retired_fields(self):
  code,value=self.request('GET','/m10v/v1/capabilities')
  self.assertEqual(code,200)
  self.assertEqual(value['stateSchema'],2)
  self.assertEqual(value['slotCount'],10)
  self.assertEqual(value['readOnlyParameters'],['grainSize','leakGain','leakPosition','leakSpread','leakVariation'])
 def test_per_film_state_stays_wire_compatible(self):
  status,state=self.request('GET','/m10v/v1/state');self.assertEqual(status,200)
  parameters=state['config']['slots'][0]['parameters']
  for key,value in {'leakGain':2,'leakPosition':3,'leakSpread':2,'leakVariation':0}.items():
   self.assertEqual(parameters[key],value)
  self.assertEqual(self.request('POST','/m10v/v1/operations',self.envelope(state))[0],202)
  for _ in range(8):
   _,receipt=self.request('GET','/m10v/v1/operations/'+'a'*32)
   if receipt['status']=='committed':break
  self.assertEqual(receipt['status'],'committed')
  self.assertEqual(receipt['snapshot']['config']['slots'][0]['parameters'],{**parameters,'grain':2})
 def test_duplicate_operation_commits_once_and_returns_verified_snapshot(self):
  status,state=self.request('GET','/m10v/v1/state');self.assertEqual(status,200);operation=self.envelope(state)
  status,queued=self.request('POST','/m10v/v1/operations',operation);self.assertEqual(status,202);self.assertEqual(queued['status'],'queued')
  self.request('POST','/m10v/v1/operations',operation)
  for _ in range(8):
   status,receipt=self.request('GET','/m10v/v1/operations/'+'a'*32)
   if receipt['status']=='committed':break
  self.assertEqual(receipt['status'],'committed');self.assertEqual(receipt['snapshot']['journalSequence'],1)
  status,after=self.request('GET','/m10v/v1/state');self.assertEqual(after['journalSequence'],1);self.assertEqual(after['config']['slots'][0]['parameters']['grain'],2)
  conflict={**operation,'patch':[{'slot':0,'grain':1}]};self.assertEqual(self.request('POST','/m10v/v1/operations',conflict)[0],409)
 def test_unauthorized_unknown_paths_and_busy_second_write(self):
  self.assertEqual(self.request('GET','/m10v/v1/state',bad_signature=True)[0],401)
  self.assertEqual(self.request('GET','/m10v/v1/unknown')[0],404)
  _,state=self.request('GET','/m10v/v1/state');self.request('POST','/m10v/v1/operations',self.envelope(state))
  code,body=self.request('POST','/m10v/v1/operations',self.envelope(state,'b'*32));self.assertEqual(code,409);self.assertEqual(body['error']['code'],'busy')
 def test_malformed_body_and_expired_receipt_never_look_committed(self):
  self.assertEqual(self.request('POST','/m10v/v1/operations',{'unknown':True})[0],400)
  code,body=self.request('GET','/m10v/v1/operations/'+'f'*32);self.assertEqual(code,404);self.assertEqual(body['error']['code'],'resultUnknown')

 def test_stage_endpoint_is_unavailable_without_a_verified_bridge(self):
  self.assertEqual(self.request('POST','/m10v/v1/films/stage',{})[0],503)
  self.assertEqual(self.request('POST','/m10v/v1/films/stageevil',{})[0],404)
 def test_timeout_keeps_unknown_write_locked_but_reads_remain_available(self):
  _,state=self.request('GET','/m10v/v1/state');self.request('POST','/m10v/v1/operations',self.envelope(state))
  time.sleep(.15)
  self.assertEqual(self.request('GET','/m10v/v1/state')[0],200)
  _,receipt=self.request('GET','/m10v/v1/operations/'+'a'*32);self.assertEqual(receipt['status'],'unknown');self.assertNotIn('snapshot',receipt)
  code,body=self.request('POST','/m10v/v1/operations',self.envelope(state,'b'*32));self.assertEqual(code,409);self.assertEqual(body['error']['code'],'busy')

 def test_retired_request_id_is_not_executed_again_after_receipt_eviction(self):
  _,state=self.request('GET','/m10v/v1/state');first=None
  for index in range(33):
   request_id=f'{index+1:032x}';operation=self.envelope(state,request_id);operation['patch'][0]['grain']=(index+1)%4
   if first is None:first=operation
   self.assertEqual(self.request('POST','/m10v/v1/operations',operation)[0],202)
   for _ in range(6):
    _,receipt=self.request('GET','/m10v/v1/operations/'+request_id)
    if receipt['status']=='committed':break
   self.assertEqual(receipt['status'],'committed');state=receipt['snapshot']
  self.assertEqual(state['journalSequence'],33)
  code,body=self.request('POST','/m10v/v1/operations',first);self.assertEqual(code,409);self.assertEqual(body['error']['code'],'resultUnknown')
  self.assertEqual(self.request('GET','/m10v/v1/state')[1]['journalSequence'],33)
 def test_http_replay_never_consumes_another_sequence(self):
  self.assertEqual(self.request('GET','/m10v/v1/state')[0],200)
  method,path,body,headers=self.last_wire
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3);connection.request(method,path,body,headers);response=connection.getresponse();response.read();self.assertEqual(response.status,401);connection.close()
  self.assertEqual(self.request('GET','/m10v/v1/state')[0],200)

 def test_owner_readback_mismatch_is_unknown_before_network_timeout(self):
  _,state=self.request('GET','/m10v/v1/state');self.request('POST','/m10v/v1/operations',self.envelope(state))
  for _ in range(4):_,receipt=self.request('GET','/m10v/v1/operations/'+'a'*32)
  self.assertEqual(receipt['status'],'unknown')
  self.assertEqual(self.request('GET','/m10v/v1/state')[1]['journalSequence'],0)

 def test_upload_chunks_verified_then_install_is_separate(self):
  record=subprocess.check_output(['node','--input-type=module','-e',"import{customFilmRecord}from'./node/gr3-sd-film-pack.mjs';process.stdout.write(customFilmRecord({name:'TEST',rgb:Buffer.alloc(6591,128)},79));"],cwd=ROOT)
  _,before=self.request('GET','/m10v/v1/state')
  metadata={'model':'GR III','schema':1,'stableId':79,'targetSlot':3,'size':len(record),'chunkBytes':4096,'rendererHash':record[8448:8480].hex(),'contentHash':hashlib.sha256(record).hexdigest()}
  code,stage=self.request('POST','/m10v/v1/films/stage',metadata);self.assertEqual(code,200);path='/m10v/v1/films/stage/'+stage['uploadId']
  self.assertEqual(self.request('PUT',path+'/chunks/1',record[4096:8192])[0],400)
  for i in range(3):self.assertEqual(self.request('PUT',path+'/chunks/'+str(i),record[i*4096:(i+1)*4096])[0],200)
  code,progress=self.request('GET',path);self.assertEqual(code,200);self.assertEqual(progress['status'],'receiving');self.assertEqual(self.request('GET','/m10v/v1/state')[1]['revision'],before['revision'])
  code,receipt=self.request('POST',path+'/verify');self.assertEqual(code,200);self.assertEqual(receipt['status'],'verified');self.assertEqual(receipt['targetSlot'],3);self.assertEqual(receipt['contentHash'],metadata['contentHash'])
  after=self.request('GET','/m10v/v1/state')[1];self.assertEqual(after['revision'],before['revision']);self.assertEqual(after['activeSlot'],before['activeSlot'])
  operation=self.envelope(after);operation['patch']=[{'slot':3,'filmId':79,'customHash':metadata['contentHash']}]
  self.assertEqual(self.request('POST','/m10v/v1/operations',operation)[0],202)
  for _ in range(5):_,installed=self.request('GET','/m10v/v1/operations/'+'a'*32)
  self.assertEqual(installed['status'],'committed');self.assertEqual(installed['snapshot']['config']['slots'][3]['customHash'],metadata['contentHash']);self.assertEqual(installed['snapshot']['activeSlot'],before['activeSlot'])

 def test_capabilities_and_snapshot_include_all_ten_slots(self):
  code,caps=self.request('GET','/m10v/v1/capabilities');self.assertEqual(code,200);self.assertEqual(caps['slotCount'],10)
  code,state=self.request('GET','/m10v/v1/state');self.assertEqual(code,200);self.assertEqual(state['schemaVersion'],2);self.assertEqual(len(state['config']['slots']),10)
  self.assertEqual(state['config']['slots'][9]['filmId'],0)

 def test_async_read_busy_and_submit_waits_for_read_turn(self):
  code,value=self.request('GET','/m10v/v1/state');self.assertEqual(code,503);self.assertEqual(value['error']['code'],'busy')
  code,state=self.request('GET','/m10v/v1/state');self.assertEqual(code,200)
  self.assertEqual(self.request('POST','/m10v/v1/operations',self.envelope(state))[0],202)
  for _ in range(10):
   _,receipt=self.request('GET','/m10v/v1/operations/'+'a'*32)
   if receipt['status']=='committed':break
  self.assertEqual(receipt['status'],'committed')

 def test_full_ten_slot_snapshot_and_receipt_fit_response_budget(self):
  code,state=self.request('GET','/m10v/v1/state');self.assertEqual(code,200);self.assertEqual(len(state['config']['slots']),10)
  for slot in state['config']['slots']:self.assertIn('leakVariation',slot['parameters'])
  operation=self.envelope(state);operation['patch']=[{'slot':9,'grain':2}]
  self.assertEqual(self.request('POST','/m10v/v1/operations',operation)[0],202)
  for _ in range(8):
   code,receipt=self.request('GET','/m10v/v1/operations/'+'a'*32)
   if receipt['status']=='committed':break
  self.assertEqual(code,200);self.assertEqual(receipt['snapshot']['config']['slots'][9]['parameters']['grain'],2)
