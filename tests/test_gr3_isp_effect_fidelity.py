"""Historical-look host model checks. Does not assert hardware pixel output."""
import unittest
import numpy as np
from scripts.analyze_gr3_isp_effect_fidelity import legacy_screen,candidate_model,native_pass_model
from scripts.build_gr3_isp_effect_textures import leak_mask
from scripts.build_gr3_isp_effect_render import leak_curves


class FidelityModelTests(unittest.TestCase):
    def test_zero_field_selects_identity_lower_endpoint_for_every_input_byte(self):
        # Stock A/C are upper curves; E/F are lower curves. The old audit
        # assumed the opposite blend polarity and never checked the deployed
        # lower endpoint itself. No hardware output is asserted here.
        for profile in leak_curves()[:9]:
            np.testing.assert_array_equal(profile[1],np.arange(256))

    def test_luma_gate_lower_endpoint_is_mask_and_upper_is_zero(self):
        upper,lower,weight=leak_curves()[9]
        self.assertEqual(upper,[0]*256)
        self.assertEqual(lower,list(range(256)))
        self.assertEqual(weight,list(range(256)))

    def test_inactive_interleaved_uv_byte_is_unchanged_after_both_real_passes(self):
        # Both Cb and Cr bytes traverse each curve. Inactive UV weight zero
        # must survive the other channel's pass for ALL input byte values.
        src=np.broadcast_to(np.arange(256,dtype=np.uint8)[:,None],(256,2)).copy()
        for strength in (1,2,3):
            cb,cr=leak_curves()[(strength-1)*3+1:strength*3]
            weights=np.tile(np.array([200,0],np.uint8),(256,1))
            out=native_pass_model(src,weights,cb)
            np.testing.assert_array_equal(out[:,1],src[:,1])
            weights[:]=[0,200];out=native_pass_model(src,weights,cr)
            np.testing.assert_array_equal(out[:,0],src[:,0])

    def test_single_side_support_is_exactly_unchanged_outside_historical_mask(self):
        rgb=np.full((128,256,3),96,np.uint8)
        for position in ('left','right'):
            for spread in ('narrow','medium','wide'):
                mask=leak_mask(256,128,position,spread)
                for strength in (1,2,3):
                    out=candidate_model(rgb,mask,strength)
                    np.testing.assert_array_equal(out[mask==0],rgb[mask==0])
                    self.assertGreater(np.abs(out.astype(int)-rgb).sum(),0)

    def test_r14_endpoint_order_reproduces_global_whitening_in_candidate_model(self):
        rgb=np.full((2,256,3),96,np.uint8);zero=np.zeros((2,256),np.uint8)
        out=candidate_model(rgb,zero,3,r14_endpoints=True)
        self.assertGreater(float(out.mean()),float(rgb.mean())+40)
        np.testing.assert_array_equal(candidate_model(rgb,zero,3),rgb)
    def test_neutral_ramp_fits_old_screen_and_preserves_white_all_strengths(self):
        rgb=np.broadcast_to(np.arange(256,dtype=np.uint8)[None,:,None],(256,256,3))
        masks=np.broadcast_to(np.arange(256,dtype=np.uint8)[:,None],(256,256))
        for strength,gain in enumerate((2,5,8),1):
            old=legacy_screen(rgb,masks,gain);new=candidate_model(rgb,masks,strength)
            self.assertLess(np.abs(old.astype(float)-new).mean(),1)
            self.assertLessEqual(np.abs(old.astype(int)-new).max(),4)
            self.assertTrue(np.all(new[:,255]==255))
            self.assertGreater(new[-1,0,0],new[-1,0,1])
            self.assertGreater(new[-1,0,1],new[-1,0,2])

    def test_zero_spatial_mask_leaves_every_neutral_level_unchanged(self):
        rgb=np.broadcast_to(np.arange(256,dtype=np.uint8)[None,:,None],(2,256,3))
        for strength in (1,2,3):
            np.testing.assert_array_equal(candidate_model(rgb,np.zeros((2,256),np.uint8),strength),rgb)
