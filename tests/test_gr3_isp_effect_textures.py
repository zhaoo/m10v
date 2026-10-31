"""Build-host resources only; these tests make no hardware claims."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zlib
import ctypes
import subprocess

import numpy as np

from scripts import build_gr3_isp_effect_textures as textures


class TextureTests(unittest.TestCase):
    def test_grain_is_centered_correlated_and_seeded(self):
        a = textures.grain_plane(256, 192, seed=123)
        self.assertEqual(a.shape, (192, 256))
        self.assertEqual(a.dtype, np.uint8)
        self.assertLess(abs(float(a.mean()) - 128), .05)
        self.assertGreater(float(a.std()), 12)
        self.assertLess(float(a.std()), 22)
        self.assertGreater(np.corrcoef(a[:, :-1].ravel(), a[:, 1:].ravel())[0, 1], .35)
        np.testing.assert_array_equal(a, textures.grain_plane(256, 192, seed=123))
        self.assertFalse(np.array_equal(a, textures.grain_plane(256, 192, seed=124)))

    def test_leak_masks_are_smooth_and_spread_is_ordered(self):
        masks = [textures.leak_mask(128, 96, position='left', spread=s) for s in ('narrow', 'medium', 'wide')]
        self.assertLess(masks[0].sum(), masks[1].sum())
        self.assertLess(masks[1].sum(), masks[2].sum())
        for a in masks:
            self.assertGreater(a[:, 0].mean(), a[:, -1].mean())
            self.assertLessEqual(np.abs(np.diff(a.astype(int), axis=1)).max(), 22)
            self.assertLessEqual(np.abs(np.diff(a.astype(int), axis=0)).max(), 11)
        right=textures.leak_mask(128,96,position='right',spread='medium')
        self.assertGreater(right[:,-1].mean(),right[:,0].mean())
        both = textures.leak_mask(128, 96, position='both', spread='medium')
        self.assertTrue(np.all(both>=masks[1]));self.assertTrue(np.all(both>=right))

    def test_legacy_masks_against_compiled_unmodified_historical_c(self):
        source=subprocess.check_output(['git','show',textures.LEGACY_LEAK_COMMIT+':native/gr3/film_5207.c'],text=True)
        def function(name):
            start=source.index('static '+('int' if name=='noise' else 'uint32_t')+' '+name+'(')
            begin=source.index('{',start);depth=1;end=begin+1
            while depth:
                depth+=(source[end]=='{')-(source[end]=='}');end+=1
            return source[start:end]
        code='#include <stdint.h>\ntypedef struct {uint32_t leak_gain,leak_position,leak_spread;} m10v_film_effects;\n'
        code+='\n'.join(function(n) for n in ('random32','noise','leak'))
        code+='\nuint32_t reference(uint32_t x,uint32_t y,uint32_t p,uint32_t s){m10v_film_effects e={8,p,s};return leak(x,y,&e,0x5207250d);}'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'reference.c').write_text(code)
            subprocess.run(['clang','-shared','-O2',str(p/'reference.c'),'-o',str(p/'reference.so')],check=True,capture_output=True)
            ref=ctypes.CDLL(str(p/'reference.so')).reference;ref.argtypes=[ctypes.c_uint32]*4;ref.restype=ctypes.c_uint32
            for w,h in ((256,128),(66,48)):
                for position,index in (('left',0),('right',1)):
                    for spread,oldspread in textures.LEGACY_SPREADS.items():
                        actual=textures.leak_mask(w,h,position,spread)
                        expected=np.array([[ref((x*((256<<16)//w))>>16,(y*((256<<16)//h))>>16,index,oldspread)
                            for x in range(w)] for y in range(h)],dtype=np.uint8)
                        np.testing.assert_array_equal(actual,expected)

    def test_raw_bundle_lengths_neutral_chroma_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / 'effects'
            manifest_path, blob_path = textures.build_resources(prefix, width=130, height=96, leak_width=64, leak_height=48, seed=45)
            manifest = textures.verify_resources(manifest_path)
            data = blob_path.read_bytes()
            self.assertEqual(manifest['parameters']['seed'], 45)
            self.assertEqual(len(manifest['assets']), 65)
            # Grain resources are independent of this leak fidelity revision.
            self.assertEqual(data[:18432],textures._pack_y8(textures.grain_plane(130,96,45))[0])
            for asset in manifest['assets']:
                raw = data[asset['offset']:asset['offset'] + asset['length']]
                self.assertEqual(hashlib.sha256(raw).hexdigest(), asset['sha256'])
                self.assertEqual(asset['offset'] % 64, 0)
                self.assertEqual(asset['stride'] % 64, 0)
                if asset['format'] == 'NV12':
                    self.assertEqual(len(raw), asset['stride'] * asset['height'] * 3 // 2)
                if asset['name'] == 'grain_nv12':
                    self.assertEqual(set(raw[asset['stride'] * asset['height']:]), {128})
            before = data
            textures.build_resources(prefix, width=130, height=96, leak_width=64, leak_height=48, seed=45)
            self.assertEqual(before, blob_path.read_bytes())
            data = bytearray(data)
            data[0] ^= 1
            blob_path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'hash|checksum'):
                textures.verify_resources(manifest_path)
            blob_path.write_bytes(before)
            manifest['assets'][0]['crc32'] = '00000000'
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                textures.verify_resources(manifest_path)

    def test_rejects_invalid_geometry_and_parameters(self):
        for w, h in ((0, 2), (3, 2), (3074, 2048), (-2, 4), (2.5, 4)):
            with self.subTest(w=w, h=h), self.assertRaises(ValueError):
                textures.grain_plane(w, h)
        with self.assertRaises(ValueError):
            textures.leak_mask(32, 32, position='top')
        with self.assertRaises(ValueError):
            textures.leak_mask(32, 32, spread='huge')

    def test_manifest_rejects_forged_geometry_planes_and_asset_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = textures.build_resources(Path(directory) / 'effects', width=32, height=32, leak_width=16, leak_height=16)
            original = json.loads(path.read_text())
            for field, value in (('offset', 1), ('length', 1), ('stride', 1),
                                 ('width', 33), ('sha256', '0' * 64),
                                 ('planes', [{'offset': 0, 'length': 1, 'stride': 64}])):
                with self.subTest(field=field):
                    manifest = json.loads(json.dumps(original))
                    manifest['assets'][0][field] = value
                    path.write_text(json.dumps(manifest))
                    with self.assertRaises(ValueError):
                        textures.verify_resources(path)

    def test_grain_y8_and_nv12_luma_match_and_padding_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path, blob_path = textures.build_resources(Path(directory) / 'effects', width=66, height=32, leak_width=16, leak_height=16)
            manifest = textures.verify_resources(path)
            data = blob_path.read_bytes()
            y8, nv12 = manifest['assets'][:2]
            plane = data[y8['offset']:y8['offset'] + y8['length']]
            self.assertEqual(plane, data[nv12['offset']:nv12['offset'] + y8['length']])
            self.assertEqual(set(np.frombuffer(plane, dtype=np.uint8).reshape(32, 128)[:, 66:].ravel()), {0})

    def test_selective_modulation_has_identical_y_masks_and_zero_other_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            path, blob = textures.build_resources(Path(directory)/'effects', width=32, height=32, leak_width=66, leak_height=48)
            manifest = textures.verify_resources(path)
            assets = {a['name']:a for a in manifest['assets']}
            data = blob.read_bytes()
            for position in ('left','right','both'):
                for spread in ('narrow','medium','wide'):
                    name = f'leak_{position}_{spread}'
                    mask = textures.leak_mask(66,48,position,spread)
                    low = np.rint(mask.astype(float).reshape(24,2,33,2).mean(axis=(1,3))).astype(np.uint8)
                    ys=[]
                    for index, channel in enumerate(('cb','cr')):
                        a=assets[name+f'_{channel}_field_nv12']
                        self.assertEqual(a['format'],f'NV12_MODULATION_Y_{channel.upper()}')
                        raw=data[a['offset']:a['offset']+a['length']]
                        y=np.frombuffer(raw[:a['stride']*48],dtype=np.uint8).reshape(48,a['stride'])
                        uv=np.frombuffer(raw[a['stride']*48:],dtype=np.uint8).reshape(24,a['stride'])
                        np.testing.assert_array_equal(y[:,:66],mask)
                        np.testing.assert_array_equal(uv[:,index:66:2],low)
                        self.assertFalse(uv[:,1-index:66:2].any())
                        self.assertFalse(uv[:,66:].any())
                        self.assertFalse(y[:,66:].any())
                        self.assertFalse(uv[:,index:66:2][low==0].any())
                        ys.append(y)
                    np.testing.assert_array_equal(*ys)

    def test_portrait_fields_rotate_scalar_masks_on_host_then_repack_channel_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            path,blob=textures.build_resources(Path(directory)/'orientation',width=64,height=48,leak_width=256,leak_height=128)
            m=textures.verify_resources(path);assets={a['name']:a for a in m['assets']};data=blob.read_bytes()
            for position in ('left','right','both'):
                for spread in ('narrow','medium','wide'):
                    horizontal=textures.leak_mask(256,128,position,spread)
                    expected=np.rot90(horizontal,k=-1)
                    for channel,index in (('cb',0),('cr',1)):
                        a=assets[f'leak_{position}_{spread}_{channel}_field_vertical_nv12']
                        self.assertEqual((a['width'],a['height'],a['stride']),(128,256,128))
                        raw=data[a['offset']:a['offset']+a['length']]
                        y=np.frombuffer(raw[:32768],np.uint8).reshape(256,128);uv=np.frombuffer(raw[32768:],np.uint8).reshape(128,128)
                        np.testing.assert_array_equal(y,expected)
                        low=np.rint(expected.astype(float).reshape(128,2,64,2).mean(axis=(1,3))).astype(np.uint8)
                        np.testing.assert_array_equal(uv[:,index::2],low);self.assertFalse(uv[:,1-index::2].any())
                    if position=='left':self.assertGreater(expected[0].mean(),expected[-1].mean())
                    if position=='right':self.assertLess(expected[0].mean(),expected[-1].mean())

    def test_runtime_pack_selects_only37_resources_and_preserves_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path, blob = textures.build_resources(Path(directory)/'effects', seed=20261031)
            packed, packed_blob = textures.pack_runtime_resources(path,Path(directory)/'runtime')
            source=textures.verify_resources(path);manifest=textures.verify_resources(packed)
            self.assertEqual(len(manifest['assets']),37)
            self.assertLessEqual(packed_blob.stat().st_size,0xc00000)
            self.assertEqual(manifest['source_manifest_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(manifest['source_blob_sha256'],source['blob_sha256'])
            originals={a['name']:a for a in source['assets']}
            original=blob.read_bytes();data=packed_blob.read_bytes()
            for a in manifest['assets']:
                old=originals[a['name']]
                self.assertEqual({k:v for k,v in a.items() if k!='offset'}, {k:v for k,v in old.items() if k!='offset'})
                self.assertEqual(data[a['offset']:a['offset']+a['length']],original[old['offset']:old['offset']+old['length']])
            self.assertEqual(manifest['assets'][0]['name'],'grain_nv12')
            self.assertTrue(all(('_field_nv12' in a['name'] or '_field_vertical_nv12' in a['name']) for a in manifest['assets'][1:]))

    def test_modulation_format_forgery_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path,_=textures.build_resources(Path(directory)/'effects',width=32,height=32,leak_width=16,leak_height=16)
            manifest=json.loads(path.read_text())
            asset=next(a for a in manifest['assets'] if a['name'].endswith('_cb_field_nv12'))
            for fmt in ('NV12','NV12_MODULATION_Y_CR','NV12_INVALID'):
                asset['format']=fmt;path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):textures.verify_resources(path)

    def test_wrong_modulation_channel_rejected_even_with_recomputed_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            path,blob=textures.build_resources(Path(directory)/'effects',width=32,height=32,leak_width=16,leak_height=16)
            manifest=json.loads(path.read_text());data=bytearray(blob.read_bytes())
            asset=next(a for a in manifest['assets'] if a['name'].endswith('_cb_field_nv12'))
            data[asset['offset']+asset['stride']*asset['height']+1]=128
            raw=data[asset['offset']:asset['offset']+asset['length']]
            asset['sha256']=hashlib.sha256(raw).hexdigest();asset['crc32']=f'{zlib.crc32(raw):08x}'
            manifest['blob_sha256']=hashlib.sha256(data).hexdigest()
            blob.write_bytes(data);path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'modulation'):textures.verify_resources(path)

    def test_runtime_pack_rejects_incomplete_sets_and_source_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path,_=textures.build_resources(Path(directory)/'effects',width=32,height=32,leak_width=16,leak_height=16)
            with self.assertRaisesRegex(ValueError,'overwrite'):
                textures.pack_runtime_resources(path,path.with_suffix(''))
            packed,_=textures.pack_runtime_resources(path,Path(directory)/'runtime')
            manifest=json.loads(packed.read_text());manifest['assets'].pop()
            packed.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'resource set'):textures.verify_resources(packed)


if __name__ == '__main__':
    unittest.main()
