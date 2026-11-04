"""Shared GR III 2.10/IIIx 1.60 native RAW chooser and request stamp."""
import hashlib
import struct

from scripts.build_gr3_menu_patches import assembly, branch

BASE = 0x53000000
IDENTITIES = {
    '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67',
    '0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6',
}
EXPORTS = tuple('m10v_raw_menu_' + key for key in (
    'init', 'model', 'destroy', 'clear', 'count', 'capacity', 'row', 'choose',
    'current', 'icon', 'name', 'remember', 'restore', 'request',
))
# Link replacements retain the stock caller ABI, including its stack args.
CALLS = (
    (0x5320b3c0, 0x5327b940, 'init', True),
    (0x5327ee7c, 0x5327ed08, 'clear', True),
    (0x5318a720, 0x53289304, 'choose', False),
    (0x531860a4, 0x532846c4, 'remember', True),
    (0x5318add4, 0x53289314, 'restore', True),
    (0x5318aaa8, 0x53283860, 'current', True),
    (0x53186768, 0x53283860, 'current', True),
    (0x531869b4, 0x53283860, 'current', True),
    (0x531869c8, 0x532891a8, 'icon', True),
    (0x5318a10c, 0x532891a8, 'icon', True),
    (0x53186778, 0x532891f4, 'name', True),
    (0x5318b460, 0x532891f4, 'name', True),
)
ENTRIES = (
    (0x5320ac20, 0xe30606e0, 'destroy'),
    (0x53283358, 0xe5d03005, 'count'),
    (0x532833bc, 0xe3a0000f, 'capacity'),
)


def build_raw_menu(base, stock, exports):
    if hashlib.sha256(stock).hexdigest() not in IDENTITIES:
        raise ValueError('RAW chooser requires an exact supported official RTOS')
    helpers = {name: exports[name] for name in EXPORTS}
    image = bytearray()
    patches = []
    shims = {}

    def target(key):
        return helpers['m10v_raw_menu_' + key]

    def patch(site, expected, address, link=False):
        if struct.unpack_from('<I', stock, site - BASE)[0] != expected:
            raise ValueError(f'RAW chooser preimage differs at {site:#x}')
        patches.append(dict(address=site, expected=expected, replacement=branch(site, address, link)))

    def thunk(key, site, expected, source, link=False):
        entry = base + len(image)
        image.extend(assembly(source, entry))
        patch(site, expected, entry, link)
        shims[key] = entry

    for site, old, key, link in CALLS:
        patch(site, branch(site, old, link), target(key), link)
    for site, expected, key in ENTRIES:
        patch(site, expected, target(key))

    # The existing guard is still responsible for publication and lifetime.
    thunk('model', 0x5320b39c, 0xe30606e0,
          f'bl {target("model"):#x};b 0x5320b3a4')

    # Preserve original table access and the exact first instruction on stock
    # rows. Extra values are only consumed by the audited chooser call sites.
    for key, site, expected, stock_op in (
        ('category', 0x532834d0, 0xe5d03005, 'ldrb r3,[r0,#5]'),
        ('value', 0x532834f0, 0xe1a0c00d, 'mov ip,sp'),
    ):
        result = 'mov r0,#0;' if key == 'category' else ''
        thunk(key, site, expected,
              f'push {{r0-r2,lr}};bl {target("row"):#x};cmp r0,#0;beq stock;'
              f'{result}add sp,sp,#12;pop {{pc}};'
              f'stock:;pop {{r0-r2,lr}};{stock_op};b {site+4:#x}')

    for key, site, save in (('preview', 0x53281978, 0), ('save', 0x532831e8, 1)):
        original = 0x5322b6e4
        thunk(key, site, branch(site, original, True),
              f'push {{r0-r4,lr}};mov r0,r2;mov r1,#{save};bl {target("request"):#x};'
              f'pop {{r0-r4,lr}};b {original:#x}', True)

    return bytes(image), dict(
        schema='m10v-gr3-raw-menu/v1', base=base, bytes=len(image), patches=patches,
        helpers=helpers, shims=shims, owner_bytes=0x3cc, stock_owner_bytes=0x3c4,
        request=dict(preview_offset=0x83c, save_offset=0x82c,
                     tag=0x4d520000, as_shot=0, stock=0xffff),
        native_styles=12, native_custom_sets=2, camera_tested=False,
    )
