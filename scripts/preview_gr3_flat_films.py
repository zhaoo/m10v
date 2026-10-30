#!/usr/bin/env python3
"""Preview production C film artwork; surrounding UI text is a host mockup."""
import ctypes,subprocess,json,tempfile,argparse,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out',type=Path,default=root/'docs/previews')
parser.add_argument('--font',default='/System/Library/Fonts/STHeiti Light.ttc')
args=parser.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
tmp=tempfile.TemporaryDirectory();library=Path(tmp.name)/'cards.so'
subprocess.run(['clang','-shared','-O2','-I',str(root/'native/gr3'),str(root/'native/gr3/m10v_film_card.c'),'-o',str(library)],check=True)
lib=ctypes.CDLL(str(library));buf=(ctypes.c_uint32*(128*128))()
films=[film for group in json.loads((root/'web/gr3/film-directory.json').read_text())['groups'] for film in group['films']]
font=ImageFont.truetype(args.font,24)
small=ImageFont.truetype(args.font,20)
pages=[]
count=math.ceil(len(films)/10)
for page in range(count):
 im=Image.new('RGB',(720,480),'#171d22');d=ImageDraw.Draw(im)
 d.text((20,15),'胶卷库  已启用 5/10',font=font,fill='white');d.text((610,18),f'{page+1}/{count}',font=font,fill='white')
 for i,film in enumerate(films[page*10:page*10+10]):
  assert lib.m10v_film_card_render(buf,film['id'],i,int(i<5 and page==0))==0
  card=Image.frombytes('RGBA',(128,128),bytes(buf))
  x=24+(i%5)*136;y=102+(i//5)*140
  if i==0:d.rectangle((x-4,y-4,x+131,y+131),outline='#ffef00',width=2)
  im.paste(card,(x,y),card)
 d.text((20,438),'方向键选择  OK启停  MENU返回  DISP拍摄',font=small,fill='white')
 im.save(out/f'film-flat-grid-r2-page{page+1}.png');pages.append(im)
contact=Image.new('RGB',(720,count*480+(count-1)*16),'#383d40')
for i,im in enumerate(pages):contact.paste(im,(0,i*496))
contact.save(out/'film-flat-grid-r2-all.png')
print(out/'film-flat-grid-r2-all.png')
