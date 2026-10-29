import {validateQualityBinding} from './gr3-fit-binding.mjs';
import {deriveFitEnvelope,envelopeViolations} from './gr3-fit-envelope.mjs';
import {assignFilmSlots} from './gr3-film-plan.mjs';
import {auditStockIntent} from './gr3-stock-audit.mjs';
import {auditFilmTexture} from './gr3-film-texture.mjs';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {inspectOfficial} from './firmware.mjs';
import {createStorePlan} from './gr3-store-plan.mjs';
import {runGr3Runtime} from './gr3-runtime.mjs';
import {auditGr3Candidate} from './gr3-candidate-audit.mjs';
import {createStockEdits} from './gr3-stock-presets.mjs';
import {planRawNr} from './gr3-raw-nr.mjs';
import {applyPatchPlan} from './gr3-patch-plan.mjs';
import {portNativeToGr3x} from './gr3x-native-port.mjs';
const baseFeatures=['recipes','timestamp','aspect','film','level'];
const nativeFeatures=['presets','negativeGrain','rawNr'];
const known=['variant','features','recipes','filmIds','filmLibrary','filmTexture','stockPresets','negativeGrainMenu','rawNr'];
const need=(v,m)=>{if(!v)throw new Error(m);};
const hash=b=>createHash('sha256').update(b).digest('hex');
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
export function normalizeCustomization(input){
 need(input&&typeof input==='object'&&!Array.isArray(input)&&Object.keys(input).every(k=>known.includes(k)),'方案包含未知字段');
 need(!input.features?.includes('filmbay'),'旧 SD 胶片库方案已废弃，不可用于固件构建');
 need(input.variant==='street'&&Array.isArray(input.features)&&input.features.length>0&&new Set(input.features).size===input.features.length&&
 input.features.every(f=>[...baseFeatures,...nativeFeatures].includes(f)),'方案功能或机型无效');
 const selection=structuredClone(input);selection.features=[...baseFeatures,...nativeFeatures].filter(f=>input.features.includes(f));
 selection.stockPresets??=[];selection.negativeGrainMenu??=false;selection.rawNr??={mode:'stock'};
 need(Array.isArray(selection.stockPresets)&&selection.stockPresets.length<=12&&typeof selection.negativeGrainMenu==='boolean','原厂预设配置无效');
 need(!selection.stockPresets.length||selection.features.includes('presets'),'请启用原厂预设功能');
 need(!selection.negativeGrainMenu||selection.features.includes('negativeGrain'),'请启用负片颗粒功能');
 need(selection.rawNr.mode==='stock'||selection.features.includes('rawNr'),'请启用RAW降噪功能');
 const occupied=new Set(selection.features.includes('film')?[2,8,9,10,11]:[]);
 if(selection.features.includes('recipes'))for(const recipe of selection.recipes||[]){
  const slot={'builtin-0b':1,'builtin-11':7,'builtin-15':11,'builtin-16':12}[recipe.slotId];if(slot)occupied.add(slot);
 }
 need(!selection.stockPresets.some(p=>occupied.has(p.slot)),'原厂预设位置已被胶片或配方占用');
 const upstreamFeatures=selection.features.filter(f=>baseFeatures.includes(f));
 const plan=upstreamFeatures.length?createStorePlan({...selection,features:upstreamFeatures}):null;
 need(selection.features.includes('film')||!Object.values(selection.filmTexture||{}).some(e=>e.grain||e.hdf),'请启用胶片后设置质感');
 return {schema:'m10v-gr3-customization/v2',selection:canonical(selection),upstreamPlan:plan};
}
function editsFor(source,config){return [...createStockEdits(source,{presets:config.selection.stockPresets,negativeGrainMenu:config.selection.negativeGrainMenu}),
 ...planRawNr(source,config.selection.rawNr)];}
export async function prepareCustomization(source,input,options={}){
 const report=inspectOfficial(source);
 const targetFitModel=options.fitReportModel||(report.model==='GR IIIx'?'gr3x':'gr3');
 for(const look of input.filmLibrary||[])if(look.quality){
  need(look.quality.model===targetFitModel,'拟合报告与固件机型不匹配');
  validateQualityBinding(look,look.quality);
  need(envelopeViolations(look,deriveFitEnvelope(source)).length===0,'拟合参数超出原厂表达范围');
 }
 if(report.model==='GR IIIx'){
  const gr3=readFileSync(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url)),prepared=await prepareCustomization(gr3,input,{...options,fitReportModel:'gr3x'});
  const engineSources=['gr3x-native-port.mjs','gr3-customization.mjs'].map(n=>[n,hash(readFileSync(new URL(n,import.meta.url)))]);
  const configuration_sha256=hash(JSON.stringify({source:report.sha256,gr3_source:hash(gr3),gr3_configuration_sha256:prepared.configuration_sha256,engineSources}));
  return {...prepared,configuration_sha256,source_sha256:report.sha256,filename:'fwdc243b.bin',gr3_configuration_sha256:prepared.configuration_sha256};
 }
 const config=normalizeCustomization(input),edits=editsFor(source,config);
 const upstream=config.upstreamPlan?(await runGr3Runtime(source,config.upstreamPlan,'prepare',undefined,options)).receipt:null;
 const diffusionRequested=Object.values(config.selection.filmTexture||{}).some(e=>e.hdf>0);
 const blockers=[...(upstream?.blockers||[]),...(diffusionRequested?['gr3_diffusion_descriptor_isolation_not_verified']:[])];
 const engineSources=[
  'gr3-fit-binding.mjs','gr3-fit-envelope.mjs','firmware.mjs','gr3-frames.mjs','gr3-store-plan.mjs','gr3-film-plan.mjs',
  'gr3-runtime.mjs','gr3-runtime-worker.py','gr3-candidate-audit.mjs',
  'gr3-stock-audit.mjs','gr3-film-texture.mjs','gr3-customization.mjs',
  'gr3-patch-plan.mjs','gr3-stock-presets.mjs','gr3-raw-nr.mjs',
  '../scripts/gr3_aspect_overlay.py','../native/gr3/m10v_aspect.c',
  '../native/gr3/m10v_aspect_hooks.S','../native/gr3/m10v_aspect_dng.c',
 ].map(n=>[n,hash(readFileSync(new URL(n,import.meta.url)))]);
 const configuration_sha256=hash(JSON.stringify({source:report.sha256,config,engineSources,upstream:upstream?.configuration_sha256}));
 return {schema:'m10v-gr3-customization-preparation/v2',ready:blockers.length===0&&(upstream?.ready??edits.length>0),
 configuration_sha256,source_sha256:report.sha256,filename:'fwdc239b.bin',features:config.selection.features,
 fit_reports:config.selection.features.includes('film')?assignFilmSlots(config.selection.filmIds||['ektar100','gold200','pro400h','portra400','vision3-250d'],config.selection.filmLibrary||[]).filter(f=>f.id.startsWith('lut-')).map(f=>({id:f.id,assessment:f.assessment,report:f.quality||null,validation_used:f.quality?(f.mode==='bleach'?{overall:f.quality.knot_validation,groups:f.quality.knot_groups}:{overall:f.quality.validation,groups:f.quality.groups}):null,encoded_curve_form:f.mode==='bleach'?'knots':'curves'})):[],
 camera_tested:false,patch_count:edits.length,affected_languages:[...new Set(edits.flatMap(e=>e.affectedLanguages||[]))],
 runtime:config.upstreamPlan?'locally_cached_grlife_browser_core + m10v audited overlays':'m10v source-locked native edits',
 blockers:blockers.length?blockers:!upstream&&!edits.length?['no_actual_customization_selected']:[]};
}
export async function buildCustomization(source,input,accepted,options={}){
 const prepared=await prepareCustomization(source,input,options);
 need(prepared.ready&&accepted===prepared.configuration_sha256,'方案已变化或预检未通过，请重新预检');
 if(inspectOfficial(source).model==='GR IIIx'){
  const gr3=readFileSync(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url));
  const result=await buildCustomization(gr3,input,prepared.gr3_configuration_sha256,{...options,fitReportModel:'gr3x'});
  const ported=portNativeToGr3x(gr3,source,result.candidate),candidate=ported.candidate;
  return {candidate,receipt:{...result.receipt,...prepared,candidate_sha256:hash(candidate),candidate_bytes:candidate.length,
   audit:{schema:'m10v-gr3x-final-audit/v1',sourceSha256:hash(source),candidateSha256:hash(candidate),candidateBytes:candidate.length,
    rtosGrowth:ported.receipt.rtos_growth,checks:ported.receipt.checks,reference_audit:'gr3_audit'},gr3_audit:result.receipt.audit,gr3x_port:ported.receipt}};
 }
 const config=normalizeCustomization(input),edits=editsFor(source,config);
 const result=config.upstreamPlan?await runGr3Runtime(source,config.upstreamPlan,'build',undefined,options):{candidate:source,receipt:{}};
 if(config.upstreamPlan){const audit=auditGr3Candidate(source,result.candidate);
 need(audit.candidateSha256===result.receipt.candidate_sha256,'兼容运行时回执与独立回读不一致');
 const film=config.upstreamPlan.features.find(f=>f.id==='film');
 if(film)auditFilmTexture(source,result.candidate,film.configuration,config.selection.features.includes('timestamp'));}
 const merged=applyPatchPlan(source,result.candidate,edits);
 const candidate=merged.candidate;
 merged.audit.stockIntent=auditStockIntent(source,candidate,config.selection);
 merged.audit.candidateSha256=hash(candidate);
 return {candidate,receipt:{...result.receipt,...prepared,candidate_sha256:hash(candidate),
   candidate_bytes:candidate.length,audit:merged.audit,status:'OFFLINE_VERIFIED_EXPERIMENTAL_CANDIDATE'}};
}
