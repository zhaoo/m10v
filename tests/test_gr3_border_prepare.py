"""Inactive prepare adapter: transactional metadata admission, never pixel RAM."""
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import test_gr3_border_bank as bank_tests
from scripts.build_gr3_m10v_library import FLAGS, link_object

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
RECIPE, MODULE, SI, RGB = 0x55010000, 0x55100000, 0x55200000, 0x55400000
CONFIG = RECIPE + 0x96c
SOURCE = ROOT / 'native/gr3/m10v_border_prepare.c'


def fixture(write, column=0, style=1):
    def words(address, *values): write(address, struct.pack('<'+'I'*len(values), *values))
    def halves(address, *values): write(address, struct.pack('<'+'H'*len(values), *values))
    words(RECIPE, 0x53d0fc90)
    words(RECIPE+0x4778, 0x31545653)
    words(RECIPE+0x510c, 0x42524400 | style)
    words(RECIPE+0x44c8, SI)
    words(RECIPE+0x5c, 0x55300000)
    words(RECIPE+0x304, 0x60000000)
    words(RECIPE+0x364, 72192000)
    halves(RECIPE+0x252, 6016, 4000, 6000, 4000)
    write(RECIPE+0x278,b'\x01')
    halves(RECIPE+0x280,4000)
    images = bank_tests.BorderBankTests().images()
    for n, offset in enumerate((0x70,0x90,0xb0,0xd0,0xf0)):
        write(RECIPE+offset, bytes(images[n]))
    words(CONFIG+0x10, 0x60000000, 72192000, images[0][1], images[0][2])
    words(CONFIG+0x30, RECIPE+0x1a8, SI, 0x55300000)
    words(MODULE+0x9ba8, RECIPE+0x1a8)
    write(MODULE+0x9904, bytes((1,1,1,1,0,0,0,0)))
    for n in range(4):
        words(MODULE+0x9914+4*n, RGB+0x100*n)
        write(RGB+0x100*n, b'\x08')
    write(MODULE+0x9938, bytes((1,1,1,1,0,0,0,0)))
    words(MODULE+0x9944,MODULE+0x8000)
    write(MODULE+0x8008,b'\x04\x00\x01')
    halves(RECIPE+0x2aa, 0, 2000, 4000)
    halves(RECIPE+0x296, 2000, 2000, 2000)
    write(MODULE+0x994c, bytes(images[0]))
    halves(MODULE+0x995c, 2000)
    words(MODULE+0x9950, images[0][1]+column, images[0][2]+column)


class PrepareHostTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.exists(), 'prepare adapter has not been implemented')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        stub = Path(self.tmp.name)/'camera.c'
        stub.write_text('#include <stdint.h>\nint m10v_border_camera_snapshot(uint32_t *s){(void)s;return 0;}\n')
        driver = Path(self.tmp.name)/'driver.c'
        driver.write_text('''#include <stdint.h>
#include <sys/mman.h>
#include <unistd.h>
extern int m10v_border_prepare(uint32_t,uint32_t);
int main(void){
    char *p=mmap((void *)0x55000000,0x1000000,3,MAP_PRIVATE|MAP_ANON|MAP_FIXED,-1,0);
    if(p==(void *)-1)return 90;
    unsigned starts[3]={0x10000,0x100000,0x400000},lengths[3]={0x5200,0xa000,0x500};
    for(;;){uint32_t args[2];unsigned got=0;while(got<8){ssize_t r=read(0,(char *)args+got,8-got);if(r<=0)return got?94:0;got+=(unsigned)r;}
    for(unsigned i=0;i<3;i++){unsigned n=0;while(n<lengths[i]){ssize_t r=read(0,p+starts[i]+n,lengths[i]-n);if(r<=0)return 91;n+=(unsigned)r;}}
    int result=m10v_border_prepare(args[0],args[1]);
    if(write(1,&result,4)!=4)return 92;
    for(unsigned i=0;i<3;i++){unsigned n=0;while(n<lengths[i]){ssize_t r=write(1,p+starts[i]+n,lengths[i]-n);if(r<=0)return 93;n+=(unsigned)r;}}
    }
}
''')
        self.binary = Path(self.tmp.name)/'prepare-host'
        # Darwin arm64 requires a4GiB PAGEZERO. An x86_64 host executable
        # under Rosetta can reserve firmware ABI metadata addresses below4GiB.
        link_flags = ['-arch','x86_64','-Wl,-pagezero_size,0x1000','-Wl,-no_pie'] if sys.platform=='darwin' else []
        result = subprocess.run(['clang','-O2','-Wall','-Wextra','-Werror',*link_flags,
            *[str(ROOT/'native/gr3'/name) for name in ('m10v_border.c','m10v_border_bank.c',
                'm10v_border_shot.c','m10v_border_prepare.c')],str(stub),str(driver),
                '-o',str(self.binary)], capture_output=True,text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.memory = bytearray(0x1000000)
        self.process = None
        self.addCleanup(self.stop_process)
        fixture(self.write)

    def write(self, address, data): self.memory[address-0x55000000:address-0x55000000+len(data)]=data
    def read(self, address, length): return bytes(self.memory[address-0x55000000:address-0x55000000+length])
    def prepare(self,module,config):
        if self.process is None:
            self.process=subprocess.Popen([str(self.binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        self.process.stdin.write(struct.pack('<2I',module,config)+self.snapshot())
        self.process.stdin.flush()
        result=self.process.stdout.read(0xf704)
        self.assertEqual(len(result),0xf704,'host executable stopped: '+str(self.process.poll()))
        offset=4
        for address,length in ((RECIPE,0x5200),(MODULE,0xa000),(RGB,0x500)):
            self.write(address,result[offset:offset+length]);offset+=length
        return struct.unpack('<i',result[:4])[0]
    def stop_process(self):
        if self.process is not None:
            self.process.stdin.close();self.process.wait(timeout=10);self.process.stdout.close()
    def put(self, address, value): self.write(address,struct.pack('<I',value))
    def get(self, address): return struct.unpack('<I',self.read(address,4))[0]
    def snapshot(self):
        return self.read(RECIPE,0x5200)+self.read(MODULE,0xa000)+self.read(RGB,0x500)

    def test_admits_each_stripe_without_common_raw_mutation_and_is_idempotent(self):
        original_status = self.read(RECIPE+0x1a8,0x180)
        raw = self.read(RECIPE+0x5110,48)
        first = None
        for column in (0,2000,4000):
            # Native helper resets output pitch each iteration from common RAW status.
            self.write(MODULE+0x9960,struct.pack('<H',6016))
            self.put(MODULE+0x9950,self.get(CONFIG+0x18)+column)
            self.put(MODULE+0x9954,self.get(CONFIG+0x1c)+column)
            self.assertEqual(self.prepare(MODULE,CONFIG),1)
            self.assertEqual(self.get(CONFIG+0x18),self.get(RECIPE+0x74))
            self.assertEqual(self.get(CONFIG+0x1c),self.get(RECIPE+0x78))
            self.assertEqual(self.get(MODULE+0x9950),self.get(CONFIG+0x18)+column)
            self.assertEqual(self.get(MODULE+0x9954),self.get(CONFIG+0x1c)+column)
            self.assertEqual(struct.unpack('<H',self.read(MODULE+0x9960,2))[0],6336)
            self.assertEqual(self.read(RECIPE+0x1a8,0x180),original_status)
            self.assertEqual(self.read(RECIPE+0x5110,48),raw)
            descriptors = self.read(RECIPE+0x70,160)
            if first is None: first = descriptors
            self.assertEqual(descriptors,first)

    def test_rejection_does_not_partially_relayout_metadata(self):
        mutations = [(CONFIG+0x30,0),(CONFIG+0x34,SI+4),(CONFIG+0x10,0x64000000),
            (MODULE+0x9ba8,0),(MODULE+0x9914,0),(RGB+4,0x60001000),
            (RECIPE+0x510c,0),(RECIPE+0x364,50000000),(CONFIG+0x18,0x60004000),
            (MODULE+0x9954,0x70000000),(MODULE+0x9958,0x70000000),
            (MODULE+0x9964,1),(RECIPE+0x2aa,0x10001770)]
        for address,value in mutations:
            self.memory[:]=bytes(len(self.memory)); fixture(self.write)
            self.put(address,value); before = self.snapshot()
            self.assertLess(self.prepare(MODULE,CONFIG),0,(hex(address),hex(value)))
            self.assertEqual(self.snapshot(),before)
        for address in (MODULE+0x9904,MODULE+0x9908,MODULE+0x9939,CONFIG+0x49,RGB):
            self.memory[:]=bytes(len(self.memory)); fixture(self.write)
            self.write(address,b'\x02'); before=self.snapshot()
            self.assertLess(self.prepare(MODULE,CONFIG),0,hex(address))
            self.assertEqual(self.snapshot(),before)

    def test_output_rejection_codes_identify_the_real_field(self):
        cases=((RECIPE+0x278,b'\0',-19),
               (MODULE+0x9958,struct.pack('<I',1),-23),
               (MODULE+0x995e,struct.pack('<H',1),-24),
               (MODULE+0x9966,struct.pack('<H',1),-26))
        for address,data,reason in cases:
            self.memory[:]=bytes(len(self.memory));fixture(self.write)
            self.write(address,data)
            before=self.snapshot()
            self.assertEqual(self.prepare(MODULE,CONFIG),reason)
            self.assertEqual(self.snapshot(),before)

    def test_off_does_not_access_module_or_image_descriptors(self):
        self.put(CONFIG+0x30,0);self.put(RECIPE+0x304,0)
        for phase in (0,6):
            self.put(RECIPE+0x510c,0x42524400|(phase<<5))
            before=self.snapshot()
            self.assertEqual(self.prepare(1,CONFIG),0)
            self.assertEqual(self.snapshot(),before)

    def test_prepare_rejects_after_postprocessing_phase_starts(self):
        for phase in (1,2,3,4,5):
            self.put(RECIPE+0x510c,0x42524401|(phase<<5))
            before=self.snapshot()
            self.assertLess(self.prepare(MODULE,CONFIG),0,phase)
            self.assertEqual(self.snapshot(),before)

    def test_prepared_phase_repeats_all_three_stripes_without_new_layout(self):
        self.assertEqual(self.prepare(MODULE,CONFIG),1)
        first=self.read(RECIPE+0x70,160)
        self.put(RECIPE+0x510c,0x425244c1) # root hook owns FROZEN0->PREPARED6
        for column in (0,2000,4000):
            self.write(MODULE+0x9960,struct.pack('<H',6016))
            self.put(MODULE+0x9950,self.get(CONFIG+0x18)+column)
            self.put(MODULE+0x9954,self.get(CONFIG+0x1c)+column)
            self.assertEqual(self.prepare(MODULE,CONFIG),1)
            self.assertEqual(self.read(RECIPE+0x70,160),first)
            self.assertEqual(self.get(RECIPE+0x510c),0x425244c1)

    def test_native_halo_keeps_roi_geometry_and_uses_reserved_row_guards(self):
        self.write(RECIPE+0x278,b'\x02') # status+d0 native enabled
        self.write(MODULE+0x800a,b'\x02')
        self.write(RECIPE+0x27c,struct.pack('<H',40))
        self.write(RECIPE+0x280,struct.pack('<H',4012))
        self.write(RECIPE+0x2aa,struct.pack('<3H',0,1960,3944))
        self.write(RECIPE+0x282,struct.pack('<3H',68,12,12))
        self.write(RECIPE+0x296,struct.pack('<3H',1972,1996,2068))
        for column,roi_x,width in ((0,68,1972),(1960,12,1996),(3944,12,2068)):
            self.put(MODULE+0x9950,self.get(CONFIG+0x18)+column)
            self.put(MODULE+0x9954,self.get(CONFIG+0x1c)+column)
            self.write(MODULE+0x995c,struct.pack('<6H',width,4012,6016,4000,roi_x,40))
            before=bytearray(self.read(MODULE+0x994c,32))
            self.assertEqual(self.prepare(MODULE,CONFIG),1)
            after=bytearray(self.read(MODULE+0x994c,32))
            for start,end in ((4,12),(20,22)):before[start:end]=after[start:end]
            self.assertEqual(before,after,'native crop/format/height/cache fields must stay unchanged')
            self.assertEqual(struct.unpack('<H',after[20:22])[0],6336)
        # Same native output widths, but an unsafe ROI causes admission to
        # fail after planning, before any relocated descriptor is committed.
        self.write(RECIPE+0x286,struct.pack('<H',1000))
        self.write(MODULE+0x9964,struct.pack('<H',1000))
        before=self.snapshot();self.assertLess(self.prepare(MODULE,CONFIG),0)
        self.assertEqual(self.snapshot(),before)
        self.write(RECIPE+0x286,struct.pack('<H',12))
        self.write(MODULE+0x9964,struct.pack('<H',12))
        self.write(RECIPE+0x27c,struct.pack('<H',200))
        self.write(MODULE+0x9966,struct.pack('<H',200))
        before=self.snapshot();self.assertLess(self.prepare(MODULE,CONFIG),0)
        self.assertEqual(self.snapshot(),before)


class PrepareArmTests(unittest.TestCase):
    def test_scalar_arm_runs_real_bank_and_shot_without_external_work(self):
        self.assertTrue(SOURCE.exists(), 'prepare adapter has not been implemented')
        from scripts.analyze_gr3_border_iip import OriginalArm
        from unicorn import UC_HOOK_CODE
        blobs=[];symbols={'m10v_border_camera_snapshot':0x560f0000}
        with tempfile.TemporaryDirectory() as tmp:
            for n,name in enumerate(('m10v_border','m10v_border_bank','m10v_border_shot','m10v_border_prepare')):
                obj=Path(tmp)/(name+'.o')
                result=subprocess.run(['clang',*FLAGS,'-c',str(ROOT/'native/gr3'/(name+'.c')),
                                       '-o',str(obj)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                exports_by_module=(('m10v_border_layout','m10v_border_storage_layout','m10v_border_preview_fit'),
                    ('m10v_border_bank_shape','m10v_border_bank_plan'),('m10v_border_shot_freeze','m10v_border_shot_read',
                     'm10v_border_shot_orientation','m10v_border_shot_phase',
                     'm10v_border_shot_transition'),('m10v_border_prepare',))
                code,exports=link_object(obj.read_bytes(),0x56000000+n*0x10000,symbols,
                                         prefix='m10v_zoom_',additional_exports=exports_by_module[n])
                symbols.update(exports);blobs.append((0x56000000+n*0x10000,code))
        for rom_path in ('builds/gr3-extension-validation/official-rtos.bin',
                         'builds/gr3-border-iip-20261027/gr3x-official-rtos.bin'):
            p=OriginalArm((ROOT/rom_path).read_bytes());p.u.mem_map(0x56000000,0x100000)
            for address,code in blobs:p.u.mem_write(address,code)
            for address,length in ((RECIPE,0x5200),(MODULE,0xa000),(RGB,0x500)):
                p.u.mem_write(address,bytes(length))
            fixture(p.u.mem_write)
            calls=[];trace=[];invalidation={'enabled':False,'return':0,'kind':'capacity','phase':0}
            def hook(u,pc,size,data):
                if 0x56030000<=pc<0x56040000:trace.append(hex(pc))
                if pc==symbols['m10v_border_bank_plan']:
                    calls.append('bank_plan')
                    if invalidation['enabled']:invalidation['return']=u.reg_read(p.A.UC_ARM_REG_LR)
                if pc==invalidation['return']:
                    if invalidation['kind']=='phase':
                        p.words(RECIPE+0x510c,0x42524401|(invalidation['phase']<<5))
                    else:p.words(CONFIG+0x14,50000000)
                    invalidation['return']=0
                if pc in (0x560f0000,0x536af2a8,0x536a9e8c,0x536abd28,0x53828014):
                    self.fail('prepare performed snapshot/alloc/wait/submit/filesystem work')
            p.u.hook_add(UC_HOOK_CODE,hook)
            self.assertEqual(p.call(symbols['m10v_border_prepare'],MODULE,CONFIG),1,str(calls)+str(trace[-24:]))
            self.assertEqual(calls,['bank_plan'])
            self.assertEqual(p.read_words(CONFIG+0x18,1),p.read_words(RECIPE+0x74,1))
            # Real native helper and output-binding fragments before each
            # stripe, followed by the adapter and real original R2Y packer.
            from scripts.border_backresize_contract import fragment
            fixture(p.u.mem_write)
            p.words(MODULE+0x9b54,0x55500000)
            p.u.mem_write(RECIPE+0x278,b'\x02')
            p.u.mem_write(RECIPE+0x27c,struct.pack('<H',40))
            p.u.mem_write(RECIPE+0x280,struct.pack('<H',4012))
            p.u.mem_write(RECIPE+0x282,struct.pack('<3H',68,12,12))
            p.u.mem_write(RECIPE+0x296,struct.pack('<3H',1972,1996,2068))
            p.u.mem_write(RECIPE+0x2aa,struct.pack('<3H',0,1960,3944))
            for index,(column,roi_x,width) in enumerate(((0,68,1972),(1960,12,1996),(3944,12,2068))):
                p.call(0x53501910,MODULE,CONFIG)
                fragment(p,0x53501f00,0x53501f24,{'r2':RECIPE+0x2aa+2*index,
                    'r6':CONFIG,'r4':MODULE+0x9000,'r0':RGB+0x400})
                fragment(p,0x53501f28,0x53501f40,{'r3':RECIPE+0x1a8+2*index,'r4':MODULE+0x9000})
                self.assertEqual(p.call(symbols['m10v_border_prepare'],MODULE,CONFIG),1,
                    str(trace[-24:])+str(list(p.u.mem_read(MODULE+0x9938,8)))+
                    str(list(p.u.mem_read(MODULE+0x994c,32))))
                if index==0:
                    self.assertEqual(p.call(symbols['m10v_border_shot_transition'],RECIPE,0,6),1)
                p.call(0x5366dc90,0x55520000,0x55510000,MODULE+0x9938)
                self.assertEqual(p.read_words(0x55510000+0x60,4),[roi_x,width,40,4012])
                self.assertEqual(p.read_words(0x55510000+0x4c,1),[6336])
                self.assertEqual(p.read_words(0x55510000+0x90,2),
                    [p.read_words(CONFIG+0x18,1)[0]+column,p.read_words(CONFIG+0x1c,1)[0]+column])
            before=bytes(p.u.mem_read(RECIPE+0x70,160))+bytes(p.u.mem_read(MODULE+0x994c,32))
            invalidation['enabled']=True
            self.assertGreaterEqual(p.call(symbols['m10v_border_prepare'],MODULE,CONFIG),0xffffff00)
            self.assertEqual(bytes(p.u.mem_read(RECIPE+0x70,160))+
                             bytes(p.u.mem_read(MODULE+0x994c,32)),before)
            self.assertEqual(p.read_words(CONFIG+0x14,1),[50000000])
            for before_phase,after_phase in ((0,6),(6,0),(6,1)):
                for address,length in ((RECIPE,0x5200),(MODULE,0xa000),(RGB,0x500)):
                    p.u.mem_write(address,bytes(length))
                fixture(p.u.mem_write)
                p.words(RECIPE+0x510c,0x42524401|(before_phase<<5))
                invalidation.update({'kind':'phase','phase':after_phase,'return':0})
                before=bytes(p.u.mem_read(RECIPE+0x70,160))+bytes(p.u.mem_read(CONFIG+0x18,8))+bytes(p.u.mem_read(MODULE+0x994c,32))
                calls.clear()
                self.assertGreaterEqual(p.call(symbols['m10v_border_prepare'],MODULE,CONFIG),0xffffff00)
                self.assertEqual(calls,['bank_plan'],'phase must change after actual planning')
                self.assertEqual(bytes(p.u.mem_read(RECIPE+0x70,160))+bytes(p.u.mem_read(CONFIG+0x18,8))+
                                 bytes(p.u.mem_read(MODULE+0x994c,32)),before)
                self.assertEqual(p.read_words(RECIPE+0x510c,1),[0x42524401|(after_phase<<5)])
            p.words(RECIPE+0x510c,0x42524400);calls.clear()
            self.assertEqual(p.call(symbols['m10v_border_prepare'],1,CONFIG),0)
            self.assertEqual(calls,[])
            self.assertEqual(p.assertions,[])


if __name__ == '__main__':unittest.main()
