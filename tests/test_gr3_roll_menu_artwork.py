import hashlib
import json
import struct
import unittest
from pathlib import Path


class RollMenuArtworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = Path(__file__).resolve().parents[1] / "web" / "gr3"
        cls.donor = (directory / "MENU-R5.M10").read_bytes()
        cls.resource = (directory / "MENU-R8.M10").read_bytes()
        cls.manifest = json.loads((directory / "MENU-R8.json").read_text())
        catalog = json.loads((directory / "film-directory.json").read_text())
        cls.film_ids = [film["id"] for group in catalog["groups"] for film in group["films"]]

    def record(self, resource, index):
        start, checksum, x, y, width, height = struct.unpack_from(
            "<IIHHHH", resource, 16 + 16 * index
        )
        end = start + (1024 + width * height if index >= 512 else 4 * width * height)
        return start, end, checksum, (x, y, x + width, y + height)

    def test_mnu8_is_contiguous_and_fits_runtime_ram_and_file_limits(self):
        self.assertEqual(
            struct.unpack_from("<4sIII", self.resource), (b"MNU8", 8, 578, len(self.resource))
        )
        position = 16 + 578 * 16
        full_frames = {*range(15), *range(384, 390)}
        for index in range(578):
            start, end, checksum, box = self.record(self.resource, index)
            with self.subTest(record=index):
                if not start:
                    self.assertNotIn(index, full_frames | set(range(400, 415)) |
                                     set(range(421, 466)) | {478, 479, 480} | set(range(512, 578)))
                    self.assertEqual((end, checksum, *box), (0, 0, 0, 0, 0, 0))
                    continue
                self.assertEqual(position, start)
                self.assertGreater(end, start)
                position = end
                if index in full_frames:
                    self.assertEqual(box, (0, 0, 720, 480))
                else:
                    self.assertLessEqual(end - start, 48 * 1024)
                    self.assertLessEqual(box[2], 720)
                    self.assertLessEqual(box[3], 480)
        self.assertEqual(position, len(self.resource))
        self.assertLess(position, 32 * 1024 * 1024)
        self.assertEqual(self.manifest["sha256"], hashlib.sha256(self.resource).hexdigest())

    def test_canister_records_follow_the_catalog_and_carry_distinct_illustrations(self):
        payloads = set()
        for index, film in enumerate([*self.film_ids, 0x10016, 0], start=512):
            with self.subTest(record=index, film=film):
                start, end, checksum, box = self.record(self.resource, index)
                self.assertEqual(box, (0, 0, 144, 197))
                tile = self.resource[start:end]
                self.assertEqual(struct.unpack_from("<I", tile)[0], film)
                self.assertEqual(len(tile), 1024 + 144 * 197)
                self.assertIn(0, tile[1024:])  # Transparent corners.
                self.assertGreater(len(set(tile[1024:])), 10)
                self.assertNotIn(tile[4:], payloads)
                payloads.add(tile[4:])
                actual = 2166136261
                for pixel, in struct.iter_unpack("<I", tile):
                    actual = ((actual ^ pixel) * 16777619) & 0xffffffff
                self.assertEqual(actual, checksum)

    def test_non_effect_r5_records_are_byte_exact(self):
        unchanged = [*range(4), *range(8, 64), *range(256, 384)]
        for index in unchanged:
            old_start, old_end, old_hash, old_box = self.record(self.donor, index)
            start, end, checksum, box = self.record(self.resource, index)
            self.assertEqual((checksum, box), (old_hash, old_box), f"record {index}")
            self.assertEqual(
                self.resource[start:end], self.donor[old_start:old_end], f"record {index}"
            )

    def test_effect_half_and_ab_keep_their_reflowed_layout(self):
        for index, row in (
            (99, 4), (147, 5), (195, 4), (243, 5),  # Half
            (201, 6), (249, 7),  # A/B
        ):
            with self.subTest(record=index):
                start, _, _, (x, y, right, bottom) = self.record(self.resource, index)
                top = 86 + 46 * row
                self.assertGreater(start, 0)
                self.assertLessEqual(top, y)
                self.assertLessEqual(bottom, top + 46)
                self.assertLessEqual(390, x)
                self.assertLessEqual(right, 650)

    def test_live_status_and_picker_patches_respect_their_rows(self):
        for frame in range(4, 8):
            top = 86 + (6 if frame & 1 else 5) * 46
            for status in range(36, 40):
                index = 64 + (frame - 4) * 48 + status
                start, _, _, (x, y, right, bottom) = self.record(self.resource, index)
                self.assertGreater(start, 0)
                self.assertGreaterEqual(x, 390)
                self.assertLessEqual(right, 650)
                self.assertGreaterEqual(y, top)
                self.assertLessEqual(bottom, top + 46)
        for index in range(390, 398):
            start, _, _, (_, _, _, bottom) = self.record(self.resource, index)
            self.assertGreater(start, 0)
            self.assertLessEqual(bottom, 245)

    def test_dynamic_fields_stay_inside_their_real_controls(self):
        hit_rects = self.manifest["hit_rects_xyxy"]
        targets = {
            458: (262, 130, 466, 174), 459: (262, 130, 466, 176),
            **dict.fromkeys(range(460, 466), hit_rects["aspect"]),
            478: hit_rects["films"][1],
            480: hit_rects["footer"]["primary"],
        }
        for index, (x, y, right, bottom) in targets.items():
            with self.subTest(record=index):
                start, _, _, box = self.record(self.resource, index)
                self.assertGreater(start, 0)
                self.assertLessEqual(x, box[0])
                self.assertLessEqual(y, box[1])
                self.assertLessEqual(box[2], right)
                self.assertLessEqual(box[3], bottom)
