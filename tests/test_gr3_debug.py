"""Bounded SD logger: execute real compiled ARM, mock only device facade/heap."""
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
from scripts.build_gr3_m10v_library import build

class DebugLogArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.tmp.cleanup)
        cls.manifest = build(Path(cls.tmp.name), debug_mode=True, debug_build_id=0x12345678)
        cls.code = (Path(cls.tmp.name)/'m10v-library-arm.bin').read_bytes()

    def setUp(self):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.mem_map(0x53000000, 0x1200000)
        self.u.mem_write(self.manifest['base'], self.code)
        self.u.mem_map(0x55000000, 0x100000)
        self.files = {}; self.handles = {}; self.calls = []; self.available = True
        self.fail_write = False; self.heap_ok = True
        self.successful_opens = 0
        self.u.mem_write(0x55004014, struct.pack('<I', 0x55004200))
        self.u.mem_write(0x55004200, struct.pack('<I', 0x53900000))
        for index,address in [(7,0x53900100),(8,0x53900200),(9,0x53900300),(10,0x53900400)]:
            self.u.mem_write(0x53900000+index*4,struct.pack('<I',address))
        self.u.hook_add(UC_HOOK_CODE,self.services)

    def services(self,u,address,size,data):
        args=[u.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        result=None
        if address==0x535847d8: result=0x55004000 if self.available else 0
        elif address==0x5320ad88: result=0x55005000
        elif address==0x5320ba9c: result=0x55068200
        elif address==self.manifest['base']+0xa0: result=77
        elif address==0x536af2a8:
            self.assertEqual(args[0],8192); result=0x55010000 if self.heap_ok else 0
        elif address==0x536af2e4: result=0
        elif address==0x53900100:
            name=bytes(u.mem_read(args[1],16)).split(b'\0')[0].decode()
            self.assertIn(name,('C:\\M10VMN0.BIN','C:\\M10VMN1.BIN','C:\\M10VCP0.BIN','C:\\M10VCP1.BIN','C:\\M10VIO0.BIN','C:\\M10VIO1.BIN','C:\\M10VAK0.BIN','C:\\M10VAK1.BIN'))
            self.assertIn(args[2],(0,1)); self.calls.append(('open',name,args[2]))
            result=int(args[2]==0 or name in self.files)
            if result:
                self.successful_opens += 1
                handle=len(self.handles)+1;self.handles[handle]=name
                u.mem_write(args[3],struct.pack('<I',handle))
                if args[2]==0:self.files[name]=b''
        elif address==0x53900200: self.calls.append(('close',args[1]));result=1
        elif address in (0x53900300,0x53900400):
            self.assertEqual(args[3],4096)
            name=self.handles[args[1]]
            if address==0x53900300:
                payload=self.files[name];result=int(len(payload)==4096)
                if result:u.mem_write(args[2],payload)
            else:
                payload=bytes(u.mem_read(args[2],args[3]))
                self.files[name]=payload[:128] if self.fail_write else payload
                result=int(not self.fail_write)
            self.calls.append(('read' if address==0x53900300 else 'write',name))
        if result is not None:
            u.reg_write(UC_ARM_REG_R0,result);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))

    def log(self,event=30,a=0x55005000,b=11,c=21,d=33):
        for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),(event,a,b,c)):
            self.u.reg_write(reg,value)
        self.u.mem_write(0x550fe000,struct.pack('<I',d))
        self.u.reg_write(UC_ARM_REG_SP,0x550fe000);self.u.reg_write(UC_ARM_REG_LR,0x550ff000)
        self.u.emu_start(self.manifest['symbols']['m10v_debug_log'],0x550ff000,count=2000000)
        self.assertEqual(self.u.reg_read(UC_ARM_REG_PC),0x550ff000)
        return self.u.reg_read(UC_ARM_REG_R0)

    def invoke(self,symbol,*args):
        for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):
            self.u.reg_write(reg,value)
        self.u.reg_write(UC_ARM_REG_SP,0x550fe000);self.u.reg_write(UC_ARM_REG_LR,0x550ff000)
        self.u.emu_start(self.manifest['symbols'][symbol],0x550ff000,count=3000000)
        self.assertEqual(self.u.reg_read(UC_ARM_REG_PC),0x550ff000)
        return self.u.reg_read(UC_ARM_REG_R0)

    def test_batch_records_share_one_sd_transaction_and_reject_mixed_channels(self):
        self.assertIn('m10v_debug_batch',self.manifest['symbols'])
        events=[(100+i,0x55001000,i,i+1,i+2) for i in range(12)]
        self.u.mem_write(0x55008000,b''.join(struct.pack('<5I',*e) for e in events))
        self.assertEqual(self.invoke('m10v_debug_batch',0x55008000,len(events)),1)
        self.assertEqual(sum(c[0]=='write' for c in self.calls),1)
        rows=self.decoded()['records']
        self.assertEqual([r['event'] for r in rows],[e[0] for e in events])
        self.assertEqual([r['arguments'] for r in rows],[list(e[1:]) for e in events])
        self.assertEqual(sum(c[0]=='close' for c in self.calls),self.successful_opens)
        self.calls.clear()
        self.u.mem_write(0x55008000,struct.pack('<10I',100,1,2,3,4,30,1,2,3,4))
        self.assertEqual(self.invoke('m10v_debug_batch',0x55008000,2),0)
        self.assertEqual(self.calls,[])

    def test_profile_sized_batches_fill_ring_and_reject_overflow_before_io(self):
        events=[(150,0x550709b8,1,100+i,0) for i in range(32)]
        self.u.mem_write(0x55008000,b''.join(struct.pack('<5I',*event) for event in events))
        for _ in range(2):self.assertEqual(self.invoke('m10v_debug_batch',0x55008000,32),1)
        rows=self.decoded()['records']
        self.assertEqual(len(rows),64)
        self.assertEqual([r['sequence'] for r in rows],list(range(1,65)))
        self.assertEqual(sum(c[0]=='write' for c in self.calls),2)
        self.assertEqual(sum(c[0]=='close' for c in self.calls),self.successful_opens)
        before=list(self.calls)
        self.assertEqual(self.invoke('m10v_debug_batch',0x55008000,33),0)
        self.assertEqual(self.calls,before)

    def test_lifecycle_channel_preserves_capture_history_and_rejects_mixed_batches(self):
        self.assertEqual(self.log(150,1,2,3,4),1)
        self.assertEqual(self.log(190,5,6,7,8),1)
        rows=self.decoded()['records']
        self.assertEqual([(r['channel'],r['event']) for r in rows],[('capture',150),('io',190)])
        self.assertTrue(any('M10VIO' in name for name in self.files))
        self.u.mem_write(0x55008000,struct.pack('<10I',190,1,2,3,4,150,1,2,3,4))
        before=list(self.calls)
        self.assertEqual(self.invoke('m10v_debug_batch',0x55008000,2),0)
        self.assertEqual(self.calls,before)

    def test_independent_page_trace_decodes_keys_state_and_error(self):
        self.assertEqual(self.log(83,0xcf,4,2,(3<<16)|1),1)
        record=self.decoded()['records'][-1]
        self.assertEqual(record['stage'],'page.state.after')
        self.assertEqual(record['page_state'],{'key':'0xcf','screen':'value','focus':2,'value':1,'error':3})

    def test_exit_checkpoints_use_ab_pages_and_decode_the_exact_boundary(self):
        self.assertEqual(self.log(230,0x55050000,0x37,2,0),1)
        record=self.decoded()['records'][-1]
        self.assertEqual(record['channel'],'ab')
        self.assertEqual(record['stage'],'adj.event.before')
        self.assertEqual(record['arguments'],[0x55050000,0x37,2,0])

    def test_focus_wrapper_records_real_slot_and_preserves_original_result(self):
        self.u.mem_write(0x55068200,b'\x15')
        self.assertEqual(self.invoke('m10v_menu_focus',0x55005000,11),77)
        records=self.decoded()['records']
        self.assertEqual([r['event'] for r in records],[30,31])
        self.assertEqual(records[0]['arguments'],[0x55005000,11,21,0])
        self.assertEqual(records[1]['arguments'][2],77)

    def test_capture_validation_failure_is_logged_and_preserved(self):
        self.assertEqual(self.invoke('m10v_capture_library',0),0xfffffffd)
        records=self.decoded()['records']
        self.assertEqual([r['event'] for r in records],[100,102,101])
        self.assertEqual(records[-1]['arguments'][1],0xfffffffd)
        self.assertEqual(records[1]['rejection']['guard'],'context')

    def test_capture_cpu_diagnostics_decode_without_claiming_jpeg_success(self):
        for event,args in ((121,(0x55001000,0x56000000,0x58000000,(6000<<16)|4000)),
                           (122,(0x55001000,0x12345678,0x9abcdef0,64)),
                           (124,(0x55001000,6016,4000,18))):
            self.assertEqual(self.log(event,*args),1)
        rows=self.decoded()['records']
        self.assertEqual(rows[0]['image']['width'],6000)
        self.assertEqual(rows[0]['image']['chroma'],'0x58000000')
        self.assertEqual(rows[1]['cpu_samples']['y_hash'],'12345678')
        self.assertIn('not an encoded JPEG',rows[1]['cpu_samples']['scope'])
        self.assertEqual(rows[2]['layout']['stock_tone'],18)

    def test_debug_capture_chain_restores_stock_arguments_flags_and_stack(self):
        registers=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,
                   UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
                   UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12)
        values=list(range(13));values[4]=0
        for sp in (0x550fe000,0x550fe004):
            seen=[];cpsr=0x68050013
            def stock(u,address,size,data):
                if address==0x536abd28:
                    seen.append(address)
                    self.assertEqual([u.reg_read(r) for r in registers],values)
                    self.assertEqual(u.reg_read(UC_ARM_REG_SP),sp)
                    self.assertEqual(u.reg_read(UC_ARM_REG_CPSR)&0xff0f0000,cpsr&0xff0f0000)
                    u.reg_write(UC_ARM_REG_R0,99);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
            hook=self.u.hook_add(UC_HOOK_CODE,stock)
            for r,v in zip(registers,values):self.u.reg_write(r,v)
            self.u.reg_write(UC_ARM_REG_SP,sp);self.u.reg_write(UC_ARM_REG_LR,0x550ff000)
            self.u.reg_write(UC_ARM_REG_CPSR,cpsr)
            self.u.emu_start(self.manifest['symbols']['m10v_chain_capture'],0x550ff000,count=3000000)
            self.assertEqual(seen,[0x536abd28]);self.assertEqual(self.u.reg_read(UC_ARM_REG_R0),99)
            self.u.hook_del(hook)

    def decoded(self):
        from scripts.read_gr3_debug_log import decode_logs
        return decode_logs(list(self.files.values()))

    def test_arm_writes_history_with_payload_build_identity_and_balanced_close(self):
        self.assertEqual(self.log(),1);self.assertEqual(self.log(31),1)
        result=self.decoded();records=result['records']
        self.assertEqual([r['event'] for r in records],[30,31])
        self.assertEqual(records[0]['arguments'],[0x55005000,11,21,33])
        self.assertEqual(result['build_ids'],['12345678'])
        self.assertEqual(sum(c[0]=='close' for c in self.calls),self.successful_opens)

    def test_ab_diagnostics_use_a_separate_persistent_history(self):
        self.assertEqual(self.log(88,a=0x37),1)
        for i in range(3):self.assertEqual(self.log(20,b=i),1)
        rows=self.decoded()['records']
        ab=[r for r in rows if r['channel']=='ab']
        self.assertEqual([(r['event'],r['arguments'][0]) for r in ab],[(88,0x37)])
        self.assertTrue(any('M10VAK' in name for name in self.files))

    def test_bounded_ring_and_capture_channel_keep_separate_histories(self):
        for i in range(70):self.assertEqual(self.log(30,b=i),1)
        self.assertEqual(self.log(100),1)
        records=self.decoded()['records'];menu=[r for r in records if r['channel']=='menu']
        self.assertEqual(len(menu),64);self.assertEqual(menu[0]['arguments'][1],6)
        self.assertEqual(menu[-1]['sequence'],70)
        self.assertEqual(len([r for r in records if r['channel']=='capture']),1)

    def test_persisted_capture_settings_and_source_decode_after_reader_restart(self):
        self.assertEqual(self.log(112,a=1,b=202534,c=4,d=2),1)
        self.assertEqual(self.log(113,a=1,b=2,c=4,d=3),1)
        self.assertEqual(self.log(114,a=12168,b=9,c=128*96,d=216),1)
        from scripts.read_gr3_debug_log import decode_logs
        result=decode_logs(list(self.files.values()))
        settings=next(r for r in result['records'] if r['event']==112)
        self.assertEqual(settings['settings'],dict(slot=1,gain=6,spread=2,threshold=7,grain=1,soft=3,sequence=4,renderer_revision=2))
        energy=next(r for r in result['records'] if r['event']==114)
        self.assertEqual(energy['highlight_energy'],dict(maximum=12168,active_pixels=9,image_pixels=128*96,gate=216))
        source=next(r for r in result['records'] if r['event']==113)
        self.assertEqual(source['provenance'],dict(slot=1,source='migrated-v2',sequence=4,journal_namespace=3))

    def test_partial_write_preserves_previous_checkpoint(self):
        self.assertEqual(self.log(30),1);self.fail_write=True
        self.assertEqual(self.log(31),0)
        self.assertEqual([r['event'] for r in self.decoded()['records']],[30])

    def test_missing_card_oom_and_reentry_do_not_leave_guard_set(self):
        self.available=False;self.assertEqual(self.log(),0)
        self.assertEqual(self.u.mem_read(0x5506821f,1),b'\0')
        self.available=True;self.heap_ok=False;self.assertEqual(self.log(),0)
        self.assertEqual(self.u.mem_read(0x5506821f,1),b'\0')
        self.u.mem_write(0x5506821f,b'\1');before=list(self.calls)
        self.assertEqual(self.log(),0);self.assertEqual(self.calls,before)
        self.assertEqual(self.u.mem_read(0x5506821f,1),b'\1')
        self.assertEqual(self.log(100),0);self.assertEqual(self.calls,before)
        self.assertEqual(self.u.mem_read(0x5506821f,1),b'\1')

if __name__=='__main__':unittest.main()

class ExitOnlyLogArmTests(unittest.TestCase):
    """Explicit diagnostic build filters unrelated traffic before any SD IO."""
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.manifest=build(Path(cls.tmp.name),debug_mode=True,debug_build_id=0x12345678,adj_exit_trace=True)
        cls.code=(Path(cls.tmp.name)/'m10v-library-arm.bin').read_bytes()
    setUp=DebugLogArmTests.setUp
    services=DebugLogArmTests.services
    log=DebugLogArmTests.log
    invoke=DebugLogArmTests.invoke
    decoded=DebugLogArmTests.decoded

    def test_unrelated_menu_preview_and_capture_events_perform_no_io(self):
        for event in (30,85,97,150,190,208):self.assertEqual(self.log(event),0)
        self.assertEqual(self.calls,[]);self.assertEqual(self.files,{})

    def test_exit_records_keep_identity_sequence_crc_and_balanced_close(self):
        for event in (230,237,264,238,239,240,247,269,270,271,272,273):self.assertEqual(self.log(event,1,2,3,4),1)
        rows=self.decoded()['records']
        self.assertEqual([r['event'] for r in rows],[230,237,264,238,239,240,247,269,270,271,272,273])
        self.assertEqual(rows[-1]['stage'],'ab.close.live-entered')
        self.assertTrue(all(r['channel']=='ab' and r['build_id']=='12345678' for r in rows))
        self.assertEqual(set(self.files),{'C:\\M10VAK0.BIN','C:\\M10VAK1.BIN'})
        self.assertEqual(sum(c[0]=='close' for c in self.calls),self.successful_opens)
        self.assertEqual(self.decoded()['rejected_pages'],0)

    def test_partial_checkpoint_write_retains_previous_valid_page(self):
        self.assertEqual(self.log(230),1)
        self.fail_write=True;self.assertEqual(self.log(233),0)
        rows=self.decoded()['records'];self.assertEqual([r['event'] for r in rows],[230])
        self.assertEqual(sum(c[0]=='close' for c in self.calls),self.successful_opens)

    def test_unavailable_card_returns_without_retry_or_fabricated_record(self):
        self.available=False;self.assertEqual(self.log(230),0)
        self.assertEqual(self.calls,[]);self.assertEqual(self.files,{})
