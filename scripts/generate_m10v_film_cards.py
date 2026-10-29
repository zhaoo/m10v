"""Antialiased portrait film boxes, using the bundled OFL Noto Sans Bold font."""
import json,re,sys,base64,hashlib,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.generate_m10v_icons import box_style,FONT

def canonical_raster():
 """Pinned coverage avoids FreeType/RAQM differences across build hosts."""
 data=json.loads((ROOT/'native/gr3/m10v_film_font_raster.json').read_text())
 if data['schema']!='m10v-film-font-raster/v1' or hashlib.sha256(FONT.read_bytes()).hexdigest()!=data['font_sha256']:raise ValueError('font raster provenance differs')
 glyphs=base64.b64decode(data['glyphs_base64'],validate=True)
 custom=base64.b64decode(data['custom_icon_base64'],validate=True)
 if len(data['widths'])!=95 or any(type(v)is not int or not 0<=v<=16 for v in data['widths']) or len(glyphs)!=95*320 or len(custom)!=6400:raise ValueError('font raster extent differs')
 if hashlib.sha256(glyphs).hexdigest()!=data['glyphs_sha256'] or hashlib.sha256(custom).hexdigest()!=data['custom_icon_sha256']:raise ValueError('font raster digest differs')
 return data['widths'],glyphs,custom

def generate():
 names=re.findall(r'\{"([^"\n]+)",[-0-9]',(ROOT/'native/gr3/m10v_library.c').read_text())
 names += [v['name'] for v in json.loads((ROOT/'web/gr3/film-catalog.json').read_text())['looks']]
 names += ['5207','蓝凤凰','哈曼 RED','Portra 160','富士业务用 100','乐凯 C200','CCD Classic','富士 C200','ProImage 100','T-Max 100','Aerochrome','2460','5203']
 if len(names)!=78:raise ValueError('film catalog differs')
 styles=json.loads((ROOT/'web/gr3/style-filters-luts.json').read_text())['stocks']
 specs=[(i,name,None) for i,name in enumerate(names,1)]+[(289,'Kodak Charmera',None),(290,'方块世界',None)]+[(v['id'],v['name'],v) for v in styles]+[(298,'5213',None)]+[(v['id'],v['name'],v) for v in json.loads((ROOT/'web/gr3/d76-luts.json').read_text())['stocks']]
 specs += [(v['id'],v['name'],v) for v in json.loads((ROOT/'web/gr3/anime-e6-luts.json').read_text())['stocks'] if v['id']>=309]
 specs += [(v['id'],v['name'],v) for v in json.loads((ROOT/'web/gr3/c41-luts.json').read_text())['stocks']]
 specs += [(v['id'],v['name'],v) for v in json.loads((ROOT/'web/gr3/extra-films-luts.json').read_text())['stocks']]
 rows=['static const struct { uint8_t brand,main,sub,header,color,ink,accent; } box_cards[]={'];palette=[];words=[]
 # Camera-only artwork identities. Stable 40px icons, renderer records and LUTs
 # retain their existing byte identities.
 identities={314:('FUJIFILM','ACROS II','100'),315:('KODAK','DOUBLE-X','5222'),316:('LOMOGRAPHY','TURQUOISE','100-400'),312:('OPTIK','OPTICOLOUR','200'),313:('ORWO','WOLFEN','NC500'),33:('CINESTILL','800T','TUNGSTEN'),66:('KODAK','5207','250D'),62:('KODAK','5219','500T'),78:('KODAK','5203','50D'),298:('KODAK','5213','200T'),77:('KODAK','AEROCOLOR IV','2460'),
 69:('KODAK','PORTRA','160'),37:('KODAK','PORTRA','400'),70:('FUJIFILM','INDUSTRIAL','100'),73:('FUJIFILM','C200','200'),56:('FUJIFILM','SUPERIA','200'),36:('FUJIFILM','PRO 400H','400'),35:('KODAK','GOLD','200'),58:('KODAK','ULTRAMAX','400'),74:('KODAK','PROIMAGE','100'),34:('KODAK','EKTAR','100'),71:('LUCKY','C200','200'),67:('HARMAN','PHOENIX II','200'),68:('HARMAN','RED','RED SCALE'),292:('LOMOGRAPHY','COLOR NEGATIVE','400'),75:('KODAK','T-MAX','100'),289:('KODAK','CHARMERA',''),72:('DIGITAL','CCD',''),293:('POLAROID','POLAROID',''),296:('CYANOTYPE','CYANOTYPE',''),290:('PIXEL','WORLDS',''),76:('KODAK','AEROCHROME',''),291:('LEICA','MONOCHROME',''),297:('GERMAN','COOL',''),65:('RICOH','GR2','')}
 for i,name,spec in specs:
  brand,title,code,header,paper,ink,accent=box_style(name,i)
  if spec:title,code,paper,ink=spec['title'],spec['code'],spec['color'],'#ffffff'
  if i in identities:brand,title,code=identities[i]
  if i==58:header,accent='#ffcf32','#ffcf32'
  for c in (header,paper,ink,accent):
   if c not in palette:palette.append(c)
  colors=','.join(str(palette.index(c)) for c in (header,paper,ink,accent))
  for word in (brand,title,code):
   if len(word.encode('ascii'))>=16:raise ValueError('card label exceeds bounded storage')
   if word not in words:words.append(word)
  rows.append(' {%d,%d,%d,%s},'%(words.index(brand),words.index(title),words.index(code),colors))
 if len(words)>256 or len(palette)>256:raise ValueError('card dictionary exceeds index capacity')
 rows=['/* Generated portrait artwork; shared labels and palette are immutable. */',
  'static const uint32_t box_palette[]={'+','.join('0xff'+c[1:]+'u' for c in palette)+'};',
  'static const char box_labels[]='+''.join(json.dumps(word)+'"\\0"' for word in words)+';',
  'static const uint16_t box_label_offsets[]={'+','.join(str(sum(len(v)+1 for v in words[:i])) for i in range(len(words)))+'};']+rows
 rows+=['};','static const uint8_t smooth_width[95]={']
 widths,glyphs,_=canonical_raster()
 rows.append(','.join(str(v) for v in widths)+'};')
 compressed=bytearray();glyph_offsets=[0]
 for i in range(95):compressed.extend(packbits(glyphs[i*320:(i+1)*320]));glyph_offsets.append(len(compressed))
 rows+=['static const uint16_t glyph_offsets[]={'+','.join(map(str,glyph_offsets))+'};',
        'static const uint8_t glyph_data[]={'+','.join(map(str,compressed))+'};']
 return '\n'.join(rows)

def caption_data():
 captions=json.loads((ROOT/'native/gr3/m10v_card_captions.json').read_text())
 if captions['schema']!='m10v-card-captions/v1' or (captions['width'],captions['height'])!=(120,28):raise ValueError('card caption format differs')
 packed=bytearray();offsets=[0]
 films=[*range(1,79),*range(289,299)]
 if len(captions['captions'])!=len(films):raise ValueError('card caption inventory differs')
 for film,caption in zip(films,captions['captions']):
  data=base64.b64decode(caption['rle'],validate=True)
  if len(data)%2 or any(data[i]==0 for i in range(0,len(data),2)):raise ValueError('invalid caption runs')
  raw=b''.join(bytes([data[i+1]])*data[i] for i in range(0,len(data),2))
  if caption['film']!=film or len(raw)!=120*28 or hashlib.sha256(raw).hexdigest()!=caption['sha256']:raise ValueError('card caption identity or digest differs')
  # Four antialias coverage levels, four pixels per byte, then PackBits.
  # Keep full names within the existing firmware growth budget.
  if film<=32:offsets.append(len(packed));continue # hidden legacy names use the shared lossless ASCII glyphs
  quantized=[(value*3+127)//255 for value in raw]
  pixels=bytes(sum(quantized[i+j]<<(j*2) for j in range(4)) for i in range(0,len(raw),4))
  packed.extend(packbits(pixels));offsets.append(len(packed))
 return offsets,packed

def packbits(pixels):
  packed=bytearray();i=0
  while i<len(pixels):
   run=1
   while i+run<len(pixels) and pixels[i+run]==pixels[i] and run<128:run+=1
   if run>=3:packed.extend((128+run-1,pixels[i]));i+=run
   else:
    start=i;i+=run
    while i<len(pixels) and i-start<128:
     if i+2<len(pixels) and pixels[i]==pixels[i+1]==pixels[i+2]:break
     i+=1
    packed.append(i-start-1);packed.extend(pixels[start:i])
  return packed

def caption_blob():
 offsets,packed=caption_data()
 return struct.pack('<'+str(len(offsets))+'I',*offsets)+packed

def custom_icon():return canonical_raster()[2]
if __name__=='__main__':
 (ROOT/'native/gr3/m10v_film_card_data.h').write_text(generate())
 (ROOT/'native/gr3/m10v_custom_icon.rgba').write_bytes(custom_icon())
