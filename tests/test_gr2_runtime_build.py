"""Execute the independently built BE32 GR II bridge, never a downloadable firmware."""
import tempfile
import unittest
from pathlib import Path
import struct
from tests.test_unity_update import ROOT,component

class Gr2RuntimeBuildTests(unittest.TestCase):
    def build(self):
        try:from scripts.build_gr2_runtime import build_gr2_runtime
        except ImportError:self.fail('GR II big-endian runtime builder is missing')
        code=component('gr2','b01firm8')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        report=build_gr2_runtime(code,{},Path(self.temp.name));return report

    def machine(self,report):
        from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_MODE_BIG_ENDIAN
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM|UC_MODE_BIG_ENDIAN)
        u.mem_map(0xa0798000,0x68000);u.mem_write(report['base'],bytes.fromhex(report['runtime_hex']))
        u.mem_map(0x50000000,0x20000);return u

    def call(self,u,entry,args):
        from unicorn import arm_const as r
        for reg,value in zip((r.UC_ARM_REG_R0,r.UC_ARM_REG_R1,r.UC_ARM_REG_R2,r.UC_ARM_REG_R3),args):u.reg_write(reg,value)
        u.reg_write(r.UC_ARM_REG_SP,0x50018000);u.reg_write(r.UC_ARM_REG_LR,0x5001f000)
        u.emu_start(entry,0x5001f000,count=10000000)
        self.assertEqual(u.reg_read(r.UC_ARM_REG_PC),0x5001f000)
        return u.reg_read(r.UC_ARM_REG_R0)

    def test_memory_reservations_are_bound_to_original_preinitialization_load_records(self):
        from scripts import build_gr2_runtime as module
        self.assertTrue(hasattr(module,'memory_reservations'))
        code=component('gr2','b01firm8');rows=module.memory_reservations(code)
        self.assertEqual([(v['address'],v['record_index'],v['expected'],v['replacement']) for v in rows],
                         [(0xa0023154,0,0xa0798000,0xa0800000),(0xa01137ec,1,0xfb0c,0x12b9c)])
        for row in rows:
            self.assertEqual(struct.unpack_from('>I',code,row['source_file_offset'])[0],row['expected'])
            self.assertEqual(row['install_stage'],'before_original_module_load')
        changed=bytearray(code);changed[rows[1]['source_file_offset']]^=1
        with self.assertRaises(ValueError):module.memory_reservations(bytes(changed))

    def test_page_configuration_validates_values_and_preserves_independent_hdf(self):
        import copy
        from scripts.build_gr2_runtime import configuration_state
        normalized,wire,native=configuration_state({})
        self.assertEqual(len(wire),104);self.assertEqual(len(native),104)
        self.assertEqual(struct.unpack_from('>IHHI',native),(0x5630314d,4,104,0))
        for field,value in (('grain',4),('film',79),('soft',True)):
            bad=copy.deepcopy(normalized);bad['slots'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):configuration_state(bad)
        bad=copy.deepcopy(normalized);bad['hdf']=1
        hdf_configuration,hdf_wire,hdf_native=configuration_state(bad)
        self.assertEqual(hdf_configuration['hdf'],1);self.assertEqual(hdf_wire,wire);self.assertEqual(hdf_native,native)
        bad['hdf']=4
        with self.assertRaises(ValueError):configuration_state(bad)
        bad=copy.deepcopy(normalized);bad['unknown']=0
        with self.assertRaises(ValueError):configuration_state(bad)
        for bad in ([],None,False):
            with self.assertRaises(ValueError):configuration_state(bad)

    def test_complete_page_configuration_compiles_to_be32_state_and_roundtrips_shared_wire_contract(self):
        import json,subprocess
        from scripts.build_gr2_runtime import build_gr2_runtime
        script="import {defaultConfiguration} from './web/gr2/native-library-state.mjs';const c=defaultConfiguration();[67,68,33,66,78].forEach((film,i)=>{c.slots[i].film=film;c.slots[i].grain=i%4;c.slots[i].soft=3;});c.slots[0].effects.filmExposure=1;c.slots[1].effects.filmExposure=2;c.stamp=2;c.format=3;c.corner=2;c.color=1;c.filmNameStamp=true;console.log(JSON.stringify(c));"
        configuration=json.loads(subprocess.check_output(['node','--input-type=module','-e',script],cwd=ROOT))
        with tempfile.TemporaryDirectory() as folder:
            report=build_gr2_runtime(component('gr2','b01firm8'),configuration,Path(folder))
        expected=subprocess.check_output(['node','--input-type=module','-e',"import {readFileSync} from 'node:fs';import {initialState} from './compat/gr2-v1/node/gr3-native-library.mjs';process.stdout.write(initialState(JSON.parse(readFileSync(0,'utf8'))));"],input=json.dumps(configuration).encode(),cwd=ROOT)
        u=self.machine(report);state=0x50001000;wire=0x50002000
        self.call(u,report['symbols']['m10v_library_init'],[state])
        self.assertEqual(self.call(u,report['symbols']['m10v_library_valid'],[state]),1)
        self.assertEqual(bytes(u.mem_read(state,104)).hex(),report['initial_state_native_hex'])
        self.assertEqual(self.call(u,report['symbols']['gr2_state_encode'],[state,wire]),1)
        self.assertEqual(bytes(u.mem_read(wire,104)),expected)
        self.assertEqual(report['initial_state_wire_hex'],expected.hex());self.assertFalse(report['can_package'])
        self.assertEqual(report['configuration']['slots'][0]['soft'],0)

    def test_compiled_text_bridge_draws_through_stock_font_services_and_rejects_invalid_bounds(self):
        from scripts.analyze_gr2_native_contract import probe_effect_view_draw
        report=self.build();self.assertTrue('gr2_text_draw' in report['symbols'])
        code=component('gr2','b01firm8');disk=component('gr2','b01firm6')
        drawn=probe_effect_view_draw(code,disk,native_runtime=report)
        self.assertEqual(drawn['native_text_return'],1)
        self.assertGreater(drawn['native_text_changed_bytes'],100)
        self.assertEqual(drawn['native_text_outside_bounds'],0)
        missing=probe_effect_view_draw(code,disk,native_runtime=report,native_font_missing=True)
        self.assertEqual(missing['native_text_return'],0)
        self.assertEqual(missing['native_text_changed_bytes'],0)
        u=self.machine(report);text=0x50001000;rect=0x50002000
        u.mem_write(text,'M10V\0'.encode('utf-16-be'));u.mem_write(rect,struct.pack('>4h',380,60,639,120))
        for count,color,bounds in ((0,0x20001,(380,60,639,120)),(4,0x20001,(-1,60,639,120)),(4,0x20001,(380,60,640,120)),(4,0x20001,(380,121,639,120)),(4,0x123456,(380,60,639,120)),(3,0x20001,(380,60,639,120))):
            u.mem_write(rect,struct.pack('>4h',*bounds))
            self.assertEqual(self.call(u,report['symbols']['gr2_text_draw'],[text,count,rect,color]),0)

    def test_compiled_film_card_uses_stock_16_bit_blitter_and_releases_pool_storage(self):
        from scripts.analyze_gr2_native_contract import probe_effect_view_draw
        report=self.build();self.assertTrue('gr2_card_draw' in report['symbols'])
        code=component('gr2','b01firm8');disk=component('gr2','b01firm6')
        for fail in (False,True):
            with self.subTest(allocation_failure=fail):
                drawn=probe_effect_view_draw(code,disk,native_runtime=report,native_card=True,native_card_allocation_failure=fail)
                self.assertEqual(drawn['native_card_return'],0 if fail else 1)
                self.assertEqual(drawn['native_card_changed_bytes'],0 if fail else 47040)
                self.assertEqual(drawn['native_card_outside_bounds'],0)
                self.assertTrue(drawn['native_card_matches_reference'])
                self.assertTrue(drawn['native_card_pool_restored'])

    def test_compiled_modal_overlay_registers_consumes_keys_exits_once_and_preserves_camera_root(self):
        from scripts.analyze_gr2_native_contract import probe_effect_view_draw
        report=self.build();self.assertTrue('gr2_overlay_attach' in report['symbols'])
        result=probe_effect_view_draw(component('gr2','b01firm8'),component('gr2','b01firm6'),native_runtime=report,attach=True,overlay=True)
        self.assertEqual(result['overlay_attach_return'],1)
        self.assertEqual(result['overlay_duplicate_return'],0)
        self.assertEqual(result['overlay_detach_return'],1)
        self.assertEqual(result['overlay_second_detach_return'],0)
        self.assertEqual(result['overlay_events'],[0x60000003,0x60002004,0x60000005])
        self.assertEqual(result['overlay_destructor_calls'],1)
        self.assertEqual(result['overlay_underlying_effects'],[6,7])
        self.assertTrue(result['active_root_matches'])
        self.assertTrue(result['overlay_full_rejected'])

    def test_compiled_rectangle_fill_matches_both_stock_pixel_formats_without_outside_writes(self):
        from scripts.analyze_gr2_native_contract import probe_effect_view_draw
        report=self.build();self.assertTrue('gr2_fill_rect' in report['symbols'])
        result=probe_effect_view_draw(component('gr2','b01firm8'),component('gr2','b01firm6'),native_runtime=report,native_fill=True)
        self.assertEqual(result['native_fill_returns'],[1,1])
        self.assertTrue(result['native_fill_matches_reference'])
        self.assertEqual(result['native_fill_outside_bounds'],0)

    def test_compiled_full_resolution_text_bridge_uses_original_720_coordinate_context(self):
        from scripts.analyze_gr2_native_contract import probe_effect_view_draw
        report=self.build();self.assertTrue('gr2_text_draw_full' in report['symbols'])
        result=probe_effect_view_draw(component('gr2','b01firm8'),component('gr2','b01firm6'),native_runtime=report,native_text_full=True)
        self.assertEqual(result['native_text_return'],1)
        self.assertGreater(result['native_text_changed_bytes'],100)
        self.assertEqual(result['native_text_outside_bounds'],0)

    def test_be32_runtime_preserves_original_post_load_result_and_audits_all_sections(self):
        report=self.build();self.assertEqual(report['endianness'],'big');self.assertFalse(report['be8'])
        self.assertFalse(report['can_package']);self.assertLess(report['memory_bytes'],0x68000)
        from scripts.analyze_gr2_native_contract import runtime_machine
        u=runtime_machine(component('gr2','b01firm8'));u.mem_write(report['base'],bytes.fromhex(report['runtime_hex']))
        self.assertEqual(self.call(u,report['symbols']['gr2_post_load'],[]),0xffffffff)
        self.assertEqual(self.call(u,report['symbols']['gr2_post_load'],[]),0xffffffff)
        self.assertEqual(struct.unpack('>I',u.mem_read(report['symbols']['gr2_boot_count'],4))[0],2)
        self.assertEqual(report['undefined_symbols'],[])

    def test_compiled_date_bridge_validates_real_calendar_without_soft_float_helpers(self):
        report=self.build();u=self.machine(report);entry=report['symbols']['gr2_date_valid']
        for fields,valid in (((2024,2,29,23,59,59),1),((2100,2,29,0,0,0),0),((2026,10,20,0,0,0),1),((2026,13,1,0,0,0),0),((2026,1,1,0,60,0),0)):
            u.mem_write(0x50001000,struct.pack('>6H',*fields))
            with self.subTest(fields=fields):self.assertEqual(self.call(u,entry,[0x50001000]),valid)

    def test_compiled_capture_bridge_decodes_planar_frame_and_refuses_overlap_or_odd_width(self):
        report=self.build();u=self.machine(report);entry=report['symbols']['gr2_capture_decode']
        descriptor=bytearray(0x30);struct.pack_into('>3I',descriptor,0,0x60000000,0x64000000,(3264<<16)|4928)
        descriptor[0xd]=2;u.mem_write(0x50001000,bytes(descriptor))
        self.assertEqual(self.call(u,entry,[0x50001000,0x50002000]),1)
        values=struct.unpack('>11I',u.mem_read(0x50002000,44))
        self.assertEqual(values,(0x60000000,0x60000000+4928*3264,0x60000000+(4928+2464)*3264,4928*3264,2464*3264,2464*3264,4928,3264,4928,2464,0x422))
        for offset,value in ((8,(3264<<16)|4927),(0x18,0x60000000)):
            changed=bytearray(descriptor);struct.pack_into('>I',changed,offset,value);u.mem_write(0x50001000,bytes(changed));u.mem_write(0x50002000,b'\xa5'*44)
            self.assertEqual(self.call(u,entry,[0x50001000,0x50002000]),0)
            self.assertEqual(bytes(u.mem_read(0x50002000,44)),b'\xa5'*44)

    def test_compiled_plane_arithmetic_matches_original_encoder_across_alignment_boundaries(self):
        from scripts.analyze_gr2_native_contract import probe_jpeg_input
        report=self.build();u=self.machine(report);entry=report['symbols']['gr2_capture_decode'];code=component('gr2','b01firm8')
        for width,height,kind in ((642,426,2),(642,426,3),(642,426,4),(4928,3264,2)):
            expected=probe_jpeg_input(code,width,height,format_kind=kind)
            descriptor=bytearray(48);struct.pack_into('>3I',descriptor,0,0x60000000,0x64000000,(height<<16)|width);descriptor[13]=kind
            u.mem_write(0x50001000,bytes(descriptor))
            with self.subTest(width=width,height=height,kind=kind):
                self.assertEqual(self.call(u,entry,[0x50001000,0x50002000]),1)
                values=struct.unpack('>11I',u.mem_read(0x50002000,44))
                self.assertEqual(values[:3],(expected['y'],expected['u'],expected['v']))
                self.assertEqual(values[8:11],(expected['y_stride'],expected['chroma_stride'],expected['input_format']))

    def test_early_native_bootstrap_loads_before_phase_one_and_never_reloads_its_bss(self):
        from scripts.analyze_unity_runtime import probe_gr2_startup_order
        report=self.build();self.assertTrue('early_bootstrap' in report)
        result=probe_gr2_startup_order(component('gr2','b01firm8'),native_runtime=report,early_native=True)
        self.assertLess(result['events'].index(['native_early_load',14]),result['events'].index(['phase',1]))
        self.assertEqual(result['native_load_count'],1);self.assertEqual(result['native_bss_canary'],0x12345678)
        self.assertTrue(result['original_stub_restored'])
        self.assertTrue(result['stack_preserved']);self.assertTrue(result['callee_saved_preserved'])
        self.assertEqual(result['native_boot_count'],1);self.assertEqual(result['returned'],0)
        failed=probe_gr2_startup_order(component('gr2','b01firm8'),native_runtime=report,early_native=True,fail_native_read=True)
        self.assertEqual(failed['returned'],0xffffffff);self.assertEqual(failed['module_indices'],[0])
        self.assertFalse(any(event[0]=='phase' for event in failed['events']))
        self.assertTrue(failed['stack_preserved']);self.assertTrue(failed['callee_saved_preserved'])

    def test_original_loader_copies_the_extended_module_zero_bootstrap_and_preserves_neighbors(self):
        from scripts import analyze_unity_runtime as native
        report=self.build();self.assertTrue(hasattr(native,'probe_gr2_bootstrap_extension'))
        result=native.probe_gr2_bootstrap_extension(component('gr2','b01firm8'),contract=report['early_bootstrap'])
        self.assertEqual(result['returned'],0)
        self.assertTrue(result['extended_payload_matches']);self.assertTrue(result['guard_preserved'])
        self.assertTrue(result['next_module_preserved']);self.assertTrue(result['bss_zeroed'])
        self.assertTrue(result['completion_flag_set'])

    def test_native_startup_chain_returns_to_stock_final_callbacks_after_record_14_load(self):
        from scripts.analyze_unity_runtime import probe_gr2_startup_order
        report=self.build()
        traced=probe_gr2_startup_order(component('gr2','b01firm8'),native_runtime=report)
        self.assertEqual(traced['post_load_return'],0xffffffff)
        self.assertEqual(traced['native_boot_count'],1)
        self.assertTrue(traced['native_loaded_by_original_indexed_loader'])
        self.assertEqual(traced['events'][-4:],[['post_load',0],['phase',0],['phase',0xffffffff],['finalize',0xffffffff]])

    def test_planar_chroma_conversion_is_reversible_for_odd_plane_lengths_and_preserves_guards(self):
        report=self.build();self.assertIn('gr2_chroma_shuffle',report['symbols']);u=self.machine(report)
        for n in (*range(1,129),320,363,364,365,1025,1092,1093,1094,3279,3280,3281):
            a=bytes(i%251 for i in range(n));b=bytes((i*7+93)%251 for i in range(n));address=0x50001004
            u.mem_write(address-4,b'\xa5'*4+a+b+b'\xa5'*4)
            with self.subTest(n=n):
                self.assertEqual(self.call(u,report['symbols']['gr2_chroma_shuffle'],[address,n,0]),1)
                self.assertEqual(bytes(u.mem_read(address,2*n)),bytes(x for pair in zip(a,b) for x in pair))
                self.assertEqual(self.call(u,report['symbols']['gr2_chroma_shuffle'],[address,n,1]),1)
                self.assertEqual(bytes(u.mem_read(address-4,2*n+8)),b'\xa5'*4+a+b+b'\xa5'*4)

    def test_capture_adapter_rejects_stride_overflow_before_converting_or_rendering(self):
        report=self.build();u=self.machine(report)
        self.call(u,report['symbols']['m10v_library_init'],[0x50001000])
        u.mem_write(0x50002000,b'\xa5'*32);u.mem_write(0x50003000,b'\xa5'*32)
        u.mem_write(0x50004000,struct.pack('>11I',0x50002000,0x50003000,0x50003010,32,16,16,8,4,8,0x80000004,0x422))
        u.mem_write(0x50018000,bytes(12))
        self.assertEqual(self.call(u,report['symbols']['gr2_render_planar'],[0x50004000,0x50001000,0,0]),0xffffffff)
        self.assertEqual(bytes(u.mem_read(0x50002000,32))+bytes(u.mem_read(0x50003000,32)),b'\xa5'*64)

    def test_compiled_allocator_handles_real_rtos_pool_exhaustion_and_release(self):
        from scripts.analyze_gr2_native_contract import probe_rtos_pool
        report=self.build();self.assertIn('gr2_allocate',report['symbols'])
        result=probe_rtos_pool(component('gr2','b01firm8'),native_runtime=report)
        self.assertTrue(result['native_allocation_in_pool'])
        self.assertEqual(result['native_exhausted_pointer'],0)
        self.assertEqual(result['native_release_returned'],0)
        self.assertEqual(result['native_reallocated_pointer'],result['native_allocated_pointer'])
        self.assertEqual(result['helpers_intercepted'],[])

    def test_compiled_clock_bridge_accepts_zero_seconds_and_rejects_invalid_dates_atomically(self):
        from scripts.analyze_gr2_native_contract import probe_rtc_get_time
        report=self.build();self.assertIn('gr2_read_clock',report['symbols'])
        for fields in ((2026,10,20,18,30,0),(2024,2,29,0,0,59)):
            result=probe_rtc_get_time(component('gr2','b01firm8'),fields,native_runtime=report)
            self.assertEqual(result['returned'],1);self.assertEqual(result['fields'],list(fields))
        invalid=probe_rtc_get_time(component('gr2','b01firm8'),(2100,2,29,0,0,0),native_runtime=report)
        self.assertEqual(invalid['returned'],0);self.assertEqual(invalid['output_hex'],'a5'*12)

    def test_user_instruction_handoff_bootstraps_through_original_svc_data_vector(self):
        from scripts import analyze_gr2_native_contract as native
        report=self.build();self.assertTrue('gr2_code_sync' in report['symbols'])
        result=native.probe_code_sync(component('gr2','b01firm8'),native_runtime=report)
        self.assertTrue(result['low_record_loader']['payload_matches']);self.assertTrue(result['low_record_loader']['bss_zeroed'])
        self.assertTrue(result['low_record_loader']['context_and_registers_restored'])
        self.assertEqual(result['returns'],[0,1,0])
        self.assertEqual(result['initial_task_entry'],0xa0020945);self.assertEqual(result['initial_task_mode'],0x10)
        self.assertEqual(result['operations'],[[7,10,4],[7,5,0]])
        self.assertEqual(result['operands'],[0,0])
        self.assertTrue(result['data_cache_vector_supported']);self.assertTrue(result['rejected_policy_no_operations'])
        self.assertTrue(result['callback_code_unchanged']);self.assertTrue(result['user_return_preserved'])
        self.assertTrue(result['callee_saved_preserved']);self.assertTrue(result['unrelated_svc_preserved'])

    def test_cache_bridge_rejects_user_irq_modes_and_emits_bounded_privileged_operations(self):
        from unicorn import UC_HOOK_CODE,arm_const as r
        report=self.build();self.assertIn('gr2_cache_before',report['symbols'])
        for name,expected in (('gr2_cache_before',(7,6,0)),('gr2_cache_after',(7,10,4))):
            for mode in (0x13,0x1f,0x10,0x12):
                u=self.machine(report);u.mem_map(0xA0044000,0x1000);u.mem_map(0xA00AF000,0x1000)
                u.mem_write(0xA00AF884,struct.pack('>I',0xA00AF8A8));observed=[]
                u.reg_write(r.UC_ARM_REG_CPSR,(u.reg_read(r.UC_ARM_REG_CPSR)&~31)|mode)
                def cp15(uc,address,size,context):
                    word=struct.unpack('>I',uc.mem_read(address,4))[0]
                    if word&0x0f100f10==0x0e000f10:
                        self.assertEqual(uc.reg_read(r.UC_ARM_REG_R0+((word>>12)&15)),0)
                        observed.append(((word>>16)&15,word&15,(word>>5)&7));uc.reg_write(r.UC_ARM_REG_PC,address+4)
                entry=report['symbols'][name];u.hook_add(UC_HOOK_CODE,cp15,begin=entry,end=report['symbols']['gr2_cache_gateway']-4)
                with self.subTest(name=name,mode=mode):
                    self.assertEqual(self.call(u,entry,[]),int(mode in (0x13,0x1f)))
                    self.assertEqual(observed,[expected] if mode in (0x13,0x1f) else [])

    def test_user_cache_bridge_runs_original_svc_dispatch_and_restores_user_context(self):
        from scripts.analyze_gr2_native_contract import runtime_machine
        from unicorn import UC_HOOK_INTR,UC_HOOK_CODE,arm_const as r
        report=self.build();self.assertTrue('cache_gateway_patch_hex' in report)
        u=runtime_machine(component('gr2','b01firm8'));u.mem_write(report['base'],bytes.fromhex(report['runtime_hex']))
        u.mem_write(0xA0044F4C,bytes.fromhex(report['cache_gateway_patch_hex']))
        from scripts.analyze_unity_runtime import parse_executable_load_map
        code=component('gr2','b01firm8');row=parse_executable_load_map(code)[15]
        u.mem_map(0,0x10000);u.mem_write(row['address'],code[row['source_file_offset']:row['source_file_offset']+row['length']])
        for name,expected in (('gr2_cache_before',(7,6,0)),('gr2_cache_after',(7,10,4))):
            operations=[];dispatch=[]
            def interrupt(uc,number,context):
                self.assertEqual(number,2)
                old=uc.reg_read(r.UC_ARM_REG_CPSR);resume=uc.reg_read(r.UC_ARM_REG_PC)
                uc.reg_write(r.UC_ARM_REG_CPSR,(old&~0x3f)|0x13)
                uc.reg_write(r.UC_ARM_REG_SP,0x50017000);uc.reg_write(r.UC_ARM_REG_SPSR,old)
                uc.reg_write(r.UC_ARM_REG_LR,resume);uc.reg_write(r.UC_ARM_REG_PC,0x844)
            def observe(uc,address,size,context):
                if address==0xA00AF858:dispatch.append(address)
                word=struct.unpack('>I',uc.mem_read(address,4))[0]
                if word&0x0f000f10==0x0e000f10:
                    self.assertEqual(uc.reg_read(r.UC_ARM_REG_CPSR)&31,19)
                    operations.append(((word>>16)&15,word&15,(word>>5)&7));uc.reg_write(r.UC_ARM_REG_PC,address+4)
            intr=u.hook_add(UC_HOOK_INTR,interrupt);obs=u.hook_add(UC_HOOK_CODE,observe)
            u.reg_write(r.UC_ARM_REG_CPSR,0x60000210)
            u.reg_write(r.UC_ARM_REG_R4,0x12345678)
            self.assertEqual(self.call(u,report['symbols'][name],[]),1)
            self.assertEqual(operations,[expected]);self.assertEqual(dispatch,[0xA00AF858])
            self.assertEqual(u.reg_read(r.UC_ARM_REG_CPSR)&31,16)
            self.assertEqual(u.reg_read(r.UC_ARM_REG_R4),0x12345678)
            self.assertEqual(u.reg_read(r.UC_ARM_REG_SP),0x50018000)
            u.hook_del(intr);u.hook_del(obs)

    def test_compiled_ui_text_bridge_preserves_original_utf16_and_rejects_invalid_language(self):
        from scripts.analyze_gr2_native_contract import probe_ui_text
        report=self.build();self.assertTrue('gr2_original_text' in report['symbols'])
        code=component('gr2','b01firm8')
        for language in range(21):
            expected=probe_ui_text(code,106,language)
            actual=probe_ui_text(code,106,language,native_runtime=report)
            self.assertEqual(actual['wire_hex'],expected['wire_hex'])
            self.assertEqual(actual['pointer'],expected['pointer'])
        self.assertEqual(probe_ui_text(code,106,21,native_runtime=report)['pointer'],0)

    def test_planar_conversion_has_linear_bounded_pixel_traffic_without_frame_scratch(self):
        from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_MEM_READ
        report=self.build();u=self.machine(report);n=8192;address=0x50001004
        original=bytes((i*17+23)%251 for i in range(2*n));u.mem_write(address-4,b'\xa5'*4+original+b'\xa5'*4)
        traffic=[0,0]
        def count(uc,access,pointer,size,value,context):traffic[0 if access==UC_MEM_READ else 1]+=size
        hook=u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,count,begin=address,end=address+2*n-1)
        for inverse in (0,1):
            traffic[:]=[0,0]
            self.assertEqual(self.call(u,report['symbols']['gr2_chroma_shuffle'],[address,n,inverse]),1)
            self.assertLess(max(traffic),16*n)
            expected=original if inverse else bytes(x for pair in zip(original[:n],original[n:]) for x in pair)
            self.assertEqual(bytes(u.mem_read(address,2*n)),expected)
        u.hook_del(hook)
        self.assertEqual(bytes(u.mem_read(address-4,2*n+8)),b'\xa5'*4+original+b'\xa5'*4)

    def test_compiled_detached_effect_view_init_matches_original_constructor_and_bounds(self):
        from scripts.analyze_gr2_native_contract import probe_effect_view_init
        report=self.build();self.assertTrue('gr2_effect_view_init' in report['symbols'])
        code=component('gr2','b01firm8');expected=probe_effect_view_init(code)
        actual=probe_effect_view_init(code,native_runtime=report)
        for key in ('returned','widget_offsets','focus','event_handler','guards_unchanged','stack_preserved','external_writes'):
            self.assertEqual(actual[key],expected[key])
        u=self.machine(report);u.mem_write(0x50004000,b'\xa5'*0x600)
        self.assertEqual(self.call(u,report['symbols']['gr2_effect_view_init'],[0x50004000,0x5ff]),0)
        self.assertEqual(bytes(u.mem_read(0x50004000,0x600)),b'\xa5'*0x600)
