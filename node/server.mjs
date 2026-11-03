import {sendFirmwareDownload} from './firmware-download.mjs';
import {requireGRemotePackageDownload} from './gr3-gremote-package.mjs';
import {createFirmwareBuildQueue} from './firmware-build-queue.mjs';
import {checkWebBuild,verifyWebBackup,requireWebDownload} from './firmware-web-safety.mjs';
import {prepareCheckedNative,readCheckedProject} from './firmware-checked-build.mjs';
import {isolatedFirmwareJob} from './firmware-isolated-build.mjs';
import {ANNIVERSARY_DOWNGRADE_PROFILES,prepareAnniversaryDowngrade} from './gr3-anniversary-downgrade.mjs';
import {readAnniversarySources} from './anniversary-downgrade-sources.mjs';
import {checkDowngradeCamera,anniversaryDowngradeJob,requireAnniversaryDownload} from './anniversary-downgrade-jobs.mjs';
import {firmwareReleasePolicy,releaseRequestLocked,requireReleaseBaseline} from './firmware-release-policy.mjs';
import {firmwareSkillArchive} from './firmware-skill.mjs';
import {handleGr2NativeRequest} from './gr2-native-routes.mjs';
import {bindPowerPreparation,applyPowerImages,previewPowerImages} from './gr3-power-images.mjs';
import {createHash} from 'node:crypto';
import {handleGr4CustomizationRequest} from './gr4-customization.mjs';
import {handleGr4NativeRequest,gr4SdLibraryHtml} from './gr4-native-routes.mjs';
import {prepareGr3Bridge,exportGr3Bridge} from './gr3-bridge.mjs';
import {exportSdFilms} from './gr3-sd-film-export.mjs';
import {renderChangelog} from './changelog.mjs';
import { fitXmp } from './gr3-xmp-fit.mjs';
import { prepareCustomization, buildCustomization } from './gr3-customization.mjs';
import { stockPresetCapabilities } from './gr3-stock-presets.mjs';
// Backend binds loopback; an explicit public origin supports a trusted reverse proxy.
import { randomBytes } from 'node:crypto';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { createBackup, inspectBackup, restoreBytes } from './backup.mjs';
import { inspectOfficial } from './firmware.mjs';
import {resolveBuildSource} from './firmware-build-source.mjs';
import { shutdownCatalog } from './features.mjs';
import { Store } from './storage.mjs';
import { listSdVolumes, resolveSdVolume } from './sd-volumes.mjs';
import { prepareOfficialSd } from './sd-write.mjs';
import { analyzeStreetCandidate, buildStreetCandidate } from './candidate.mjs';
import { analyzeVersionProbe } from './version-candidate.mjs';
import { createRegistry } from './platform/adapter-registry.mjs';
import { createGr3Adapter } from './adapters/gr3/index.mjs';
import { createGr4Adapter } from './adapters/gr4/index.mjs';
import { gr2Descriptor } from './adapters/gr2/index.mjs';
import { Gr4Runtime } from './gr4-runtime.mjs';
import { handleGr4Request } from './gr4-routes.mjs';
import {inspectModelFirmware,readModelOfficial} from './model-firmware.mjs';
import { createStorePlan } from './gr3-store-plan.mjs';
import { runGr3Runtime, runtimeAvailable } from './gr3-runtime.mjs';
import { auditGr3Candidate } from './gr3-candidate-audit.mjs';
import { fitCube } from './gr3-lut-fit.mjs';
import {nativeCatalog,readNativeOfficial,prepareNative,generateNative} from './gr3-native-library.mjs';
import {resolveIspEffectOptions} from './gr3-isp-effect-options.mjs';
import { prepare800T, build800T } from './gr3-800t-build.mjs';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const web = path.join(root, 'web');
const MAX_UPLOAD = 128 * 1024 * 1024;
const staticFiles = {
  '/support/': ['index.html', 'text/html; charset=utf-8'],
  '/support': ['index.html', 'text/html; charset=utf-8'],
  '/': ['gr3/index.html', 'text/html; charset=utf-8'],
  '/changelog.json': ['changelog.json', 'application/json; charset=utf-8'],
  '/guide/': ['guide.html', 'text/html; charset=utf-8'],
  '/guide': ['guide.html', 'text/html; charset=utf-8'],
  '/skills/': ['skills.html', 'text/html; charset=utf-8'],
  '/skills': ['skills.html', 'text/html; charset=utf-8'],
  '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
  '/styles.css': ['styles.css', 'text/css; charset=utf-8'],
};
const adapters = createRegistry([createGr3Adapter(), createGr4Adapter(), gr2Descriptor]);

function send(response, status, body, type = 'application/json; charset=utf-8', filename) {
  const bytes = Buffer.isBuffer(body) ? body : Buffer.from(JSON.stringify(body));
  response.writeHead(status, {
    'Content-Type': type, 'Content-Length': bytes.length,
    'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    ...(filename ? { 'Content-Disposition': `attachment; filename="${filename}"` } : {}),
  });
  response.end(bytes);
}

async function readBody(request, limit = MAX_UPLOAD) {
  const header = request.headers['content-length'];
  if (!/^(0|[1-9][0-9]*)$/.test(header || '')) throw new Error('missing or invalid Content-Length');
  const size = Number(header);
  if (!Number.isSafeInteger(size) || size > limit) throw new Error('upload exceeds limit');
  const chunks = [];
  let length = 0;
  for await (const chunk of request) {
    length += chunk.length;
    if (length > size) throw new Error('upload exceeds declared length');
    chunks.push(chunk);
  }
  if (length !== size) throw new Error('incomplete upload');
  return Buffer.concat(chunks, size);
}

export function createServer(store = new Store(path.join(root, 'data')),
  sd = { listSdVolumes, resolveSdVolume, prepareOfficialSd },
  gr4 = new Gr4Runtime(path.join(root, 'data', 'gr4')), {publicOrigin,queueOptions,downgradeSources=readAnniversarySources} = {}) {
  const buildQueue=createFirmwareBuildQueue(queueOptions);
  const downgradePlans=new Map();
  const readDowngradePlan=async model=>{
    if(!downgradePlans.has(model)){
      const pending=(async()=>{
        const {newSource,oldSource}=await downgradeSources(model);
        return Object.freeze(prepareAnniversaryDowngrade(newSource,oldSource,model));
      })();
      downgradePlans.set(model,pending);
      pending.catch(()=>{if(downgradePlans.get(model)===pending)downgradePlans.delete(model);});
    }
    return downgradePlans.get(model);
  };
  const cameraHeader=request=>{
    const raw=request.headers['x-m10v-camera'];if(!raw)return undefined;
    if(typeof raw!=='string'||raw.length>2048)throw Error('机身信息格式无效。');
    return JSON.parse(Buffer.from(raw,'base64').toString('utf8'));
  };
  let configuredOrigin=null;
  if(publicOrigin){
    const url=new URL(publicOrigin);
    if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.pathname!=='/'||url.search||url.hash)throw new Error('M10V_PUBLIC_ORIGIN must be a single HTTP(S) origin');
    configuredOrigin=url.origin;
  }
  const token = randomBytes(32).toString('base64url');
  const server = http.createServer(async (request, response) => {
    let buildSource;
    const readBuildOriginal=async id=>{
      const resolved=await readCheckedProject(store,id);
      buildSource=resolved.report.build_source;
      response.setHeader('X-M10V-Build-Source',Buffer.from(JSON.stringify(buildSource)).toString('base64'));
      return resolved.source;
    };
    // Feature builders must preserve the uploaded component versions. Never
    // disguise a different executable baseline with a raised package version.
    const sendBuild=(candidate,filename,audit)=>{
      requireWebDownload(candidate,audit);
      if(audit.filename!==filename)throw Error('下载文件名与校验记录不同。');
      response.setHeader('X-M10V-Firmware-Safety',Buffer.from(JSON.stringify(audit)).toString('base64'));
      return sendFirmwareDownload(request,response,candidate,filename);
    };
    const sendJobResult=result=>{
      if(result.audit?.schema==='m10v-gremote-delivery-safety/v1'){
        const audit=requireGRemotePackageDownload(result.candidate,result.audit);
        if(audit.filename!==result.filename)throw Error('GRemote 连接包文件名与校验记录不同。');
        for(const [name,value] of Object.entries(result.headers||{}))response.setHeader(name,value);
        return sendFirmwareDownload(request,response,result.candidate,result.filename);
      }
      if(result.audit?.schema==='m10v-anniversary-downgrade-safety/v1'){
        const audit=requireAnniversaryDownload(result.candidate,result.audit);
        if(audit.filename!==result.filename)throw Error('降级套件文件名与校验记录不同。');
        response.setHeader('X-M10V-Downgrade-Safety',Buffer.from(JSON.stringify(audit)).toString('base64'));
        return send(response,200,result.candidate,'application/zip',result.filename);
      }
      for(const [name,value] of Object.entries(result.headers||{}))response.setHeader(name,value);
      return sendBuild(result.candidate,result.filename,result.audit);
    };
    const waitForBuild=async job=>{
      const cancelled=()=>{if(!response.writableFinished)buildQueue.cancel(job.id);};response.once('close',cancelled);
      try{const result=await buildQueue.wait(job.id);if(!response.destroyed)return sendJobResult(result);}
      finally{response.removeListener('close',cancelled);}
    };
    const localOrigin = `http://127.0.0.1:${server.address().port}`;
    const origin=configuredOrigin||localOrigin;
    const allowedHosts=[new URL(localOrigin).host,new URL(origin).host];
    if (!allowedHosts.includes(request.headers.host)) return send(response, 403, { error: 'invalid host' });
    // Apply before model handlers or body reads, including cached projects and
    // old browser tabs. A hidden upload control is not an export restriction.
    if(releaseRequestLocked(request.url||'')){
      if(request.method==='POST'&&(request.headers['x-m10v-token']!==token||
        (request.headers.origin&&request.headers.origin!==origin)))return send(response,403,{error:'authorization failed'});
      return send(response,423,{code:'FIRMWARE_RELEASE_LOCKED',error:firmwareReleasePolicy.message});
    }
    if (await handleGr4CustomizationRequest({request,response,runtime:gr4,token,readBody,send,origin})) return;
    if (await handleGr2NativeRequest({request,response,runtime:gr4,token,readBody,send,origin})) return;
    if (await handleGr4NativeRequest({request,response,runtime:gr4,token,readBody,send,origin})) return;
    if (request.url?.startsWith('/api/gr4/')) {
      await handleGr4Request({ request, response, runtime: gr4, token, readBody, send, origin });
      return;
    }
    // Only generated film artwork accepts its bounded content version query.
    // Keep the existing strict URL contract for APIs and all other assets.
    const pathname = request.method==='GET'&&/^\/gr3\/film-icons\/\d+(?:-large)?\.png\?v=[a-f0-9]{12}$/.test(request.url||'')?request.url.split('?')[0]:request.url;
    if (!pathname || pathname.includes('?') || pathname.includes('#') || pathname.includes('%') ||
      pathname.includes('\\') || pathname.includes('..')) return send(response, 404, { error: 'not found' });
    const firmwareJob=/^\/api\/firmware-jobs\/([a-f0-9]{48})(?:\/(download|cancel))?$/.exec(pathname);
    if(request.method==='GET'&&firmwareJob){
      try{
        const job=buildQueue.get(firmwareJob[1]);if(!job)return send(response,404,{error:'构建任务不存在或已清理。'});
        if(!firmwareJob[2])return send(response,200,{job});
        if(firmwareJob[2]!=='download')return send(response,405,{error:'POST required'});
        const result=buildQueue.result(job.id);
        if(!result)return send(response,job.state==='expired'?410:409,{error:job.error?.message||'构建及校验尚未完成，不能下载。',job});
        return sendJobResult(result);
      }catch(error){return send(response,412,{code:error.code||'M10V_FIRMWARE_CHECK_FAILED',error:error.message});}
    }
    if(pathname==='/hooks/github'){
      if(request.method!=='POST')return send(response,405,{error:'POST required'});
      try{
        const body=await readBody(request,32*1024*1024);
        const upstream=await fetch('http://127.0.0.1:3001/hooks/github',{method:'POST',body,
          headers:{'Content-Type':'application/json','X-Hub-Signature-256':request.headers['x-hub-signature-256']||'',
            'X-GitHub-Event':request.headers['x-github-event']||''},signal:AbortSignal.timeout(5000)});
        return send(response,upstream.status,await upstream.json());
      }catch{return send(response,503,{error:'deployment receiver unavailable'});}
    }
    if (request.method === 'GET') {
      if(pathname==='/api/downgrade/status')return send(response,200,{models:Object.fromEntries(
        Object.entries(ANNIVERSARY_DOWNGRADE_PROFILES).map(([model,p])=>[model,{available:true,
          model,from_version:p.from_version,to_version:p.to_version,source_sha256:p.source_sha256,
          restore_sha256:p.restore_sha256,camera_tested:false}]))});
      if(pathname==='/downloads/m10v-firmware-safety-skill.zip'){
        try{return send(response,200,await firmwareSkillArchive(),'application/zip','m10v-firmware-safety-skill.zip');}
        catch{return send(response,503,{error:'skill download unavailable'});}
      }
      if(['/gr2','/gr2/','/gr2/workbench.html','/gr4','/gr4/'].includes(pathname))return send(response,200,await readFile(path.join(web,'firmware-locked.html')),'text/html; charset=utf-8');
      if(pathname==='/gr2/inspect/')return send(response,200,await readFile(path.join(web,'gr2/index.html')),'text/html; charset=utf-8');
      if(pathname==='/gr4/sd-library.html')return send(response,200,Buffer.from(gr4SdLibraryHtml(await readFile(path.join(web,'gr3/sd-library.html'),'utf8'))),'text/html; charset=utf-8');
      if(pathname==='/gr4/sd-library.js')return send(response,200,await readFile(path.join(web,'gr3/sd-library.js')),'text/javascript; charset=utf-8');
      if(pathname==='/gr4/sd-library.css')return send(response,200,await readFile(path.join(web,'gr3/sd-library.css')),'text/css; charset=utf-8');
      if(['/gr4/reference','/gr4/reference/'].includes(pathname))return send(response,200,await readFile(path.join(web,'gr4/index.html')),'text/html; charset=utf-8');
      if(pathname==='/changelog/'||pathname==='/changelog'){
        try{return send(response,200,Buffer.from(renderChangelog()),'text/html; charset=utf-8');}
        catch{return send(response,503,{error:'release history unavailable'});}
      }
      if(pathname==='/gr3/native-library.html'){response.writeHead(302,{Location:'/gr3/','Cache-Control':'no-store'});response.end();return;}

      if(pathname === '/api/gr3/native-library/catalog') {
        try {return send(response,200,await nativeCatalog());}catch(error){return send(response,400,{error:error.message});}
      }
      if (pathname === '/api/platform/adapters') return send(response, 200, {
        schema_version: 1,
        adapters: adapters.list().map((adapter) => ({ ...adapter,
          capabilities: typeof adapters.get(adapter.id).capabilities==='function' ? adapters.get(adapter.id).capabilities() : null })),
        active_workspace: 'gr3', release_models:['gr3','gr3x'], inspection_models:['gr3','gr3x','gr4','gr2'], gr4_evidence: 'reference_verified', hardware: 'not_tested',
      });
      if (pathname === '/api/status') return send(response, 200, {
        firmware_release_policy:firmwareReleasePolicy,
        session_token: token, can_generate: true, model: 'GR III / GR IIIx', hardware: 'not_tested',
        official_sd_supported: process.platform === 'darwin', candidate_sd_blocked: true,
        candidate_offline_analysis: true, candidate_export_allowed: true,
        version_strategy: 'same_version_first', version_probe_available: true,
        blockers: [
          'camera_edition_value_and_shutdown_runtime_unverified',
          'modified_package_acceptance_unverified',
          'hardware_recovery_not_verified',
        ],
        gr3_custom_runtime: await runtimeAvailable(),
        features: {
          crop: { status: 'unsupported', can_preview: true, can_generate: false },
          shutdown: { status: 'verified_export', can_preview: true, can_generate: true },
        },
      });
      if (/^\/api\/projects\/[0-9a-f]{64}\/stock-presets$/.test(pathname)) {
        try { return send(response, 200, stockPresetCapabilities(await readBuildOriginal(pathname.split('/')[3]))); }
        catch (error) { return send(response, 400, {error:error.message}); }
      }
      if (pathname === '/api/sd/volumes') {
        try { return send(response, 200, await sd.listSdVolumes()); }
        catch (error) { return send(response, 503, { error: error.message || 'SD scan unavailable' }); }
      }
      if (/^\/api\/projects\/[0-9a-f]{64}\/shutdown-catalog$/.test(pathname)) {
        try { return send(response, 200, shutdownCatalog(await readBuildOriginal(pathname.split('/')[3]))); }
        catch { return send(response, 404, { error: 'official resource catalog unavailable' }); }
      }
      if (/^\/api\/projects\/[0-9a-f]{64}$/.test(pathname)) {
        try { return send(response, 200, (await resolveBuildSource(await store.readOriginal(pathname.split('/').at(-1)))).report); }
        catch { return send(response, 404, { error: 'project not found' }); }
      }
      const asset = staticFiles[pathname];
      if (!asset) {
        if (['/gr2', '/gr2/', '/gr3', '/gr3/', '/gr3x', '/gr3x/', '/gr4', '/gr4/'].includes(pathname)) {
          const model = pathname.slice(1, 4);
          return send(response, 200, await readFile(path.join(web, model, 'index.html')), 'text/html; charset=utf-8');
        }
        const match = /^\/(gr2|gr3|gr4|shared)\/([a-zA-Z0-9_./-]+)$/.exec(pathname);
        if (match && !match[2].includes('..')) {
          const target = path.resolve(web, match[1], match[2]);
          const base = path.resolve(web, match[1]);
          if (target.startsWith(`${base}${path.sep}`)) try {
            const type = /\.m?js$/.test(target) ? 'text/javascript; charset=utf-8' :
              target.endsWith('.css') ? 'text/css; charset=utf-8' :
                target.endsWith('.json') ? 'application/json; charset=utf-8' :
                target.endsWith('.html') ? 'text/html; charset=utf-8' :
                  target.endsWith('.svg') ? 'image/svg+xml; charset=utf-8' :
                  target.endsWith('.png') ? 'image/png' :
                    /\.jpe?g$/.test(target) ? 'image/jpeg' : 'application/octet-stream';
            return send(response, 200, await readFile(target), type);
          } catch { /* fall through */ }
        }
        return send(response, 404, { error: 'not found' });
      }
      return send(response, 200, await readFile(path.join(web, asset[0])), asset[1]);
    }
    if (request.method !== 'POST') return send(response, 405, { error: 'method not allowed' });
    const backupMatch = /^\/api\/projects\/([0-9a-f]{64})\/backup$/.exec(pathname);
    const sdMatch = /^\/api\/projects\/([0-9a-f]{64})\/sd\/prepare$/.exec(pathname);
    const candidateMatch = /^\/api\/projects\/([0-9a-f]{64})\/candidates\/shutdown\/analyze$/.exec(pathname);
    const candidateExportMatch = /^\/api\/projects\/([0-9a-f]{64})\/candidates\/shutdown\/export$/.exec(pathname);
    const versionMatch = /^\/api\/projects\/([0-9a-f]{64})\/versions\/probe$/.exec(pathname);
    const bridgeMatch = /^\/api\/projects\/([0-9a-f]{64})\/bridge\/(prepare|export)$/.exec(pathname);
    const downgradeMatch=/^\/api\/downgrade\/(gr3|gr3x)\/(prepare|jobs)$/.exec(pathname);
    const nativeMatch = /^\/api\/projects\/([0-9a-f]{64})\/native-library\/(prepare|build|jobs)$/.exec(pathname);
    const haloMatch = /^\/api\/projects\/([0-9a-f]{64})\/800t\/(prepare|build)$/.exec(pathname);
    const editMatch = /^\/api\/projects\/([0-9a-f]{64})\/edit\/(prepare|build)$/.exec(pathname);
    if (!['/api/import', '/api/backup/inspect', '/api/backup/restore', '/api/gr3/film/fit',
      '/api/gr3/power-images/preview','/api/gr3/sd-library/export','/api/gr3/film-bay/pack','/api/gr3/native-library/import-official','/api/platform/inspect','/api/platform/inspect-official'].includes(pathname) &&
      !backupMatch && !sdMatch && !candidateMatch && !candidateExportMatch && !versionMatch && !editMatch && !haloMatch && !nativeMatch && !bridgeMatch && !downgradeMatch && !(firmwareJob?.[2]==='cancel'))
      return send(response, 404, { error: 'not found' });
    if (request.headers['x-m10v-token'] !== token ||
      (request.headers.origin && request.headers.origin !== origin))
      return send(response, 403, { error: 'authorization failed' });
    try {
      const body = await readBody(request, downgradeMatch||firmwareJob?.[2]==='cancel'?4096:pathname==='/api/gr3/sd-library/export' ? 24 * 1024 * 1024 : pathname==='/api/gr3/film-bay/pack' ? 2048 :
        pathname === '/api/platform/inspect-official' ? 4096 :
        pathname === '/api/gr3/film/fit' ? 8 * 1024 * 1024 :
        nativeMatch || pathname==='/api/gr3/power-images/preview' ? 3*1024*1024 : bridgeMatch || pathname === '/api/gr3/native-library/import-official' ? 4096 : haloMatch ? 4096 : editMatch ? 256 * 1024 : versionMatch ? 0 :
        sdMatch ? 1024 : candidateMatch || candidateExportMatch ? 2 * 1024 * 1024 : MAX_UPLOAD);
      if(firmwareJob?.[2]==='cancel'){
        const job=buildQueue.cancel(firmwareJob[1]);return job?send(response,200,{job}):send(response,404,{error:'构建任务不存在。'});
      }
      if(downgradeMatch){
        const model=downgradeMatch[1],input=JSON.parse(body.toString('utf8'));
        if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).some(k=>!['camera','accepted_plan_id','acknowledge_instructions'].includes(k)))
          throw Error('降级请求字段无效。');
        checkDowngradeCamera(model,input.camera);
        if(downgradeMatch[2]==='prepare'){
          const plan=await readDowngradePlan(model);
          return send(response,200,{...plan,ready:true,firmware_filename:plan.filename,filename:plan.zip_filename});
        }
        if(!downgradePlans.has(model))throw Error('请先核验对应机型的降级方案。');
        const plan=await downgradePlans.get(model);
        if(input.accepted_plan_id!==plan.plan_id||input.acknowledge_instructions!==true)throw Error('降级方案已变化，请重新核验并确认。');
        const job=buildQueue.submit(anniversaryDowngradeJob(downgradeSources,model,input,plan));
        return send(response,202,{job});
      }
      if(pathname==='/api/gr3/power-images/preview')return send(response,200,previewPowerImages(JSON.parse(body.toString('utf8'))));
      if(pathname==='/api/gr3/sd-library/export'){const {zip}=await exportSdFilms(JSON.parse(body.toString('utf8')));return send(response,200,zip,'application/zip','M10V-SD-films.zip');}
      if(pathname==='/api/platform/inspect'||pathname==='/api/platform/inspect-official'){
        const bytes=pathname==='/api/platform/inspect'?body:await readModelOfficial(JSON.parse(body.toString('utf8')).model);
        return send(response,200,await inspectModelFirmware(bytes));
      }
      if(pathname === '/api/gr3/native-library/import-official') {
        const input=JSON.parse(body.toString('utf8'));
        if(!input||Array.isArray(input)||typeof input!=='object'||Object.keys(input).some(k=>k!=='model')||
          (input.model!==undefined&&!['gr3','gr3x'].includes(input.model)))throw Error('仅可选择 GR III 2.10 / GR IIIx 1.60 内置来源');
        const model=input.model||'gr3';
        const original=requireReleaseBaseline(await readNativeOfficial(model),model),record=await store.importOfficial(original);
        return send(response,200,{project_id:record.id,source_sha256:record.sha256});
      }
      if(bridgeMatch) {
        const original=await readBuildOriginal(bridgeMatch[1]),input=JSON.parse(body.toString('utf8'));
        if(bridgeMatch[2]==='prepare'){
          if(!input||Array.isArray(input)||typeof input!=='object'||Object.keys(input).length)throw Error('桥接预检不接受自定义版本或补丁');
          return send(response,200,{...prepareGr3Bridge(original),build_source:buildSource});
        }
        const {zip}=exportGr3Bridge(original,input);
        return send(response,200,zip,'application/zip','M10V-GRIII-bridge-2.10.33.27.zip');
      }
      if(nativeMatch) {
        const original=await readBuildOriginal(nativeMatch[1]),input=JSON.parse(body.toString('utf8'));
        const {plan:powerPreparation}=prepareCheckedNative(original,input);
        if(nativeMatch[2]==='prepare')return send(response,200,{...powerPreparation,build_source:buildSource});
        input.camera??=cameraHeader(request);checkWebBuild(original,input.camera,input);
        if(input.accepted_configuration_sha256!==powerPreparation.configuration_sha256)throw Error('方案已变化，请重新核验图片与固件');
        const job=buildQueue.submit(isolatedFirmwareJob(store,nativeMatch[1],input));
        if(nativeMatch[2]==='jobs')return send(response,202,{job});
        return await waitForBuild(job);
      }
      if (pathname === '/api/gr3/film-bay/pack') {
        return send(response, 410, { error: '旧 SD 胶片库方案已废弃，不可用。' });
      }
      if (pathname === '/api/gr3/film/fit') {
        const cancellation=new AbortController();response.once('close',()=>{if(!response.writableFinished)cancellation.abort();});
        const filename=decodeURIComponent(request.headers['x-m10v-filename']||'Imported LUT.cube');
        return send(response,200,await (/\.xmp$/i.test(filename)?fitXmp:fitCube)(body,filename,{signal:cancellation.signal,model:request.headers['x-m10v-fit-model']||'gr3',...(request.headers['x-m10v-approximation-strength']!==undefined?{approximationStrength:Number(request.headers['x-m10v-approximation-strength'])}:{})}));
      }
      if (haloMatch) {
        const original = await readBuildOriginal(haloMatch[1]);
        const input = JSON.parse(body.toString('utf8'));
        if (haloMatch[2] === 'prepare') return send(response, 200, {...prepare800T(original, input.selection),build_source:buildSource});
        try {
          input.camera??=cameraHeader(request);checkWebBuild(original,input.camera,input);
          return await waitForBuild(buildQueue.submit(isolatedFirmwareJob(store,haloMatch[1],input,'800t')));
        } catch (error) {
          if (error.code === 'M10V_800T_EVIDENCE_REQUIRED')
            return send(response, 409, { error: error.message, blockers: error.blockers });
          throw error;
        }
      }
      if (editMatch) {
        const cancellation=new AbortController();
        response.once('close',()=>{if(!response.writableFinished)cancellation.abort();});
        const options={signal:cancellation.signal};
        const original = await readBuildOriginal(editMatch[1]);
        const input = JSON.parse(body.toString('utf8'));
        const prepared = await prepareCustomization(original, input.selection, options);
        if (editMatch[2] === 'prepare') return send(response, 200, {...prepared,build_source:buildSource});
        if (input.accepted_configuration_sha256 !== prepared.configuration_sha256 || !prepared.ready)
          return send(response, 409, { error: '方案已变化或预检未通过，请重新预检并确认风险。' });
        input.camera??=cameraHeader(request);checkWebBuild(original,input.camera,input);
        return await waitForBuild(buildQueue.submit(isolatedFirmwareJob(store,editMatch[1],input,'edit')));
      }
      if (versionMatch) {
        const original = await readBuildOriginal(versionMatch[1]);
        return send(response, 200, analyzeVersionProbe(original));
      }
      if (candidateMatch) {
        const original = await readBuildOriginal(candidateMatch[1]);
        return send(response, 200, analyzeStreetCandidate(original, body));
      }
      if (candidateExportMatch) {
        const original = await readBuildOriginal(candidateExportMatch[1]);
        const camera=cameraHeader(request);checkWebBuild(original,camera);
        const accepted_configuration_sha256=createHash('sha256').update(Buffer.concat([Buffer.from(candidateExportMatch[1]),body])).digest('hex');
        return await waitForBuild(buildQueue.submit(isolatedFirmwareJob(store,candidateExportMatch[1],{jpeg:body,camera,accepted_configuration_sha256},'shutdown')));
      }
      if (sdMatch) {
        const selection = JSON.parse(body.toString('utf8'));
        if (!selection || typeof selection.device_identifier !== 'string' ||
          !/^disk[0-9]+s[0-9]+$/.test(selection.device_identifier))
          throw new Error('invalid SD device selection');
        const volume = await sd.resolveSdVolume(selection.device_identifier);
        const original = await store.readOriginal(sdMatch[1]);
        return send(response, 200, await sd.prepareOfficialSd(original, volume));
      }
      if (pathname === '/api/import') {
        const {report}=await resolveBuildSource(body);
        const record = await store.importOfficial(body);
        return send(response, 200, { project_id: record.id, ...report });
      }
      if (backupMatch) {
        const original = await readBuildOriginal(backupMatch[1]),candidate=createBackup(original);
        const audit=verifyWebBackup({source:original,candidate,camera:cameraHeader(request)});
        requireWebDownload(candidate,audit);response.setHeader('X-M10V-Firmware-Safety',Buffer.from(JSON.stringify(audit)).toString('base64'));
        return send(response, 200, candidate, 'application/zip', audit.filename);
      }
      if (pathname === '/api/backup/inspect') return send(response, 200, inspectBackup(body));
      const original = restoreBytes(body);
      const folder = await mkdtemp(path.join(os.tmpdir(), 'm10v-rehearsal-'));
      try {
        const trial = new Store(folder);
        const record = await trial.importOfficial(original);
        if (!(await trial.readOriginal(record.id)).equals(original)) throw new Error('rehearsal readback differs');
      } finally { await rm(folder, { recursive: true, force: true }); }
      const actual = await store.importOfficial(original);
      return send(response, 200, { project_id: actual.id, original_sha256: actual.sha256,
        recovery_scope: 'computer_official_package_only', camera_flash_included: false });
    } catch (error) {
      if(response.destroyed)return;
      return send(response,error.code==='M10V_BUILD_QUEUE_FULL'?503:error.code==='M10V_FIRMWARE_CHECK_FAILED'?412:400,
        {code:error.code,error:error.message || 'operation failed'});
    }
  });
  server.once('close',()=>buildQueue.close());
  return server;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const rawPort=process.env.M10V_PORT;
  if(rawPort!==undefined&&(!/^[1-9][0-9]{0,4}$/.test(rawPort)||Number(rawPort)>65535))throw new Error('M10V_PORT must be an integer between 1 and 65535');
  const server = createServer(undefined,undefined,undefined,{publicOrigin:process.env.M10V_PUBLIC_ORIGIN});
  server.listen(rawPort?Number(rawPort):0, '127.0.0.1', () => {
    const url = `http://127.0.0.1:${server.address().port}/`;
    console.log(url);
    if (process.env.M10V_NO_BROWSER !== '1' && process.platform === 'darwin') {
      const child = spawn('open', [url], { stdio: 'ignore' });
      child.on('error', (error) => console.error(`无法自动打开浏览器：${error.message}`));
    }
  });
}
