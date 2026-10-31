"""Build bounded per-recipe native looks; original ISP CPU ABI, no hardware claim."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, struct, subprocess, tempfile
ROOT=Path(__file__).resolve().parents[1]
API={f'm10v_isp_native_look_{s}' for s in ('prepare','apply','matches')}
FIRMWARE_SHA256='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'

def encode_curve_deltas(delta):
    """LSB-first 2bit codes:0=same,1=+1,2=-1,3=8bit absolute delta."""
    out=bytearray();acc=bits=previous=0
    for value in delta:
        diff=value-previous;code=0 if diff==0 else 1 if diff==1 else 2 if diff==-1 else 3
        acc|=code<<bits;bits+=2
        if code==3:acc|=value<<bits;bits+=8
        while bits>=8:out.append(acc&255);acc>>=8;bits-=8
        previous=value
    if bits:out.append(acc)
    return bytes(out)

def decode_curve_deltas(data,count=255):
    acc=bits=at=previous=0;out=[]
    def read(n):
        nonlocal acc,bits,at
        while bits<n:acc|=data[at]<<bits;bits+=8;at+=1
        v=acc&((1<<n)-1);acc>>=n;bits-=n;return v
    for _ in range(count):
        code=read(2)
        previous=previous if code==0 else previous+1 if code==1 else previous-1 if code==2 else read(8)
        if not 0<=previous<=255:raise ValueError('invalid lossless delta stream')
        out.append(previous)
    return out

def profiles():
    fit=json.loads((ROOT/'builds/gr3-native-film-fit/native-film-fit.json').read_text())
    old=json.loads((ROOT/'native/gr3/isp-film-targets.json').read_text())
    arr=lambda v:'{'+','.join(map(str,v))+'}'
    curve_data=bytearray()
    def frame(q,old=False):
        m,p=q['matrixQ13' if old else 'matrix_q13'],q['postQ512' if old else 'post_q9']
        curves=q['curves']
        m=[v for row in m for v in row] if isinstance(m[0],list) else m
        p=[v for row in p for v in row] if isinstance(p[0],list) else p
        if len(m)!=9 or len(p)!=9 or len(curves)!=3 or any(len(c)!=256 or min(c)<0 or max(c)>16383 or any(a>b for a,b in zip(c,c[1:])) for c in curves):raise ValueError('invalid frame profile')
        if any(not -32768<=v<=32767 for v in m+p):raise ValueError('matrix overflow')
        delta=[[b-a for a,b in zip(c,c[1:])] for c in curves]
        if any(v>255 for c in delta for v in c):raise ValueError('curve delta overflow')
        offsets=[]
        for channel in delta:
            packed=encode_curve_deltas(channel)
            if decode_curve_deltas(packed)!=channel:raise ValueError('lossless curve roundtrip failed')
            offsets.append(len(curve_data));curve_data.extend(packed)
        if len(curve_data)>65535:raise ValueError('curve stream offset overflow')
        return '{'+arr(m)+','+arr(p)+','+arr([c[0] for c in curves])+','+arr(offsets)+'}'
    header='/* Generated LOSSLESS 2bit delta-of-delta packed native creative profiles; camera calibration UNVERIFIED.\n * 5207 reference MIT Jan Lohse; retain third_party/spectral-film-lut/LICENSE. */\n'
    header+='typedef struct { int16_t matrix[9],post[9]; uint16_t first[3],offset[3]; } native_frame_packed;\n'
    for name,key in [('5207','5207'),('phoenix','phoenix_ii')]:
        q=fit['targets'][key]['parameters']
        header+=f'static const native_frame_packed native_{name}_frame = '+frame(q)+';\n'
        raw=(ROOT/f'builds/gr3-native-film-fit/{key}-multiaxis.bin').read_bytes()
        if len(raw)!=3712:raise ValueError('multiaxis layout mismatch')
        m12=struct.unpack_from('<540I',raw,52)
        expected=[v&4095 for h in q['hue_q10'] for _ in range(5) for row in h for v in row]
        if list(m12)!=expected:raise ValueError('sector/report mismatch')
        h=[v for sector in q['hue_q10'] for row in sector for v in row]
        if min(h)<-2048 or max(h)>2047:raise ValueError('sector overflow')
        header+=f'static const int16_t native_{name}_hue[108] = '+arr(h)+';\n'
    phoenix120=json.loads((ROOT/'native/gr3/phoenix-exposure-native.json').read_text())
    for path,digest in phoenix120['files'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('stale Phoenix EI120 profile: '+path)
    q=phoenix120['parameters']
    header+='static const native_frame_packed native_phoenix120_frame = '+frame(q)+';\n'
    header+='static const int16_t native_phoenix120_hue[108] = '+arr([v for sector in q['hue_q10'] for row in sector for v in row])+';\n'
    red=[next(t for t in old['targets'] if t['film_id']==68 and t['ei']==ei) for ei in (125,64,250)]
    header+='static const native_frame_packed native_red_frame[3] = {'+','.join(frame(q,True) for q in red)+'};\n'
    # New 800T creative definition: same mild contrast/lift/bend, desaturation,
    # blue/cyan midtones. A representable native look, not CPU YUV equivalence.
    curve=[]
    for tint in (-.088,.030,.069):
        c=[]
        for i in range(256):
            x=i/255;v=(128+(i-128)*264/256+(255-i)/255+3*i*(255-i)/16384)/255
            c.append(round(max(0,min(1,v+tint*(1-abs(2*x-1))))*16383))
        curve.append(c)
    sat=238/256;weights=(.299,.587,.114)
    post=[round(((sat if r==c else 0)+(1-sat)*weights[c])*512) for r in range(3) for c in range(3)]
    film33={'matrix_q13':[8192,0,0,0,8192,0,0,0,8192],'post_q9':post,'curves':curve}
    header+='static const native_frame_packed native_800t_frame = '+frame(film33)+';\n'
    curated=json.loads((ROOT/'native/gr3/curated-reference.json').read_text())
    header+='static const native_frame_packed native_curated_frame[4] = {'+','.join(frame(q) for q in curated['native_profiles_full'])+'};\n'
    header+='static const int16_t native_curated_hue[4][108] = {'+','.join(arr([v for sector in q['hue_q10'] for row in sector for v in row]) for q in curated['native_profiles_full'])+'};\n'
    newstocks=json.loads((ROOT/'native/gr3/newstocks-reference.json').read_text())
    header+='static const native_frame_packed native_newstocks_frame[6] = {'+','.join(frame(q) for q in newstocks['native_profiles_full'])+'};\n'
    header+='static const int16_t native_newstocks_hue[6][108] = {'+','.join(arr([v for sector in q['hue_q10'] for row in sector for v in row]) for q in newstocks['native_profiles_full'])+'};\n'
    styles=json.loads((ROOT/'native/gr3/style-filters-reference.json').read_text())
    header+='static const m10v_isp_frame_target native_style_filters_frame[7] = {'+','.join('{'+arr([v for row in q['matrix_q13'] for v in row])+','+arr([v for row in q['post_q9'] for v in row])+',{'+','.join(arr(c) for c in q['curves'])+'}}' for q in styles['native_profiles_full'])+'};\n'
    header+='static const int16_t native_style_filters_hue[7][108] = {'+','.join(arr([v for sector in q['hue_q10'] for row in sector for v in row]) for q in styles['native_profiles_full'])+'};\n'
    header+='static const uint8_t native_curve_stream['+str(len(curve_data))+'] = '+arr(curve_data)+';\n'
    evidence={'schema':'gr3-native-look/v1','camera_validated':False,'hardware_pixel_emulated':False,'old_cpu_color_equivalent':False,'static_profile_bytes':17*48+7*1572+len(curve_data)+20*216,'curve_stream_bytes':len(curve_data),'profile_curve_encoding':'lossless 2bit delta-of-delta with8bit absolute escape; exact original256 knots',
       '800t':'new representable native creative definition: contrast264 saturation238 lift1 bend3, blue/cyan midtone tint; old YUV LUT equivalence unclaimed',
       'curated':{str(q['film_id']):q['holdout'] for q in curated['native_profiles_full']},
       'newstocks':{str(q['film_id']):q['holdout'] for q in newstocks['native_profiles_full']},
       'style_filters':{str(q['film_id']):q['holdout'] for q in styles['native_profiles_full']},
       'profiles':{'5207':fit['targets']['5207']['metrics']['random_holdout'],'phoenix':fit['targets']['phoenix_ii']['metrics']['random_holdout'],
        'red':{str(q['ei']):q['holdout'] for q in red}},
       'phoenix_ei120':phoenix120['holdout'],
       'red_model_warning':'RED errors use synthetic reference domain, not extracted full native stock-gamma model; new creative profile requires visual camera validation',
       'stock_frame_preservation':'relative current-frame CCA/CSP; gamma derived from initialized stock object; no tuning/cache/white-balance writes',
       'cpu_skip_contract':'matches(film,exposure,queued_generation) only after APPLIED; all textures/spatial effects still required'}
    return header,evidence

def build(out,base=0x54160000):
    if type(base) is not int or base&4095 or not 0x540b6000<=base<=0x54f00000:raise ValueError('invalid isolated base')
    rom=ROOT/'builds/gr3-extension-validation/official-rtos.bin'
    if hashlib.sha256(rom.read_bytes()).hexdigest()!=FIRMWARE_SHA256:raise ValueError('unsupported RTOS hash')
    from scripts.build_gr3_isp_multiaxis import FLAGS
    clang=os.environ.get('M10V_LLVM_CLANG') or shutil.which('clang');linker=shutil.which('ld.lld')
    if not clang or not linker:raise RuntimeError('clang and ld.lld required')
    header,evidence=profiles();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    # Source header is checked in so production compilers need no offline fit.
    checked=ROOT/'native/gr3/m10v_isp_native_look_profiles.h'
    if checked.read_text()!=header:raise ValueError('stale generated profile header; run --generate-profiles')
    with tempfile.TemporaryDirectory(prefix='m10v-native-look-') as d:
        d=Path(d);objs=[]
        for stem in ('m10v_isp_native_look','m10v_isp_frame_color','m10v_isp_multiaxis','m10v_library'):
            obj=d/(stem+'.o');subprocess.run([clang,*FLAGS,'-DM10V_FOUR_LOOKS_NATIVE=1','-ffunction-sections','-fdata-sections','-c',str(ROOT/f'native/gr3/{stem}.c'),'-o',str(obj)],check=True,capture_output=True);objs.append(str(obj))
        script=d/'link.ld';script.write_text(f'SECTIONS {{ . = {base}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}')
        elf=d/'look.elf';subprocess.run([linker,'--gc-sections',*[f'--undefined={s}' for s in sorted(API)],'-T',str(script),'--entry=m10v_isp_native_look_apply',*objs,'-o',str(elf)],check=True,capture_output=True)
        b=elf.read_bytes();shoff=struct.unpack_from('<I',b,32)[0];size,count,nidx=struct.unpack_from('<HHH',b,46)
        if b[:7]!=b'\x7fELF\x01\x01\x01' or size!=40:raise ValueError('invalid ARM ELF')
        rows=[struct.unpack_from('<10I',b,shoff+40*i) for i in range(count)];nr=rows[nidx];names=b[nr[4]:nr[4]+nr[5]];image=bytearray();symbols={}
        for row in rows:
            name=names[row[0]:].split(b'\0',1)[0].decode()
            if row[2]&2 and row[5]:
                if row[1]!=1 or row[2]&1 or name not in ('.text','.rodata') or not base<=row[3]<base+65536 or row[3]+row[5]>base+65536:raise ValueError('unexpected allocated section '+name)
                off=row[3]-base;image.extend(bytes(max(0,off+row[5]-len(image))));image[off:off+row[5]]=b[row[4]:row[4]+row[5]]
            if row[1]==2:
                sr=rows[row[6]];strings=b[sr[4]:sr[4]+sr[5]]
                for at in range(row[4],row[4]+row[5],16):
                    n,value,_,info,_,section=struct.unpack_from('<IIIBBH',b,at);symbol=strings[n:].split(b'\0',1)[0].decode()
                    if section==0 and symbol:raise ValueError('undefined symbol '+symbol)
                    if symbol in API and info&15==2:symbols[symbol]=value
        if set(symbols)!=API:raise ValueError('missing API')
        (out/'m10v-isp-native-look-arm.elf').write_bytes(b)
        (out/'m10v-isp-native-look-arm.bin').write_bytes(image)
        (out/'m10v-isp-native-look-arm.o').write_bytes((d/'m10v_isp_native_look.o').read_bytes())
    evidence.update(base=base,symbols=symbols,bytes=len(image),recipe_bytes=1600,firmware_activated=False,original_firmware_sha256=FIRMWARE_SHA256,patches=[])
    (out/'manifest.json').write_text(json.dumps(evidence,indent=2)+'\n');return bytes(image),evidence
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out');p.add_argument('--generate-profiles',action='store_true');a=p.parse_args()
    if a.generate_profiles:(ROOT/'native/gr3/m10v_isp_native_look_profiles.h').write_text(profiles()[0])
    if a.out:print(json.dumps(build(a.out)[1],indent=2))
