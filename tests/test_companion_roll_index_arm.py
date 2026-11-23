"""Run the actual read-only ARM archive scanner against a virtual SD filesystem."""
from pathlib import Path
import ctypes
import os
import struct
import subprocess
import tempfile
import unittest
import zlib

from tests.test_gr3_roll_photo import fixture, ROLL_ID

ROOT = Path(__file__).resolve().parents[1]


class RollIndexArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        d = Path(cls.temp.name)
        wrapper = d / 'probe.c'
        wrapper.write_text('''#include "linux_roll.h"
void m10v_linux_trace(const char *event,const uint32_t *values,unsigned count){
 register unsigned r0 __asm__("r0")=(unsigned)event,r1 __asm__("r1")=(unsigned)values,r2 __asm__("r2")=count,r7 __asm__("r7")=0xfe00;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r7):"memory","cc");
}
int latest_probe(m10v_roll_record *out){return m10v_linux_roll_index_source.latest(0,out);}
int page_probe(uint32_t cursor,m10v_roll_index_page *out){return m10v_linux_roll_index_source.photos(0,cursor,out);}
''')
        objects = []
        for source in [ROOT/'native/companion/linux_roll.c', ROOT/'native/companion/roll_photo.c',
                       ROOT/'native/companion/runtime.c', ROOT/'native/gr3/m10v_roll.c', wrapper]:
            obj = d/(source.stem+'.o')
            subprocess.run(['/opt/homebrew/opt/llvm/bin/clang', '--target=armv7-none-eabi',
                            '-mcpu=cortex-a9', '-marm', '-mfloat-abi=soft', '-Os', '-std=c11',
                            '-ffreestanding', '-fno-builtin', '-DM10V_COMPANION_LIVE_SOURCE=1', '-ffunction-sections', '-fdata-sections',
                            '-Wall', '-Wextra', '-Werror', '-I', str(ROOT/'native/companion'),
                            '-c', str(source), '-o', str(obj)], check=True, capture_output=True)
            objects.append(str(obj))
        elf = d/'scanner.elf'
        subprocess.run(['/opt/homebrew/bin/ld.lld', '-m', 'armelf_linux_eabi', '-Ttext=0x10000',
                        '--gc-sections', '--entry=latest_probe', '--undefined=page_probe', *objects,
                        '-o', str(elf)], check=True, capture_output=True)
        cls.binary = elf.read_bytes()
        names = subprocess.check_output(['/opt/homebrew/opt/llvm/bin/llvm-nm', elf], text=True)
        cls.symbols = {line.split()[2]: int(line.split()[0],16) for line in names.splitlines() if len(line.split())==3}

    def setUp(self):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR
        from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
            UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R7, UC_ARM_REG_LR,
            UC_ARM_REG_SP, UC_ARM_REG_PC)
        self.reg = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                    UC_ARM_REG_R4, UC_ARM_REG_R5)
        self.r7,self.lr,self.sp,self.pc = UC_ARM_REG_R7,UC_ARM_REG_LR,UC_ARM_REG_SP,UC_ARM_REG_PC
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map(0x10000, 0x200000)
        off = struct.unpack_from('<I',self.binary,28)[0]
        size,count = struct.unpack_from('<HH',self.binary,42)
        for n in range(count):
            seg = struct.unpack_from('<8I',self.binary,off+n*size)
            if seg[0]==1:self.uc.mem_write(seg[2],self.binary[seg[1]:seg[1]+seg[4]])
        self.files = {}
        self.dirs = {'/media/storage1':['DCIM'], '/media/storage1/DCIM':['100RICOH'],
                     '/media/storage1/DCIM/100RICOH':[]}
        self.handles = {}
        self.opens = self.reads = 0
        self.traces = []
        self.offline = False
        self.mapping = False
        self.allocation_fail = False
        self.fail_read_from = None
        self.uc.hook_add(UC_HOOK_INTR,self.syscall)

    def text(self, at):
        out=bytearray()
        while self.uc.mem_read(at,1)!=b'\0':out+=self.uc.mem_read(at,1);at+=1
        return out.decode()

    def syscall(self, uc, _interrupt, _unused):
        n=uc.reg_read(self.r7);a=[uc.reg_read(r) for r in self.reg]
        if n == 0xfe00:
            self.traces.append((self.text(a[0]),struct.unpack('<'+'I'*a[2],uc.mem_read(a[1],a[2]*4))))
            result = 0
        elif n == 192:
            self.assertFalse(self.mapping)
            self.assertLessEqual(a[1], 6000)
            self.assertEqual((a[2],a[3],a[4]), (3,0x22,0xffffffff))
            result = -12 if self.allocation_fail else 0x190000
            if not self.allocation_fail:
                self.mapping = True
                uc.mem_write(result, bytes(a[1]))
        elif n == 91:
            self.assertTrue(self.mapping)
            self.assertEqual(a[0],0x190000)
            self.mapping = False
            result = 0
        elif n in (5,322):
            path=self.text(a[0] if n==5 else a[1])
            if n==322:path=self.handles[a[0]][0]+'/'+path
            self.opens+=1
            if self.offline or path not in self.files and path not in self.dirs:result=-2
            else:
                result=max([9,*self.handles])+1;self.handles[result]=[path,0]
        elif n==6:
            self.handles.pop(a[0],None);result=0
        elif n==19:
            source=self.files[self.handles[a[0]][0]]
            result=source.stat().st_size if isinstance(source,Path) else len(source)
        elif n==180:
            self.reads+=1
            if self.fail_read_from is not None and a[4] >= self.fail_read_from: result = -5
            else:
                source=self.files[self.handles[a[0]][0]]
                if isinstance(source,Path):
                    with source.open('rb') as stream: stream.seek(a[4]);data=stream.read(a[2])
                else:data=source[a[4]:a[4]+a[2]]
                uc.mem_write(a[1],data);result=len(data)
        elif n==217:
            path,pos=self.handles[a[0]];entries=self.dirs[path];data=bytearray()
            while pos<len(entries):
                name=entries[pos].encode()+b'\0';length=(19+len(name)+7)&~7
                if len(data)+length>a[2]:break
                entry=bytearray(length);struct.pack_into('<QQH',entry,0,pos+1,pos+1,length)
                entry[19:19+len(name)]=name;data+=entry;pos+=1
            self.handles[a[0]][1]=pos;uc.mem_write(a[1],bytes(data));result=len(data)
        else:self.fail(f'write or unexpected syscall {n}')
        uc.reg_write(self.reg[0],result&0xffffffff)

    def invoke(self,name,*args):
        for reg,arg in zip(self.reg,args):self.uc.reg_write(reg,arg)
        self.uc.reg_write(self.sp,0x200000)
        self.uc.reg_write(self.lr,0x1f0000)
        self.uc.emu_start(self.symbols[name],0x1f0000,count=2000000)
        return ctypes.c_int32(self.uc.reg_read(self.reg[0])).value

    def journal(self, *,count=0, corrupt=False):
        raw=struct.pack('<II16sIIIII',0x314c4f52,3,b'j'*16,66,0,36,count,3)
        return raw+struct.pack('<I',zlib.crc32(raw)^(1 if corrupt else 0))

    def test_closed_latest_zero_photo_and_crc_fallback_without_writes(self):
        self.files['/media/storage1/M10VRL1.BIN']=self.journal()
        bad=bytearray(self.journal(corrupt=True));struct.pack_into('<I',bad,4,4)
        self.files['/media/storage1/M10VRL0.BIN']=bytes(bad)
        self.assertEqual(self.invoke('latest_probe',0x180000),1)
        result=bytes(self.uc.mem_read(0x180000,48))
        self.assertEqual(struct.unpack_from('<IIIII',result,24),(66,0,36,0,3))
        self.assertEqual(self.reads,2)
        self.assertFalse(self.handles)

    def test_bounded_pages_discover_older_markers_skip_partial_and_missing_files(self):
        names=[f'R{i:07}.JPG' for i in range(25)]
        self.dirs['/media/storage1/DCIM/100RICOH']=names+['R9999999.JPG']
        for i,name in enumerate(names):
            data=fixture(True) if i>=20 else b'\xff\xd8\xff\xda\x00\x02\xff\xd9'
            if i==24:data=fixture(True,complete=False)
            self.files['/media/storage1/DCIM/100RICOH/'+name]=data
        self.assertEqual(self.invoke('page_probe',0,0x180000),1)
        first=bytes(self.uc.mem_read(0x180000,800));cursor,checked,skipped=struct.unpack_from('<III',first)
        self.assertEqual(checked,16);self.assertEqual(first[12:15],b'\x00\x01\x00')
        self.assertEqual(self.invoke('page_probe',cursor+1,0x180000),0)
        self.assertEqual(self.invoke('page_probe',cursor,0x180000),1)
        page=bytes(self.uc.mem_read(0x180000,800));_,checked,skipped=struct.unpack_from('<III',page)
        self.assertEqual((checked,skipped),(26,2))
        self.assertEqual(page[12:15],b'\x04\x00\x00')
        summaries = [values for name,values in self.traces if name == 'ROLL_INDEX_PAGE']
        self.assertEqual(len(summaries),2)
        self.assertEqual(summaries[-1][5],26)
        self.assertEqual(page[16:32],ROLL_ID)
        self.assertEqual(struct.unpack_from('<III',page,32),(7,24,0))
        self.assertFalse(self.handles)
        self.assertFalse(self.mapping)

    def test_completed_dng_is_its_own_verified_roll_reference(self):
        self.dirs['/media/storage1/DCIM/100RICOH']=['00000001.DNG','00000002.DNG']
        self.files['/media/storage1/DCIM/100RICOH/00000001.DNG']=fixture(False)
        self.files['/media/storage1/DCIM/100RICOH/00000002.DNG']=fixture(False,complete=False)
        self.assertEqual(self.invoke('page_probe',0,0x180000),1)
        page=bytes(self.uc.mem_read(0x180000,640))
        self.assertEqual(page[12],1)
        self.assertEqual(page[16:32],ROLL_ID)
        self.assertEqual(struct.unpack_from('<III',page,32),(7,24,0))
        self.assertEqual(page[53:66].split(b'\0')[0],b'00000001.DNG')
        self.assertEqual(struct.unpack_from('<II',page,4),(2,1))

    @unittest.skipUnless(os.environ.get('M10V_CAMERA_ROLL_PHOTO_DIR'),
                         'requires explicitly selected read-only R12 camera originals')
    def test_actual_sd_scan_exposes_two_tagged_dng_originals_without_guessing_jpeg_pairs(self):
        directory=Path(os.environ['M10V_CAMERA_ROLL_PHOTO_DIR'])
        self.dirs['/media/storage1/DCIM']=[directory.name]
        base='/media/storage1/DCIM/'+directory.name
        names=sorted(p.name for p in directory.iterdir() if p.suffix in ('.JPG','.DNG'))
        self.dirs[base]=names
        for name in names:self.files[base+'/'+name]=directory/name
        self.assertEqual(self.invoke('page_probe',0,0x180000),1)
        page=bytes(self.uc.mem_read(0x180000,640))
        self.assertEqual(page[12],2)
        found=[]
        for index in range(page[12]):
            at=16+index*52
            frame,target,film=struct.unpack_from('<III',page,at+16)
            found.append((page[at+37:at+50].split(b'\0')[0].decode(),frame,target,film))
        self.assertEqual(found,[('00004562.DNG',1,36,0x1042),('00004563.DNG',2,36,0x1042)])
        self.assertEqual(struct.unpack_from('<II',page,4),(8,0))

    def test_page_diagnostics_distinguish_uncached_read_failure_from_bad_metadata(self):
        name = '00000001.JPG'
        self.dirs['/media/storage1/DCIM/100RICOH'] = [name]
        self.files['/media/storage1/DCIM/100RICOH/'+name] = fixture(True)[:-2] + bytes(6000) + b'\xff\xd9'
        self.fail_read_from = 4096
        self.assertEqual(self.invoke('page_probe',0,0x180000),1)
        summary = next(values for name,values in self.traces if name == 'ROLL_INDEX_PAGE')
        self.assertEqual((summary[5],summary[7],summary[8],summary[10],summary[12]), (1,0,1,0,9))

    def test_allocation_failure_and_restart_release_previous_scan(self):
        self.allocation_fail = True
        self.assertEqual(self.invoke('page_probe',0,0x180000),-1)
        self.assertFalse(self.handles)
        self.allocation_fail = False
        names = [f'R{i:07}.JPG' for i in range(20)]
        self.dirs['/media/storage1/DCIM/100RICOH'] = names
        for name in names:self.files['/media/storage1/DCIM/100RICOH/'+name]=fixture(True)
        self.assertEqual(self.invoke('page_probe',0,0x180000),1)
        self.assertTrue(self.mapping)
        self.assertEqual(self.invoke('page_probe',0,0x180000),1)
        self.assertTrue(self.mapping)
        self.assertLessEqual(len(self.handles),3)
        cursor = struct.unpack('<I',self.uc.mem_read(0x180000,4))[0]
        self.assertEqual(self.invoke('page_probe',cursor,0x180000),1)
        self.assertFalse(self.mapping)
        self.assertFalse(self.handles)

    def test_absent_journal_and_offline_are_distinct(self):
        self.assertEqual(self.invoke('latest_probe',0x180000),0)
        self.offline=True
        self.assertEqual(self.invoke('latest_probe',0x180000),-1)
        self.assertEqual(self.invoke('page_probe',0,0x180000),-1)


@unittest.skipUnless(os.environ.get('M10V_ROLL_INDEX_SERVICE_ELF'),
                     'requires explicitly selected final companion service ELF')
class DeliveredRollIndexArmTests(RollIndexArmTests):
    """Repeat the same filesystem proof in the final linked service binary.

    Only diagnostic output is a leaf stub. Original parsing, format/size proof,
    directory/syscall ABI, bounded state and allocator lifecycle execute.
    """
    @classmethod
    def setUpClass(cls):
        executable=Path(os.environ['M10V_ROLL_INDEX_SERVICE_ELF'])
        cls.binary=executable.read_bytes()
        names=subprocess.check_output(['/opt/homebrew/opt/llvm/bin/llvm-nm',executable],text=True)
        cls.native_symbols={line.split()[2]:int(line.split()[0],16)
                            for line in names.splitlines() if len(line.split())==3}
        cls.symbols={'latest_probe':cls.native_symbols['index_latest'],
                     'page_probe':cls.native_symbols['index_photos']}

    def setUp(self):
        super().setUp()
        from unicorn import UC_HOOK_CODE
        def trace(machine,address,_size,_context):
            if address!=self.native_symbols['m10v_linux_trace']:return
            event,values,count=[machine.reg_read(r) for r in self.reg[:3]]
            self.traces.append((self.text(event),struct.unpack('<'+'I'*count,
                               machine.mem_read(values,count*4))))
            machine.reg_write(self.pc,machine.reg_read(self.lr))
        self.uc.hook_add(UC_HOOK_CODE,trace)

    def invoke(self,name,*args):
        return super().invoke(name,0,*args)
