"""Execute native AppMain mailbox adapter, including session ABA protection."""
import json,struct
from tests import test_gr3_companion_ui_owner_arm as native

class TornExtensions(native.ProductionOwner):
 feature_flags=['-DM10V_TORN_ENABLED=1']
 native_sources=['native/companion/extensions_json.c']
 extra_roots=['m10v_extensions_parse']
 extra_ports=['m10v_torn_state','m10v_torn_set','m10v_torn_busy']
 def extra_port(self,m,pc,args):
  if pc==self.ports['m10v_torn_state']:
   m.set(args[0],getattr(m,'torn_stage',0));m.set(args[1],getattr(m,'torn_generation',1));return 1
  if pc==self.ports['m10v_torn_busy']:return int(getattr(m,'torn_busy',False))
  if pc==self.ports['m10v_torn_set']:
   self.assertEqual(args[0],0x55860000);self.assertIn(args[1],(0,1))
   m.torn_writes=getattr(m,'torn_writes',0)+1;m.torn_stage=args[1];m.torn_generation=getattr(m,'torn_generation',1)+1;return 0
  self.fail('unexpected native torn port')
 def test_real_portable_json_parser_allows_actions_and_rejects_stage_writes(self):
  m=self.machine();body=0x558e0000;tokens=0x558e1000;patch=0x558e3000
  for value in [0,1,2,3,4,5,-1,True,'1']:
   raw=json.dumps(dict(requestId='01'*16,bootId='02'*16,contractHash='03'*32,baseRevision='04'*32,field='tornSession',value=value)).encode();m.u.mem_write(body,raw)
   self.assertEqual(m.run(self.symbols['m10v_extensions_parse'],body,len(raw),tokens,patch),0 if type(value)is int and value in (0,1) else 5)
   if type(value)is int and value in (0,1):self.assertEqual(struct.unpack('<II',m.u.mem_read(patch+96,8)),(24,value))
 def test_torn_actions_bind_generation_reject_stages_and_never_write_journal(self):
  m=self.machine();owner=0x55860000;m.run(self.symbols['m10v_companion_ui_init'],owner);wire=m.word(owner+0x6400+16)
  m.run(self.symbols['m10v_companion_ui_start'],owner);self.exchange(m,wire,2,1,bytes([7]*16))
  code,read=self.exchange(m,wire,4,5);self.assertEqual(code,0);self.assertEqual(struct.unpack_from('<I',read,12)[0],(31<<12)|(1<<24))
  contract=bytes.fromhex('c5e4a67763f11333c72f40ceee652919b280ab83235b21a535bc9145b73a224d')
  def patch(ident,action,revision):return bytes([ident]*16)+bytes([7]*16)+contract+revision+struct.pack('<II',24,action)
  # A local restart that returns to the same visible stage invalidates CAS.
  m.torn_generation=2
  self.assertEqual(self.exchange(m,wire,6,6,patch(8,1,read[-32:]))[0],7)
  _,fresh=self.exchange(m,wire,8,5);self.assertNotEqual(fresh[-32:],read[-32:])
  start=patch(9,1,fresh[-32:]);code,result=self.exchange(m,wire,10,6,start)
  self.assertEqual(code,0);self.assertEqual(m.torn_writes,1);self.assertEqual(m.saves,0)
  self.exchange(m,wire,12,6,start);self.assertEqual(m.torn_writes,1)
  # New request restarts stage1; same-value scalar optimization must not eat it.
  code,result=self.exchange(m,wire,14,6,patch(10,1,result[-32:]));self.assertEqual(code,0);self.assertEqual(m.torn_writes,2)
  for sequence,stage in [(16,2),(18,3),(20,4)]:
   self.assertEqual(self.exchange(m,wire,sequence,6,patch(stage+10,stage,result[-32:]))[0],5)
  m.torn_busy=True
  self.assertEqual(self.exchange(m,wire,22,6,patch(20,0,result[-32:]))[0],6);self.assertEqual(m.torn_writes,2)
  m.torn_busy=False
  code,result=self.exchange(m,wire,24,6,patch(21,0,result[-32:]));self.assertEqual(code,0);self.assertEqual(m.torn_writes,3);self.assertEqual(m.saves,0)

for _case in native.ProductionOwner.__dict__:
 if _case.startswith('test_'):setattr(TornExtensions,_case,None)
