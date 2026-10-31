"""Decode CRC-protected GR III debug pages, including independent IO pages."""
import argparse
import json
import struct
import zlib
EFFECTS_MENU_EVENTS={32:'effects.lifecycle',33:'effects.ready.before',34:'effects.ready.stage',
                     35:'effects.enter',36:'effects.key.before',37:'effects.route',39:'effects.key.after'}
from pathlib import Path

EVENTS={10:'menu.enter.before',11:'menu.enter.after',20:'menu.key.before',21:'menu.key.after',
        30:'menu.focus.before',31:'menu.focus.after',40:'menu.confirm.before',41:'menu.confirm.after',
        50:'menu.redraw.before',51:'menu.redraw.after',60:'settings.commit.before',61:'settings.commit.after',
        70:'detail.change',71:'detail.reset',80:'page.enter.before',81:'page.enter.after',
        82:'page.key.before',83:'page.state.after',84:'page.draw.after',112:'capture.settings',113:'capture.settings.source',114:'capture.highlight.energy',130:'capture.texture',131:'capture.texture.grain',100:'capture.before',101:'capture.after',110:'capture.render.before',111:'capture.render.after',120:'capture.clock'}
EVENTS.update({85:'ab.disp.route',86:'ab.setup.navigate',87:'ab.switch.result',88:'ab.controller.disp',89:'ab.setup.branch',90:'ab.owner',91:'ab.adj.scope',92:'ab.page.load',93:'ab.page.view',94:'ab.page.enter',95:'ab.raw.packet',96:'ab.navigation.return',99:'ab.navigation.gate'})
EVENTS.update({218:'half-pair.result',219:'half-pair.bank',220:'half-pair.layout',221:'half-pair.session',222:'half-pair.iip.time',223:'half-pair.probe',224:'half-pair.native-wait.probe'})
HALF_PAIR_STAGES={0:'entry',1:'first-ready',2:'pair-composed',3:'pending-cancelled',-1:'identity',-2:'topology',-3:'image-layout',-4:'protected-memory',-5:'thumbnail-layout',-6:'filesystem',-7:'first-write',-8:'scratch-unavailable',-9:'pending-read-or-compose',-10:'owner-unavailable',-11:'busy',-12:'pending-reset',-15:'native-iip-not-ready',-16:'native-iip-rejected',-19:'owned-frame-integrity'}
EVENTS.update({210:'zoom.set.before',211:'zoom.set.after',212:'firmware.assert'})
EVENTS.update({208:'ab.dispatch.physical-down',209:'ab.dispatch.fallback'})
EVENTS.update({97:'ab.display.snapshot',98:'ab.display.return'})
EVENTS.update(dict(enumerate([
    'adj.event.before','adj.event.after','adj.restore.before',
    'adj.restore.refresh.before','adj.restore.refresh.after',
    'adj.restore.position.before','adj.restore.position.after',
    'adj.exit.before','adj.exit.after','live.enter.before','live.enter.native.after',
    'live.init.factory.before','live.init.factory.after','live.init.reconcile.before',
    'live.init.reconcile.after','live.init.load.before','live.init.load.after',
    'live.enter.return','ab.live.before','ab.live.navigate.before','ab.live.navigate.after',
    'dispatch.before','dispatch.after','selector.before','selector.after',
    'live.leave.before','live.leave.after','live.destroy.before','live.destroy.after',
    'adj.changed.suppressed','adj.refresh.before','adj.refresh.after',
    'live.event.before','live.event.after','adj.exit.native.before',
    'adj.destroy.before','adj.destroy.after','adj.changed.native.before',
    'live.pair.before','live.pair.after'],230)))
EVENTS.update({270:'ab.entry.blocked-closing',271:'ab.a1.native-pass',
               272:'ab.close.pending',273:'ab.close.live-entered'})
EVENTS.update({102:'capture.rejected',121:'capture.image',125:'capture.request.identity',126:'capture.raw.lifetime',122:'capture.cpu-samples.before',
               123:'capture.cpu-samples.after',124:'capture.layout'})
PROFILE_STAGES={1:'adapter.enter',2:'settings.before',3:'settings.after',4:'allocation.after',
    5:'cache.before',6:'cache.after',7:'spatial.before-color.after',8:'color-fused-texture.after',
    9:'post-spatial-texture.after',10:'stamp.after',11:'cache-writeback.after',12:'adapter.exit'}
PROFILE_INTERVALS={2:'validation',3:'settings-read',4:'date-seed-allocation',5:'descriptor-setup',
    6:'cache-before',7:'spatial-before-color',8:'color-and-fused-texture',9:'post-spatial-and-texture',
    10:'stamp',11:'cache-after',12:'release-and-return'}
EVENTS.update({204:'module.dispatch.enter',205:'module.dispatch.return',206:'module.store.opcode',207:'module.dispatch.time'})
EVENTS.update({132:'capture.profile.settings',134:'capture.texture.backend',135:'capture.native.completed',137:'capture.native.grain.quality',138:'capture.cpu.residual',150:'capture.profile.time'})
EVENTS.update({180:'save.begin',181:'save.callback.payload',182:'save.return',
    183:'raw.setter.after',184:'raw.pool.dispatch.return',185:'raw.transfer',186:'raw.release.before',
    187:'raw.setter.before',188:'raw.allocation.return',189:'raw.release.after',
    190:'jpeg.submit.before',191:'jpeg.submit.return',192:'jpeg.wait.return',
    193:'capture.owner.enter',194:'capture.owner.exit',195:'save.worker.before',
    196:'save.worker.after',197:'save.native.metadata',198:'isp.recipe.observation',199:'lifecycle.trace.overflow'})
EVENTS.update({200:'save.be.before',201:'save.be.after',202:'save.be.status',203:'save.be.context'})
GUARDS={1:'context',2:'recipe',3:'topology',4:'sequence-mode',5:'objects',6:'jpeg-request',
        7:'stock-tone',8:'image-layout',9:'image-planes',10:'raw-dimensions-pointer',
        11:'raw-dimensions',12:'raw-bank',13:'protected-overlap',14:'preview-layout',
        15:'preview-planes',16:'settings',17:'scratch-allocation',18:'scratch-overlap'}

EVENTS.update(EFFECTS_MENU_EVENTS)

def page_records(data):
    if len(data)!=4096:return None
    h=struct.unpack_from('<16I',data)
    if h[0]!=0x4744564d or h[1]!=1 or h[3]>63 or h[4]>=63 or not 0<h[5]<0xffffff00 or h[5]<h[3] or h[6] not in (1,2,3,4) or h[15]!=zlib.crc32(data[:60]) or (h[3]<63 and h[4]!=h[3]):return None
    records=[]
    for index in range(h[3]):
        raw=data[64+index*64:128+index*64];r=struct.unpack('<16I',raw)
        if r[0]!=0x474c564d or r[1]!=1 or not 0<r[2]<=h[5] or r[8]!=h[2] or r[9]!=h[6] or r[15]!=zlib.crc32(raw[:60]):return None
        records.append({'sequence':r[2],'event':r[3],'stage':EVENTS.get(r[3],f'unknown.{r[3]}'),
                        'arguments':list(r[4:8]),'build_id':f'{r[8]:08x}','channel':{1:'menu',2:'capture',3:'io',4:'ab'}[r[9]]})
    for record in records:
        if record['event']==198:
            recipe,tag,a,b=record['arguments']
            fields={0x46583030:('magic','owner'),0x46583031:('ready','sequence'),
                0x46583032:('leak_gain','blur_gain'),0x46583033:('planned','native_completed'),
                0x46583034:('failed','source_si'),0x46583035:('stock_workspace_bytes','stock_query_valid'),
                0x46583036:('effective_grain_strength','grain_mode'),0x46583037:('current_si','native_flags'),
                0x46583038:('planned_width','planned_height'),0x46583039:('workspace_bytes','saved_orientation')}
            if tag in fields:
                first,second=fields[tag]
                record['isp_effects']={'recipe':hex(recipe),'tag':f'{tag:08x}',first:a,second:b,
                    'diagnostic_only':True}
            elif tag==0x46584800:
                names={1:'settings.ready.before-native',2:'workspace.query.return',3:'stock.execution.return',
                    4:'effects.completed',10:'hold.invalid-execution-parameters',11:'hold.stock-result-or-query',
                    12:'hold.workspace',13:'hold.blur-parameters',14:'hold.partial-completion',15:'hold.renderer',
                    16:'hold.completion-publish',20:'hold.encoder-context',21:'hold.encoder-tone',
                    22:'hold.encoder-snapshot',23:'hold.encoder-settings',24:'hold.encoder-completion'}
                record['isp_effects_checkpoint']={'recipe':hex(recipe),'id':a,'stage':names.get(a,'unknown'),
                    'detail':b,'diagnostic_only':True}
            elif tag==0x46584d00:
                record['isp_effects_checkpoint']={'recipe':hex(recipe),'stage':'module.return.safe-sink',
                    'kind':a,'request_spatial':b&255,'context_enabled':(b>>8)&255,
                    'context_mode':(b>>16)&255,'diagnostic_only':True}
            elif tag in (0x46585730,0x46585731):
                record['isp_effects_workspace']={'recipe':hex(recipe),
                    'kind':'native-allocation' if tag==0x46585730 else 'owned-aligned-view',
                    'base':hex(a),'capacity':b,'diagnostic_only':True}
        if record['event'] in (223,224):
            phase,a,b,c=record['arguments']
            names={10:'ready.before',11:'ready.after',20:'pool-manager.before',21:'pool-manager.after',22:'frame-alloc.before',23:'frame-alloc.after',30:'copy.enter',33:'gate.before',34:'gate.after',35:'client-construct.before',36:'client-construct.after',37:'source-cache.before',38:'destination-cache.before',39:'cache.after',40:'transfer-prepare.before',41:'transfer-submit.before',42:'transfer-submit.after',44:'destination-cache-post.before',45:'destination-cache-post.after',50:'client-wait.before',51:'client-wait.after',60:'transfer-worker.before',61:'transfer-worker.after',62:'dma-wait.before',63:'dma-wait.after',70:'notify.enter',71:'native-notify.after',80:'gate.observe',100:'transfer-factory.before',101:'transfer-factory.after',102:'fill-factory.before',103:'fill-factory.after',104:'resize-factory.before',105:'resize-factory.after'}
            record['half_pair_probe']={'phase_id':phase,'phase':names.get(phase,'unknown'),'details':[hex(a),hex(b),hex(c)],'diagnostic_only':True}
        if record['event']==221:
            owner,generation,token,state=record['arguments']
            record['half_pair_session']={'owner':hex(owner),'generation':generation,'owned_token':hex(token),'flags_or_transition':state}
        if record['event']==222:
            recipe,phase,duration,token=record['arguments']
            record['half_pair_iip']={'recipe':hex(recipe),'phase':{1:'first-transfer',2:'second-transfer',3:'compose-and-previews'}.get(phase,phase),'native_ticks':duration,'owned_token':hex(token),'camera_performance_verified':False}
        if record['event']==219:
            bank,capacity,y,c=record['arguments'];record['half_pair_bank']={'bank':hex(bank),'capacity':capacity,'source_y':hex(y),'source_c':hex(c)}
        if record['event']==220:
            recipe,size,pitch_rows,origin=record['arguments'];record['half_pair_layout']={'recipe':hex(recipe),'width':size&65535,'height':size>>16,'pitch':pitch_rows&65535,'rows':pitch_rows>>16,'origin_x':origin&65535,'origin_y':origin>>16}
        if record['event']==218:
            recipe,stage,a,b=record['arguments'];signed=stage if stage<0x80000000 else stage-0x100000000
            record['half_pair']={'recipe':hex(recipe),'result':signed,'reason':HALF_PAIR_STAGES.get(signed,'unknown'),'detail':[a,b]}
        if record['event']==208:
            controller,route,kind,permission=record['arguments']
            record['physical_disp']={'controller':hex(controller),'route':hex(route),'adj_type':kind,'phase1_enabled_before_dispatch':permission}
        if record['event']==209:
            controller,route,handled,mode=record['arguments']
            record['disp_fallback']={'controller':hex(controller),'route':hex(route),'handled':handled,'host_mode':mode}
        if record['event']==89:
            key,reason,detail,value=record['arguments']
            record['ab_branch']={'key':hex(key),'reason':{1:'invalid-model',2:'non-shooting-context',3:'private-submenu',4:'owner-unavailable',5:'release',6:'hold',7:'duplicate-down',8:'navigate',9:'pending-navigation-stale-a1'}.get(reason,reason),'detail':hex(detail),'value':value}
        if record['event']==102:
            context,guard,a,b=record['arguments']
            record['rejection']={'context':hex(context),'guard':GUARDS.get(guard,guard),
                                 'guard_id':guard,'details':[a,b]}
        if record['event']==121:
            context,y,chroma,dimensions=record['arguments']
            record['image']={'context':hex(context),'y':hex(y),'chroma':hex(chroma),
                             'width':dimensions>>16,'height':dimensions&65535}
        if record['event'] in (122,123):
            context,y,chroma,count=record['arguments']
            record['cpu_samples']={'context':hex(context),'y_hash':f'{y:08x}',
                                   'chroma_hash':f'{chroma:08x}','pairs':count,
                                   'scope':'CPU samples only; not an encoded JPEG check'}
        if record['event']==124:
            context,stride,allocated,tone=record['arguments']
            record['layout']={'context':hex(context),'stride':stride,
                              'allocated_height':allocated,'stock_tone':tone}
        if record['event']==125:
            context,tone,mode,raw=record['arguments']
            record['request_identity']={'context':hex(context),'stock_tone':tone,'sequence_mode':mode,'raw_source':hex(raw)}
        if record['event']==197:
            recipe,tag,value,detail=record['arguments']
            if tag&0xff000000==0x4a000000:
                offset=(tag>>8)&0xfff;pair=tag&255
                diagnostic={'recipe':hex(recipe),'kind':'jpeg.handoff',
                    'boundary':'after' if tag&0x100000 else 'before'}
                if pair==0:diagnostic.update(descriptor=hex(offset),y=hex(value),c=hex(detail))
                elif pair==1:diagnostic.update(descriptor=hex(offset),size=[value&65535,value>>16],
                    stride=detail&65535,rows=detail>>16)
                elif pair==2:diagnostic.update(shot_word=hex(value),full_size=[detail&65535,detail>>16])
                elif pair==3:diagnostic.update(bank=hex(value),capacity=detail)
                record['border_diagnostic']=diagnostic
            elif tag==0x424f5244:
                record['border_diagnostic']={'recipe':hex(recipe),'kind':'rejection',
                    'stage':value,'reason':detail}
            elif tag==0x4d313030:
                record['border_diagnostic']={'recipe':hex(recipe),'kind':'module10.return',
                    'shot_word':hex(value),'main_width':detail&65535,'main_height':detail>>16}
            elif tag==0x53524353:
                record['border_diagnostic']={'recipe':hex(recipe),'kind':'jpeg.entry.descriptors',
                    'source_size':[value&65535,value>>16],
                    'extra_size':[detail&65535,detail>>16]}
            elif tag==0x504c414e:
                record['border_diagnostic']={'recipe':hex(recipe),'kind':'jpeg.entry.planes',
                    'source_y':hex(value),'main_y':hex(detail)}
            elif tag==0x42534453:
                record['border_diagnostic']={'recipe':hex(recipe),'kind':'backresize.descriptors',
                    'source_size':[value&65535,value>>16],
                    'main_size':[detail&65535,detail>>16]}
            elif tag==0x42534459:
                record['border_diagnostic']={'recipe':hex(recipe),'kind':'backresize.planes',
                    'source_y':hex(value),'main_y':hex(detail)}
        if record['event']==184:
            recipe,buffer_id,backing,result=record['arguments']
            record['pool_dispatch']={'recipe':hex(recipe),'buffer_id':buffer_id,'backing':hex(backing),
                'return':result,'successful_free_proven':False}
        if record['event'] in (82,83,84):
            key,screen,focus,packed=record['arguments']
            record['page_state']={'key':hex(key),'screen':{0:'closed',1:'films',2:'catalog',3:'stamp',4:'value'}.get(screen,screen),'focus':focus,'value':packed&0xffff,'error':packed>>16}
        if record['event']==112:
            slot,packed,sequence,revision=record['arguments']
            record['settings']={'slot':slot,'gain':packed&15,'spread':(packed>>4)&15,
                'threshold':(packed>>8)&15,'grain':(packed>>12)&15,'soft':(packed>>16)&15,
                'sequence':sequence,'renderer_revision':revision}
        if record['event']==114:
            peak,active,pixels,gate=record['arguments']
            record['highlight_energy']={'maximum':peak,'active_pixels':active,'image_pixels':pixels,'gate':gate}
        if record['event']==113:
            slot,source,sequence,namespace=record['arguments']
            record['provenance']={'slot':slot,'source':{0:'journal-v3',1:'defaults',2:'migrated-v2',3:'migrated-v1',4:'per-frame-snapshot'}.get(source,'unknown'),
                'sequence':sequence,'journal_namespace':namespace}
    return (h[2],h[6],h[5]),records

def capture_profiles(records):
    profiles=[];current=None
    def finish():
        marks=current['marks'];stages=[r['id'] for r in marks]
        valid=all(r['valid'] for r in marks)
        monotonic=all(b['ticks']>=a['ticks'] for a,b in zip(marks,marks[1:]))
        complete=stages==list(range(1,13)) and valid and monotonic
        bounds=len(marks)>=2 and stages[0]==1 and stages[-1]==12 and marks[0]['valid'] and marks[-1]['valid'] and marks[-1]['ticks']>=marks[0]['ticks']
        current.update(complete=complete,units='milliseconds',
            total_ticks=marks[-1]['ticks']-marks[0]['ticks'] if complete else None,
            total_seconds=(marks[-1]['ticks']-marks[0]['ticks'])/1000 if complete else None,
            entry_exit_ticks=marks[-1]['ticks']-marks[0]['ticks'] if bounds else None,
            intervals=[{'phase':PROFILE_INTERVALS[b['id']],'ticks':b['ticks']-a['ticks']}
                for a,b in zip(marks,marks[1:]) if b['id']==a['id']+1 and b['id'] in PROFILE_INTERVALS and a['valid'] and b['valid'] and b['ticks']>=a['ticks']])
        profiles.append(current)
    for record in records:
        event=record['event'];args=record['arguments']
        if event==150:
            context,packed,low,high=args;stage=packed&0x7fffffff
            if current is not None and (stage==1 or current['build_id']!=record['build_id'] or current['context']!=hex(context)):
                finish();current=None
            if current is None:current={'build_id':record['build_id'],'context':hex(context),'film':None,'marks':[]}
            current['marks'].append({'id':stage,'stage':PROFILE_STAGES.get(stage,stage),'valid':not bool(packed&0x80000000),'ticks':(high<<32)|low})
            if stage==12:finish();current=None
        elif current is not None and event==132 and current['context']==hex(args[0]):
            current['film']=args[1];current['grain_size']=args[2]
            packed=args[3];current['leak']={'gain':packed&255,'position':(packed>>8)&255,'spread':(packed>>16)&255,'variation':packed>>24}
        elif current is not None and event==126 and current['context']==hex(args[0]):
            current['raw_lifetime']={'status':args[1],'backing':hex(args[2]),'source':hex(args[3])}
        elif current is not None and event==138 and current['context']==hex(args[0]):
            current['cpu_plan']={'native_mask':args[1],'stages':args[2]};current['film']=args[3]
        elif current is not None and event==137 and current['context']==hex(args[0]):
            current['native_grain_quality']={'strength':args[1],'size':args[2],'noise_shaped':bool(args[3])}
        elif current is not None and event==135 and current['context']==hex(args[0]):
            current['native_completed']={'mask':args[1],'sequence':args[2],'film':args[3]}
        elif current is not None and event==134 and current['context']==hex(args[0]):
            current['texture_backend']={'batch_pixels':args[1],'cache_hits':args[2],
                'cache_selected':bool(args[3]&1),'batch_compiled':bool(args[3]&2),
                'cache_supplied':bool(args[3]&4),'batch_rejected':bool(args[3]&8)}
        elif current is not None and event==102:current['rejection']=record.get('rejection')
    if current is not None:finish()
    return profiles

def lifecycle_profiles(records):
    rows=[];active={};observations={};hdf_observations={}
    for record in records:
        event=record['event']
        if event==198:
            recipe,tag,packed,sequence=record['arguments']
            if tag==0x49535001:
                status=packed>>16
                observations[(record['build_id'],recipe)]={'status':status,
                    'mode':'observer' if status==7 else 'unknown',
                    'stock_tone':packed&65535,'sequence':sequence,
                    'effects_offloaded':False if status==7 else None}
            elif tag==0x48444601:
                flags=packed>>8
                hdf_observations[(record['build_id'],recipe)]={'strength':packed&255,
                    'flags':flags,'snapshot_loaded':bool(flags&1),'gate_passed':bool(flags&2),
                    'settings_written':bool(flags&4),'processing_returned_success':bool(flags&8),
                    'processing_failed':bool(flags&16),'si_rejected':bool(flags&32),
                    'context_rejected':bool(flags&64),'load_failed':bool(flags&128),
                    'shooting_pointer':hex(sequence)}
            continue
        if event not in range(190,195):continue
        recipe,low,high,result=record['arguments'];key=(record['build_id'],recipe)
        if event==193 or key not in active:
            row={'build_id':key[0],'recipe':hex(recipe),'marks':{},'clock_valid':True,'file_save_proven':False}
            if key in hdf_observations:row['hdf']=hdf_observations[key]
            if key in observations:row['isp']=observations.pop(key)
            rows.append(row);active[key]=row
        row=active[key];valid=not bool(high&0x80000000)
        row['clock_valid']&=valid
        row['marks'][event]={'ticks':((high<<32)|low) if valid else None,'result':result}
    for row in rows:
        marks=row.pop('marks')
        row['render_begin_ticks']=marks.get(193,{}).get('ticks')
        row['jpeg_wait_return_ticks']=marks.get(192,{}).get('ticks')
        for field,a,b in [('render_ticks',193,194),('jpeg_submit_ticks',190,191),('jpeg_wait_ticks',191,192)]:
            x=marks.get(a,{}).get('ticks');y=marks.get(b,{}).get('ticks')
            row[field]=y-x if x is not None and y is not None and y>=x else None
        result=marks.get(194,{}).get('result')
        row['render_result']=None if result is None else result-(1<<32) if result&(1<<31) else result
        row['jpeg_event_received']=marks.get(192,{}).get('result')==1
        row['submit_return_observed']=191 in marks
        row['wait_return_observed']=192 in marks
    return rows

def file_profiles(records):
    rows=[];active={}
    for record in records:
        event=record['event'];args=record['arguments']
        if event not in (180,181,182,195,196,197):continue
        task=args[0] if event in (195,196,197) else args[3] if event==181 else args[2]
        key=(record['build_id'],task)
        if event==195 or key not in active:
            row={'build_id':key[0],'descriptor':hex(task),'callbacks':[],
                 'durable_file_proven':False,'recipe_association_proven':False,
                 'service_ticks':None,'service_result':None,'clock_valid':True}
            rows.append(row);active[key]=row
        row=active[key]
        if event in (195,196):
            _,low,high,packed=args;valid=not bool(packed&0x80000000)
            row['clock_valid']&=valid;ticks=(high<<32)|low if valid else None
            if event==195:row['begin_ticks']=ticks
            else:
                row['end_ticks']=ticks;row['service_result']=packed&0x7fffffff
                begin=row.get('begin_ticks')
                if begin is not None and ticks is not None and ticks>=begin:row['service_ticks']=ticks-begin
        elif event==181:row['callbacks'].append({'object':hex(args[0]),'opcode':hex(args[1]),'payload_status':args[2]})
        elif event==182:row['bridge_result']=args[1];row['bridge_result_byte']=args[3]
        elif event==197:row['native_kind']=args[1];row['native_metadata']=hex(args[2])
    return rows

def be_file_profiles(records):
    """Actual BE blocking service; context cookies are not recipe addresses."""
    rows=[];active={}
    for record in records:
        event=record['event']
        if event not in (200,201,202,203):continue
        cookie,a,b,result=record['arguments'];key=(record['build_id'],cookie)
        if event==200 or key not in active:
            row={'build_id':key[0],'context_cookie':hex(cookie),'recipe_association_proven':False,
                 'durable_file_proven':False,'clock_valid':True,'service_ticks':None}
            rows.append(row);active[key]=row
        row=active[key]
        if event==203:
            row.update(context_vptr=hex(a),parameters_pointer=hex(b),shooting_pointer=hex(result))
        elif event==202:
            row.update(stage_id=a,stage={0:'success',2:'open-error',4:'metadata-error',6:'close-error'}.get(a,'unknown'),
                       frame_slot=b,service_result=result)
        else:
            valid=not bool(result&0x80000000);row['clock_valid']&=valid
            ticks=((b<<32)|a) if valid else None
            row['begin_ticks' if event==200 else 'end_ticks']=ticks
            begin=row.get('begin_ticks');end=row.get('end_ticks')
            if begin is not None and end is not None and end>=begin:row['service_ticks']=end-begin
    return rows

def decode_logs(pages):
    groups={};rejected=0;conflicts=0
    for data in pages:
        parsed=page_records(data)
        if parsed is None:rejected+=1;continue
        (build,channel,sequence),records=parsed
        groups.setdefault((build,channel),[]).append((sequence,records))
    records=[]
    for pages in groups.values():
        pages.sort(key=lambda item:item[0],reverse=True)
        merged={r['sequence']:r for r in pages[0][1]}
        for _,entries in pages[1:]:
            overlap=[r for r in entries if r['sequence'] in merged]
            # A sequence reset can leave stale pages from an earlier session.
            # Extend history only when overlapping CRC-valid records agree.
            if not overlap or any(merged[r['sequence']]!=r for r in overlap):
                conflicts+=1;continue
            merged.update({r['sequence']:r for r in entries})
        records.extend(merged.values())
    records.sort(key=lambda r:(r['build_id'],r['channel'],r['sequence']))
    return {'capture_profiles':capture_profiles(records),'lifecycle_profiles':lifecycle_profiles(records),'file_profiles':file_profiles(records),'be_file_profiles':be_file_profiles(records),'schema':'m10v-gr3-sd-debug/v1','build_ids':sorted({r['build_id'] for r in records}),
            'rejected_pages':rejected,'unmerged_pages':conflicts,'records':records}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('files',nargs='+',type=Path)
    args=parser.parse_args();result=decode_logs([p.read_bytes() for p in args.files])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['records']:raise SystemExit(1)
