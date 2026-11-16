import hashlib
import struct
import unittest
from pathlib import Path


class MenuArtworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        asset = Path(__file__).resolve().parents[1] / "web/gr3/MENU-R5.M10"
        cls.data = asset.read_bytes()

    def record(self, index):
        offset, digest, x, y, width, height = struct.unpack_from(
            "<IIHHHH", self.data, 16 + 16 * index
        )
        return offset, digest, (x, y, width, height)

    def test_versioned_directory_and_runtime_patch_budget(self):
        self.assertEqual(
            struct.unpack_from("<4sIII", self.data), (b"MNU5", 5, 384, len(self.data))
        )
        end = 16 + 16 * 384
        for index in range(384):
            offset, digest, box = self.record(index)
            with self.subTest(record=index):
                x, y, width, height = box
                if offset == 0:
                    self.assertGreaterEqual(index, 15)
                    self.assertEqual((digest, *box), (0, 0, 0, 0, 0))
                    continue
                self.assertEqual(offset, end)
                length = width * height * 4
                self.assertGreater(length, 0)
                if index < 15:
                    self.assertEqual(box, (0, 0, 720, 480))
                else:
                    self.assertLessEqual(length, 48 * 1024)
                    self.assertLessEqual(x + width, 720)
                    self.assertLessEqual(y + height, 480)
                end += length
        self.assertEqual(end, len(self.data))
        self.assertLess(end, 32 * 1024 * 1024)

    def test_about_and_payment_frames_preserve_r4_pixels(self):
        for index, expected in (
            (10, "65deb6108f981e4e1b125cb6845c8b21309646860bf24c0f9c066faf7bb80031"),
            (12, "f6b7f227e27e6470454fcd71e6f420b12ada1c4a724a04d0a05216413b4b91c2"),
        ):
            offset, _, (_, _, width, height) = self.record(index)
            self.assertEqual(
                hashlib.sha256(self.data[offset:offset + width * height * 4]).hexdigest(),
                expected,
            )

    def test_half_status_patch_stays_on_its_visible_row(self):
        # Effects 4 and 6 omit torn paper, which moves Half up one row.
        for index, top in ((99, 298), (147, 351), (195, 298), (243, 351)):
            with self.subTest(record=index):
                offset, _, (x, y, width, height) = self.record(index)
                self.assertGreater(offset, 0)
                self.assertGreaterEqual(x, 390)
                self.assertLessEqual(x + width, 650)
                self.assertGreaterEqual(y, top)
                self.assertLessEqual(y + height, top + 53)
