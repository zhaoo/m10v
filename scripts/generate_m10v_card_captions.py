"""Pin bounded caption coverage; normal builds do not depend on system fonts.

Regenerate with --font path/to/NotoSansCJKsc-Regular.otf --resources manifest.json.
The manifest is produced by the normal native build before changing captions.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'native/gr3/m10v_card_captions.json'
WIDTH,HEIGHT=120,28

def resource(film):
 if 318<=film<=321:return 1159+film-318
 if film==317:return 1158
 if 314<=film<=316:return 1152+film-314
 if 312<=film<=313:return 1150+film-312
 if 306<=film<=311:return 1142+film-306
 if 299<=film<=305:return 1130+film-299
 if film==298:return 1128
 if film==290:return 1023
 if film==289:return 1012
 if film>=291:return 1104+film-291
 if film<=32:return 785+film
 if film==33:return 860
 if film<=65:return 879+film-34
 if film==66:return 911
 if film<=68:return 930+film-67
 return 978+film-69

def rle(raw):
 out=bytearray();start=0
 while start<len(raw):
  end=start+1
  while end<len(raw) and raw[end]==raw[start] and end-start<255:end+=1
  out.extend((end-start,raw[start]));start=end
 return bytes(out)

def generate(font_path,manifest_path):
 texts=json.loads(Path(manifest_path).read_text())['resources']['texts'];rows=[]
 for film in [*range(1,79),*range(289,299)]:
  name=texts[resource(film)-786]
  font=ImageFont.truetype(str(font_path),18)
  while font.getlength(name)>114 and font.size>6:font=ImageFont.truetype(str(font_path),font.size-1)
  shown=name
  while font.getlength(shown)>114:shown=shown[:-2]+'…'
  image=Image.new('L',(WIDTH,HEIGHT));d=ImageDraw.Draw(image)
  box=d.textbbox((0,0),shown,font=font)
  d.text(((WIDTH-d.textlength(shown,font=font))/2,(HEIGHT-(box[3]-box[1]))//2-box[1]),shown,font=font,fill=255)
  raw=image.tobytes();packed=rle(raw)
  rows.append(dict(film=film,name=name,shown=shown,font_size=font.size,sha256=hashlib.sha256(raw).hexdigest(),rle=base64.b64encode(packed).decode()))
 result=dict(schema='m10v-card-captions/v1',width=WIDTH,height=HEIGHT,font_source='https://github.com/notofonts/noto-cjk/blob/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf',font_sha256=hashlib.sha256(Path(font_path).read_bytes()).hexdigest(),license='SIL Open Font License 1.1',captions=rows)
 OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--font',type=Path,required=True);p.add_argument('--resources',type=Path,required=True)
 a=p.parse_args();generate(a.font,a.resources)
