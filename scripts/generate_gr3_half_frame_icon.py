"""Native 3:4 tile derived only from the stock 4:3 tile; old tiles unchanged."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]

def generate():
    from scripts.build_gr3_m10v_library import capture_stock_rtos
    rtos=capture_stock_rtos()
    directory=(ROOT/'native/gr3/m10v_stock_icon_directory.bin').read_bytes()
    at=struct.unpack_from('<I',directory,339*4)[0]-0x53000000
    w,h,offset=struct.unpack_from('<HHI',rtos,at)
    script="import{readFileSync}from'node:fs';import{officialResources}from'./node/gr3-stock-presets.mjs';const{decoded:d,sections:s}=officialResources(readFileSync('bin/fwdc239b-gr3-official.bin'));process.stdout.write(d.subarray(s.ICONBIN.offset,s.ICONBIN.offset+s.ICONBIN.size));"
    icons=subprocess.check_output(['node','--input-type=module','-e',script],cwd=ROOT)
    original=Image.frombytes('RGBA',(w,h),icons[offset*4:offset*4+w*h*4])
    tile=original.copy()
    # Equal-size digit cells; retain the native colon, border and alpha.
    tile.paste(original.crop((32,9,45,29)),(14,9))
    tile.paste(original.crop((14,9,27,29)),(32,9))
    payload=tile.tobytes()
    return tile,payload,{'schema':'m10v-half-frame-icon/v1','label':'3:4','width':w,'height':h,
        'stock_frame_icon':339,'iconbin_sha256':hashlib.sha256(icons).hexdigest(),
        'sha256':hashlib.sha256(payload).hexdigest()}

if __name__=='__main__':
    _,payload,report=generate()
    (ROOT/'native/gr3/m10v_half_frame_icon.rgba').write_bytes(payload)
    (ROOT/'native/gr3/half-frame-icon.json').write_text(json.dumps(report,indent=2)+'\n')
