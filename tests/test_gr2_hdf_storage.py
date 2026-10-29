"""Independent GR3-compatible HDF wire journal on the GR II BE32 CPU."""
import struct,tempfile,unittest,zlib
from pathlib import Path
from tests import test_gr2_runtime_build as runtime_tests
from tests.test_unity_update import component

class Gr2HdfStorageTests(unittest.TestCase):
    def test_independent_hdf_journal_keeps_active_copy_verifies_readback_and_never_resets_unknown_files(self):
        from scripts.build_gr2_runtime import build_gr2_runtime
        from unicorn import UC_HOOK_CODE,arm_const as r
        with tempfile.TemporaryDirectory() as folder:runtime=build_gr2_runtime(component('gr2','b01firm8'),{},Path(folder))
        self.assertIn('gr2_hdf_journal_load',runtime['symbols']);self.assertIn('gr2_hdf_journal_store',runtime['symbols'])
        u=runtime_tests.Gr2RuntimeBuildTests.machine(self,runtime);io=0x50000000;out=0x50001000
        u.mem_write(io,struct.pack('>2I',0x5001d000,0x5001d004));paths=['H:/M10VHD0.BIN','H:/M10VHD1.BIN']
        def wire(sequence,strength):
            data=struct.pack('<5I',0x31464448,1,sequence,strength,0);return data+struct.pack('<I',zlib.crc32(data))
        files={};writes=[];fault={'mode':None}
        def boundary(uc,address,size,unused):
            path=bytes(uc.mem_read(uc.reg_read(r.UC_ARM_REG_R0),24)).split(b'\0',1)[0].decode();self.assertIn(path,paths)
            buffer=uc.reg_read(r.UC_ARM_REG_R1);count=uc.reg_read(r.UC_ARM_REG_R2)
            if address==0x5001d000:
                self.assertEqual(count,25)
                if path not in files or writes and path==writes[-1] and fault['mode']=='read':value=-1
                else:
                    data=files[path][:count];uc.mem_write(buffer,data);value=len(data)
            else:
                self.assertEqual(count,24);data=bytes(uc.mem_read(buffer,count));writes.append(path)
                if fault['mode']=='short':data=data[:12]
                if fault['mode']=='trailing':data+=b'!'
                if fault['mode']=='crc':data=data[:-1]+bytes([data[-1]^1])
                files[path]=data;value=-1 if fault['mode']=='close' else 12 if fault['mode']=='short' else count
            uc.reg_write(r.UC_ARM_REG_R0,value&0xffffffff);uc.reg_write(r.UC_ARM_REG_PC,uc.reg_read(r.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,boundary,begin=0x5001d000,end=0x5001d004)
        call=lambda name,args:runtime_tests.Gr2RuntimeBuildTests.call(self,u,runtime['symbols'][name],args)
        def load():
            u.mem_write(out,b'\xa5'*8);return call('gr2_hdf_journal_load',[io,out,out+4])
        for mode in (None,'short','trailing','crc','read','close'):
            with self.subTest(mode=mode):
                files.clear();files.update(zip(paths,(wire(6,1),wire(7,2))));writes.clear();fault['mode']=mode
                self.assertEqual(load(),1);self.assertEqual(struct.unpack('>2I',u.mem_read(out,8)),(2,7))
                self.assertEqual(call('gr2_hdf_journal_store',[io,3]),int(mode is None));self.assertEqual(writes,[paths[0]])
                self.assertEqual(files[paths[1]],wire(7,2))
                self.assertEqual(load(),1);self.assertEqual(struct.unpack('>2I',u.mem_read(out,8)),(3,8) if mode in (None,'close') else (2,7))
                if mode is None:self.assertEqual(files[paths[0]],wire(8,3))
        fault['mode']=None;files.clear();files.update(zip(paths,(wire(7,2),wire(6,1))));writes.clear()
        self.assertEqual(call('gr2_hdf_journal_store',[io,3]),1);self.assertEqual(writes,[paths[1]])
        self.assertEqual(files[paths[0]],wire(7,2));self.assertEqual(files[paths[1]],wire(8,3))
        fault['mode']=None
        for bad in ({},{paths[0]:b'broken',paths[1]:b'unknown'},{paths[1]:wire(0xffffffff,1)}):
            files.clear();files.update(bad);writes.clear();before=dict(files)
            self.assertEqual(call('gr2_hdf_journal_store',[io,1]),0);self.assertEqual(writes,[]);self.assertEqual(files,before)
        files.clear();writes.clear();self.assertEqual(load(),0);self.assertEqual(bytes(u.mem_read(out,8)),b'\xa5'*8)
        self.assertEqual(call('gr2_hdf_journal_store',[io,4]),0);self.assertEqual(writes,[])

    def test_hdf_absence_uses_original_fat_search_independently_of_film_journals(self):
        from scripts.build_gr2_runtime import build_gr2_runtime
        from scripts.analyze_gr2_native_contract import probe_fat_directory
        code=component('gr2','b01firm8')
        with tempfile.TemporaryDirectory() as folder:runtime=build_gr2_runtime(code,{},Path(folder))
        self.assertIn('gr2_hdf_journals_absent',runtime['symbols'])
        for entries,error,short,expected in (((),0,False,1),(('M10V5A.bin','M10V5B.bin'),0,False,1),(('M10VHD0.BIN',),0,False,0),(('M10VHD1.BIN',),0,False,0),((),9,False,-1),((),0,True,-1)):
            result=probe_fat_directory(code,entries=entries,read_error=error,short_read=short,native_runtime=runtime,cache_boundary=True,hdf=True)
            self.assertEqual(result['native_absent_return'],expected);self.assertTrue(result['pool_restored'])

    def _assert_first_initialization(self,strength):
        from scripts.build_gr2_runtime import build_gr2_runtime
        from unicorn import UC_HOOK_CODE,arm_const as r
        from scripts.build_gr2_runtime import configuration_state
        configuration=configuration_state({})[0];configuration['hdf']=strength
        with tempfile.TemporaryDirectory() as folder:runtime=build_gr2_runtime(component('gr2','b01firm8'),configuration,Path(folder))
        self.assertEqual(runtime['initial_hdf_strength'],strength)
        self.assertIn('gr2_hdf_initialize_state',runtime['symbols'])
        u=runtime_tests.Gr2RuntimeBuildTests.machine(self,runtime);files={};writes=[];absence=[];behavior={'ready':1,'absent':1,'fail':False,'pool':1}
        paths=['H:/M10VHD0.BIN','H:/M10VHD1.BIN']
        def boundary(uc,address,size,unused):
            if address==runtime['symbols']['gr2_ui_storage_ready']:value=behavior['ready']
            elif address==runtime['symbols']['gr2_hdf_journals_absent']:absence.append(True);value=behavior['absent']
            elif address==runtime['symbols']['gr2_hdf_prepare_pool']:
                self.assertEqual(uc.reg_read(r.UC_ARM_REG_R0),strength);value=behavior['pool']
            else:
                path=bytes(uc.mem_read(uc.reg_read(r.UC_ARM_REG_R0),24)).split(b'\0',1)[0].decode();self.assertIn(path,paths)
                buffer=uc.reg_read(r.UC_ARM_REG_R1);count=uc.reg_read(r.UC_ARM_REG_R2)
                if address==runtime['symbols']['gr2_file_read']:
                    data=files.get(path);value=-1 if data is None else min(count,len(data))
                    if value>0:uc.mem_write(buffer,data[:value])
                else:
                    writes.append(path);files[path]=bytes(uc.mem_read(buffer,count));value=-1 if behavior['fail'] else count
            uc.reg_write(r.UC_ARM_REG_R0,value&0xffffffff);uc.reg_write(r.UC_ARM_REG_PC,uc.reg_read(r.UC_ARM_REG_LR))
        for name in ('gr2_ui_storage_ready','gr2_hdf_journals_absent','gr2_file_read','gr2_file_write','gr2_hdf_prepare_pool'):
            u.hook_add(UC_HOOK_CODE,boundary,begin=runtime['symbols'][name],end=runtime['symbols'][name])
        call=lambda:runtime_tests.Gr2RuntimeBuildTests.call(self,u,runtime['symbols']['gr2_hdf_initialize_state'],[])
        for ready,absent,existing,expected in ((0,1,{},0),(1,0,{paths[0]:b'broken'},0),(1,-1,{},0),(1,1,{},1)):
            files.clear();files.update(existing);writes.clear();absence.clear();behavior.update(ready=ready,absent=absent)
            self.assertEqual(call(),expected)
            self.assertEqual(writes,[paths[1]] if expected else [])
            if not ready:self.assertEqual(absence,[])
            if expected:
                raw=files[paths[1]];self.assertEqual(struct.unpack('<6I',raw),(0x31464448,1,1,strength,0,zlib.crc32(raw[:20])))
                writes.clear();absence.clear();behavior['absent']=0;self.assertEqual(call(),1);self.assertEqual(writes,[]);self.assertEqual(absence,[])

        if strength:
            # A configured first-use grade must be admitted before creating a
            # journal. A valid existing grade still wins over compiled defaults.
            old=struct.pack('<5I',0x31464448,1,2,0,0);old+=struct.pack('<I',zlib.crc32(old))
            files.clear();files[paths[0]]=old;writes.clear();behavior.update(absent=0,pool=0)
            self.assertEqual(call(),1);self.assertEqual(files[paths[0]],old);self.assertEqual(writes,[])
            files.clear();behavior['absent']=1;self.assertEqual(call(),0);self.assertEqual(writes,[])

    def test_hdf_first_initialization_requires_exact_absence_and_keeps_corrupt_or_unreadable_banks(self):
        self._assert_first_initialization(0)

    def test_web_hdf_initial_strength_is_used_only_for_proven_absent_journals_after_pool_admission(self):
        for strength in (1,2,3):
            with self.subTest(strength=strength):self._assert_first_initialization(strength)

    def test_native_hdf_file_bridge_admits_only_exact_independent_root_names(self):
        from scripts.build_gr2_runtime import build_gr2_runtime
        from scripts.analyze_gr2_native_contract import runtime_machine
        from unicorn import UC_HOOK_CODE,arm_const as r
        code=component('gr2','b01firm8')
        with tempfile.TemporaryDirectory() as folder:runtime=build_gr2_runtime(code,{},Path(folder))
        u=runtime_machine(code);u.mem_write(runtime['base'],bytes.fromhex(runtime['runtime_hex']));opened=[]
        def fail_open(uc,address,size,unused):
            opened.append(bytes(uc.mem_read(uc.reg_read(r.UC_ARM_REG_R0),32)).split(b'\0',1)[0].decode())
            self.assertEqual(uc.reg_read(r.UC_ARM_REG_R1),1);uc.reg_write(r.UC_ARM_REG_R0,0);uc.reg_write(r.UC_ARM_REG_PC,uc.reg_read(r.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,fail_open,begin=0xa002c70e,end=0xa002c70e)
        allowed=['H:/M10VHD0.BIN','H:/M10VHD1.BIN']
        denied=['H:/M10VHD2.BIN','H:/M10VHD0.BIN.extra','H:/M10VHD0.BIN/../other','A:/M10VHD0.BIN','H:/M10VHD.BIN','H:/M10VHD00.BIN']
        for path in allowed+denied:
            opened.clear();u.mem_write(0x50001000,path.encode()+b'\0')
            self.assertEqual(runtime_tests.Gr2RuntimeBuildTests.call(self,u,runtime['symbols']['gr2_file_write'],[0x50001000,0x50002000,24]),0xffffffff)
            self.assertEqual(opened,[path] if path in allowed else [])
