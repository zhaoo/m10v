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
    identity_enabled='m10v_isp_frame_identity_code' in symbols
    identity_hooks={}
    if identity_enabled:
        # Only ProcessingManager's dedicated 100-element SI pool grows. Other
        # factory/config objects keep their stock extent. Clear at constructor,
        # checkout and return so reusing a slot cannot inherit an old identity.
        patch(0x53523984,0xe3043270,movw(3,0x4280))
        identity_hooks['pool_init']=hook(0x535239e4,branch(0x535239e4,0x5355e87c,True),
            'push {r4,lr};mov r4,r0;bl 0x5355e87c;movw ip,#0x4270;movt ip,#7;add ip,r4,ip;'
            'mov r1,#0;str r1,[ip];str r1,[ip,#4];str r1,[ip,#8];str r1,[ip,#12];pop {r4,lr};b 0x535239e8')
        for name,at,expected,si in [('checkout',0x53523e00,0xe5c12024,'r6'),('return',0x53523a68,0xe5c32024,'r1')]:
            # Checkout publishes the lease before clearing; return clears while
            # it is still leased, before the original availability store.
            clear='push {r0-r12,lr};mrs ip,cpsr;push {ip,lr};mov r0,'+si+';bl '+hex(symbols['m10v_isp_frame_identity_clear'])+';pop {ip,lr};msr cpsr_f,ip;pop {r0-r12,lr};'
            identity_hooks[name]=hook(at,expected,
                ('.word '+hex(expected)+';'+clear if name=='checkout' else clear+'.word '+hex(expected)+';')+'b '+hex(at+4))
        copy=base+len(image)
        image.extend(assembly('push {r0-r4,lr};bl '+hex(symbols['m10v_isp_frame_identity_clear'])+';pop {r0-r4,lr};b 0x5313fd80',copy))
        patch(0x53510830,branch(0x53510830,0x5313fd80,True),branch(0x53510830,copy,True))
        identity_hooks['copy']=copy
        writer=base+len(image)
        image.extend(assembly('push {r0-r4,lr};mov r0,r2;bl '+hex(symbols['m10v_isp_frame_identity_code'])+';cmp r0,#0;beq original;'
            'mov r2,r0;ldr r0,[sp,#4];mov r1,#0;add sp,sp,#16;pop {r4,lr};b 0x535d02c8;'
            'original:;pop {r0-r4,lr};b 0x535c780c',writer))
        for at in (0x53608080,0x5361c0cc):patch(at,branch(at,0x535c780c,True),branch(at,writer,True))
        identity_hooks['writer']=writer
    # The legacy EXIF writer stores slot tones 25..34 as ImageTone 0x10c..0x115.
    # Official EXIF reader 0x535c24ec clamps normalized values >11 to zero.
    # Preserve its stock mapping and teach only its unknown branch about our
    # recorded private range; otherwise the existing playback hooks never see it.
    metadata_decode=base+len(image)
    image.extend(assembly('cmp r0,#21;orrls r2,r0,#0x10000;bls decoded;mov r2,#0;'
        'movw ip,#0xf01;cmp r0,ip;blo decoded;movw ip,#0x104e;cmp r0,ip;bls exact;'
        'movw ip,#0x1f00;cmp r0,ip;blo decoded;movw ip,#0xdfc5;cmp r0,ip;bhi decoded;'
        'exact:;orr r2,r0,#0x20000;decoded:;cmp r0,#11;b 0x535c2520',metadata_decode))
    patch(0x535c251c,0x83a02000,(branch(0x535c251c,metadata_decode)&0x0fffffff)|0x80000000)
    # Key25 marker1 retains legacy slot-only metadata; marker2 carries the
    # recorded film code. Neither playback adapter consults a current slot.
    icon=base+len(image)
    image.extend(assembly('push {r4,lr};bl 0x532b6eec;cmp r0,#0;bne done;'
        'bl 0x5320ad88;bl 0x5320b97c;cmp r0,#0;beq done;ldr r0,[r0,#0x220];bl '+hex(symbols['m10v_menu_recorded_icon'])+';done:;pop {r4,pc}',icon))
    detail=base+len(image)
    image.extend(assembly('push {r0,r1,r4,lr};bl 0x532b44bc;cmp r0,#0;bne done;'
        'ldr r0,[sp];ldr r0,[r0,#0x220];bl '+hex(symbols['m10v_menu_recorded_icon'])+';cmp r0,#0;beq done;'
        'ldr r1,[sp,#4];cmp r1,#0;movne r2,#11;strbne r2,[r1];mov r0,#1;'
        'done:;add sp,sp,#8;pop {r4,pc}',detail))
    patch(0x53179b7c,0xeb04f4da,branch(0x53179b7c,icon,True))
    patch(0x532b7cfc,0xebfff1ee,branch(0x532b7cfc,detail,True))
    return bytes(image),dict(schema='m10v-gr3-appended-slots/v2',base=base,bytes=len(image),
        tones=list(range(25,35)),stock_choices=12,shooting_choices='12+enabled_films',shooting_choices_max=22,
        library_index='14+enabled_films',movie_choices=10,raw_development_choices=12,
        entries=dict(count=count,index=index,position=position,maximum=maximum,display=display),
        exif_table=table,exif_bytes=88,patches=patches,
        playback=dict(icon=icon,detail=detail,metadata_decode=metadata_decode,icon_id=876,metadata_key=0x25,recorded_codes=[0x10c,0x115],identity="recorded-film-short-v1",identity_hooks=identity_hooks,identity_enabled=identity_enabled,
            recording=dict(builtin='0x1000+film_id',custom='0x2000+(film_id-79)*235+bank-21',custom_banks=[21,255],custom_codes=[0x2000,0xe0c5],si_tail_offset=0x74270,si_tail_bytes=16,pool_count=100,extra_pool_bytes=1600,source='immutable recipe snapshot; leased ShootingInfo only',filesystem_calls=0,legacy='unknown film icon; never current slot',mutable_legacy_custom='slot-only fallback')),
        stock_parameter_proxy=False,state_version=5,camera_tested=False)
