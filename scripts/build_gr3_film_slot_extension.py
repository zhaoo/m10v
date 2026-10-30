"""GR III 2.10 shooting-only tone extension; no stock parameter-bank proxies.

Exact official instructions and metadata pairs are checked again by the Node
packager. Movie and RAW-development enumeration keeps its original tables.
"""
import struct
from scripts.build_gr3_menu_patches import assembly, branch, movw


def build_appended_slots(base, native_base, stock, symbols):
    image = bytearray()
    patches = []
    def patch(at, expected, replacement):
        if struct.unpack_from('<I',stock,at-0x53000000)[0]!=expected:
            raise ValueError('appended slot preimage differs: '+hex(at))
        patches.append(dict(address=at,expected=expected,replacement=replacement))
    def hook(at, expected, source):
        entry=base+len(image)
        image.extend(assembly(source,entry))
        patch(at,expected,branch(at,entry))
        return entry
    dynamic_count=hex(symbols['m10v_camera_library_shooting_count'])
    count=hook(0x532c2a9c,0xe1a0c00d,
        'ldrb ip,[r0,#0x1b];cmp ip,#0;bne fallback;'
        'push {r4,lr};bl '+dynamic_count+';pop {r4,pc};'
        'fallback:;mov ip,sp;b 0x532c2aa0')
    index=hook(0x532c2c80,0xe1a0c00d,
        'ldrb ip,[r0,#0x1b];cmp ip,#0;bne fallback;'
        'push {r4,r5,r6,lr};mov r4,r0;mov r5,r1;bl '+dynamic_count+';'
        'cmp r5,#12;blo restore;cmp r5,r0;sublo r0,r5,#12;addlo r0,r0,#25;'
        'poplo {r4,r5,r6,pc};restore:;mov r0,r4;mov r1,r5;pop {r4,r5,r6,lr};'
        'fallback:;mov ip,sp;b 0x532c2c84')
    position=hook(0x532c2f08,0xe1a0c00d,
        'ldrb ip,[r0,#0x1b];cmp ip,#0;bne fallback;'
        'push {r4,r5,r6,lr};mov r4,r0;mov r5,r1;bl '+dynamic_count+';'
        'sub r0,r0,#12;sub ip,r5,#25;cmp ip,r0;addlo r0,ip,#12;'
        'poplo {r4,r5,r6,pc};mov r0,r4;mov r1,r5;pop {r4,r5,r6,lr};'
        'fallback:;mov ip,sp;b 0x532c2f0c')
    maximum=hook(0x532c2b7c,0xe30d3368,'b '+dynamic_count)
    display=hook(0x5326c240,branch(0x5326c240,0x5326c2a0),
        'sub r0,r3,#25;cmp r0,#10;movlo r0,r3;blo 0x5326c22c;b 0x5326c2a0')
    for at,old,name in [
        (0x531ab7a8,0x532a985c,'menu_name'),
        (0x531ab894,0x532a9988,'menu_icon'),(0x531ab8bc,0x532a9988,'menu_icon'),
        (0x531a05ac,0x532c2c80,'index'),(0x531a070c,0x532c2c80,'index'),
        (0x531a0588,0x532a985c,'adj_name'),(0x531a06e0,0x532a9988,'adj_icon'),
    ]:
        patch(at,branch(at,old,True),branch(at,symbols['m10v_tone_menu_'+name],True))
    for at,name in [(0x531abe0c,'menu_matches'),(0x531a1500,'adj_matches'),(0x531a0ba0,'adj_select')]:
        patch(at,0xe1a0c00d,branch(at,symbols['m10v_tone_menu_'+name]))
    # Preserve all official EXIF pairs, append distinct private ImageTone codes.
    table=base+len(image)
    pairs=stock[0xd2b6f4:0xd2b6f4+48]+b''.join(struct.pack('<BBH',25+i,0,0x10c+i) for i in range(10))
    if len(pairs)!=88:raise ValueError('invalid stock ImageTone pairs')
    image.extend(pairs)
    for at,old,new in [
        (0x53599df4,0xe3a00030,0xe3a00058),
        (0x53599e20,0xe30bc6f4,movw(12,table&65535)),
        (0x53599e2c,0xe345c3d2,0xe340c000|(((table>>16)&0xf000)<<4)|((table>>16)&0xfff)),
        (0x53599e30,0xe2801030,0xe2801058),
        (0x53599e4c,0xe353000c,0xe3530016),
        (0x53599e60,0xe2800030,0xe2800058),
    ]:patch(at,old,new)
    # The EXIF writer above stores slot tones 25..34 as ImageTone 0x10c..0x115.
    # Official EXIF reader 0x535c24ec clamps normalized values >11 to zero.
    # Preserve its stock mapping and teach only its unknown branch about our
    # recorded private range; otherwise the existing playback hooks never see it.
    metadata_decode=base+len(image)
    image.extend(assembly('cmp r0,#21;orrls r2,r0,#0x10000;movhi r2,#0;'
        'cmp r0,#11;b 0x535c2520',metadata_decode))
    patch(0x535c251c,0x83a02000,(branch(0x535c251c,metadata_decode)&0x0fffffff)|0x80000000)
    # Private metadata key25 is 0x10000 | (ImageTone - 0x100).
    # Use a generic film mark: journals can be reassigned after capture, so a
    # current-slot artwork would incorrectly relabel older photos.
    private='movw ip,#12;movt ip,#1;sub r2,r2,ip;cmp r2,#9;'
    icon=base+len(image)
    image.extend(assembly('push {r4,lr};bl 0x532b6eec;cmp r0,#0;bne done;'
        'bl 0x5320ad88;bl 0x5320b97c;cmp r0,#0;beq done;ldr r2,[r0,#0x220];'+private+
        'movls r0,#754;movhi r0,#0;done:;pop {r4,pc}',icon))
    detail=base+len(image)
    image.extend(assembly('push {r0,r1,r4,lr};bl 0x532b44bc;cmp r0,#0;bne done;'
        'ldr r2,[sp];ldr r2,[r2,#0x220];'+private+'bhi done;'
        'ldr r1,[sp,#4];cmp r1,#0;movne r2,#11;strbne r2,[r1];mov r0,#1;'
        'done:;add sp,sp,#8;pop {r4,pc}',detail))
    patch(0x53179b7c,0xeb04f4da,branch(0x53179b7c,icon,True))
    patch(0x532b7cfc,0xebfff1ee,branch(0x532b7cfc,detail,True))
    return bytes(image),dict(schema='m10v-gr3-appended-slots/v2',base=base,bytes=len(image),
        tones=list(range(25,35)),stock_choices=12,shooting_choices='12+enabled_films',shooting_choices_max=22,
        library_index='14+enabled_films',movie_choices=10,raw_development_choices=12,
        entries=dict(count=count,index=index,position=position,maximum=maximum,display=display),
        exif_table=table,exif_bytes=88,patches=patches,
        playback=dict(icon=icon,detail=detail,metadata_decode=metadata_decode,icon_id=754,metadata_key=0x25,recorded_codes=[0x10c,0x115],identity="recorded-slot-generic-film"),
        stock_parameter_proxy=False,state_version=5,camera_tested=False)
