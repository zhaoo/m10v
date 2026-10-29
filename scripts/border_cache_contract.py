#!/usr/bin/env python3
"""Original ARM cache routing/CP15 requests; no physical cache state emulated."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from analyze_gr3_border_iip import BASE,HASHES,OriginalArm,validate

SPANS={'native_cache_adapter':(0x536bbc30,0x536bbd00),
       'cache_dispatch':(0x5383c4e8,0x5383c8e4),
       'remote_handler':(0x5383c8e4,0x5383c93c),
       'address_limit_controls':(0x5383c93c,0x5383ca10),
       'cp15_range':(0x530008d8,0x5300095c),
       'cp15_setway':(0x530009e0,0x53000d3c),
       'stillmake_bank_cache':(0x53502568,0x53502578),
       'original_prepared_fill_caller':(0x534ccb94,0x534ccbac),
       'original_fill_wrapper':(0x534c8d64,0x534c8df8),
       'public_fill':(0x534abc18,0x534abce8),
       'backresize_cleanup':(0x534ff148,0x534ff294)}


class CacheArm(OriginalArm):
    def __init__(self,rom,eligible=True,core=2):
        super().__init__(rom)
        from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
        from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
        self.events=[];self.selector=0;self.core=core
        self.threshold=self.read_words(0x55039904,1)[0]
        self.u.mem_map(0x1d001000,0x1000)
        self.boundaries={0x53050eb8:lambda:0 if eligible else 0xffee0000,
            0x5304dfcc:lambda:0,0x5304dfe8:lambda:0,
            0x53844e9c:lambda:0,0x53844ed8:lambda:0,
            0x53000844:lambda:self.core,
            0x536b9f1c:lambda:self.events.append({'kind':'native_warning'})}
        decoder=Cs(CS_ARCH_ARM,CS_MODE_ARM)
        # Decode only immutable original spans. CP15 reads get a tiny explicit
        # cache-geometry fixture; maintenance instructions are recorded/skipped.
        decoded={}
        for a,b in ((0x530008d8,0x53000d3c),(0x5383c4e8,0x5383c93c)):
            for ins in decoder.disasm(rom[a-BASE:b-BASE],a):
                if ins.mnemonic in ('mrc','mcr','dsb','isb'):
                    decoded[ins.address]=(ins.mnemonic,ins.op_str)
        def reg(name):
            aliases={'ip':'r12','sl':'r10','sb':'r9','fp':'r11','lr':'r14'}
            return getattr(self.A,'UC_ARM_REG_'+aliases.get(name,name).upper())
        def instruction(u,pc,size,data):
            if pc in (0x536bbc3c,0x536bbcc0):
                self.events.append({'kind':'adapter','pc':pc,
                    'address':u.reg_read(self.A.UC_ARM_REG_R1),'bytes':u.reg_read(self.A.UC_ARM_REG_R2)})
            if pc in (0x5383c834,0x5383c8a8):
                self.events.append({'kind':'backend','pc':pc,
                    'address':u.reg_read(self.A.UC_ARM_REG_R0),'bytes':u.reg_read(self.A.UC_ARM_REG_R1)})
            if pc not in decoded:return
            mnemonic,operands=decoded[pc]
            if mnemonic in ('dsb','isb'):
                self.events.append({'kind':mnemonic,'pc':pc});return
            parts=operands.split(', ')
            if mnemonic=='mrc':
                if operands.endswith('c0, c0, #1'):value=0x02000023 # two cache levels
                elif parts[1]=='#1' and operands.endswith('c0, c0, #0'):value=0x200a #2sets*2ways,64B
                elif parts[1]=='#2' and operands.endswith('c0, c0, #0'):value=self.selector
                else:raise AssertionError('unexpected CP15 read '+operands)
                u.reg_write(reg(parts[2]),value)
            elif parts[1]=='#2' and operands.endswith('c0, c0, #0'):
                self.selector=u.reg_read(reg(parts[2]))
            elif parts[3]=='c7' and parts[4] in ('c6','c10','c14'):
                self.events.append({'kind':'maintenance','pc':pc,'opcode':operands,
                    'mode':{'c6':'invalidate','c10':'clean','c14':'clean_invalidate'}[parts[4]],
                    'scope':'mva' if parts[5]=='#1' else 'setway',
                    'level':None if parts[5]=='#1' else self.selector//2,
                    'operand':u.reg_read(reg(parts[2]))})
            else:raise AssertionError('unexpected CP15 write '+operands)
            u.reg_write(self.A.UC_ARM_REG_PC,pc+4)
        def write(u,access,address,size,value,data):
            if address==0x1d001f00:
                targets=(value>>16)&7
                self.events.append({'kind':'sgi_request','targets':targets,'value':value})
                # Explicit remote-ACK double, not remote-cache completion.
                for cpu in range(3):
                    if targets&(1<<cpu):self.words(0x55384700+4*cpu,1)
            if 0x55384700<=address<0x5538470c:
                self.events.append({'kind':'ack_store','core':(address-0x55384700)//4,'value':value})
        self.u.hook_add(UC_HOOK_CODE,instruction)
        self.u.hook_add(UC_HOOK_MEM_WRITE,write)

    def result(self):
        return {'events':self.events,'assertions':self.assertions,
            'threshold':self.threshold,'cp15_geometry_fixture':{'CLIDR':0x02000023,'CCSIDR':0x200a},
            'remote_ack_is_double':any(e['kind']=='sgi_request' for e in self.events),
            'maintenance_is_recorded_not_physical':True,
            'pixels_mapped':False,'camera_tested':False}


def probe_cache(rom,entry=0x536bbcc0,length=72192000,eligible=True,address=0x60000025):
    p=CacheArm(rom,eligible)
    if entry in (0x536bbc3c,0x536bbcc0):p.call(entry,0x5536d1b4,address,length)
    else:p.call(entry,address,length)
    return p.result()


def probe_remote(rom,mode=2,core=0):
    p=CacheArm(rom,core=core)
    p.u.mem_write(0x5538470c,bytes((mode,)))
    p.call(0x5383c8e4)
    return p.result()


def probe_limit_controls(rom):
    p=CacheArm(rom)
    p.call(0x536bbcbc,0x5536d1b4)
    disabled=p.read_words(0x55039900,2)
    p.call(0x5383c8a8,0x60000000,0x40000)
    disabled_events=list(p.events)
    p.call(0x536bbcb8,0x5536d1b4)
    return {'disabled':disabled,'restored':p.read_words(0x55039900,2),
        'disabled_events':disabled_events,'assertions':p.assertions,
        'pixels_mapped':False,'hardware_executed':False}


def probe_stillmake(rom):
    p=CacheArm(rom);config=0x55200000
    p.words(config+0x10,0x60000000,72192000)
    p.u.reg_write(p.A.UC_ARM_REG_R6,config)
    p.u.reg_write(p.A.UC_ARM_REG_SP,0x55ffe000)
    p.u.emu_start(0x53502568,0x53502578,count=100000)
    if p.u.reg_read(p.A.UC_ARM_REG_PC)!=0x53502578:raise AssertionError('StillMake fragment did not return')
    return p.result()


def probe_backresize_cleanup(rom):
    p=CacheArm(rom);module,desc=0x55100000,0x55200000
    p.words(module+0x8aa8,0x72000000,0x73000000)
    p.u.mem_write(module+0x8a5c,struct.pack('<2H',6336,4000))
    p.words(module+0x8a14,desc)
    p.u.mem_write(module+0x8a2b,b'\x01')
    p.u.mem_write(desc,b'\x01');p.words(desc+4,0x60180000,0x64180000,0)
    p.u.mem_write(desc+16,struct.pack('<6H',6000,2248,6336,4000,0,0))
    def thumbnail():
        p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R1),struct.pack('<H',160))
        p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R2),struct.pack('<H',120))
    p.boundaries[0x536a2f10]=thumbnail
    p.call(0x534ff1b8,module)
    return p.result()


def probe_prepared_one(rom):
    """Original prepared=1 callsite/wrapper/public branches; no hardware body."""
    p=OriginalArm(rom);events=[];factory=0x55200000;owner=0x55210000;desc=0x55220000;color=0x55230000
    p.words(factory+4,0x55240000);p.u.mem_write(color+2,b'\x07')
    p.boundaries={0x536c938c:lambda:0x8080ff,0x534aacc8:lambda:0,
        0x534ac164:lambda:0,0x53658a68:lambda:factory,
        0x534ab1a4:lambda:events.append('pre_cache_method'),
        0x534ab60c:lambda:events.append('post_cache_method'),
        0x534aad6c:lambda:events.append('native_dispatch_boundary')}
    p.u.reg_write(p.A.UC_ARM_REG_R5,color);p.u.reg_write(p.A.UC_ARM_REG_R6,owner)
    p.u.reg_write(p.A.UC_ARM_REG_R8,desc);p.u.reg_write(p.A.UC_ARM_REG_SP,0x55ffe000)
    p.u.emu_start(0x534ccb98,0x534ccbac,count=10000)
    if p.u.reg_read(p.A.UC_ARM_REG_PC)!=0x534ccbac:raise AssertionError('prepared caller did not return')
    prepared=list(events);events.clear()
    p.call(0x534abc18,owner,desc,255,128,128,0)
    return {'original_prepared_one_events':prepared,'unprepared_events':events,
        'assertions':p.assertions,'hardware_executed':False,'pixels_mapped':False,
        'scope':'original caller proves API usage, not ownership for new canvas'}


def analyze(rom,model):
    return {'schema':'m10v-border-cache-contract/v1','model':model,'rtos_sha256':validate(rom,model),
        'analyzer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'spans':{n:{'start':a,'end':b,'sha256':hashlib.sha256(rom[a-BASE:b-BASE]).hexdigest()} for n,(a,b) in SPANS.items()},
        'stillmake':probe_stillmake(rom),'backresize_cleanup':probe_backresize_cleanup(rom),
        'post_range_cinv':probe_cache(rom,length=128),'post_range_inv':probe_cache(rom,length=128,eligible=False),
        'pre_ineligible':probe_cache(rom,entry=0x536bbc3c,length=128,eligible=False),
        'remote_mode2':[probe_remote(rom,2,cpu) for cpu in (0,1)],
        'prepared_one':probe_prepared_one(rom),
        'capture_sources':{name:hashlib.sha256((Path(__file__).resolve().parents[1]/'native/gr3'/name).read_bytes()).hexdigest()
            for name in ('m10v_library_capture.c','m10v_library.c','m10v_anime.h')},
        'activation_ready':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtos',type=Path,required=True);parser.add_argument('--model',choices=sorted(HASHES),required=True)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=json.dumps(analyze(args.rtos.read_bytes(),args.model),indent=2)+'\n'
    if args.output:args.output.write_text(result)
    else:print(result,end='')
