"""Verify the original-file evidence required for GR III roll recovery."""
import ctypes as c
import os
import pathlib
import struct
import subprocess
import tempfile
import unittest
import zlib

from tests.test_gr3_roll_state import Record

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROLL_ID = bytes(range(1, 17))
Read = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_uint32, c.POINTER(c.c_uint8), c.c_uint32)


class Photo(c.Structure):
    _fields_ = [("context", c.c_void_p), ("bytes", c.c_uint32), ("read", Read)]


def fixture(jpeg, *, complete=True, good_tag=True):
    note = bytearray(b"RICOH\0II" + struct.pack("<H", 1))
    note.extend(struct.pack("<HHII", 0xc7f2, 7, 32, 24))
    note.extend(b"\0" * 2)
    marker = b"M10R" + ROLL_ID + struct.pack("<II", 7, 24)
    note.extend(marker + struct.pack("<I", zlib.crc32(marker) ^ (not good_tag)))
    tiff = bytearray(256 if complete else 215)

    def put(at, fmt, *fields):
        struct.pack_into("<" + fmt, tiff, at, *fields)

    tiff[:2] = b"II"
    put(2, "HI", 42, 8)
    if jpeg:
        put(8, "H", 1)
        put(10, "HHII", 0x8769, 4, 1, 32)
        put(32, "H", 1)
        put(34, "HHII", 0x927c, 7, len(note), 72)
    else:
        put(8, "H", 4)
        put(10, "HHII", 0x0106, 3, 1, 32803)
        put(22, "HHII", 0x0111, 4, 1, 200)
        put(34, "HHII", 0x0117, 4, 1, 32)
        put(46, "HHII", 0xc634, 1, len(note), 72)
    tiff[72:72 + len(note)] = note
    if not jpeg:
        return bytes(tiff)
    app1 = b"Exif\0\0" + tiff
    return (b"\xff\xd8\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 +
            b"\xff\xda\x00\x02" + (b"\xff\xd9" if complete else b"\x00\x00"))


class IndexedMarker(c.Structure):
    _fields_ = [("id", c.c_uint8 * 16), ("frame", c.c_uint32),
                ("target", c.c_uint32), ("film_code", c.c_uint32)]


class RollPhotoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory(prefix="m10v-photo-test-")
        cls.addClassCleanup(scratch.cleanup)
        out = pathlib.Path(scratch.name) / "photo.so"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared",
                        str(ROOT / "native/companion/roll_photo.c"), "-o", str(out)], check=True)
        cls.lib = c.CDLL(str(out))
        cls.lib.m10v_roll_photo_index.argtypes = [c.POINTER(Photo), c.POINTER(IndexedMarker)]
        cls.lib.m10v_live_photo_token.argtypes = [c.POINTER(Photo), c.POINTER(c.c_uint32)]
        cls.lib.m10v_roll_photo_frame.argtypes = [c.POINTER(Photo), c.c_int, c.POINTER(Record)]

    def frame(self, data, jpeg, roll_id=ROLL_ID):
        record = Record()
        record.id[:] = roll_id
        record.target = 24

        @Read
        def read(_context, offset, out, count):
            if offset + count > len(data):
                return 0
            c.memmove(out, bytes(data[offset:offset + count]), count)
            return 1

        photo = Photo(None, len(data), read)
        return self.lib.m10v_roll_photo_frame(c.byref(photo), jpeg, c.byref(record))

    def test_finished_jpeg_requires_marker_and_end_of_image(self):
        self.assertEqual(self.frame(fixture(True), True), 7)
        self.assertEqual(self.frame(fixture(True), True, b"z" * 16), 0)
        self.assertEqual(self.frame(fixture(True, complete=False), True), -1)

    def test_dng_requires_the_raw_extent_and_valid_marker(self):
        self.assertEqual(self.frame(fixture(False), False), 7)
        self.assertEqual(self.frame(fixture(False, complete=False), False), -1)
        self.assertEqual(self.frame(fixture(False, good_tag=False), False), -1)


    def test_archive_marker_requires_crc_completion_and_consistent_exif_identity(self):
        def detect(data):
            @Read
            def read(_context, offset, out, count):
                if offset + count > len(data): return 0
                c.memmove(out, bytes(data[offset:offset + count]), count)
                return 1
            photo = Photo(None, len(data), read)
            marker = IndexedMarker()
            return self.lib.m10v_roll_photo_index(c.byref(photo), c.byref(marker)), marker
        result, marker = detect(fixture(True))
        self.assertEqual((result, bytes(marker.id), marker.frame, marker.target), (7, ROLL_ID, 7, 24))
        zero = bytearray(fixture(True))
        zero[12 + 72 + 24:12 + 72 + 56] = bytes(32)
        self.assertEqual(detect(zero)[0], 0)
        self.assertEqual(detect(fixture(True, good_tag=False))[0], -1)
        self.assertEqual(detect(fixture(True, complete=False))[0], -1)
        # A second valid APP1 describing a different roll must not overwrite the first.
        other = bytearray(fixture(True))
        marker_at = 12 + 72 + 24
        other[marker_at + 4:marker_at + 20] = b'z' * 16
        struct.pack_into('<I', other, marker_at + 28, zlib.crc32(other[marker_at:marker_at + 28]))
        multiple = fixture(True)[:-6] + other[2:]
        self.assertEqual(detect(multiple)[0], -1)

    @unittest.skipUnless(os.environ.get("M10V_CAMERA_ROLL_PHOTO_DIR"),
                         "requires explicitly selected read-only R12 camera originals")
    def test_actual_r12_sd_has_valid_dng_frames_but_no_jpeg_roll_tags(self):
        directory = pathlib.Path(os.environ["M10V_CAMERA_ROLL_PHOTO_DIR"])
        raw = (directory.parent.parent / "M10VRL0.BIN").read_bytes()
        self.assertEqual(len(raw), 48)
        self.assertEqual(zlib.crc32(raw[:44]), int.from_bytes(raw[44:], "little"))
        roll = Record.from_buffer_copy(raw)
        self.assertEqual((roll.film, roll.target, roll.count, roll.status), (66, 36, 2, 3))
        expected = {"00004560": 0, "00004561": 0, "00004562": 1, "00004563": 2}
        for stem, frame in expected.items():
            for extension in ("JPG", "DNG"):
                path = directory / (stem + "." + extension)
                with path.open("rb") as source:
                    @Read
                    def read(_context, offset, out, count):
                        source.seek(offset)
                        data = source.read(count)
                        if len(data) != count: return 0
                        c.memmove(out, data, count)
                        return 1
                    photo = Photo(None, path.stat().st_size, read)
                    found = self.lib.m10v_roll_photo_frame(c.byref(photo), extension == "JPG", c.byref(roll))
                    self.assertEqual(found, frame if extension == "DNG" else 0, path.name)
                    if extension == "JPG":
                        marker = IndexedMarker()
                        self.assertEqual(self.lib.m10v_roll_photo_index(c.byref(photo), c.byref(marker)), 0)

    def test_live_token_is_independent_of_the_roll_marker(self):
        token = bytes(range(17, 33))
        version = struct.pack("<I", 1)
        roll = fixture(True)
        live = bytearray(roll)
        tag_at = 12 + 72 + 10
        struct.pack_into("<HHII", live, tag_at, 0xc7f3, 7, 24, 24)
        live[tag_at + 14:tag_at + 38] = b"M10L" + version + token

        def detect(data):
            words = (c.c_uint32 * 4)()

            @Read
            def read(_context, offset, out, count):
                if offset + count > len(data):
                    return 0
                c.memmove(out, bytes(data[offset:offset + count]), count)
                return 1

            photo = Photo(None, len(data), read)
            return self.lib.m10v_live_photo_token(c.byref(photo), words), bytes(words)

        self.assertEqual(detect(roll), (0, bytes(16)))
        self.assertEqual(detect(live), (1, token))
        self.assertEqual(detect(live[:-2] + b"\x00\x00")[0], -1)
        self.assertEqual(self.frame(live, True), 0)
