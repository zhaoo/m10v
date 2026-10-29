import {envelopeViolations} from './gr3-fit-envelope.mjs';
import {STANDARD_LOOK_Q13,BASE_GAMMA,MID_INDEX} from '../.runtime/grlife/web/firmware-store/film-camera-model.js';
import {filmRender,standardRender,deltaE2000,expandKnots,fitSamples,gamutSamples,knotsOf} from '../.runtime/grlife/web/firmware-store/film-fit.js';
import {encodedParameters,parameterHash,sealReport,sha256} from './gr3-fit-binding.mjs';
export {encodedParameters,parameterHash,validateQualityBinding} from './gr3-fit-binding.mjs';
export const SAMPLE_VERSION='m10v-heldout-linear-v1';
export const POLICY_VERSION='m10v-grey-skin-guard-v1';
const clamp=v=>Math.max(0,Math.min(1,v));
// The training manifest is the actual upstream fitter input. Validation excludes exact matches.
let sampleCache;
export function qualitySamples(){
 if(sampleCache)return sampleCache;
 const training=[...fitSamples().samples,...gamutSamples()].map(rgb=>({rgb}));const seen=new Set(training.map(v=>JSON.stringify(v.rgb)));const validation=[];
 const add=(rgb,group)=>{if(!seen.has(JSON.stringify(rgb)))validation.push({rgb,group});};
 for(let i=0;i<81;i++){const v=.18*2**(-6.93+i*10.91/80);add([v,v,v],'grey');}
 for(const base of [[.39,.21,.14],[.61,.38,.27],[.18,.10,.075],[.72,.49,.37]])for(let i=0;i<13;i++)add(base.map(v=>v*2**(-2.37+i*.347)),'skin');
 for(let i=0;i<72;i++){const h=i/72*6,k=Math.floor(h),f=h-k;const rgb=[[1,f,0],[1-f,1,0],[0,1,f],[0,1-f,1],[f,0,1],[1,0,1-f]][k];add(rgb.map(v=>.0037+v*.437),'saturated');}
 let seed=0x281026;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/2**32;};for(let i=0;i<600;i++)add([random()**2*1.2,random()**2*1.2,random()**2*1.2],'coverage');
 sampleCache={training,validation};return sampleCache;
}
function stats(values){const sorted=[...values].sort((a,b)=>a-b);return {count:values.length,mean:values.reduce((s,v)=>s+v,0)/values.length,p95:sorted[Math.ceil(values.length*.95)-1],max:sorted.at(-1)};}
export function guardCandidate(base,next){
 const reasons=[];if(!(next.validation.mean<base.validation.mean-1e-6)||next.validation.p95>base.validation.p95+1e-6)reasons.push('no independent mean/P95 improvement');
 for(const key of ['grey','skin'])for(const metric of ['mean','max'])if(next.groups[key][metric]>base.groups[key][metric]+.05)reasons.push(key+' '+metric+' regression');
 if(base.knot_validation&&next.knot_validation){if(next.knot_validation.mean>base.knot_validation.mean+1e-6||next.knot_validation.p95>base.knot_validation.p95+1e-6)reasons.push('knot validation regression');for(const key of ['grey','skin'])for(const metric of ['mean','max'])if(next.knot_groups[key][metric]>base.knot_groups[key][metric]+.05)reasons.push('knot '+key+' '+metric+' regression');}return {accepted:reasons.length===0,reasons};
}
export const approximateTarget=(target,strength)=>{if(!Number.isFinite(strength)||strength<0||strength>1)throw Error('invalid convergence strength');return rgb=>target(rgb).map((v,c)=>rgb[c]+strength*(v-rgb[c]));};
// Exact Standard frame fixture, also used by fit_gr3_native_film_targets.py.
// These are native signed fields, not the GRLife absolute look matrix.
const FRAME_CCA=[436,-184,4,-48,400,-96,1,-104,359];
const FRAME_CSP=[77,150,29,-43,-85,128,128,-107,-21];
const multiply3=(a,b)=>Array.from({length:9},(_,i)=>[0,1,2].reduce((sum,k)=>sum+a[Math.floor(i/3)*3+k]*b[k*3+i%3],0));
function inverse3(m){
 const [a,b,c,d,e,f,g,h,i]=m,co=[e*i-f*h,c*h-b*i,b*f-c*e,f*g-d*i,a*i-c*g,c*d-a*f,d*h-e*g,b*g-a*h,a*e-b*d];
 const det=a*co[0]+b*co[3]+c*co[6];if(!Number.isFinite(det)||Math.abs(det)<1e-12)throw Error('singular Standard frame model');return co.map(v=>v/det);
}
export function relativeFrameLook(absolute){
 encodedParameters(absolute);
 const matrixQ13=multiply3(absolute.matrixQ13,inverse3(STANDARD_LOOK_Q13)).map(v=>Math.round(v*8192)||0);
 for(let r=0;r<3;r++)matrixQ13[r*3+r]+=8192-matrixQ13.slice(r*3,r*3+3).reduce((s,v)=>s+v,0);
 const result={...absolute,matrixQ13};encodedParameters(result);return result;
}
export function nativeFrameModel(look){
 const encoded=encodedParameters(look),cca=multiply3(encoded.matrixQ13,FRAME_CCA).map(v=>Math.floor((v+4096)/8192)),csp=multiply3(FRAME_CSP,encoded.postQ512).map(v=>Math.floor((v+256)/512));
 const violations=[];if(cca.some(v=>v< -2048||v>2047))violations.push('native signed12 CCA overflow');if(csp.some(v=>v< -256||v>255))violations.push('native signed9 CSP overflow');
 return {matrix:multiply3(multiply3(cca,inverse3(FRAME_CCA)),STANDARD_LOOK_Q13.map(v=>v/8192)),post:multiply3(inverse3(FRAME_CSP),csp),violations,
  contract:{schema:'m10v-relative-frame-fit/v1',baseline:'official Standard frame fixture; physical calibration unverified',cca_signed12:cca,csp_signed9:csp,base_cca_signed12:FRAME_CCA,base_csp_signed9:FRAME_CSP,composition:'CCA=round(relativeQ13*stockCCA/8192); CSP=round(stockCSP*postQ512/512)',gamma:'original baseQ14/64 integer correction lookup; original 256-entry packer'}};
}
function frameRenderer(frame,curves){
 const mapped=curves.map(curve=>BASE_GAMMA.map(v=>{const index=v>>6,frac=v&63;return index>=255?curve[255]:(curve[index]*(64-frac)+curve[index+1]*frac+32)>>6;}));
 return linear=>{
  const mixed=[0,1,2].map(r=>[0,1,2].reduce((sum,c)=>sum+frame.matrix[r*3+c]*linear[c],0));
  const rgb=mixed.map((v,c)=>{const x=Math.max(0,Math.min(255,v*MID_INDEX/.18)),i=Math.min(254,Math.floor(x)),fraction=x-i;return (mapped[c][i]*(1-fraction)+mapped[c][i+1]*fraction)/16384;});
  return [0,1,2].map(r=>clamp([0,1,2].reduce((sum,c)=>sum+frame.post[r*3+c]*rgb[c],0)));
 };
}
export function assessFit({look,target,model='gr3',sourceSha256,provenance={},originalTarget,envelope,frameRelative=false}){
 if(!['gr3','gr3x'].includes(model))throw Error('unsupported fit model');const encoded=encodedParameters(look),expanded=encoded.knots.map(expandKnots),frame=frameRelative?nativeFrameModel(look):null,m=frame?.matrix??encoded.matrixQ13.map(v=>v/8192),p=frame?.post??encoded.postQ512.map(v=>v/512);
 const render=frame?frameRenderer(frame,encoded.curves):rgb=>filmRender(m,encoded.curves,p,rgb),renderKnots=frame?frameRenderer(frame,expanded):rgb=>filmRender(m,expanded,p,rgb);
 if(frame)provenance={...provenance,native_frame:frame.contract};
 const groups={},knotGroups={},full=[],knotErrors=[],movement=[],targetMovement=[];let outside=0,mono=0,toned=0;
 for(const {rgb,group} of qualitySamples().validation){const input=standardRender(rgb).map(clamp),expected=target(input);if(!Array.isArray(expected)||expected.length!==3||expected.some(v=>!Number.isFinite(v)))throw Error('nonfinite target');if(expected.some(v=>v<0||v>1))outside++;
 const actual=render(rgb),knot=renderKnots(rgb),error=deltaE2000(actual,expected);(groups[group]??=[]).push(error);full.push(error);const knotError=deltaE2000(knot,expected);knotErrors.push(knotError);(knotGroups[group]??=[]).push(knotError);if(originalTarget){movement.push(deltaE2000(actual,originalTarget(input)));targetMovement.push(deltaE2000(expected,originalTarget(input)));}
 if(Math.max(...expected)-Math.min(...expected)<.002)mono++;else if(Math.max(...expected)-Math.min(...expected)<.08)toned++;
 }
 const violations=[...envelopeViolations(encoded,envelope),...(frame?.violations||[])];
 const diff=encoded.curves.flatMap((c,k)=>c.map((v,i)=>Math.abs(v-expanded[k][i])));
 return sealReport({schema:'m10v-gr3-fit-quality/v1',fitter_version:'m10v-guarded-joint-v1',model,official_firmware:model==='gr3'?'2.10':'1.60',source_sha256:sourceSha256,parameter_sha256:parameterHash(encoded),sample_version:SAMPLE_VERSION,samples:{training_count:qualitySamples().training.length,validation_count:full.length,training_sha256:sha256(qualitySamples().training),validation_sha256:sha256(qualitySamples().validation),overlap_count:0},policy_version:POLICY_VERSION,policy:{minimum_mean_improvement:1e-6,maximum_p95_regression:1e-6,maximum_grey_skin_mean_or_max_regression:.05,advisory_mean_warning:5},domain:'Standard display-referred sRGB approximation; scene-linear samples, D65, CIEDE2000',camera_verified:false,validation:stats(full),knot_validation:stats(knotErrors),knot_groups:Object.fromEntries(Object.entries(knotGroups).map(([k,v])=>[k,stats(v)])),groups:Object.fromEntries(Object.entries(groups).map(([k,v])=>[k,stats(v)])),envelope:{encodable:violations.length===0,violations,policy:envelope||'protocol-only-unassessed-factory-envelope',matrix:'signed int16, exact Q13/Q512 row sums',curves:'monotone unsigned 14-bit',endpoints:encoded.curves.map(c=>[c[0],c[255]]),target_outside_unit_cube:outside,clipping_definition:'model clamps encoded output to [0,1]; target outside [0,1] counted before Lab clamp'},reconstruction:{matrix_quantization:'input parameters already quantized; no unquantized matrix available',max_curve_units:Math.max(...diff),mean_curve_units:diff.reduce((s,v)=>s+v,0)/diff.length},style:detectTargetStyle(target),quality_hint:full.reduce((s,v)=>s+v,0)/full.length>5?'visible mismatch likely; inspect preview':'inspect preview',...(originalTarget?{approximation_to_original:stats(movement),approximate_target_to_original_target:stats(targetMovement)}:{}),provenance});
}

// Rank-one colour targets cannot use an inverse post matrix. Fit a grey camera
// input and three monotone output curves instead; no singular-matrix inversion.
export function detectTargetStyle(target){
 const values=qualitySamples().validation.filter(v=>v.group==='coverage').slice(0,100).map(({rgb})=>target(standardRender(rgb).map(clamp)));
 if(values.every(v=>Math.max(...v)-Math.min(...v)<.002))return 'neutral-monochrome';
 const mean=[0,1,2].map(c=>values.reduce((s,v)=>s+v[c],0)/values.length),vectors=values.map(v=>v.map((x,c)=>x-mean[c]));const axis=vectors.reduce((best,v)=>v.reduce((s,x)=>s+x*x,0)>best.reduce((s,x)=>s+x*x,0)?v:best,[0,0,0]),norm=axis.reduce((s,x)=>s+x*x,0);
 let residual=0,total=0;for(const v of vectors){const scale=v.reduce((s,x,c)=>s+x*axis[c],0)/(norm||1);for(let c=0;c<3;c++){residual+=(v[c]-scale*axis[c])**2;total+=v[c]**2;}}
 return total>1e-6&&residual/total<1e-4?'toned-monochrome':'colour';
}
export function monochromeFit(target){
 const row=[0,1,2].map(c=>Math.round(.2126*STANDARD_LOOK_Q13[c]+.7152*STANDARD_LOOK_Q13[c+3]+.0722*STANDARD_LOOK_Q13[c+6]));row[1]+=8192-row.reduce((s,v)=>s+v,0);
 const curves=[0,1,2].map(c=>{let floor=0;return Array.from({length:256},(_,i)=>{const value=target([i/256,i/256,i/256])[c];if(!Number.isFinite(value))throw Error('nonfinite monochrome target');floor=Math.max(floor,Math.round(clamp(value)*16383));return floor;});});
 return {matrixQ13:[...row,...row,...row],postQ512:[512,0,0,0,512,0,0,0,512],curves,knots:curves.map(knotsOf)};
}
