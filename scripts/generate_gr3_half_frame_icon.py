"""Literal Half status tile inside the unchanged native GR III ratio frame."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from PIL import Image, ImageDraw, ImageFont

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
    # Literal Half avoids confusing the new mode with the existing 4:3 tile.
    # Keep every pixel outside the native label's 36x26 interior unchanged.
    font_path=ROOT/'third_party/noto-sans/NotoSans-Bold.ttf'
    scale=4
    label=Image.new('RGBA',(36*scale,26*scale),(53,53,54,255))
    draw=ImageDraw.Draw(label)
    font=ImageFont.truetype(str(font_path),20*scale)
    while draw.textbbox((0,0),'Half',font=font)[2]>34*scale:
        font=ImageFont.truetype(str(font_path),font.size-1)
    box=draw.textbbox((0,0),'Half',font=font)
    x=(label.width-(box[2]-box[0]))//2-box[0]
    y=(label.height-(box[3]-box[1]))//2-box[1]
    draw.text((x,y),'Half',font=font,fill=(255,255,255,255))
    tile.paste(label.resize((36,26),Image.Resampling.LANCZOS),(12,7))
    payload=tile.tobytes()
    return tile,payload,{'schema':'m10v-half-frame-icon/v1','label':'Half','width':w,'height':h,
        'stock_frame_icon':339,'font':'NotoSans-Bold.ttf','font_sha256':hashlib.sha256(font_path.read_bytes()).hexdigest(),'iconbin_sha256':hashlib.sha256(icons).hexdigest(),
        'sha256':hashlib.sha256(payload).hexdigest()}

if __name__=='__main__':
    _,payload,report=generate()
    (ROOT/'native/gr3/m10v_half_frame_icon.rgba').write_bytes(payload)
    (ROOT/'native/gr3/half-frame-icon.json').write_text(json.dumps(report,indent=2)+'\n')
