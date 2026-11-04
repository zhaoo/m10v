"""Install the native Grid Style choices and scoped still-view draw adapters."""
import struct

from scripts.build_gr3_menu_patches import branch

ROM = 0x53000000
HOOKS = (
    (0x5317681c, 0xe1a0c00d, "m10v_guides_hook_update", False),
    (0x53391b14, 0xe1a0c00d, "m10v_guides_hook_prepare", False),
    (0x53391be0, 0xeb000850, "m10v_guides_hook_paint", True),
    (0x5339c3b0, 0xe1a0c00d, "m10v_guides_hook_grid", False),
)
MENU = (
    (0x53b3dcc8, 0x531b3cac, "m10v_guides_camera_count"),
    (0x53b3dcd0, 0x531b5c74, "m10v_guides_camera_draw"),
    (0x53b3dcd8, 0x531b7604, "m10v_guides_camera_apply"),
    (0x53b3dce0, 0x531b8de8, "m10v_guides_camera_checked"),
    (0x53b365b8, 0x53198560, "m10v_guides_camera_summary"),
)
CAPTIONS = ["黄金分割", "黄金螺旋（左上）", "黄金螺旋（右上）", "黄金螺旋（左下）", "黄金螺旋（右下）"]


def build_guides_hooks(base, stock, symbols):
    def patch(address, expected, name, link=None):
        offset = address - ROM
        if offset + 4 > len(stock) or struct.unpack_from("<I", stock, offset)[0] != expected:
            raise ValueError(f"guide preimage differs at {address:#x}")
        target = symbols[name]
        if target < base or target & 3:
            raise ValueError(f"guide entry outside native module: {name}")
        replacement = target if link is None else branch(address, target, link)
        return dict(address=address, expected=expected, replacement=replacement, name=name)

    return dict(schema="m10v-gr3-guides/v1", owner_offset=0x6600,
                stock_styles=2, private_styles=5, first_caption=1181,
                patches=[patch(*row) for row in (*HOOKS, *MENU)])
