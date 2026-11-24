"""Keep the immutable crop module inside its original 8 KiB allocation."""
import os
import struct
from unittest.mock import patch
import unittest
from scripts import gr3_aspect_overlay as overlay


def elf_storage(address=overlay.MODULE, size=4, flags=2, kind=1):
    data=bytearray(52)
    data[:7]=b'\x7fELF\x01\x01\x01'
    payload=len(data)
    data.extend(bytes(size))
    names=b'\0.test\0.shstrtab\0'
    names_offset=len(data)
    data.extend(names)
    data.extend(bytes(-len(data)&3))
    table=len(data)
    rows=[(0,)*10,(1,kind,flags,address,payload,size,0,0,4,0),
          (7,3,0,0,names_offset,len(names),0,0,1,0)]
    for row in rows:data.extend(struct.pack('<10I',*row))
    struct.pack_into('<I',data,32,table)
    struct.pack_into('<HHH',data,46,40,len(rows),2)
    return bytes(data)


class AspectModuleStorage(unittest.TestCase):
    def test_original_exact_eight_kib_readonly_boundary_is_allowed(self):
        code,symbols=overlay.elf_image(elf_storage(size=0x2000))
        self.assertEqual(len(code),0x2000)
        self.assertEqual(symbols,{})
        self.assertEqual(overlay.END-overlay.MODULE,0x2000)

    def test_overflow_is_rejected_with_section_and_exact_range(self):
        with self.assertRaisesRegex(ValueError,r'\.test type=1 flags=0x2 range=0x540bdffc\.\.0x540be004'):
            overlay.elf_image(elf_storage(overlay.END-4,8))

    def test_later_writable_section_prevents_size_only_retry(self):
        data=bytearray(elf_storage(overlay.END-4,8))
        data.extend(struct.pack('<10I',1,1,3,overlay.MODULE,52,4,0,0,4,0))
        struct.pack_into('<H',data,48,4)
        with self.assertRaises(ValueError) as raised:
            overlay.elf_image(bytes(data))
        self.assertNotIsInstance(raised.exception,overlay.CropModuleOverflow)
        self.assertIn('flags=0x3',str(raised.exception))

    def test_writable_and_unbacked_storage_remain_rejected(self):
        with self.assertRaisesRegex(ValueError,r'type=1 flags=0x3'):
            overlay.elf_image(elf_storage(flags=3))
        with self.assertRaisesRegex(ValueError,r'type=8 flags=0x2'):
            overlay.elf_image(elf_storage(kind=8))


class AspectModuleRetry(unittest.TestCase):
    def test_size_only_overflow_recompiles_all_sources_with_oz(self):
        original=overlay.subprocess.run
        with patch.object(overlay.subprocess,'run',wraps=original) as commands, \
             patch.object(overlay,'elf_image',side_effect=[overlay.CropModuleOverflow('readonly overflow'),(b'ok',{})]):
            self.assertEqual(overlay.build_module(),(b'ok',{}))
        compiles=[call.args[0] for call in commands.call_args_list if '-c' in call.args[0]]
        self.assertEqual(len(compiles),2*len(overlay.SOURCES))
        self.assertTrue(all('-Os' in command and '-Oz' not in command for command in compiles[:3]))
        self.assertTrue(all('-Oz' in command and '-Os' not in command for command in compiles[3:]))

    def test_writable_or_other_storage_failure_does_not_retry(self):
        original=overlay.subprocess.run
        with patch.object(overlay.subprocess,'run',wraps=original) as commands, \
             patch.object(overlay,'elf_image',side_effect=ValueError('writable storage')):
            with self.assertRaisesRegex(ValueError,'writable storage'):
                overlay.build_module()
        compiles=[call.args[0] for call in commands.call_args_list if '-c' in call.args[0]]
        self.assertEqual(len(compiles),len(overlay.SOURCES))
        self.assertTrue(all('-Oz' not in command for command in compiles))


class AspectOptimizationEquivalence(unittest.TestCase):
    def test_os_and_oz_preserve_native_lcd_and_capture_contracts(self):
        if not os.environ.get('M10V_MENU_HUB_CANDIDATE'):
            self.skipTest('accepted final candidate required for retained native LCD hooks')
        from tests.test_gr3_aspect_preview import NativeAspectPreview
        NativeAspectPreview.setUpClass()
        methods=('test_adj_background_publishes_native_cropped_viewport_without_grid_layer',
                 'test_liveview_grid_uses_immediate_selection_before_capture_model_catches_up')
        for optimization in ('-Os','-Oz'):
            with self.subTest(optimization=optimization):
                flags=[optimization if flag in ('-Os','-Oz') else flag for flag in overlay.FLAGS]
                with patch.object(overlay,'FLAGS',flags),patch.dict(os.environ,{'M10V_PREVIEW_SOURCE':'1'}):
                    code,_=overlay.build_module()
                    self.assertLessEqual(len(code),0x2000)
                    suite=unittest.TestSuite(NativeAspectPreview(method) for method in methods)
                    result=unittest.TestResult()
                    suite.run(result)
                    self.assertTrue(result.wasSuccessful(),str(result.failures+result.errors))
                    self.assertEqual(result.testsRun,2)
