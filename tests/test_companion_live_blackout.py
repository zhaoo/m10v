"""Bounded real-frame blackout windows; R15 interior samples are interpolated."""
import ctypes as c
import struct
import unittest
from tests import test_companion_live_clip as clip_test
Clip, Write = clip_test.Clip, clip_test.Write

BlackoutClip = Clip

class LiveBlackoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clip_test.LiveClipTests.setUpClass.__func__(cls)
        for name in ('init','push','shutter','complete','write_clip'):
            function=getattr(cls.lib,'m10v_live_'+name)
            function.argtypes=[c.POINTER(BlackoutClip)]+function.argtypes[1:]

    def setUp(self):
        self.clip=BlackoutClip();self.storage=c.create_string_buffer(48*8)
        self.ptr=c.byref(self.clip)
        self.assertEqual(self.lib.m10v_live_init(self.ptr,self.storage,len(self.storage),8,192,128),1)

    def push(self,t):return self.lib.m10v_live_push(self.ptr,t,b'\xff\xd8\xff\xd9',4)
    def shutter(self,t,before=True):return self.lib.m10v_live_shutter(self.ptr,t,int(before))
    def complete(self,t):return self.lib.m10v_live_complete(self.ptr,t)
    def encoded(self):
        data=bytearray()
        @Write
        def write(ctx,at,n):data.extend(c.string_at(at,n));return 1
        self.assertEqual(self.lib.m10v_live_write_clip(self.ptr,write,None),1)
        return data

    def test_r15_measured_endpoints_keep_real_timestamps_with_interpolated_interior(self):
        for oldest,newest,event,resumed in ((0x486e,0x4e27,0x4fd4,0x5a28),(0x5a28,0x6003,0x613b,0x67e8)):
            with self.subTest(event=event):
                self.setUp()
                # Only these endpoints and count12 come from R15BOOT.
                times=[oldest+(newest-oldest)*i//11 for i in range(12)]
                for t in times:self.assertEqual(self.push(t),1)
                self.assertEqual(self.shutter(event),1)
                self.assertEqual(self.complete(event+1500),0)
                post=list(range(resumed,resumed+1500,100))
                for t in post:self.assertEqual(self.push(t),1)
                self.assertEqual(self.complete(resumed+1500),1)
                data=self.encoded();header=struct.unpack_from('<4sHHHHIII',data)
                self.assertEqual(header[5:7],(event-oldest,resumed+1500-oldest+1))
                actual=[struct.unpack_from('<I',data,24+i*12)[0] for i in range(header[2])]
                self.assertEqual(actual,[t-oldest for t in times+post])
                self.assertEqual(header[2],27)

    def test_precoverage_and_freshness_are_separate_from_capture_blackout(self):
        for span,gap,expected in ((1249,100,0),(1250,1500,1),(1500,1501,0)):
            with self.subTest(span=span,gap=gap):
                self.setUp();self.assertEqual(self.push(10000),1);self.assertEqual(self.push(10000+span),1)
                self.assertEqual(self.shutter(10000+span+gap),expected)

    def test_first_post_deadline_exact_boundary_and_after_only_pts(self):
        self.assertEqual(self.shutter(10000,False),1)
        self.assertEqual(self.push(15000),1)
        self.assertEqual(self.push(16400),1)
        self.assertEqual(self.complete(16499),0)
        self.assertEqual(self.complete(16500),1)
        data=self.encoded()
        self.assertEqual(struct.unpack_from('<III',data,12),(0,6501,0))
        self.assertEqual(struct.unpack_from('<I',data,24),(5000,))
        self.setUp();self.assertEqual(self.shutter(10000,False),1)
        self.assertEqual(self.push(15001),0);self.assertEqual(self.complete(16501),0)
        self.assertTrue(self.clip.failed)

    def test_no_post_one_post_stalled_post_and_duplicate_shutter_never_succeed(self):
        for posts in ((),(12000,),(12000,12100)):
            with self.subTest(posts=posts):
                self.setUp();self.assertEqual(self.shutter(10000,False),1)
                self.assertEqual(self.shutter(10001,False),0)
                for t in posts:self.assertEqual(self.push(t),1)
                self.assertEqual(self.complete(20000),0);self.assertTrue(self.clip.failed)

    def test_final_edge_boundary_is_not_relaxed(self):
        for final,expected in ((13250,1),(13249,0)):
            with self.subTest(final=final):
                self.setUp();self.assertEqual(self.shutter(10000,False),1)
                self.assertEqual(self.push(12000),1);self.assertEqual(self.push(final),1)
                self.assertEqual(self.complete(13500),expected)

    def test_maximum_valid_span_and_original_event_are_bounded(self):
        self.assertEqual(self.push(10000),1)
        self.assertEqual(self.push(11500),1)
        self.assertEqual(self.shutter(13000),1)
        self.assertEqual(self.push(18000),1)
        self.assertEqual(self.push(19400),1)
        self.assertEqual(self.complete(19500),1)
        data=self.encoded()
        self.assertEqual(struct.unpack_from('<III',data,12),(3000,9501,0))
        self.assertLessEqual(len(data),24+48*12)
        self.assertEqual(struct.unpack_from('<I',data,24+2*12),(8000,))

    def test_future_preframe_and_timestamp_overflow_remain_rejected(self):
        self.assertEqual(self.push(11000),1)
        self.assertEqual(self.shutter(10000),0)
        self.assertEqual(self.clip.rejection,5)
        self.setUp()
        self.assertEqual(self.shutter(0xffffffffffffffff-6499,False),0)
        self.assertEqual(self.clip.rejection,2)

    def test_ring_capacity_and_invalid_frames_do_not_create_motion(self):
        self.assertEqual(self.shutter(10000,False),1)
        self.assertEqual(self.lib.m10v_live_push(self.ptr,11000,b'bad!',4),0)
        self.assertEqual(self.clip.post_start,0xffffffffffffffff)
        # Make a complete ring of valid prehistory, then enforce capacity.
        self.clip.count=48;self.clip.frames[47].time=10000
        self.clip.post_start=10000;self.clip.end=11500
        self.assertEqual(self.push(10100),0);self.assertTrue(self.clip.failed)

if __name__=='__main__':unittest.main()
