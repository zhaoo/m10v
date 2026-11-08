"""Execute the real ARM SD adapter against subset cards and exact directory IDs."""
import struct,subprocess,unittest,gzip,json,os,tempfile,hashlib
from pathlib import Path
import tests.test_gr3_sd_camera as support
ROOT=support.ROOT

class DirectorySDTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  candidate=os.environ.get('M10V_DIRECTORY_CANDIDATE')
  if not candidate:
   return support.SdCameraTests.setUpClass.__func__(cls)
  folder=Path(candidate)
  cls.manifest=json.loads((folder/'M10V-runtime-manifest.json').read_text())
  receipt=json.loads((folder/'M10V-build-receipt.json').read_text())
  binary=folder/receipt['filename']
  assert hashlib.sha256(binary.read_bytes()).hexdigest()==receipt['candidate_sha256']
  script="import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
  rtos=subprocess.check_output(['node','--input-type=module','-e',script,str(binary)],cwd=ROOT)
  start=cls.manifest['base']-0x53000000
  cls.code=rtos[start:start+cls.manifest['code_bytes']]
  assert hashlib.sha256(cls.code).hexdigest()==cls.manifest['code_sha256']
  cls.rom_bytes=0x2000000
  cls.pack=subprocess.check_output(['node','--input-type=module','-e',"import {buildSdFilmPack} from './node/gr3-sd-film-pack.mjs';process.stdout.write(buildSdFilmPack());"],cwd=ROOT)
 setUp=support.SdCameraTests.setUp
 w=support.SdCameraTests.w
 n=support.SdCameraTests.n
 string=support.SdCameraTests.string
 hook=support.SdCameraTests.hook
 call=support.SdCameraTests.call

 def test_final_candidate_new_film_names_do_not_alias_imprint_resources(self):
  if not os.environ.get('M10V_DIRECTORY_CANDIDATE'):
   self.skipTest('Requires the complete native candidate with menu resources')
  for film,resource,name in ((328,1211,'SHD50'),(329,1212,'Revolog KOLOR'),(330,1213,'Pegasus')):
   self.assertEqual(self.call('m10v_menu_film_resource',film),resource)
   resources=self.manifest['resources']
   self.assertEqual(resources['texts'][resource-resources['first_id']],name)

 def test_final_candidate_directory_art_is_distinct_and_new_small_icons_match(self):
  if not os.environ.get('M10V_DIRECTORY_CANDIDATE'):
   self.skipTest('Requires the complete native candidate with card resources')
  directory=json.loads((ROOT/'web/gr3/film-directory.json').read_text())
  films=[film['id'] for group in directory['groups'] for film in group['films']]
  images={};pixels=0x55080004;size=128*128*4
  self.w(pixels-4,0x12345678);self.w(pixels+size,0x12345678)
  for film in films:
   self.assertEqual(self.call('m10v_film_card_render',pixels,67,0,0),0)
   self.assertEqual(self.call('m10v_film_card_render',pixels,film,0,0),0,film)
   digest=hashlib.sha256(self.u.mem_read(pixels,size)).hexdigest()
   self.assertNotIn(digest,images,(film,images.get(digest)))
   images[digest]=film
   self.assertEqual((self.n(pixels-4),self.n(pixels+size)),(0x12345678,0x12345678))
  self.assertEqual(len(images),60)
  payload=(ROOT/'native/gr3/m10v_three_films.rgba').read_bytes()
  for i in range(3):
   descriptor=self.n(self.manifest['icons']['table']+(888+i)*4)
   width,height,words=struct.unpack('<HHI',self.u.mem_read(descriptor,8))
   self.assertEqual((width,height),(40,40))
   self.assertEqual(bytes(self.u.mem_read(words*4,6400)),payload[i*6400:(i+1)*6400])

 def test_current_full_card_exposes_every_camera_directory_entry(self):
  directory=json.loads((ROOT/'web/gr3/film-directory.json').read_text())
  ids=[film['id'] for group in directory['groups'] for film in group['films']]
  self.card=subprocess.check_output(['node','--input-type=module','-e',"import {buildSdFilmPack} from './node/gr3-sd-film-pack.mjs';process.stdout.write(buildSdFilmPack());"],cwd=ROOT)
  self.assertEqual(self.call('m10v_sd_camera_directory_extent'),len(ids))
  self.assertEqual([self.call('m10v_sd_camera_directory_item',i) for i in range(len(ids))],ids)
  for film in (328,329,330):self.assertIn(film,ids)
  self.assertEqual(self.call('m10v_sd_camera_directory_item',len(ids)),0)
  self.assertEqual((self.opened,self.allocated),(0,0))

 def test_pre_fix_sixty_film_card_still_authenticates_new_and_last_directory_films(self):
  self.card=gzip.decompress((ROOT/'tests/fixtures/gr3-pre-directory-count-films.m10.gz').read_bytes())
  self.assertEqual(hashlib.sha256(self.card).hexdigest(),'496df3c83208ab49a5521accff816e5112544ba02b5d7f73efb793c6ddbbbac8')
  self.assertEqual(self.call('m10v_sd_camera_directory_extent'),60)
  for index,film in ((28,329),(29,330),(44,328),(57,65),(58,319),(59,320)):
   self.assertEqual(self.call('m10v_sd_camera_directory_item',index),film)
   record=self.card[4096+index*12288:4096+(index+1)*12288]
   self.u.mem_write(0x55070000,record)
   self.assertEqual(self.call('m10v_sd_record',0x55070000,len(record),film),film)
  self.assertEqual((self.opened,self.allocated),(0,0))

 def test_directory_mapping_uses_stock_identity_in_a_subset_card(self):
  self.card=subprocess.check_output(['node','--input-type=module','-e',"import {buildSdFilmPack} from './node/gr3-sd-film-pack.mjs';process.stdout.write(buildSdFilmPack([290,37,298]));"],cwd=ROOT)
  for index,expected in [(4,298),(7,37),(32,290),(0,0),(37,0),(255,0)]:
   self.assertEqual(self.call('m10v_sd_camera_directory_item',index),expected)
  self.assertEqual(self.call('m10v_sd_camera_item',32,0),0)
  self.assertEqual((self.opened,self.allocated),(0,0));self.assertEqual(self.calls,[])

 def test_5213_snapshot_and_journal_never_alias_another_sparse_film(self):
  self.assertEqual(self.call('m10v_sd_camera_directory_install',4,298,2),0)
  self.assertEqual(self.calls[0],('save','M10VS09.bin',12288))
  self.assertEqual(struct.unpack_from('<I',self.files['M10VS09.bin'],8)[0],298)
  self.card=b'';self.assertEqual(self.call('m10v_camera_library_load',0x5500a000),0)
  self.assertEqual(struct.unpack_from('<H',self.u.mem_read(0x5500a000,184),28)[0],298)
  self.assertEqual((self.opened,self.allocated),(0,0))

 def test_authentic_old_full_card_maps_only_requested_identities(self):
  self.card=gzip.decompress((ROOT/'tests/fixtures/gr3-pre-directory-films.m10.gz').read_bytes())
  for index,expected in [(0,33),(4,0),(5,77),(7,37),(32,290),(36,65)]:
   self.assertEqual(self.call('m10v_sd_camera_directory_item',index),expected)
  self.assertEqual(self.call('m10v_sd_camera_directory_install',4,298,2),0xffffffff)
  self.assertEqual(self.calls,[]);self.assertEqual((self.opened,self.allocated),(0,0))

 def test_previous_flat_catalog_pack_including_5213_survives_new_2460_renderer(self):
  self.card=gzip.decompress((ROOT/'tests/fixtures/gr3-pre-aerocolor-films.m10.gz').read_bytes())
  self.assertEqual(self.call('m10v_sd_camera_directory_item',4),298)
  self.assertEqual(self.call('m10v_sd_camera_directory_item',5),77)
  self.assertEqual(self.call('m10v_sd_camera_directory_install',4,298,2),0)
  self.assertEqual(self.call('m10v_sd_camera_directory_install',5,77,2),0)
  self.assertEqual((self.opened,self.allocated),(0,0))

 def test_stale_identity_corrupt_record_and_close_failure_do_not_save(self):
  self.assertEqual(self.call('m10v_sd_camera_directory_install',4,77,2),0xffffffff)
  card=bytearray(self.pack);card[4096+4*12288+80]^=1;self.card=bytes(card)
  self.assertEqual(self.call('m10v_sd_camera_directory_install',4,298,2),0xffffffff)
  self.card=self.pack;self.fail_close=True
  self.assertEqual(self.call('m10v_sd_camera_directory_install',4,298,2),0xffffffff)
  self.assertEqual((self.opened,self.allocated),(0,0));self.assertEqual(self.calls,[])

class DirectoryGeneratorTests(unittest.TestCase):
 def test_generated_native_inventory_count_and_lookup_cover_the_shared_directory(self):
  from scripts.generate_m10v_directory import generate,directory
  expected=[f for group in directory() for f in group['films']]
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'directory.h').write_text(generate())
   (p/'probe.c').write_text('#include "directory.h"\n#include <stdio.h>\nint main(void){printf("%u\\n",M10V_DIRECTORY_COUNT);for(unsigned i=0;i<M10V_DIRECTORY_COUNT;i++)printf("%u:%s\\n",m10v_directory[i].id,m10v_directory_name(m10v_directory[i].id));return 0;}\n')
   subprocess.run(['clang','-Wall','-Wextra','-Werror',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True)
   output=subprocess.check_output([str(p/'probe')],text=True).splitlines()
  self.assertEqual(int(output[0]),len(expected))
  self.assertEqual(output[1:],[str(f['id'])+':'+f['name'] for f in expected])

if __name__=='__main__':unittest.main()
