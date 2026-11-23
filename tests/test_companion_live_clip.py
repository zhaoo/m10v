"""Native Live clip ownership, shutter windows and M10L transfer contract."""
import ctypes as c
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FRAME = bytes.fromhex("ffd8ffd9")


class Frame(c.Structure):
    _fields_ = [("time", c.c_uint64), ("bytes", c.c_uint32)]


class Clip(c.Structure):
    _fields_ = [
        ("storage", c.c_void_p), ("stride", c.c_uint32),
        ("width", c.c_uint16), ("height", c.c_uint16),
        ("head", c.c_uint32), ("count", c.c_uint32),
        ("shutter", c.c_uint64), ("end", c.c_uint64),
        ("pending", c.c_uint8), ("complete", c.c_uint8), ("failed", c.c_uint8),
        ("frames", Frame * 48), ("nv12", c.c_uint8),
        ("post_start", c.c_uint64), ("rejection", c.c_uint32),
    ]


Write = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_void_p, c.c_uint32)


class LiveClipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        library = Path(scratch.name) / "live.so"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
            str(ROOT / "native/companion/live_clip.c"), "-o", str(library),
        ], check=True)
        cls.lib = c.CDLL(str(library))
        ptr = c.POINTER(Clip)
        cls.lib.m10v_live_init.argtypes = [ptr, c.c_void_p, c.c_uint32, c.c_uint32, c.c_uint16, c.c_uint16]
        cls.lib.m10v_live_init_nv12.argtypes = [ptr, c.c_void_p, c.c_uint32, c.c_uint16, c.c_uint16]
        cls.lib.m10v_live_push.argtypes = [ptr, c.c_uint64, c.c_void_p, c.c_uint32]
        cls.lib.m10v_live_shutter.argtypes = [ptr, c.c_uint64, c.c_int]
        cls.lib.m10v_live_complete.argtypes = [ptr, c.c_uint64]
        cls.lib.m10v_live_write_clip.argtypes = [ptr, Write, c.c_void_p]

    def setUp(self):
        self.clip = Clip()
        self.storage = c.create_string_buffer(48 * 8)
        self.ptr = c.byref(self.clip)
        self.assertEqual(self.lib.m10v_live_init(self.ptr, self.storage, len(self.storage), 8, 384, 256), 1)

    def push(self, time, jpeg=FRAME):
        return self.lib.m10v_live_push(self.ptr, time, jpeg, len(jpeg))

    def encode(self, succeed=True):
        data = bytearray()

        @Write
        def append(_context, ptr, length):
            if not succeed:
                return 0
            data.extend(c.string_at(ptr, length))
            return 1

        outcome = self.lib.m10v_live_write_clip(self.ptr, append, None)
        return outcome, data

    def test_shutter_has_owned_before_and_after_frames(self):
        for t in range(10000, 11900, 100):
            source = c.create_string_buffer(FRAME)
            self.assertEqual(self.lib.m10v_live_push(self.ptr, t, source, len(FRAME)), 1)
            source[0] = b"\0"  # Native producer is free to reuse its buffer.
        self.assertEqual(self.lib.m10v_live_shutter(self.ptr, 11900, 1), 1)
        self.assertEqual(self.lib.m10v_live_shutter(self.ptr, 12000, 1), 0)
        for t in range(11900, 13500, 100):
            self.assertEqual(self.push(t), 1)
        self.assertEqual(self.lib.m10v_live_complete(self.ptr, 13399), 0)
        self.assertEqual(self.lib.m10v_live_complete(self.ptr, 13400), 1)
        success, data = self.encode()
        self.assertEqual(success, 1)
        self.assertEqual(struct.unpack_from("<4sHHHHIII", data),
                         (b"M10L", 1, 32, 384, 256, 1600, 3101, 0))
        for i in range(32):
            offset = 24 + i * 12
            self.assertEqual(struct.unpack_from("<II", data, offset), (i * 100, 4))
            self.assertEqual(data[offset + 8:offset + 12], FRAME)
        self.assertEqual(len(data), 24 + 32 * 12)

    def test_short_preview_and_stalled_post_capture_never_make_a_clip(self):
        self.assertEqual(self.push(100), 1)
        self.assertEqual(self.lib.m10v_live_shutter(self.ptr, 200, 1), 0)
        self.assertEqual(self.lib.m10v_live_shutter(self.ptr, 200, 0), 1)
        self.assertEqual(self.push(200), 1)
        self.assertEqual(self.push(199), 0)
        self.assertEqual(self.push(250), 0)
        self.assertEqual(self.push(300, b"bad!"), 0)
        self.assertEqual(self.push(300), 1)
        self.assertEqual(self.lib.m10v_live_complete(self.ptr, 1700), 0)
        self.assertEqual(self.encode(), (0, b""))

    def test_after_only_marks_first_frame_and_surfaces_writer_failure(self):
        self.assertEqual(self.lib.m10v_live_shutter(self.ptr, 2000, 0), 1)
        for t in range(2050, 3500, 100):
            self.assertEqual(self.push(t), 1)
        self.assertEqual(self.push(3551), 0)
        self.assertEqual(self.lib.m10v_live_complete(self.ptr, 3550), 1)
        self.assertEqual(self.encode(False), (0, b""))
        success, data = self.encode()
        self.assertEqual(success, 1)
        self.assertEqual(struct.unpack_from("<III", data, 12), (0, 1551, 0))


    def test_native_nv12_window_serializes_without_a_boundary_frame(self):
        raw = bytes([42]) * (192 * 128) + bytes([128]) * (192 * 64)
        storage = c.create_string_buffer(48 * len(raw))
        self.assertEqual(self.lib.m10v_live_init_nv12(self.ptr, storage, len(storage), 192, 128), 1)
        self.assertEqual(self.lib.m10v_live_shutter(self.ptr, 2000, 0), 1)
        self.assertEqual(self.push(2040, raw[:-1]), 0)
        for tick in range(2060, 3500, 90):
            self.assertEqual(self.push(tick, raw), 1)
        self.assertEqual(self.lib.m10v_live_complete(self.ptr, 3580), 1)
        success, data = self.encode()
        self.assertEqual(success, 1)
        self.assertEqual(struct.unpack_from("<4sHHHHIII", data),
                         (b"M10L", 2, 16, 192, 128, 0, 1561, 1))
        self.assertEqual(struct.unpack_from("<II", data, 24), (60, len(raw)))
        self.assertEqual(data[32:32 + len(raw)], raw)
