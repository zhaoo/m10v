"""Standalone runtime installation plan; no firmware/device activation."""
import hashlib
import importlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
EXTERNALS={name:0x540c0000+0x100*i for i,name in enumerate((
    'm10v_border_shot_read','m10v_border_shot_orientation','m10v_border_shot_phase',
    'm10v_border_shot_transition','m10v_capture_library','m10v_save_trace_recipe_mark'))}


def target(at,word):
    offset=(word&0xffffff)<<2
    if offset&(1<<25):offset-=1<<26
    return (at+8+offset)&0xffffffff


class BorderRuntimeBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache={}
        cls.roms={m:(ROOT/p).read_bytes() for m,p in (
            ('gr3','builds/gr3-extension-validation/official-rtos.bin'),
            ('gr3x','builds/gr3-border-iip-20261027/gr3x-official-rtos.bin'))}

    def builder(self):
        self.assertTrue((ROOT/'scripts/build_gr3_border_runtime.py').exists(),
                        'standalone border runtime builder has not been implemented')
        return importlib.import_module('scripts.build_gr3_border_runtime')

    def built(self,model='gr3',base=0x54160000):
        key=(model,base)
        if key not in self.cache:
            self.cache[key]=self.builder().build(base,self.roms[model],EXTERNALS,camera_model=model,enabled=True)
        return self.cache[key]

    def test_default_off_does_not_compile_touch_files_or_require_runtime_inputs(self):
        builder=self.builder()
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'unused'
            with (patch.object(builder.guard,'build',side_effect=AssertionError('OFF called guard builder')),
                  patch.object(builder.subprocess,'run',side_effect=AssertionError('OFF compiled'))):
                code,report=builder.build(stock=object(),externals=None,out_dir=out)
            self.assertEqual(code,b'');self.assertFalse(report['enabled'])
            self.assertEqual(report['patches'],[]);self.assertEqual(report['symbols'],{})
            self.assertFalse(out.exists())

    def test_both_models_compile_exact_twenty_patch_plan_and_readback(self):
        builder=self.builder()
        for model in self.roms:
            code,report=self.built(model)
            self.assertEqual(report['code_sha256'],hashlib.sha256(code).hexdigest())
            self.assertEqual(report['code_bytes'],len(code))
            self.assertEqual(report['original_rtos_sha256'],hashlib.sha256(self.roms[model]).hexdigest())
            self.assertEqual(len(report['patches']),20)
            self.assertEqual(len({p['address'] for p in report['patches']}),20)
            image=builder.apply_patch_plan(self.roms[model],report['patches'])
            for p in report['patches']:
                self.assertEqual(struct.unpack_from('<I',image,p['address']-0x53000000)[0],p['replacement'])
                if 'target' in p:self.assertEqual(target(p['address'],p['replacement']),p['target'])
            self.assertEqual(image[0x535048e8-0x53000000:0x535048e8-0x53000000+16],
                             self.roms[model][0x535048e8-0x53000000:0x535048e8-0x53000000+16])
            self.assertEqual(image[0x53510fa0-0x53000000:0x53511240-0x53000000],
                             self.roms[model][0x53510fa0-0x53000000:0x53511240-0x53000000])
            self.assertEqual(report['metadata_allocation_bytes'],5820)
            self.assertTrue(report['installed_software_layer'])
            self.assertFalse(report['camera_tested']);self.assertFalse(report['hardware_activation'])
            self.assertTrue(report['native_jpeg_encoded_capacity_preserved'])
            self.assertEqual(report['reused_central_symbols'],EXTERNALS)
            self.assertTrue(set(EXTERNALS).isdisjoint(report['symbols']))
            self.assertNotIn('native/gr3/m10v_border_shot.c',report['compiled_sources'])
            self.assertNotIn('native/gr3/m10v_library_capture.c',report['compiled_sources'])
            self.assertEqual(set(report['symbols']),set(report['guard']['symbols'])|
                {symbol for module in builder.MODULES for symbol in module[1]}|set(builder.HOOK_EXPORTS))

    def test_relocation_at_second_base_and_output_artifacts(self):
        builder=self.builder();old,first=self.built();code,second=self.built(base=0x54180000)
        self.assertNotEqual(old,code)
        for p in second['patches']:
            if 'target' in p:self.assertEqual(target(p['address'],p['replacement']),p['target'])
        self.assertEqual(second['symbols']['m10v_border_runtime_before_submit']-
                         first['symbols']['m10v_border_runtime_before_submit'],0x20000)
        with tempfile.TemporaryDirectory() as folder:
            emitted,report=builder.build(0x54160000,self.roms['gr3'],EXTERNALS,enabled=True,out_dir=folder)
            self.assertEqual((Path(folder)/'m10v-border-runtime-arm.bin').read_bytes(),emitted)
            self.assertEqual(json.loads((Path(folder)/'m10v-border-runtime-arm.json').read_text()),report)

    def test_changing_sources_during_compile_cannot_emit_false_source_receipt(self):
        builder=self.builder()
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'rejected'
            with patch.object(builder,'_source_hashes',side_effect=[{'source':'old'},{'source':'new'}]):
                with self.assertRaisesRegex(ValueError,'sources changed during compilation'):
                    builder.build(0x54160000,self.roms['gr3'],EXTERNALS,enabled=True,out_dir=out)
            self.assertFalse(out.exists())

    def test_input_preimage_collision_and_external_rejections(self):
        builder=self.builder();stock=self.roms['gr3']
        for kwargs in ({'enabled':1},{'enabled':True,'stock':None},
                       {'enabled':True,'stock':stock[:-1]+bytes([stock[-1]^1])},
                       {'enabled':True,'camera_model':'gr3x'},
                       {'enabled':True,'camera_model':'gr2'},
                       {'enabled':True,'base':0x54160004},
                       {'enabled':True,'base':0x55000000},
                       {'enabled':True,'externals':{}},
                       {'enabled':True,'externals':{**EXTERNALS,'m10v_capture_library':0x540c0001}}):
            args={'base':0x54160000,'stock':stock,'externals':EXTERNALS};args.update(kwargs)
            with self.subTest(kwargs=repr({k:v for k,v in kwargs.items() if k!='stock'})):
                with self.assertRaises((ValueError,TypeError)):builder.build(**args)
        _,report=self.built()
        with self.assertRaises(ValueError):builder.apply_patch_plan(stock,report['patches']+[report['patches'][0]])
        mutated=bytearray(stock);at=report['patches'][-1]['address']-0x53000000;mutated[at]^=1
        with self.assertRaises(ValueError):builder.apply_patch_plan(bytes(mutated),report['patches'])
        with self.assertRaises(ValueError):
            builder.build(0x54160000,stock,{**EXTERNALS,'m10v_capture_library':0x54160000},enabled=True)
        with self.assertRaises(ValueError):
            builder.arm_branch(0x53501f98,0x55501fa0,True)

    def test_hooks_preserve_full_context_and_original_displaced_behavior(self):
        from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
        from unicorn import arm_const as A
        builder=self.builder();code,report=self.built();base=report['base']
        for model,role,at,resume in ((model,*case) for model in self.roms for case in (
            ('before_submit',0x53501f98,0x53501f9c),('after_resize',0x534ff458,0x534ff45c))):
            stock=builder.apply_patch_plan(self.roms[model],report['patches'])
            for misalignment in (0,4):
                u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x2000000)
                u.mem_write(0x53000000,stock);u.mem_write(base,code);u.mem_map(0x55000000,0x100000)
                flags=0xa80f0013;u.reg_write(A.UC_ARM_REG_CPSR,flags)
                registers=[0x10001000+17*i for i in range(13)]
                registers[4]=0x55109000 if role=='before_submit' else 0x55010904
                registers[6]=0x5501096c;registers[7]=0x55100000;registers[11]=0x550ff100
                for i,value in enumerate(registers):u.reg_write(getattr(A,f'UC_ARM_REG_R{i}'),value)
                sp=0x550fe000+misalignment;u.reg_write(A.UC_ARM_REG_SP,sp)
                u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
                u.mem_write(registers[11]-0x28,struct.pack('<I',0xdecafbad))
                seen=[];entry=report['symbols']['m10v_border_runtime_'+role]
                def observe(uc,pc,size,data):
                    if pc==entry:
                        seen.append((uc.reg_read(A.UC_ARM_REG_R0),uc.reg_read(A.UC_ARM_REG_R1)))
                        self.assertEqual(uc.reg_read(A.UC_ARM_REG_SP)&7,0)
                        ret=uc.reg_read(A.UC_ARM_REG_LR)
                        for i in range(13):uc.reg_write(getattr(A,f'UC_ARM_REG_R{i}'),0xbad00000+i)
                        uc.reg_write(A.UC_ARM_REG_CPSR,0x60000013)
                        uc.reg_write(A.UC_ARM_REG_LR,0xbaadbaac);uc.reg_write(A.UC_ARM_REG_PC,ret)
                    elif pc==0x536abd28:
                        self.assertEqual(role,'before_submit')
                        self.assertEqual([uc.reg_read(getattr(A,f'UC_ARM_REG_R{i}')) for i in range(13)],registers)
                        self.assertEqual(uc.reg_read(A.UC_ARM_REG_CPSR),flags)
                        self.assertEqual(uc.reg_read(A.UC_ARM_REG_SP),sp)
                        self.assertEqual(uc.reg_read(A.UC_ARM_REG_LR),resume)
                        uc.reg_write(A.UC_ARM_REG_PC,resume)
                u.hook_add(UC_HOOK_CODE,observe);u.emu_start(at,resume,count=10000)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),resume)
                expected=list(registers)
                if role=='after_resize':expected[2]=0xdecafbad
                self.assertEqual([u.reg_read(getattr(A,f'UC_ARM_REG_R{i}')) for i in range(13)],expected)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),sp)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_CPSR),flags)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_LR),resume if role=='before_submit' else 0x550ff800)
                self.assertEqual(seen,[(0x55100000,registers[6] if role=='before_submit' else registers[4])])


if __name__=='__main__':unittest.main()
