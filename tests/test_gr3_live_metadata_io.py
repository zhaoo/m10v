"""Final runtime metadata reads; storage/device endpoints are boundaries."""
import struct
import unittest
import zlib
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests import test_gr3_film_pipeline_current as pipeline


class LiveMetadataIoTests(unittest.TestCase):
    setUpClass = classmethod(pipeline.CurrentFilmPipelineTests.setUpClass.__func__)
    fixture = pipeline.CurrentFilmPipelineTests.fixture
    publish_owner = pipeline.CurrentFilmPipelineTests.publish_owner
    call = pipeline.CurrentFilmPipelineTests.call

    def test_repeated_builtin_name_and_icon_refresh_never_reads_sd(self):
        e, *_, data = self.fixture(35)
        owner = self.publish_owner(e, data)
        storage = []
        def boundary(u, at, size, unused):
            if at == 0x53828014:
                storage.append(at); result = 0
            elif at == 0x5320ad88: result = 0x55006000
            elif at == 0x5320ba9c: result = 0x55068200
            else: return
            u.reg_write(A.UC_ARM_REG_R0, result)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, boundary)
        for _ in range(20):
            self.assertEqual(self.call(e, 'm10v_menu_name', 0, 25), 880)
            self.assertEqual(self.call(e, 'm10v_menu_icon', 0, 25), 705)
        self.assertEqual(storage, [])
        # A published change must immediately update both labels and icons.
        changed = bytearray(e.u.mem_read(data, 184))
        struct.pack_into('<H', changed, 12, 66)
        struct.pack_into('<I', changed, 8, 8)
        struct.pack_into('<I', changed, 180, zlib.crc32(changed[:180]))
        e.u.mem_write(owner + 0x2144, bytes(changed)); e.w32(owner + 0x2140, 4)
        self.assertEqual(self.call(e, 'm10v_menu_name', 0, 25), 911)
        self.assertEqual(self.call(e, 'm10v_menu_icon', 0, 25), 736)
        self.assertEqual(storage, [])


if __name__ == '__main__': unittest.main()
