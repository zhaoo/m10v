"""Original M10V cartridge art. One RGBA source for web and camera, no borrowed assets."""
from pathlib import Path
import re,json,hashlib
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
GLYPHS={'0':['111','101','101','101','111'],'1':['010','110','010','010','111'],'2':['111','001','111','100','111'],'3':['111','001','111','001','111'],'4':['101','101','111','001','001'],'5':['111','100','111','001','111'],'6':['111','100','111','101','111'],'7':['111','001','010','010','010'],'8':['111','101','111','101','111'],'9':['111','101','111','001','111'],'M':['10001','11011','10101','10001','10001'],'V':['101','101','101','101','010'],'T':['111','010','010','010','010'],'E':['111','100','110','100','111'],'G':['111','100','101','101','111'],'P':['110','101','110','100','100'],'H':['101','101','111','101','101'],'D':['110','101','101','101','110'],'C':['111','100','100','100','111'],'F':['111','100','110','100','100'],'L':['100','100','100','100','111']}
# Compact original 3×5 capitals, sized for the camera's 40px sprites.
GLYPHS.update({
 'A':['010','101','111','101','101'],'B':['110','101','110','101','110'],
 'I':['111','010','010','010','111'],'J':['001','001','001','101','010'],
 'K':['101','101','110','101','101'],'N':['101','111','111','111','101'],
 'O':['010','101','101','101','010'],'Q':['010','101','101','111','011'],
 'R':['110','101','110','101','101'],'S':['111','100','111','001','111'],
 'U':['101','101','101','101','111'],'W':['101','101','111','111','101'],
 'X':['101','101','010','101','101'],'Y':['101','101','010','010','010'],
 'Z':['111','001','010','100','111'],'M':['101','111','111','101','101']})
PALETTE=['#728d88','#c78d48','#6a87a6','#b48373','#626977','#b29597','#508b9d','#ba794f','#858761','#aebcb1','#498c92','#b47787','#b2aa90','#9caec1','#9c7a53','#917b61','#899090','#b3b4a9','#66696a','#a99988','#839ba5','#6c967c','#a08baa','#c1a275','#748895','#8eab6a','#bb6655','#c9c6b5','#667fa7','#bca26c','#687469','#bab7a4','#c83737']
def label(name,i):
 # Labels describe existing presets; this does not add or rename any recipe.
 if name=='蓝凤凰':return 'PHNX','II200','#397ac4'
 if name=='哈曼 RED':return 'RED','125','#c74435'
 if name=='富士业务用 100':return 'FUJI','100','#41a66b'
 if name=='乐凯 C200':return 'LUCKY','C200','#d94735'
 if name=='富士 C200':return 'FUJI','C200','#41995b'
 if name=='ProImage 100':return 'PROIM','100','#c7a357'
 if name=='T-Max 100':return 'TMAX','100','#84817b'
 if name=='Aerochrome':return 'AERO','1443','#ca527d'
 if name=='2460':return 'AERO','2460','#58a3a8'
 if name=='Tri-X 400':return 'TRI-X','400','#49443b'
 if name=='Ilford Delta 100':return 'DELTA','100','#777b83'
 if name=='Ilford Pan 400':return 'PAN','400','#b19b51'
 if name=='Rollei Infrared 400':return 'INFRARED','400 IR','#9c473b'
 if name=='Ilford SFX 200':return 'SFX','200 IR','#923f40'
 if name=='Fomapan 400':return 'FOMAPAN','400','#387e9e'
 if name=='CatLABS X Film 80':return 'X FILM','80 MKII','#71916f'
 if name=='5213':return '5213','200T','#b59a45'
 if name=='5203':return '5203','50D','#bfaa4c'
 if name=='CCD Classic':return 'GR','CCD','#567f8e'
 if name=='5207':return '5207','250D','#b59a45'
 if name=='800T':return 'CINE','800T','#c83737'
 if name=='Gold 200':return 'KODA','200','#d5a844'
 if name.startswith('Ektar '):return 'EKTAR',name.split()[-1],'#c94c47'
 if name=='Pro 400H':return 'FUJI','400H','#669c7a'
 if name.startswith('Portra '):return 'PORTR',name.split()[-1],'#a484ad'
 if name.startswith('V3 500T'):
  # KODAK VISION3 500T stock number, verified against Kodak's product page.
  return '5219','500TN' if name.endswith(' N') else '500T',PALETTE[(i-1)%32]
 if name=='V3 5207':return 'V3','5207',PALETTE[(i-1)%32]
 if name.startswith('Vision3 ') or name.startswith('V3 250D'):
  return 'V3','250DF' if name.endswith(' Flat') else '250D','#c6a450'
 aliases={'Neutral':'NEUTR','Morning':'MORN','Portrait':'PORTR','Autumn':'AUTMN',
          'Bleached':'BLEAC','Silver':'SILVR','Golden':'GOLDN','Superia':'SUPRA',
          'Reversal':'REVRS','Harubeni':'HARUB','Radiant':'RADNT','Kyushu':'KYUSH',
          'Miyabi':'MYABI'}
 words=name.removeprefix('M10V ').split()
 def short(w):return aliases.get(w,re.sub('[^A-Z0-9]','',w.upper())[:5])
 return short(words[0]),short(words[1]) if len(words)>1 else '',PALETTE[(i-1)%32]

def text(d,x,y,s,c):
 for ch in s:
  rows=GLYPHS[ch]
  for yy,row in enumerate(rows):
   for xx,v in enumerate(row):
    if v=='1':d.point((x+xx,y+yy),fill=c)
  x+=len(rows[0])+1

FONT=ROOT/'third_party/noto-sans/NotoSans-Bold.ttf'
def box_style(name,i):
 title,code,color=label(name,i)
 brand='M10V';header=color;paper='#eee9d9';ink='#25363b';accent=color
 if any(k in name for k in ('Portra','Gold','Ektar','ProImage','Vision3','V3 ','520','521','T-Max','2460','Aerochrome','Charmera')):
  brand='KODAK';header='#ffcf32';paper='#6556ae' if 'Portra' in name else '#efbe32' if 'Gold' in name else '#b92538' if 'Ektar' in name else '#252628'
  ink='#f8f4e8' if paper!='#efbe32' else '#9e2335';accent='#ffcf32'
 elif any(k in name for k in ('富士','Pro 400H','Superia','Reversal')):
  brand='FUJIFILM';header='#00956a';paper='#ede9d8';ink='#245346';accent='#188caa'
 elif name=='800T':brand='CINESTILL';header='#22272a';paper='#d9bf69';ink='#22272a';accent='#d93b36'
 elif '哈曼' in name:brand='HARMAN';header='#c12f3b';paper='#e9e5d8';ink='#a62936'
 elif '凤凰' in name:brand='HARMAN';header='#e4a738';paper='#317bb5';ink='#fff0d6'
 elif '乐凯' in name:brand='LUCKY';header='#cf343a';paper='#eadb9c';ink='#9f2836'
 if name=='Tri-X 400':brand,header,accent='KODAK','#ffcf32','#ffcf32'
 if name.startswith('Ilford '):brand,header,accent='ILFORD','#34373b','#cf473e'
 if name=='Rollei Infrared 400':brand,header,accent='ROLLEI','#34373b','#d45b40'
 if name=='Fomapan 400':brand,header,accent='FOMA','#eae7df','#387e9e'
 if name=='CatLABS X Film 80':brand,header,accent='CATLABS','#354438','#71916f'
 if name.startswith('Portra '):title='PORTRA'
 if name=='Gold 200':title='GOLD'
 if name=='Kodak Charmera':title,code='CHARMERA','PIXEL'
 if name=='方块世界':title,code,header,paper,ink,accent='PIXEL','WORLD','#52783d','#a0ba6f','#233c23','#815b3b'
 if name=='Custom LUT':title,code='CUSTOM','LUT'
 return brand,title,code,header,paper,ink,accent

def box_icon(name,i,size=40,spec=None):
 brand,title,code,header,paper,ink,accent=box_style(name,i)
 if spec:title,code,paper,ink=spec['title'],spec['code'],spec['color'],'#ffffff'
 scale=4;side=size*scale
 im=Image.new('RGBA',(side,side));d=ImageDraw.Draw(im)
 def rect(b,c):d.rectangle(tuple(round(v*side/40) for v in b),fill=c)
 rect((1,1,38.5,38.5),'#92968b');rect((1.6,1.6,37.9,37.9),paper)
 rect((1.6,1.6,37.9,10.8),header);rect((1.6,11,37.9,11.3),'#f3eedc')
 def centered(value,y,points,color):
  f=ImageFont.truetype(str(FONT),round(points*side/40))
  while d.textlength(value,font=f)>side*.84:f=ImageFont.truetype(str(FONT),f.size-1)
  d.text((side/2,y*side/40),value,font=f,fill=color,anchor='mt')
 centered(brand,4,4.4,'#ae2636' if brand=='KODAK' else '#fff8e5')
 centered(title,16,5.8,ink)
 if code:centered(code,25,6.5 if len(code)<=4 else 4.7,ink)
 rect((1.6,35.3,37.9,37.9),accent)
 return im.resize((size,size),Image.Resampling.LANCZOS)

def generate():
 names=re.findall(r'\{"([^"\n]+)",[-0-9]',(ROOT/'native/gr3/m10v_library.c').read_text())
 names += [v['name'] for v in json.loads((ROOT/'web/gr3/film-catalog.json').read_text())['looks']]
 names += ['5207','蓝凤凰','哈曼 RED','Portra 160','富士业务用 100','乐凯 C200','CCD Classic','富士 C200','ProImage 100','T-Max 100','Aerochrome','2460','5203']
 if len(names)!=78:raise ValueError('catalog must contain 78 films')
 # Preserve exact official directory pointers; original descriptors stay in RAM.
 import subprocess,struct
 js="import {readFileSync} from 'node:fs';import {officialResources} from './node/gr3-stock-presets.mjs';const {decoded:d,sections:s}=officialResources(readFileSync('bin/fwdc239b-gr3-official.bin'));process.stdout.write(d.subarray(s.RTOS.offset+0x107b540+0x20fc,s.RTOS.offset+0x107b540+0x20fc+671*4));"
 directory=subprocess.check_output(['node','--input-type=module','-e',js],cwd=ROOT)
 if len(directory)!=2684:raise ValueError('official icon directory invalid')
 (ROOT/'native/gr3/m10v_stock_icon_directory.bin').write_bytes(directory)
 pixels=bytearray();meta=[];sheet=Image.new('RGBA',(10*120,8*130),'#171a18')
 out=ROOT/'web/gr3/film-icons';out.mkdir(exist_ok=True)
 for i,name in enumerate(names,1):
  title,code,color=label(name,i);im=box_icon(name,i)
  rgba=im.tobytes();pixels+=rgba;im.save(out/f'{i:02d}.png',optimize=True)
  box_icon(name,i,160).save(out/f'{i:02d}-large.png',optimize=True)
  meta.append({'id':i,'name':name,'title':title,'code':code,'color':color,'icon_url':f'/gr3/film-icons/{i:02d}-large.png','sha256':hashlib.sha256(rgba).hexdigest()})
  big=im.resize((120,120),Image.Resampling.NEAREST);sheet.alpha_composite(big,((i-1)%10*120,(i-1)//10*130))
 (ROOT/'native/gr3/m10v_icons.rgba').write_bytes(pixels)
 # Append the noncontiguous Charmera identity without moving historical pixels.
 im=box_icon('Kodak Charmera',289)
 box_icon('Kodak Charmera',289,160).save(out/'289-large.png')
 raw=im.tobytes();im.save(out/'289.png');(ROOT/'native/gr3/m10v_charmera.rgba').write_bytes(raw)
 meta.append({'id':289,'name':'Kodak Charmera','title':'KODA','code':'PIXEL','color':'#fad84e','icon_url':'/gr3/film-icons/289-large.png','sha256':hashlib.sha256(raw).hexdigest()})
 im=box_icon('方块世界',290)
 box_icon('方块世界',290,160).save(out/'290-large.png')
 raw=im.tobytes();im.save(out/'290.png');(ROOT/'native/gr3/m10v_pixel_world.rgba').write_bytes(raw)
 meta.append({'id':290,'name':'方块世界','title':'PIXEL','code':'WORLD','color':'#76a849','icon_url':'/gr3/film-icons/290-large.png','sha256':hashlib.sha256(raw).hexdigest()})
 # Sparse styles append artwork without renumbering the 78 historical sprites.
 styles=json.loads((ROOT/'web/gr3/style-filters-luts.json').read_text())['stocks'];style_pixels=bytearray()
 for spec in styles:
  im=box_icon(spec['name'],spec['id'],spec=spec)
  box_icon(spec['name'],spec['id'],160,spec).save(out/f"{spec['id']}-large.png",optimize=True)
  raw=im.tobytes();style_pixels+=raw;im.save(out/f"{spec['id']}.png",optimize=True)
  meta.append(dict(id=spec['id'],name=spec['name'],title=spec['title'],code=spec['code'],color=spec['color'],icon_url=f"/gr3/film-icons/{spec['id']}-large.png",sha256=hashlib.sha256(raw).hexdigest()))
 (ROOT/'native/gr3/m10v_style_filters.rgba').write_bytes(style_pixels)
 from scripts.generate_m10v_directory import names as display_names
 display=display_names()
 for row in meta:
  if row['id'] in display:row['name']=display[row['id']]
 im=box_icon('5213',298);raw=im.tobytes();im.save(out/'298.png');box_icon('5213',298,160).save(out/'298-large.png');(ROOT/'native/gr3/m10v_5213.rgba').write_bytes(raw)
 meta.append({'id':298,'name':'5213','title':'5213','code':'200T','color':'#b59a45','icon_url':'/gr3/film-icons/298-large.png','sha256':hashlib.sha256(raw).hexdigest()})
 d76_pixels=bytearray()
 for spec in json.loads((ROOT/'web/gr3/d76-luts.json').read_text())['stocks']:
  im=box_icon(spec['name'],spec['id'],spec=spec);raw=im.tobytes();d76_pixels+=raw
  im.save(out/f"{spec['id']}.png",optimize=True);box_icon(spec['name'],spec['id'],160,spec).save(out/f"{spec['id']}-large.png",optimize=True)
  meta.append(dict(id=spec['id'],name=spec['name'],title=spec['title'],code=spec['code'],color=spec['color'],icon_url=f"/gr3/film-icons/{spec['id']}-large.png",sha256=hashlib.sha256(raw).hexdigest()))
 (ROOT/'native/gr3/m10v_d76.rgba').write_bytes(d76_pixels)
 anime_pixels=bytearray()
 for spec in json.loads((ROOT/'web/gr3/anime-e6-luts.json').read_text())['stocks']:
  im=box_icon(spec['name'],spec['id'],spec=spec);raw=im.tobytes();anime_pixels+=raw
  if spec['id']<309:continue
  im.save(out/f"{spec['id']}.png",optimize=True);box_icon(spec['name'],spec['id'],160,spec).save(out/f"{spec['id']}-large.png",optimize=True)
  meta.append(dict(id=spec['id'],name=spec['name'],title=spec['title'],code=spec['code'],color=spec['color'],icon_url=f"/gr3/film-icons/{spec['id']}-large.png",sha256=hashlib.sha256(raw).hexdigest()))
 (ROOT/'native/gr3/m10v_anime_e6.rgba').write_bytes(anime_pixels)
 c41_pixels=bytearray()
 for spec in json.loads((ROOT/'web/gr3/c41-luts.json').read_text())['stocks']:
  im=box_icon(spec['name'],spec['id'],spec=spec);raw=im.tobytes();c41_pixels+=raw
  im.save(out/f"{spec['id']}.png",optimize=True);box_icon(spec['name'],spec['id'],160,spec).save(out/f"{spec['id']}-large.png",optimize=True)
  meta.append(dict(id=spec['id'],name=spec['name'],title=spec['title'],code=spec['code'],color=spec['color'],icon_url=f"/gr3/film-icons/{spec['id']}-large.png",sha256=hashlib.sha256(raw).hexdigest()))
 (ROOT/'native/gr3/m10v_c41.rgba').write_bytes(c41_pixels)
 extra_pixels=bytearray()
 for spec in json.loads((ROOT/'web/gr3/extra-films-luts.json').read_text())['stocks']:
  im=box_icon(spec['name'],spec['id'],spec=spec);raw=im.tobytes();extra_pixels+=raw
  im.save(out/f"{spec['id']}.png",optimize=True);box_icon(spec['name'],spec['id'],160,spec).save(out/f"{spec['id']}-large.png",optimize=True)
  meta.append(dict(id=spec['id'],name=spec['name'],title=spec['title'],code=spec['code'],color=spec['color'],icon_url=f"/gr3/film-icons/{spec['id']}-large.png",sha256=hashlib.sha256(raw).hexdigest()))
 (ROOT/'native/gr3/m10v_extra_films.rgba').write_bytes(extra_pixels)
 (out/'catalog.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
 # Include every sparse identity and custom artwork in the visual inventory.
 sheet=Image.new('RGBA',(1200,((len(meta)+10)//10)*130),'#171a18')
 for n,m in enumerate(meta):sheet.alpha_composite(Image.open(out/f"{m['id']:02d}.png").resize((120,120),Image.Resampling.LANCZOS),(n%10*120,n//10*130))
 box_icon('Custom LUT',0,120).save(out/'custom.png')
 sheet.alpha_composite(box_icon('Custom LUT',0,120),(len(meta)%10*120,len(meta)//10*130))
 sheet.save(ROOT/'docs/previews/m10v-film-icons.png')
 return meta
if __name__=='__main__':generate()
