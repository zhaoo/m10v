"""Independent Capstone replay of typed references in a delivered target BIN."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from capstone.arm import ARM_INS_B, ARM_INS_BL, ARM_INS_BLX, ARM_INS_MOVT, ARM_OP_IMM

ROOT=Path(__file__).resolve().parents[1]


def verify(folder,profile_path,candidate_rtos,icon_directory):
    p=Path(folder)
    load=lambda n:json.loads((p/n).read_text())
    old=(p/'M10V-reference-runtime-arm.bin').read_bytes()
    new=(p/'M10V-runtime-arm.bin').read_bytes()
    m=load('M10V-reference-runtime-manifest.json')
    tm=load('M10V-runtime-manifest.json')
    receipt=load('M10V-build-receipt.json')
    refs=load('M10V-target-relocations.json')
    ranges=load('M10V-target-coverage.json')
    amap={int(a,16):int(b,16) for a,b in json.loads(Path(profile_path).read_text())['addresses'].items()}
    sha=lambda b:hashlib.sha256(b).hexdigest()
    canon=lambda v:json.dumps(v,separators=(',',':')).encode()
    bind=m['target_relocations']
    base=m['base'];directory=m['icons']['table'];directory_end=directory+671*4
    assert len(old)==len(new)==m['code_bytes']==tm['code_bytes']
    assert candidate_rtos[base-0x53000000:]==new,'delivered runtime differs from fresh BIN'
    assert sha(old)==m['code_sha256']==bind['runtime_sha256']
    assert sha(new)==tm['code_sha256']==receipt['runtime_sha256']==receipt['native_target']['runtime_sha256']
    assert len(refs)==bind['count'] and sha(canon(refs))==bind['sha256'],'typed reference list differs'
    assert sha(canon(ranges))==bind['coverage_sha256']
    word=lambda raw,s:struct.unpack_from('<I',raw,s-base)[0]
    fw=lambda v:0x53000000<=v<0x540b5740 or 0x55000000<=v<0x56000000
    md=Cs(CS_ARCH_ARM,CS_MODE_ARM);md.detail=True

    def instruction(raw,site):
        ins=list(md.disasm(raw[site-base:site-base+4],site))
        assert len(ins)==1 and ins[0].size==4
        return ins[0]

    types={};end=base
    for region in ranges:
        a,b,kind=region['start'],region['end'],region['kind']
        assert base<=a<b<=base+len(old) and not((a|b)&3) and a>=end and kind in ('code','data')
        types.update((site,kind) for site in range(a,b,4));end=b
    sites={};permitted=set()
    for row in refs:
        kind,ss,ww=row['kind'],row['sites'],row['words']
        assert kind in ('branch','pointer','mov_pair')
        assert len(ss)==len(ww)==(2 if kind=='mov_pair' else 1)
        for site,value in zip(ss,ww):
            assert base<=site<=base+len(old)-4 and not(site&3) and site not in sites and word(old,site)==value
            assert types[site]==('data' if kind=='pointer' else 'code')
            sites[site]=row;permitted.update(range(site-base,site-base+4))
        if directory<=ss[0]<directory_end:
            assert kind=='pointer';continue
        destination=amap[row['target']]
        if kind=='pointer':assert word(new,ss[0])==destination
        elif kind=='branch':
            a,b=instruction(old,ss[0]),instruction(new,ss[0])
            assert a.id in (ARM_INS_B,ARM_INS_BL) and b.id==a.id and b.cc==a.cc
            assert a.operands[0].imm==row['target'] and b.operands[0].imm==destination
        else:
            lo,hi=instruction(new,ss[0]),instruction(new,ss[1])
            assert lo.mnemonic.startswith('movw') and hi.id==ARM_INS_MOVT and lo.cc==hi.cc
            assert lo.operands[0].reg==hi.operands[0].reg
            assert (lo.operands[1].imm|(hi.operands[1].imm<<16))==destination
            assert all((word(old,site)&0xfff0f000)==(word(new,site)&0xfff0f000) for site in ss)
    # Discover references independently, using instruction operands and actual
    # register writes. Never disassemble arbitrary LUTs or image resources.
    decoded=0
    for region in ranges:
        a,b,kind=region['start'],region['end'],region['kind']
        if kind=='data':
            for site in range(a,b,4):
                if fw(word(old,site)):assert site in sites and sites[site]['kind']=='pointer'
            continue
        instructions=list(md.disasm(old[a-base:b-base],a))
        assert len(instructions)*4==b-a
        lows={}
        for ins in instructions:
            decoded+=1
            if ins.id in (ARM_INS_B,ARM_INS_BL,ARM_INS_BLX) and ins.operands[0].type==ARM_OP_IMM and fw(ins.operands[0].imm):
                assert ins.address in sites and sites[ins.address]['kind']=='branch','missing external branch'
            if ins.mnemonic.startswith('movw'):
                lows[ins.operands[0].reg]=(ins.operands[1].imm,ins.address,ins.cc)
            elif ins.id==ARM_INS_MOVT:
                reg=ins.operands[0].reg
                if reg in lows:
                    low,site,cc=lows[reg];value=low|(ins.operands[1].imm<<16)
                    if cc==ins.cc and fw(value):
                        assert site in sites and ins.address in sites and sites[site] is sites[ins.address],'missing external pair'
            else:
                for reg in ins.regs_access()[1]:lows.pop(reg,None)
    source,dest=struct.unpack_from('<II',candidate_rtos,0x450)
    at=source-0x53000000+icon_directory-dest
    assert 0<=at and at+671*4<=len(candidate_rtos)
    assert new[directory-base:directory_end-base]==candidate_rtos[at:at+671*4]
    permitted.update(range(directory-base,directory_end-base))
    assert all(a==b or off in permitted for off,(a,b) in enumerate(zip(old,new))),'untyped code/data/art byte modified'
    return dict(references=len(refs),regions=len(ranges),decoded_instructions=decoded)


def read_candidate(folder):
    script="""import{readFileSync}from'node:fs';import{officialResources,stockResourceLayout}from'./node/gr3-stock-presets.mjs';
const b=readFileSync(process.argv[1]),{decoded,sections}=officialResources(b),s=sections.RTOS;
process.stdout.write(JSON.stringify(stockResourceLayout(b))+'\\n');process.stdout.write(decoded.subarray(s.offset,s.offset+s.size));"""
    output=subprocess.check_output(['node','--input-type=module','-e',script,str(Path(folder)/'fwdc239b.bin')],cwd=ROOT)
    header,rtos=output.split(b'\n',1)
    return rtos,json.loads(header)['iconDirectory']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    args=parser.parse_args()
    rtos,directory=read_candidate(args.folder)
    print(json.dumps(verify(args.folder,ROOT/'node/gr3-220-native-target.json',rtos,directory)))
