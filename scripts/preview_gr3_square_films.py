"""Actual ARM card buffers and widget geometry; host-rendered surrounding text.

This is an offline resource/layout preview, not a physical camera framebuffer.
"""
import json,struct,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_gr3_directory_view import DirectoryViewTests

def generate():
 DirectoryViewTests.setUpClass();f=DirectoryViewTests()
 films=[34,35,37,33,314,76,66,299,317,316]
 u=f.machine(catalog_ids=dict(enumerate(films)));f.call(u,'create',0x10001000)
 f.state(u,0)
 # A ten-slot library can show the six approved reference families together.
 u.mem_write(0x10002000+184,struct.pack('<I',1))
 for i,film in enumerate(films):u.mem_write(0x10002000+12+i*8,struct.pack('<H',film))
 f.call(u,'draw',0x10001000,0x10002000,0x10003000)
 widgets=struct.unpack('<56I',u.mem_read(0x10001000,224))
 heap=widgets[55];out=ROOT/'docs/previews/square-film';out.mkdir(exist_ok=True,parents=True)
 image=Image.new('RGBA',(720,480),'#141a1d');d=ImageDraw.Draw(image)
 font=ImageFont.truetype(str(ROOT/'third_party/noto-sans/NotoSans-Bold.ttf'),22)
 d.text((24,18),'FILM LIBRARY',fill='#f5efdf',font=font)
 d.text((24,62),'Classic pack / square artwork',fill='#a4b7bc',font=font.font_variant(size=16))
 d.text((24,434),'Select film     OK Enable     MENU Back',fill='#d6e1dc',font=font.font_variant(size=17))
 geometry=[];sheet=Image.new('RGBA',(6*160,160),'#151a1d')
 for i,film in enumerate(films):
  x,y,w,h=struct.unpack('<4I',u.mem_read(widgets[26+i]+0x20,16))
  cw,ch,p=struct.unpack('<HHI',u.mem_read(heap+655360+i*8,8))
  card=Image.frombytes('RGBA',(cw,ch),bytes(u.mem_read(p*4,cw*ch*4)))
  if i==0:d.rectangle((x-4,y-4,x+w+3,y+h+3),outline='#f4d232',width=2)
  image.alpha_composite(card,(x,y));card.save(out/f'camera-{film}.png')
  if i<6:sheet.alpha_composite(card,((i*160)+16,16))
  geometry.append(dict(film=film,rect=[x,y,w,h],bitmap=[cw,ch]))
 image.save(out/'camera-layout-720x480.png');sheet.save(out/'camera-cards-actual128.png')
 web=Image.new('RGBA',(6*256,256),'#141a1d')
 for i,film in enumerate(films[:6]):
  art=Image.open(ROOT/f'web/gr3/film-icons/{film:02d}-large.png').resize((256,256),Image.Resampling.LANCZOS)
  web.alpha_composite(art,(i*256,0))
 web.save(out/'approved-six-web.png')
 (out/'geometry.json').write_text(json.dumps({'evidence':'ARM card buffers and actual widget geometry; host surrounding text','cards':geometry},indent=2)+'\n')
 f.call(u,'destroy',0x10001000)
 if f.live:raise RuntimeError('native allocation leak')
 print(out)
if __name__=='__main__':generate()
