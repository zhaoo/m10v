"""GR III 2.10: use Standard ISP inputs for native still/LiveView carriers.

Only the local tone register is substituted. ShootingInfo (including its tone
and the large R2Y output areas) stays in place. Shared helpers require the exact
Still or LiveView object vtable; local-process requires its still-plan caller.
"""
import struct
from scripts.build_gr3_menu_patches import assembly

HOOKS = (
    (0x536db7f8, 0xe5d3277c, 2, 'ldr r0,[r0]', 'parameters'),
    (0x536dc26c, 0xe5d7277c, 2, 'ldr r0,[r6]', 'color_table'),
    (0x536dc4bc, 0xe5d7377c, 3, 'ldr r0,[r6]', 'color_flags'),
    (0x536dd3e0, 0xe5d7177c, 1, 'ldr r0,[r4,#-0x1e0]', 'curve'),
    (0x535131c0, 0xe5d1377c, 3, 'mov r0,lr', 'local_process'),
)
STILL_VTABLE = 0x53dbd8a0
LIVE_VTABLE = 0x53dbd938
STILL_PLAN_RETURN = 0x53513620


def build_isp_base(base,appended_slots=False,adj_preview=False):
    image = bytearray(); entries = {}; patches = []
    inventory=HOOKS
    if adj_preview:
        if not appended_slots:raise ValueError('ADJ preview requires appended slots')
        inventory+=((0x536dc998,0xe5d5c77c,12,'ldr r0,[r4]','live_cache_tone'),)
    for address, expected, result, object_load, name in inventory:
        entry = base + len(image); offset = 4 + (4 if result==12 else result) * 4
        compare = STILL_PLAN_RETURN if name == 'local_process' else STILL_VTABLE
        object_gate=f'{object_load};movw r1,#{compare&65535};movt r1,#{compare>>16};cmp r0,r1;'
        if name!='local_process':
            object_gate+=f'beq {"done" if name=="live_cache_tone" else "active"};movw r1,#{LIVE_VTABLE&65535};movt r1,#{LIVE_VTABLE>>16};cmp r0,r1;'
            if adj_preview:
                tuning={'parameters':'r0','color_table':'r6','color_flags':'r6',
                        'curve':'r4','live_cache_tone':'r4'}[name]
                # Use the actual tuning object, not the local register after
                # its vtable load. Curve uses a +0x1e0 biased binding.
                load={'parameters':'ldr r2,[sp,#4];ldr r2,[r2,#0x210]',
                      'curve':'ldr r2,[r4,#0x30]'}.get(name,f'ldr r2,[{tuning},#0x210]')
                object_gate+=f'bne done;{load};uxtb r2,r2;cmp r2,#0;strne r2,[sp,#{offset}];'
        if name=='live_cache_tone':
            object_gate+='done:;'
        else:
            object_gate+='bne done;active:;' if not adj_preview or name=='local_process' else 'active:;'
        # Save scratch registers AND condition/status flags. In particular the
        # curve load sits between CMP and MOVNE/MOVEQ in the stock function.
        tone_gate=(f'ldr r2,[sp,#{offset}];sub r2,r2,#25;cmp r2,#9;bhi done;nop;nop;' if appended_slots else f'ldr r2,[sp,#{offset}];cmp r2,#12;beq neutral;sub r2,r2,#18;cmp r2,#3;bhi done;')
        if name=='live_cache_tone':tone_gate=''
        neutral_tone=25 if appended_slots and name=='parameters' else 11
        code = assembly(
            'push {r0-r3,ip,lr};mrs ip,cpsr;push {ip};'
            f'.word {hex(expected)};str '+('ip' if result==12 else f'r{result}')+f',[sp,#{offset}];'
            +object_gate+
            (tone_gate+f'neutral:;mov r2,#{neutral_tone};str r2,[sp,#{offset}];' if tone_gate else '')+
            ('done:;' if tone_gate else '')+f'pop {{ip}};msr cpsr_fs,ip;pop {{r0-r3,ip,lr}};b {hex(address+4)}', entry)
        image += code
        entries[name] = entry
        patches.append({'address':address, 'expected':expected, 'entry':entry})
    if adj_preview:
        at=base+len(image)
        entries['live_refresh']=at
        # Stock resets the gamma dirty byte inside its parser. Reassert it
        # afterwards while displaying a candidate and once after cancellation.
        image.extend(assembly('push {r2,r3};mrs r2,cpsr;ldr r3,[r4,#0x210];cmp r3,#0;'
            'movne r3,#1;strbne r3,[r4,#0xe];msr cpsr_fs,r2;pop {r2,r3};'
            'ldrb r3,[r4,#0xb];b 0x536de134',at))
        patches.append({'address':0x536de130,'expected':0xe5d4300b,'entry':at})
        at=base+len(image)
        entries['live_ctor']=at
        image.extend(assembly('mov r3,#0;str r3,[r4,#0x210];.word 0xe89da818',at))
        patches.append({'address':0x536de408,'expected':0xe89da818,'entry':at})
        patches.append({'address':0x536f032c,'expected':0xe3a00e21,'replacement':0xe3000218})
    return bytes(image), {'schema':'m10v-gr3-isp-base/v3' if adj_preview else 'm10v-gr3-isp-base/v2', 'base':base,
                          'bytes':len(image), 'entries':entries, 'patches':patches,
                          'carriers':list(range(25,35)) if appended_slots else [12,18,19,20,21], 'base_tone':11,
                          'still_vtable':STILL_VTABLE, 'live_vtable':LIVE_VTABLE,
                          'live_view':'standard', 'still_plan_return':STILL_PLAN_RETURN}
