"""Original M10V cartridge art. One RGBA source for web and camera, no borrowed assets."""
from pathlib import Path
import re,json,hashlib,sys
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
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

def artwork(name,i,spec=None):
 """Shared square pack identity. Motifs are content, not interchangeable tints."""
 if i==-1:return 'RECORDED','FILM','?','#565e65','#f3efe0','#9aabaf',7
 brand,title,code,header,paper,ink,accent=box_style(name,i)
 if spec:title,code,paper,ink=spec['title'],spec['code'],spec['color'],'#fff7e7'
 motif=8
 if 1<=i<=32:
  title=name.removeprefix('M10V ').upper();code='RECIPE %02d'%i;motif=6+i%4
 curated={
 33:('CINESTILL','800T','TUNGSTEN','#061b2b','#fff5df','#ff2945',3),
 34:('KODAK','EKTAR','100','#c50e22','#fff5db','#ffd137',0),
 35:('KODAK','GOLD','200','#ffcf25','#171c1b','#d62927',1),
 36:('FUJIFILM','PRO 400H','400','#e7e5d1','#195e43','#62a56d',8),
 37:('KODAK','PORTRA','400','#f2e5cc','#431934','#bd7b8e',2),
 56:('FUJIFILM','SUPERIA','200','#e9e9cf','#145d42','#5aaa6a',8),
 57:('FUJIFILM','SUPERIA','200 B','#e3e7d0','#16564b','#61a489',8),
 58:('KODAK','ULTRAMAX','400','#f5cf32','#1a3e83','#e2382f',1),
 59:('KODAK','ULTRAMAX','400 W','#eec63a','#2b3b78','#e8873f',1),
 60:('KODAK','ULTRAMAX','400 RC','#e8c83c','#20375b','#ba4440',1),
 69:('KODAK','PORTRA','160','#f4e6d0','#502347','#b88b9e',2),
 76:('KODAK','AEROCHROME','1443','#07344c','#fff1dd','#ef2357',5),
 314:('FUJIFILM','ACROS II','100','#202326','#f3efe2','#b6b7b4',4),
 289:('KODAK','CHARMERA','PIXEL','#ffcc24','#b32a30','#ed4933',10),
 290:('PIXEL','WORLDS','8 BIT','#a8c578','#173d2e','#557d38',10),
 66:('KODAK','5207','250D','#e5b72b','#1f2a27','#a52e24',7),
 62:('KODAK','5219','500T','#282d30','#fff1cf','#d8a82f',7),
 78:('KODAK','5203','50D','#efcf58','#272d28','#ae3c25',7),
 298:('KODAK','5213','200T','#caab46','#1b302a','#91472f',7),
 77:('KODAK','AEROCOLOR IV','2460','#86d0d0','#112f36','#fff0c7',9),
 67:('HARMAN','PHOENIX II','200','#1577bb','#fff2ce','#f1ac25',6),
 68:('HARMAN','RED','RED SCALE','#d33728','#fff0cf','#742333',6),
 70:('FUJIFILM','INDUSTRIAL','100','#f3ebd4','#125e3e','#3ba977',8),
 71:('LUCKY','C200','200','#edddac','#ac2730','#d83237',8),
 72:('DIGITAL','CCD','CLASSIC','#94bac3','#163344','#eee6c9',10),
 73:('FUJIFILM','C200','200','#eae9c5','#166949','#74aa39',8),
 74:('KODAK','PROIMAGE','100','#e6c884','#463425','#ae453c',1),
 75:('KODAK','T-MAX','100','#e4e1d7','#222528','#b79e63',4),
 291:('LEICA','MONOCHROME','MONO','#272b2d','#f4eee0','#b53032',4),
 292:('LOMOGRAPHY','COLOR NEG','400','#f4d858','#302b30','#cb363f',6),
 293:('POLAROID','POLAROID','600','#f1eee3','#282a2e','#ef4c3d',11),
 294:('FUJIFILM','VELVIA','50','#eaeee0','#382b52','#4b9f5a',8),
 295:('NIGHT CITY','CYBERPUNK','NEON','#181638','#60edeb','#ed2980',3),
 296:('BLUEPRINT','CYANOTYPE','BLUE','#123d80','#f4f1df','#81b4c7',9),
 297:('GERMAN','COOL','DE','#a7bdc7','#243848','#e4d7bc',9),
 299:('KODAK','TRI-X','400','#23272b','#f4efe0','#e6b934',4),
 300:('ILFORD','DELTA','100','#e6e4df','#23262a','#ba333c',4),
 301:('ILFORD','PAN','400','#282a2d','#f1eee3','#d6b34a',4),
 302:('ROLLEI','INFRARED','400 IR','#202628','#f7efe1','#b93c39',5),
 303:('ILFORD','SFX','200 IR','#20272b','#f7efe1','#cf4148',5),
 304:('FOMA','FOMAPAN','400','#e7e7dc','#174f79','#4d8eac',4),
 305:('CATLABS','X FILM','80 MKII','#d8dfca','#243d31','#71936b',4),
 309:('FUJIFILM','PROVIA','100F','#e8ecdc','#16422e','#319466',8),
 310:('KODAK','EKTACHROME','E100','#e6bc2c','#1b427a','#b43930',9),
 311:('KODAK','EKTACHROME','5294','#dfc22e','#173d73','#ae3432',7),
 312:('OPTIK','OPTICOLOUR','200','#e3e5ca','#2f522b','#de8c2b',6),
 313:('ORWO','WOLFEN','NC500','#262829','#f4e8ce','#d96a2b',7),
 315:('KODAK','DOUBLE-X','5222','#d5bd61','#232c2c','#7c8348',7),
 316:('LOMOGRAPHY','TURQUOISE','100-400','#1b6875','#f2e4ac','#d5993c',5),
 317:('FUJIFILM','INSTAX','800','#eee9d6','#14684e','#db4b59',11),
 318:('KODAK','2383','PRINT','#d6b348','#282d28','#9d4635',7),
 319:('FUJIFILM','CLASSIC','NEGATIVE','#d5d7bc','#203e32','#a3654a',8),
 320:('FUJIFILM','CLASSIC','CHROME','#a6b3ae','#263c43','#ba8d58',9),
 321:('LOMOGRAPHY','LOMOCHROME','PURPLE','#543250','#f6e6cb','#b978af',5)}
 if i in curated:brand,title,code,paper,ink,accent,motif=curated[i]
 return brand,title,code,paper,ink,accent,motif

def box_icon(name,i,size=40,spec=None):
 brand,title,code,paper,ink,accent,motif=artwork(name,i,spec)
 side=512;im=Image.new('RGBA',(side,side),paper);d=ImageDraw.Draw(im)
 def poly(points,c):d.polygon([(round(x*4),round(y*4)) for x,y in points],fill=c)
 def line(points,c,w=1):d.line([(round(x*4),round(y*4)) for x,y in points],fill=c,width=round(w*4))
 def ellipse(b,c):d.ellipse(tuple(round(v*4) for v in b),fill=c)
 def rect(b,c):d.rectangle(tuple(round(v*4) for v in b),fill=c)
 compact=size<=40
 # Text occupies the upper two thirds; characteristic illustration lives below.
 if motif==0:
  poly([(0,88),(70,88),(128,22),(128,128),(0,128)],accent)
  poly([(74,128),(128,64),(128,84),(91,128)],'#e96717')
  ellipse((99,94,116,111),'#fff4b8')
 elif motif in (1,2):
  for k,c in enumerate(([accent,'#ef762a'] if motif==1 else ['#d9b39c',accent,'#733a63'])):
   # Concentric sweeping pack curves, kept clear of the name.
   ellipse((-169-k*8,-206-k*9,181-k*8,157-k*9),c)
  ellipse((-188,-230,173,137),paper)
  if motif==1:
   ellipse((96,93,110,107),'#fff1b0')
   for x,y,h in [(115,96,31),(103,109,19),(91,115,13)]:
    line([(x,y),(x-2,y+h)],'#592a24',1.3)
    for dx,dy in [(-8,-3),(-7,2),(-3,-6),(5,-5),(8,0),(6,4)]:line([(x,y),(x+dx,y+dy)],'#592a24',1.2)
 elif motif==3:
  poly([(0,128),(46,85),(83,85),(128,128)],'#0d4051')
  for x in [5,23,103,122]:
   line([(x,91),(x,118)],'#2a707e',.6);ellipse((x-1.5,88,x+1.5,91),'#74f7ed')
  line([(0,118),(128,103)],accent,1.5);line([(0,121),(128,107)],'#37e6e4',1)
  d.arc((285,180,555,520),195,330,fill=accent,width=5)
 elif motif==4:
  poly([(25,128),(89,76),(128,107),(128,128)],accent)
  poly([(24,128),(90,77),(104,96),(94,88),(86,100),(80,94),(46,128)],ink)
  poly([(66,128),(114,89),(128,105),(128,128)],'#777c7b')
  line([(0,128),(128,0)],accent,.6)
 elif motif==5:
  rect((0,100,128,128),'#146485');poly([(0,109),(45,92),(69,108),(94,98),(128,113)],'#52aac0')
  for x in [3,12,119,127]:
   line([(x,128),(x,87)],'#303b3e',1)
   for j in range(8):
    y=91+j*4;ellipse((x-9+(j%2)*3,y-5,x+7,y+7),accent)
 elif motif==6:
  for k in range(5):poly([(k*26,128),(65,83),(k*26+18,128)],accent)
  ellipse((53,87,76,110),ink);ellipse((59,89,78,104),paper)
 elif motif==7:
  poly([(0,128),(0,108),(128,79),(128,128)],accent)
  rect((0,116,128,128),'#252d2d')
  for x in range(3,128,13):rect((x,120,x+6,124),paper)
 elif motif==8:
  for k in range(3):poly([(28+k*25,128),(84+k*18,79),(101+k*18,79),(44+k*25,128)],accent)
 elif motif==9:
  for k in range(4):line([(0,101+k*7),(128,89+k*8)],accent,1.5)
  ellipse((99,78,115,94),accent)
 elif motif==10:
  for y in range(88,128,8):
   for x in range(0,128,8):
    if (x//8+y//8+i)%3==0:rect((x,y,x+7,y+7),accent)
 elif motif==11:
  for k,c in enumerate(['#d95155','#ed9d38','#e9cb42','#569c72','#5089ad']):rect((k*26,101,k*26+26,128),c)
  rect((8,107,120,128),paper)
 # Delicate printed edge; no pseudo 3D enclosure competing with the name.
 d.rectangle((1,1,510,510),outline=ink,width=2)
 def label_at(value,x,y,points,color,maxw=112):
  f=ImageFont.truetype(str(FONT),round(points*4))
  while d.textlength(value,font=f)>maxw*4:f=ImageFont.truetype(str(FONT),f.size-1)
  d.text((x*4,y*4),value,font=f,fill=color,anchor='lt',stroke_width=0)
 if compact:
  # Brand is intentionally omitted at 40px: model/code must survive actual LCD size.
  compact_title={'AEROCHROME':'AERO','EKTACHROME':'EKTA','MONOCHROME':'MONO','COLOR NEG':'LOMO','OPTICOLOUR':'OPTIK','INDUSTRIAL':'FUJI'}.get(title,title)
  label_at(compact_title,7,17,27,ink,114)
  label_at(code,8,56,25 if len(code)<=4 else 17,ink,110)
 else:
  label_at(brand,8,10,13,accent if motif==3 else ink)
  if title=='AEROCHROME':
   label_at('AERO',7,31,29,ink);label_at('CHROME',7,59,25,ink)
   label_at(code,8,89,13,ink)
  else:
   label_at(title,7,33,34,ink)
   label_at(code,8,73,27 if len(code)<=4 else 16,ink)
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
 four_pixels=bytearray()
 for spec in json.loads((ROOT/'web/gr3/four-looks-luts.json').read_text())['stocks']:
  im=box_icon(spec['name'],spec['id'],spec=spec);raw=im.tobytes();four_pixels+=raw
  im.save(out/f"{spec['id']}.png",optimize=True);box_icon(spec['name'],spec['id'],160,spec).save(out/f"{spec['id']}-large.png",optimize=True)
  meta.append(dict(id=spec['id'],name=spec['name'],title=spec['title'],code=spec['code'],color=spec['color'],icon_url=f"/gr3/film-icons/{spec['id']}-large.png",sha256=hashlib.sha256(raw).hexdigest()))
 (ROOT/'native/gr3/m10v_four_looks.rgba').write_bytes(four_pixels)
 for row in meta:
  large=out/f"{row['id']:02d}-large.png"
  revision=hashlib.sha256(large.read_bytes()).hexdigest()[:12]
  row['icon_compact_url']=f"/gr3/film-icons/{row['id']:02d}.png?v={row['sha256'][:12]}"
  row['icon_url']=f"/gr3/film-icons/{row['id']:02d}-large.png?v={revision}"
  row['artwork_revision']='classic-square-v1'
 (out/'catalog.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
 # Include every sparse identity and custom artwork in the visual inventory.
 sheet=Image.new('RGBA',(1200,((len(meta)+10)//10)*130),'#171a18')
 for n,m in enumerate(meta):sheet.alpha_composite(Image.open(out/f"{m['id']:02d}.png").resize((120,120),Image.Resampling.LANCZOS),(n%10*120,n//10*130))
 box_icon('Custom LUT',0,120).save(out/'custom.png')
 unknown=box_icon('Unknown film',-1)
 unknown.save(out/'unknown.png');box_icon('Unknown film',-1,160).save(out/'unknown-large.png')
 (ROOT/'native/gr3/m10v_unknown_film.rgba').write_bytes(unknown.tobytes())
 sheet.alpha_composite(box_icon('Custom LUT',0,120),(len(meta)%10*120,len(meta)//10*130))
 sheet.save(ROOT/'docs/previews/m10v-film-icons.png')
 previews=ROOT/'docs/previews/square-film';previews.mkdir(parents=True,exist_ok=True)
 compact=Image.new('RGBA',(8*128,((len(meta)+7)//8)*76),'#171d21')
 large=Image.new('RGBA',(8*160,((len(meta)+7)//8)*184),'#171d21')
 f=ImageFont.truetype(str(FONT),10)
 cd=ImageDraw.Draw(compact);ld=ImageDraw.Draw(large)
 for n,row in enumerate(meta):
  with Image.open(out/f"{row['id']:02d}.png") as icon:compact.alpha_composite(icon,(n%8*128+44,n//8*76+4))
  with Image.open(out/f"{row['id']:02d}-large.png") as icon:large.alpha_composite(icon,(n%8*160,n//8*184))
  caption=f"{row['id']} {row['name']}"
  # Inventory labels are auxiliary; artwork itself contains Latin model/code.
  cd.text((n%8*128+2,n//8*76+47),caption,font=f,fill='#e8e3d9')
  ld.text((n%8*160+3,n//8*184+164),caption,font=f,fill='#e8e3d9')
 compact.save(previews/'compact-actual40.png');large.save(previews/'catalog-large160.png')
 return meta
if __name__=='__main__':generate()
