"""Read-only M10V official-source check; never writes firmware, SD or camera."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

PROFILES={
 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4':('gr3','2.10',0x020a151b,30391780,True),
 '708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7':('gr3x','1.60',0x013c0b11,30391788,True),
 '5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e':('gr3','2.20',0x0214141c,30472516,False),
 'aa8e3ae1349d94e83be381c20530e41d5e57b75c27ef24ba81c7b017d6c11592':('gr3x','1.70',0x01461412,30472528,False),
}


def inspect(file, model=None, repo=None):
    raw=Path(file).read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest not in PROFILES:
        raise ValueError('Unknown or modified source; do not build or flash.')
    camera,version,word,size,allowed=PROFILES[digest]
    if model is not None and model!=camera:
        raise ValueError('Wrong camera model; renaming a BIN does not change its model.')
    project,magic=(588,0x024c024c) if camera=='gr3' else (609,0x02610261)
    if len(raw)!=size or struct.unpack_from('<I',raw,48)[0]!=project or any(
            struct.unpack_from('<I',raw,offset)[0]!=value for offset,value in
            [(120,magic),(124,0xa55a5aa5),(len(raw)-24,magic),(len(raw)-20,0xa55a5aa5),(len(raw)-16,2)]):
        raise ValueError('Container identity differs.')
    if any(struct.unpack_from('>I',raw,offset)[0]!=word for offset in (0x38,0x50)) or sum(
            v[0] for v in struct.iter_unpack('<I',raw))&0xffffffff:
        raise ValueError('Version/checksum differs.')
    result=dict(model=camera,public_version=version,sha256=digest,bytes=len(raw),
                source_identity_verified=True,full_decode_verified=False,
                supported_build_source=allowed,camera_tested=False,
                status='supported_source_only' if allowed else 'blocked_new_version')
    if repo:
        module=(Path(repo).resolve()/'node/firmware.mjs').as_uri()
        # The full hash above authenticates this read-only inventory. IIIx 1.70
        # is intentionally outside inspectOfficial's supported ABI; use the
        # strict structural importer without treating its identity=false as a
        # reason to lose the already pinned blocked-version classification.
        code="import{readFileSync}from'node:fs';const{inspectFirmwareImport}=await import(process.argv[1]);process.stdout.write(JSON.stringify(inspectFirmwareImport(readFileSync(process.argv[2]))));"
        checked=subprocess.run(['node','--input-type=module','-e',code,module,str(Path(file).resolve())],
                               capture_output=True,text=True,check=True,timeout=60)
        report=json.loads(checked.stdout)
        required=('container','decoded','sections','versions','strict_frames')
        if report['sha256']!=digest or not all(report['proof'].get(key) is True for key in required):
            raise ValueError('Strict project inspection differs.')
        result['full_decode_verified']=True
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--model',choices=['gr3','gr3x'])
    parser.add_argument('--repo',type=Path,help='M10V checkout for full strict decoding')
    args=parser.parse_args()
    try:
        result=inspect(args.input,args.model,args.repo)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['supported_build_source'] else 2
    except Exception as error:
        print(json.dumps(dict(status='rejected',reason=str(error),supported_build_source=False)),file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
