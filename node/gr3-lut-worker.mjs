import {readFileSync} from 'node:fs';
import { parentPort, workerData } from 'node:worker_threads';
import { parseCube, sampleLut } from '../.runtime/grlife/web/recipes/custom-recipe-core.js';
import { fitLookChoices, fitSummary } from '../.runtime/grlife/web/firmware-store/film-fit.js';
import {assessFit,guardCandidate,approximateTarget,detectTargetStyle,monochromeFit} from './gr3-fit-quality.mjs';
import {sha256,sealReport} from './gr3-fit-binding.mjs';
try {
 const lut=parseCube(workerData.cube,workerData.filename),original=(r,g,b)=>sampleLut(lut,r,g,b);
 const originalTarget=rgb=>original(...rgb),strength=workerData.approximationStrength;
 const target=strength===undefined?originalTarget:approximateTarget(originalTarget,strength);
 const sourceSha256=workerData.sourceSha256||sha256(workerData.cube);
 const sourceFiles=['./gr3-fit-quality.mjs','./gr3-fit-binding.mjs','./gr3-fit-envelope.mjs','./gr3-lut-worker.mjs','../.runtime/grlife/web/firmware-store/film-fit.js','../.runtime/grlife/web/firmware-store/film-camera-model.js','../.runtime/grlife/web/recipes/custom-recipe-core.js',...(workerData.inputType==='xmp'?['./gr3-xmp-fit.mjs','./gr3-xmp-worker.py','../vendor/gr4/gr4_editor/offline_look.py']:[])];
 const provenance={references:[{project:'Darkslide GR',commit:'5f57f6dba7992b537344ae49025846d4c4838b47',methods:'factory envelope and explicit convergence'},{project:'Ricoh GRMod',commit:'1f4216e4b80d737a3e670c0b6169398f57598b5e',methods:'held-out grey/skin guard and dedicated monochrome'}],fitter_sources:Object.fromEntries(sourceFiles.map(file=>[file,sha256(readFileSync(new URL(file,import.meta.url)))])),input_type:workerData.inputType||'cube',...(workerData.provenance||{}),...(strength===undefined?{}:{explicit_approximation:true,retained_source_strength:strength})};
 let fits;
 try{if(detectTargetStyle(target)!=='colour'){const look=monochromeFit(target);fits={tone:look,gamut:structuredClone(look)};}else fits=fitLookChoices((r,g,b)=>target([r,g,b]));}catch(error){parentPort.postMessage({error:error.message,approximation_available:true});process.exit(0);}
 const choices=Object.fromEntries(Object.entries(fits).map(([id,fit])=>{
 const look={matrixQ13:fit.matrixQ13,postQ512:fit.postQ512,curves:fit.curves,knots:fit.knots};
 const quality=assessFit({look,target,model:workerData.model,sourceSha256,provenance,envelope:workerData.envelope,originalTarget:strength===undefined?undefined:originalTarget});
 return [id,{look,note:{lutName:workerData.filename.slice(0,80),...(fit.prediction?fitSummary(fit):{fitMean:quality.validation.mean,fitMax:quality.validation.max,algorithm:'monochrome-rank-one-monotone-v1'})},quality}];}));
 // Both actual fits are optimization candidates; protect grey/skin on held-out samples.
 const baselines={...choices};
 for(const id of ['tone','gamut']){const other=id==='tone'?'gamut':'tone',base=baselines[id],next=baselines[other];const guard=next.quality.envelope.encodable?guardCandidate(base.quality,next.quality):{accepted:false,reasons:['candidate outside representation envelope']};const selected=guard.accepted?next:base;
 const {report_sha256,...body}=selected.quality;
 choices[id]={...selected,quality:sealReport({...body,requested_choice:id,selected_candidate:guard.accepted?other:id,optimization:{accepted:guard.accepted,reasons:guard.reasons},candidates:[id,other].map(k=>({id:k,parameter_sha256:(k===id?base:next).quality.parameter_sha256,validation:(k===id?base:next).quality.validation,groups:(k===id?base:next).quality.groups}))})};
 }
 parentPort.postMessage({choices,provenance});
}catch(error){parentPort.postMessage({error:error.message});}
