"""Checked factory-owned recipe tail, bounded lifecycle trace and save ABI."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class SaveTraceTests(unittest.TestCase):
    def test_linked_module_and_manifest_fail_closed(self):
        spec=importlib.util.spec_from_file_location('save_trace_builder',ROOT/'scripts/build_gr3_save_trace.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            blob,manifest=module.build(Path(d),0x540e0000)
            self.assertTrue(blob)
            self.assertFalse(manifest['camera_tested'])
            self.assertEqual(len(manifest['patches']),13)
            self.assertEqual(manifest['storage']['extended_recipe_bytes'],0x5140)
            self.assertTrue(manifest['automatic_hook_installation'])
            self.assertEqual(manifest['mutable_global_bytes'],0)
            self.assertIn('m10v_save_trace_bridge',manifest['exports'])
            self.assertIn('m10v_save_trace_callback',manifest['exports'])
            vt=manifest['vtable']-manifest['base']
            self.assertEqual(struct.unpack_from('<III',blob,vt),(0x534ecc2c,0x534ecc54,manifest['exports']['m10v_save_trace_callback']))
            self.assertNotIn('m10v_debug_batch',manifest['undefined_symbols'])


class SaveTraceArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hashlib
        path=ROOT/'builds/gr3-extension-validation/official-rtos.bin'
        if not path.exists():raise unittest.SkipTest('locked RTOS missing')
        cls.stock=path.read_bytes()
        if hashlib.sha256(cls.stock).hexdigest()!='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67':raise AssertionError('wrong RTOS')
        spec=importlib.util.spec_from_file_location('save_trace_arm_builder',ROOT/'scripts/build_gr3_save_trace.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cls.temp=tempfile.TemporaryDirectory();cls.blob,cls.manifest=module.build(Path(cls.temp.name),0x540e0000)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def run_bridge(self,status,instrumented=True,vptr=0x53c5ed78):
        from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
        from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_SP,UC_ARM_REG_CPSR
        regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
        saved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x1200000);u.mem_write(0x53000000,self.stock);u.mem_write(self.manifest['base'],self.blob);u.mem_map(0x55000000,0x4000000);u.mem_map(0x60000000,0x10000)
        obj,info,trace,payload=0x55021000,0x55023000,0x55020000,0x55024000
        manager,service,vt=0x55010000,0x55010100,0x55010200
        dispatch,callback_return,stop=0x60000100,0x60000200,0x60000300
        def word(a,v):u.mem_write(a,struct.pack('<I',v))
        word(manager+8,service);word(service,vt);word(vt+0x14,dispatch)
        if vptr!=0x53c5ed78:word(vptr+8,0x534ec9b8)
        u.mem_write(obj,struct.pack('<5I',vptr,0x11111111,0x22222222,0x33333333,0x7f))
        u.mem_write(payload+4,bytes([status]));word(trace,0x31545653)
        signals=[];waits=[];finished=[];dispatch_lr=[];callbacks=[]
        def returned(uc,value):uc.reg_write(UC_ARM_REG_R0,value);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        def hook(uc,address,size,data):
            if address==stop:finished.append(True);uc.emu_stop()
            elif address==0x535ca78c:returned(uc,manager)
            elif address==dispatch:
                proxy=uc.reg_read(UC_ARM_REG_R1);self.assertEqual(uc.reg_read(UC_ARM_REG_R2),info)
                dispatch_lr.append(uc.reg_read(UC_ARM_REG_LR));word(proxy+0x10,0x7f)
                callback=struct.unpack('<I',uc.mem_read(struct.unpack('<I',uc.mem_read(proxy,4))[0]+8,4))[0]
                callbacks.append(callback)
                for reg,val in zip(regs,[proxy,0x42000,payload]):uc.reg_write(reg,val)
                uc.reg_write(UC_ARM_REG_LR,callback_return);uc.reg_write(UC_ARM_REG_PC,callback)
            elif address==callback_return:uc.reg_write(UC_ARM_REG_PC,dispatch_lr.pop())
            elif address==0x536a9d1c:signals.append(uc.reg_read(UC_ARM_REG_R1));returned(uc,0)
            elif address==0x530512a8:
                waits.append(struct.unpack('<I',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),4))[0]);returned(uc,0)
            elif address in (0x536b9f1c,0x536a9dd4):returned(uc,0)
        u.hook_add(UC_HOOK_CODE,hook)
        sp=0x550ff000;u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,stop)
        for i,reg in enumerate(saved):u.reg_write(reg,0x12340000+i)
        for reg,val in zip(regs,[obj,info,trace,0xabcd1234]):u.reg_write(reg,val)
        start=self.manifest['exports']['m10v_save_trace_bridge'] if instrumented else 0x534ecb3c
        u.emu_start(start,stop+4,count=30000)
        self.assertTrue(finished,'bounded execution must reach return sentinel')
        self.assertEqual(u.reg_read(UC_ARM_REG_SP),sp)
        self.assertEqual([u.reg_read(reg) for reg in saved],[0x12340000+i for i in range(8)])
        self.assertEqual(signals,[2]);self.assertEqual(waits,[0xffffffff])
        words=struct.unpack('<164I',u.mem_read(trace,656));count=words[1]
        events=[list(words[4+i*5:9+i*5]) for i in range(count)]
        return dict(result=u.reg_read(UC_ARM_REG_R0),object_bytes=bytes(u.mem_read(obj,20)),events=events,callbacks=callbacks,flags=u.reg_read(UC_ARM_REG_CPSR)&0xf0000000)
    def test_stock_bridge_callback_status_and_abi_match(self):
        for status in [0,1,2,3]:
            with self.subTest(status=status):
                stock=self.run_bridge(status,False);actual=self.run_bridge(status)
                self.assertEqual(actual['result'],stock['result'])
                self.assertEqual(actual['object_bytes'],stock['object_bytes'])
                self.assertEqual(actual['result'],{0:1,1:0,2:0,3:0x7f}[status])
                self.assertEqual([row[0] for row in actual['events']],[180,181,182])
                self.assertEqual(actual['events'][1],[181,0x55021000,0x42000,status,0xabcd1234])
                self.assertEqual(actual['events'][2],[182,0x55021000,actual['result'],0xabcd1234,actual['result']])
    def test_foreign_object_bypasses_instrumentation(self):
        # Reuse exact callback table but with a cloned vptr. Wrapper must leave
        # the object alone and execute the original bridge without proxying.
        # A real foreign vtable is not safe for our synthetic service fixture.
        actual=self.run_bridge(0,True,vptr=0x55025000)
        self.assertEqual(actual['events'],[])
        self.assertEqual(actual['result'],1)
        self.assertEqual(actual['callbacks'],[0x534ec9b8])
    def test_bounded_owned_storage_and_lifecycle_records(self):
        from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
        from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_LR,UC_ARM_REG_SP
        regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(self.manifest['base'],0x2000);u.mem_write(self.manifest['base'],self.blob);u.mem_map(0x55000000,0x20000)
        trace,sp,stop=0x55001000,0x5501f000,0x5501e000
        u.mem_write(trace-4,b'\xa5'*664);u.reg_write(UC_ARM_REG_SP,sp)
        finished=[]
        def hook(uc,address,size,data):
            if address==stop:finished.append(True);uc.emu_stop()
        u.hook_add(UC_HOOK_CODE,hook)
        def call(name,args):
            finished.clear();u.reg_write(UC_ARM_REG_LR,stop)
            for r,v in zip(regs,args):u.reg_write(r,v)
            if len(args)>4:u.mem_write(sp,struct.pack('<'+'I'*(len(args)-4),*args[4:]))
            u.emu_start(self.manifest['exports'][name],stop+4,count=10000)
            self.assertTrue(finished);self.assertEqual(u.reg_read(UC_ARM_REG_SP),sp)
            return u.reg_read(UC_ARM_REG_R0)
        call('m10v_save_trace_init',[trace])
        for i in range(34):
            ok=call('m10v_save_trace_append',[trace,184,0x55030000,1,48_000_000,i])
            self.assertEqual(ok,int(i<25))
        words=struct.unpack('<164I',u.mem_read(trace,656));self.assertEqual(words[:4],(0x31545653,25,9,0))
        self.assertEqual(u.mem_read(trace-4,4),b'\xa5'*4);self.assertEqual(u.mem_read(trace+656,4),b'\xa5'*4)
        call('m10v_save_trace_init',[trace])
        specs=[('raw_set',183),('allocation',184),('transfer',185),('release',186)]
        for name,event in specs:call('m10v_save_trace_'+name,[trace,0x55030000,1,2,3])
        words=struct.unpack('<164I',u.mem_read(trace,656));self.assertEqual(words[1],4)
        for i,(_,event) in enumerate(specs):self.assertEqual(words[4+i*5:9+i*5],(event,0x55030000,1,2,3))
        # Contention never spins and never overwrites a current writer.
        u.mem_write(trace+12,struct.pack('<I',1));before=bytes(u.mem_read(trace,656))
        self.assertEqual(call('m10v_save_trace_append',[trace,999,1,2,3,4]),0)
        self.assertEqual(bytes(u.mem_read(trace,656)),before)

    def test_recipe_factory_setter_and_drain_preserve_ownership(self):
        from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
        from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_SP
        args=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
        saved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x1200000);u.mem_write(0x53000000,self.stock);u.mem_write(self.manifest['base'],self.blob);u.mem_map(0x55000000,0x200000)
        recipe,output,sp,stop=0x55010000,0x55020000,0x551f0000,0x551ff000
        returned_alloc=[recipe];calls=[];finished=[]
        def hook(uc,address,size,data):
            if address==stop:finished.append(True);uc.emu_stop()
            elif address==0x5351091c:
                calls.append(uc.reg_read(UC_ARM_REG_R0));uc.reg_write(UC_ARM_REG_R0,returned_alloc[0]);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
            elif address in (0x535216d0,0x53521d14):
                calls.append(tuple(uc.reg_read(r) for r in args));uc.reg_write(UC_ARM_REG_R0,0x71);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        def call(name,values):
            finished.clear();u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,stop)
            for i,r in enumerate(saved):u.reg_write(r,0x12345600+i)
            for r,v in zip(args,values):u.reg_write(r,v)
            if len(values)>4:u.mem_write(sp,struct.pack('<I',values[4]))
            u.emu_start(self.manifest['exports'][name],stop+4,count=50000)
            self.assertTrue(finished);self.assertEqual(u.reg_read(UC_ARM_REG_SP),sp)
            self.assertEqual([u.reg_read(r) for r in saved],[0x12345600+i for i in range(8)])
            return u.reg_read(UC_ARM_REG_R0)
        u.mem_write(recipe,b'\xa5'*0x5144)
        self.assertEqual(call('m10v_save_trace_recipe_alloc',[0x4778]),recipe)
        self.assertEqual(calls,[0x5140]);self.assertEqual(u.mem_read(recipe+0x4774,4),b'\xa5'*4)
        self.assertEqual(u.mem_read(recipe+0x5140,4),b'\xa5'*4)
        self.assertEqual(u.mem_read(recipe+0x4a08,1796),bytes(1796))
        u.mem_write(recipe,struct.pack('<I',0x53d0fc90));u.mem_write(recipe+0x252,struct.pack('<H',2))
        call('m10v_save_trace_recipe_set',[recipe,1,0x57000000])
        self.assertEqual(struct.unpack('<I',u.mem_read(recipe+0x60,4))[0],0x57000100)
        self.assertEqual(call('m10v_save_trace_recipe_allocate',[0x55550000,recipe,1,7]),0x71)
        self.assertEqual(call('m10v_save_trace_recipe_release',[0x55550000,recipe,1]),0x71)
        self.assertEqual(call('m10v_save_trace_recipe_mark',[recipe,199,1,2,3]),1)
        self.assertEqual(call('m10v_save_trace_recipe_take',[recipe,output,31]),0)
        count=call('m10v_save_trace_recipe_take',[recipe,output,32]);self.assertEqual(count,6)
        rows=struct.unpack('<30I',u.mem_read(output,120))
        self.assertEqual(list(rows[::5]),[187,183,188,186,189,199])
        self.assertEqual(call('m10v_save_trace_recipe_take',[recipe,output,32]),0)
        for i in range(35):call('m10v_save_trace_recipe_mark',[recipe,184,i,0,0])
        for i in range(6):self.assertEqual(call('m10v_save_trace_recipe_mark',[recipe,190+i,i,0,0]),1)
        self.assertEqual(call('m10v_save_trace_recipe_take',[recipe,output,32]),32)
        overflow=struct.unpack('<160I',u.mem_read(output,640))
        self.assertEqual(list(overflow[25*5:31*5:5]),list(range(190,196)))
        self.assertEqual(overflow[-5:],(199,recipe,10,31,0))
        returned_alloc[0]=0
        self.assertEqual(call('m10v_save_trace_recipe_alloc',[0x4778]),0)
        self.assertEqual(calls[-1],0x5140)
        self.assertEqual(call('m10v_save_trace_recipe_alloc',[0x20]),0)
        self.assertEqual(calls[-1],0x20)

    def test_raw_release_attestation_executes_original_pool_dispatch_and_setter_without_debug_records(self):
        from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
        import unicorn.arm_const as a
        spec=importlib.util.spec_from_file_location('pool_token',ROOT/'scripts/build_gr3_pool_release_trace.py');pool=importlib.util.module_from_spec(spec);spec.loader.exec_module(pool)
        with tempfile.TemporaryDirectory() as d:pb,pm=pool.build(d,0x540e4000,self.manifest['exports']['m10v_save_trace_recipe_mark'],raw_pool_return=self.manifest['exports']['m10v_save_trace_recipe_pool_return'])
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x1200000);u.mem_write(0x53000000,self.stock);u.mem_write(self.manifest['base'],self.blob);u.mem_write(pm['base'],pb);u.mem_map(0x55000000,0x300000);u.mem_map(0x60000000,0x10000)
        regs=[a.UC_ARM_REG_R0,a.UC_ARM_REG_R1,a.UC_ARM_REG_R2,a.UC_ARM_REG_R3];recipe=0x55010000;si=0x55100000;backing=0xa6d48380;source=0xa6e08370;sp=0x552f0000;stop=0x60000100;poolobj=0x55030000;vt=0x55030100;frees=[]
        def word(at,v):u.mem_write(at,struct.pack('<I',v))
        def ret(value):u.reg_write(a.UC_ARM_REG_R0,value);u.reg_write(a.UC_ARM_REG_PC,u.reg_read(a.UC_ARM_REG_LR))
        def hook(uc,at,size,data):
            if at in (stop,0x5351fd54):uc.emu_stop()
            elif at==0x5351091c:ret(recipe)
            elif at==0x536a2424:ret(0x55032000)
            elif at==0x536abf18:ret(poolobj)
            elif at==0x60000200:ret(1)
            elif at==0x60000300:frees.append(uc.reg_read(a.UC_ARM_REG_R1));ret(1)
            elif at==0x536b9f1c:ret(0)
        u.hook_add(UC_HOOK_CODE,hook)
        def call(name,args,lr=stop):
            u.reg_write(a.UC_ARM_REG_SP,sp);u.reg_write(a.UC_ARM_REG_LR,lr)
            for r,v in zip(regs,args):u.reg_write(r,v)
            u.emu_start(self.manifest['exports'][name],0x6000ffff,count=100000);self.assertEqual(u.reg_read(a.UC_ARM_REG_SP),sp);return u.reg_read(a.UC_ARM_REG_R0)
        call('m10v_save_trace_recipe_alloc',[0x4778]);word(recipe,0x53d0fc90);word(recipe+0x44c8,si);word(recipe+0x2f4,backing);word(recipe+0x60,source)
        word(poolobj,vt);word(vt+0x18,0x60000200);word(vt+0xc,0x60000300)
        word(0x53d0fc90+0x70,self.manifest['exports']['m10v_save_trace_recipe_set'])
        for patch in pm['patches']:u.mem_write(patch['address'],bytes.fromhex(patch['replacement_hex']))
        # Busy ring drops every diagnostic; control must not depend on them.
        word(recipe+0x4778+12,1)
        call('m10v_save_trace_recipe_release',[0x55040000,recipe,1],0x5351fd54)
        self.assertEqual(frees,[backing]);self.assertEqual(u.mem_read(recipe+0x2f4,4),bytes(4));self.assertEqual(u.mem_read(recipe+0x60,4),bytes(4))
        self.assertEqual(call('m10v_save_trace_recipe_raw_status',[recipe,si,0,0]),2)
        self.assertEqual(call('m10v_save_trace_recipe_raw_status',[recipe,si+4,0,0]),0)
        call('m10v_save_trace_init',[recipe+0x4778]);self.assertEqual(call('m10v_save_trace_recipe_raw_status',[recipe,si,0,0]),2)
        # A forged caller sample cannot hide a current nonzero RAW pointer.
        word(recipe+0x60,source);self.assertEqual(call('m10v_save_trace_recipe_raw_status',[recipe,si,0,0]),0);word(recipe+0x60,0)
        call('m10v_save_trace_recipe_set',[recipe,1,backing]);self.assertEqual(call('m10v_save_trace_recipe_raw_status',[recipe,si,0,0]),0)

if __name__=='__main__':unittest.main()
