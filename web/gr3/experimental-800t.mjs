import { apply800THalation } from './halation.mjs';
import { previewFilmPixels } from './film-preview.mjs';
import { createLatestPhotoLoader } from './photo-load.mjs';

const $ = (id) => document.getElementById(id);
const sample = '/gr3/gr3-street-photo.png';
let original = null;
let photoName = 'm10v-example';
let timer = null;
let sourceSha = null;
let requestLocal = null;
let preparation = null;
let colorLook = null;
let requestSequence = 0;
let notifyState = () => {};
function publishState(phase) {notifyState({phase,configuration:firmwareSelection()});}
const presets = {
  weak: { threshold: 82, radius: 8, strength: 45 },
  strong: { threshold: 78, radius: 16, strength: 85 },
};
function firmwareSelection() {
  return { strength: $('halation-preset').value, timestamp: $('halation-timestamp').checked, slot: 'bleach' };
}
function invalidatePreparation() {
  preparation = null; colorLook = null; requestSequence++;
  $('halation-firmware').disabled = true;
  $('halation-preflight').disabled = !sourceSha;
  $('halation-preflight-result').textContent = sourceSha ? '方案已更新，请重新检查。' : '请先导入并核验官方固件。';
  publishState('waiting');
}
function applyPreset() {
  const selected = presets[$('halation-preset').value];
  if (!selected) return;
  for (const key of ['threshold', 'radius', 'strength']) $('halation-' + key).value = selected[key];
  invalidatePreparation(); parameters(); render();
}
async function preflight() {
  if (!sourceSha || !requestLocal) return;
  const sha = sourceSha, selection = firmwareSelection(), ticket = ++requestSequence;
  preparation = null; colorLook = null;
  $('halation-firmware').disabled = true; $('halation-preflight').disabled = true;
  $('halation-preflight-result').textContent = '正在核对原厂固件和 800T 方案…';
  publishState('checking');
  try {
    const response = await requestLocal(`/api/projects/${sha}/800t/prepare`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ selection }),
    });
    const report = await response.json();
    if (ticket !== requestSequence || sha !== sourceSha) return;
    preparation = report;
    publishState(report.ready?'ready':'error');
    colorLook = report.color_plan?.custom?.find((row) => row.name === '800T') || null;
    $('halation-firmware').disabled = !(report.ready === true && report.source_sha256 === sourceSha);
    $('halation-preflight-result').textContent = report.ready === true ? '离线方案已通过预检，可生成实验固件。尚未实机验证；DNG 的 JPEG 预览可能同步出现红晕，CFA 原始数据不参与处理。' :
      '当前不能导出固件：' + report.blockers.map((row) => row.message).join('；') + '。';
    render();
  } catch (error) {
    if (ticket === requestSequence) {$('halation-preflight-result').textContent = error.message;publishState('error');}
  } finally {
    if (ticket === requestSequence) $('halation-preflight').disabled = !sourceSha;
  }
}

function parameters() {
  const threshold = Number($('halation-threshold').value) / 100;
  const radius = Number($('halation-radius').value);
  const strength = Number($('halation-strength').value) / 100;
  $('halation-threshold-value').textContent = `${Math.round(threshold * 100)}%`;
  $('halation-radius-value').textContent = `${radius} px`;
  $('halation-strength-value').textContent = `${Math.round(strength * 100)}%`;
  return { threshold, radius, strength };
}

function render() {
  if (!original) return;
  const canvas = $('halation-after');
  const context = canvas.getContext('2d');
  const data = new ImageData(
    apply800THalation(colorLook ? previewFilmPixels(original.data, colorLook) : original.data, original.width, original.height, parameters()),
    original.width, original.height,
  );
  context.putImageData(data, 0, 0);
  $('halation-export-image').disabled = false;
}

function applyPhoto(bitmap, name) {
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  for (const id of ['halation-before', 'halation-after']) {
    const canvas = $(id);
    canvas.width = width;
    canvas.height = height;
  }
  const context = $('halation-before').getContext('2d', { willReadFrequently: true });
  context.drawImage(bitmap, 0, 0, width, height);
  original = context.getImageData(0, 0, width, height);
  photoName = name;
  $('halation-photo-status').textContent = `${name} · ${width} × ${height} · 预览尺寸；仅在本机浏览器处理。`;
  render();
}

const loadPhoto = createLatestPhotoLoader({
  decode: (source) => createImageBitmap(source), apply: applyPhoto,
  onError: (error) => { $('halation-photo-status').textContent = `照片无法解码：${error.message}`; },
});

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function initialize800TExperiment({ openSource, request, onState=()=>{} }) {
  requestLocal = request;
  notifyState=onState;
  applyPreset();
  loadPhoto(fetch(sample).then((response) => {
    if (!response.ok) throw new Error('示例照片读取失败');
    return response.blob();
  }), 'm10v 示例照片');

  $('halation-file').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 50 * 1024 * 1024) {
      $('halation-photo-status').textContent = '请选择小于 50 MiB 的 JPEG 或 PNG。';
      return;
    }
    await loadPhoto(file, file.name);
  });
  for (const id of ['halation-threshold', 'halation-radius', 'halation-strength']) {
    $(id).addEventListener('input', () => {
      parameters();
      clearTimeout(timer);
      timer = setTimeout(render, 120);
    });
  }
  $('halation-export-image').addEventListener('click', () =>
    $('halation-after').toBlob((blob) => {
      if (blob) downloadBlob(blob, 'm10v-800t-halation-reference.png');
    }, 'image/png'));
  $('halation-export-params').addEventListener('click', () => {
    const record = {
      experiment: '800t-red-halation', status: 'browser_reference_only',
      target: 'GR III JPEG capture', sourcePhoto: photoName,
      previewSize: original ? [original.width, original.height] : null,
      referencePreset: $('halation-preset').value, parameters: parameters(),
    };
    downloadBlob(new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' }),
      'm10v-800t-halation-parameters.json');
  });
  $('halation-preset').addEventListener('change', applyPreset);
  $('halation-timestamp').addEventListener('change', invalidatePreparation);
  $('halation-preflight').addEventListener('click', preflight);
  $('halation-firmware').addEventListener('click', async () => {
    if (!preparation?.ready || !sourceSha || !requestLocal) return;
    const ticket=requestSequence,sha=sourceSha,selection=firmwareSelection();
    $('halation-firmware').disabled = true;
    $('halation-preflight-result').textContent='正在构建并独立回读固件，请稍候…';
    publishState('building');
    try {
      const response = await requestLocal(`/api/projects/${sourceSha}/800t/build`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selection, accepted_configuration_sha256: preparation.configuration_sha256 }),
      });
      const blob=await response.blob();
      if (ticket!==requestSequence || sha!==sourceSha) return;
      const receipt=JSON.parse(atob(response.headers.get('X-M10V-800T-Receipt')));
      await verifyFirmwareBlob(blob,{audit:readFirmwareSafety(response),sourceSha256:sha,
        configurationSha256:preparation.configuration_sha256,model:'gr3',filename:'fwdc239b.bin',receipt});
      if(ticket!==requestSequence||sha!==sourceSha)return;
      downloadBlob(blob, 'fwdc239b.bin');
      downloadBlob(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}),'m10v-800t-build.json');
      $('halation-preflight-result').textContent=`已生成并通过独立回读 · ${receipt.candidate_sha256.slice(0,12)}… · 尚未实机验证。`;
      publishState('built');
    } catch (error) {if(ticket===requestSequence) {$('halation-preflight-result').textContent = error.message;publishState('error');} }
    finally {if(ticket===requestSequence) $('halation-firmware').disabled=!preparation?.ready;}
  });
  $('halation-open-source').addEventListener('click', openSource);
}

export function update800TSourceState(sha256) {
  sourceSha = /^[0-9a-f]{64}$/.test(sha256 || '') ? sha256 : null;
  invalidatePreparation();
  $('halation-source-state').textContent = sha256 ? `已核验 · ${sha256.slice(0, 12)}…` : '等待导入并核验';
}
import {readFirmwareSafety,verifyFirmwareBlob} from './firmware-verification.mjs';
