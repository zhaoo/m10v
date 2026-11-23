"""Production ARM storage against an 8.3 camera filesystem syscall model."""
from pathlib import Path
import hashlib
import os
import struct
import subprocess
import tempfile
import unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parents[1]
TOKEN = bytes.fromhex("585d5be6448ef66e6537585101000000")

def photo_fixture(token):
    from tests.test_gr3_roll_photo import fixture
    data = bytearray(fixture(True))
    tag_at = 12 + 72 + 10
    struct.pack_into('<HHII', data, tag_at, 0xc7f3, 7, 24, 24)
    data[tag_at + 14:tag_at + 38] = b'M10L' + struct.pack('<I', 1) + token
    return bytes(data)

class LiveFilesystemArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        fixture = directory / 'fixture.c'
        fixture.write_text(r'''
#include "linux_live.c"
void m10v_linux_trace(const char *event,const uint32_t *values,unsigned count){
 register unsigned r0 __asm__("r0")=(unsigned)event,r1 __asm__("r1")=(unsigned)values,
 r2 __asm__("r2")=count,r7 __asm__("r7")=0xfe00;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r7):"memory","cc");
}
int save_probe(const uint32_t *token){
 for(unsigned i=0;i<4;i++)shot_token[i]=token[i];
 m10v_live_reset(&memory->clip);
 for(unsigned i=0;i<FRAME_BYTES;i++)memory->frame[i]=(uint8_t)(i+token[3]);
 if(!m10v_live_shutter(&memory->clip,10000,0))return 0;
 for(unsigned t=10050;t<=11550;t+=500)
  if(!m10v_live_push(&memory->clip,t,memory->frame,FRAME_BYTES))return 0;
 return m10v_live_complete(&memory->clip,11580)&&save_clip();
}
int lookup_probe(const char *directory,const char *name,m10v_live_pair *out){
 return m10v_linux_live_source.lookup(0,directory,name,out);
}
int read_probe(const m10v_live_pair *pair,uint32_t offset,uint8_t *out,uint32_t bytes){
 return m10v_linux_live_source.read(0,pair,offset,out,bytes);
}
''')
        objects=[]
        for source in [fixture]+[ROOT/'native/companion'/f'{name}.c' for name in ('live_clip','roll_photo','runtime','auth')]:
            output=directory/(source.stem+'.o')
            subprocess.run(['/opt/homebrew/opt/llvm/bin/clang','--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os','-DM10V_COMPANION_LIVE_SOURCE=1','-std=c11','-ffreestanding','-fno-builtin','-ffunction-sections','-fdata-sections','-I',str(ROOT/'native/companion'),'-Wall','-Wextra','-Werror','-c',str(source),'-o',str(output)],check=True)
            objects.append(str(output))
        executable=directory/'filesystem.elf'
        subprocess.run(['/opt/homebrew/bin/ld.lld','-m','armelf_linux_eabi','-Ttext=0x10000','--gc-sections','--entry=m10v_linux_live_attach','--undefined=save_probe','--undefined=lookup_probe','--undefined=read_probe',*objects,'-o',str(executable)],check=True)
        cls.binary=executable.read_bytes()
        output=subprocess.check_output(['/opt/homebrew/opt/llvm/bin/llvm-nm',str(executable)],text=True)
        cls.symbols={line.split()[-1]:int(line.split()[0],16) for line in output.splitlines() if len(line.split())==3}

    def machine(self, policy='reject', files=None, directory_sync=-22, file_sync=0, rename_error=0):
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        for address,size in ((0x10000,0x100000),(0x1000000,0x200000)):
            u.mem_map(address,size)
        offset=struct.unpack_from('<I',self.binary,28)[0]
        size,count=struct.unpack_from('<HH',self.binary,42)
        for index in range(count):
            s=struct.unpack_from('<8I',self.binary,offset+index*size)
            if s[0]==1:u.mem_write(s[2],self.binary[s[1]:s[1]+s[4]])
        files={} if files is None else files
        dirs={'/media/storage1','/media/storage1/M10V','/media/storage1/M10V/LIVE','/media/storage1/DCIM','/media/storage1/DCIM/141_1123'}
        for path in files:
            dirs.update(str(p) for p in Path(path).parents if str(p)!='.')
        descriptors={}; events=[]; accesses=[]; logs=[]
        def string(at):
            b=bytearray()
            while u.mem_read(at,1)!=b'\0':b+=u.mem_read(at,1);at+=1
            return b.decode()
        def path_at(fd,name):
            base=descriptors[fd][0]
            if policy!='long' and not name.replace('.','').replace('_','').isalnum(): return None
            if policy!='long' and (len(name.split('.')[0])>8 or len(name.split('.'))>2 or ('.' in name and len(name.split('.')[1])>3)):
                if policy in ('reject','invalid'):return None
                pieces=name.split('.');name=pieces[0][:8]+('.'+pieces[1][:3] if len(pieces)>1 else '')
            return base+'/'+name.upper()
        def allocate(path):
            fd=max(descriptors.keys(),default=9)+1;descriptors[fd]=[path,0];return fd
        def syscall(machine,interrupt,unused):
            n=machine.reg_read(A.UC_ARM_REG_R7)
            a=[machine.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(6)]
            result=0
            if n==192:result=0x1000000
            elif n==5:result=allocate(string(a[0]))
            elif n in (322,323):
                raw=string(a[1]);path=path_at(a[0],raw);accesses.append((n,raw,path))
                if path is None:result=-22 if policy=='invalid' else -36
                elif n==323:
                    if path in dirs:result=-17
                    else:dirs.add(path)
                elif a[2]&0x4000:result=allocate(path) if path in dirs else -2
                elif a[2]&64:
                    if path in files and a[2]&128:result=-17
                    else:files[path]=b'';result=allocate(path)
                else:result=allocate(path) if path in files else -2
            elif n==6:descriptors.pop(a[0],None)
            elif n==118:result=directory_sync if descriptors[a[0]][0] in dirs else file_sync
            elif n==19:
                path,pos=descriptors[a[0]];result=0 if path in dirs else len(files[path]);descriptors[a[0]][1]=result
            elif n==217:
                path,pos=descriptors[a[0]]
                entries=sorted(p[len(path)+1:] for p in files if p.startswith(path+'/') and '/' not in p[len(path)+1:])
                data=bytearray()
                for name in entries[pos:]:
                    encoded=name.encode()+b'\0';length=(19+len(encoded)+7)&~7
                    data.extend(struct.pack('<QQHB',1,pos+1,length,8)+encoded+b'\0'*(length-19-len(encoded)));pos+=1
                descriptors[a[0]][1]=pos
                if data:u.mem_write(a[1],bytes(data))
                result=len(data)
            elif n==180:
                path=descriptors[a[0]][0];data=files[path][a[4]:a[4]+a[2]]
                u.mem_write(a[1],data);result=len(data)
            elif n==4:
                data=bytes(u.mem_read(a[1],a[2]));result=len(data)
                if a[0]==1:logs.append(data)
                else:
                    path=descriptors[a[0]][0];files[path]+=data
            elif n==329:
                old=path_at(a[0],string(a[1]));new=path_at(a[2],string(a[3]))
                result=rename_error
                if not result:files[new]=files.pop(old)
            elif n==328:files.pop(path_at(a[0],string(a[1])),None)
            elif n==0xfe00:events.append((string(a[0]),struct.unpack('<'+'i'*a[2],u.mem_read(a[1],a[2]*4))))
            else:self.fail(f'unexpected syscall {n}')
            machine.reg_write(A.UC_ARM_REG_R0,result&0xffffffff)
        u.hook_add(UC_HOOK_INTR,syscall)
        def call(name,*args):
            for i,arg in enumerate(args):u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),arg)
            u.reg_write(A.UC_ARM_REG_SP,0xa0000);u.reg_write(A.UC_ARM_REG_LR,0x80000)
            u.emu_start(self.symbols[name],0x80000,count=1000000000)
            self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x80000)
            value=u.reg_read(A.UC_ARM_REG_R0);return value if value<0x80000000 else value-0x100000000
        u.mem_write(0x90000,struct.pack('<8I',1,0x56000000,111232,0x56020000,3,36992,36864,1))
        self.assertEqual(call('m10v_linux_live_attach',0x90000,0x56020000),1)
        return u,call,files,events,accesses,logs

    @staticmethod
    def physical(token):
        s=token.hex().upper();return '/media/storage1/M10V/LIVE/'+'/'.join(s[i:i+8] for i in (0,8,16))+'/'+s[24:]+'.M10'

    def test_same_prefix_tokens_save_and_reopen_on_rejecting_and_truncating_camera_filesystem(self):
        for policy in ('reject','truncate','invalid'):
            with self.subTest(policy=policy):
                u,call,files,events,accesses,logs=self.machine(policy)
                for final in (1,2):
                    token=TOKEN[:12]+struct.pack('<I',final);u.mem_write(0x90100,token)
                    self.assertEqual(call('save_probe',0x90100),1,(events,accesses))
                    self.assertIn(self.physical(token),files)
                self.assertEqual(len(files),2)
                self.assertNotEqual(*files.values())
                self.assertTrue(all(len(n.split('.')[0])<=8 and ('.' not in n or len(n.split('.')[1])<=3) for _,n,_ in accesses))
                self.assertNotIn('LIVE_SAVE_ERROR',[n for n,_ in events])
                self.assertIn(('LIVE_DIR_SYNC_UNSUPPORTED',(-22,)),events)
                # A fresh service loses all RAM/cache state and resolves solely
                # from the exact 128 bits in the persisted JPEG metadata.
                self.verify_pairs(files,policy)

    def verify_pairs(self,files,policy='reject',legacy=False):
        # Use real camera JPEGs when explicitly enabled; default fixture keeps
        # CI independent of a mounted private SD card.
        jpeg_data=[]
        for final in (1,2):
            token=TOKEN[:12]+struct.pack('<I',final)
            if os.environ.get('M10V_LIVE_CAMERA_JPEGS'):
                data=(Path(os.environ['M10V_LIVE_CAMERA_JPEGS'])/f'000045{67+final}.JPG').read_bytes()
            else:
                data=photo_fixture(token)
            files[f'/media/storage1/DCIM/141_1123/000045{67+final}.JPG']=data;jpeg_data.append(data)
        u,call,files,events,accesses,logs=self.machine(policy,files)
        for final,data in enumerate(jpeg_data,1):
            token=TOKEN[:12]+struct.pack('<I',final)
            u.mem_write(0x90200,b'141_1123\0');u.mem_write(0x90300,f'000045{67+final}.JPG'.encode()+b'\0')
            self.assertEqual(call('lookup_probe',0x90200,0x90300,0x90400),1)
            pair=bytes(u.mem_read(0x90400,116))
            # ABI: jpeg hash[32], clip hash[32], directory[17], file[23].
            self.assertEqual(pair[64:81],token.hex()[:16].encode()+b'\0')
            self.assertEqual(pair[81:103],token.hex()[16:].encode()+b'.M10L\0')
            clip=files['/media/storage1/M10V/LIVE/'+token.hex().upper()+'.M10L' if legacy else self.physical(token)]
            self.assertEqual(pair[:32],hashlib.sha256(data).digest())
            self.assertEqual(pair[32:64],hashlib.sha256(clip).digest())
            self.assertEqual(call('read_probe',0x90400,0,0xb0000,len(clip)),1)
            self.assertEqual(bytes(u.mem_read(0xb0000,len(clip))),clip)

    def test_file_sync_and_rename_errors_remain_fatal_and_distinct(self):
        for file_sync, rename_error, stage in ((-5, 0, 4), (0, -13, 6)):
            with self.subTest(stage=stage):
                u,call,files,events,accesses,logs=self.machine(file_sync=file_sync,rename_error=rename_error)
                u.mem_write(0x90100,TOKEN)
                self.assertEqual(call('save_probe',0x90100),0)
                self.assertEqual([v for n,v in events if n=='LIVE_SAVE_ERROR'],[(stage,file_sync or rename_error)])
                self.assertEqual(files,{})
        u,call,files,events,accesses,logs=self.machine(directory_sync=-5)
        u.mem_write(0x90100,TOKEN)
        self.assertEqual(call('save_probe',0x90100),1)
        self.assertIn(('LIVE_DIR_SYNC_ERROR',(-5,)),events)
        self.assertIn(self.physical(TOKEN),files)

    def test_exact_full_legacy_name_is_readable_only_when_enumerated(self):
        u,call,files,events,accesses,logs=self.machine('long')
        for final in (1,2):
            token=TOKEN[:12]+struct.pack('<I',final);u.mem_write(0x90100,token)
            self.assertEqual(call('save_probe',0x90100),1)
            clip=files.pop(self.physical(token))
            files['/media/storage1/M10V/LIVE/'+token.hex().upper()+'.M10L']=clip
        self.verify_pairs(files,'long',legacy=True)

    def test_truncated_legacy_artifact_never_matches_another_token(self):
        # Long-name errors are compatibility misses, never an HTTP 503 bridge error.
        for policy in ('reject','invalid','truncate'):
            with self.subTest(policy=policy):
                files={'/media/storage1/M10V/LIVE/585D5BE6.M10':b'ambiguous old clip'}
                files['/media/storage1/DCIM/141_1123/00004568.JPG']=photo_fixture(TOKEN)
                u,call,files,events,accesses,logs=self.machine(policy,files)
                u.mem_write(0x90200,b'141_1123\0');u.mem_write(0x90300,b'00004568.JPG\0')
                self.assertEqual(call('lookup_probe',0x90200,0x90300,0x90400),0)

if __name__=='__main__':unittest.main()
