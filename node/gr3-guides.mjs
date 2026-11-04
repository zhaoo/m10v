const instructionPatches = [
  [0x5317681c, 0xe1a0c00d, 'm10v_guides_hook_update', false],
  [0x53391b14, 0xe1a0c00d, 'm10v_guides_hook_prepare', false],
  [0x53391be0, 0xeb000850, 'm10v_guides_hook_paint', true],
  [0x5339c3b0, 0xe1a0c00d, 'm10v_guides_hook_grid', false],
];

const menuPointers = [
  [0x53b3dcc8, 0x531b3cac, 'm10v_guides_camera_count'],
  [0x53b3dcd0, 0x531b5c74, 'm10v_guides_camera_draw'],
  [0x53b3dcd8, 0x531b7604, 'm10v_guides_camera_apply'],
  [0x53b3dce0, 0x531b8de8, 'm10v_guides_camera_checked'],
  [0x53b365b8, 0x53198560, 'm10v_guides_camera_summary'],
];

const need = (condition, message) => {
  if (!condition) throw Error('GR III guides: ' + message);
};

export function guidesPatches(runtime, manifest) {
  const report = manifest.camera_guides;
  if (!report) return [];

  need(report.schema === 'm10v-gr3-guides/v1' && report.owner_offset === 0x6600 &&
    report.stock_styles === 2 && report.private_styles === 5 && report.first_caption === 1181,
    'owner or menu contract differs');
  need(manifest.sd_library && manifest.appended_slots && manifest.film_library_enabled !== false &&
    ['gr3', 'gr3x'].includes(manifest.camera_model), 'unsupported build');

  const patches = [...instructionPatches, ...menuPointers].map(([address, expected, name, link]) => {
    const target = manifest.symbols?.[name];
    const offset = target - manifest.base;
    need(Number.isInteger(target) && !(target & 3) && offset >= 0 && offset + 4 <= runtime.length,
      'runtime symbol outside allocation: ' + name);
    if (link === undefined) return {address, expected, replacement: target, name};

    // The paint veneer keeps the canvas in r4 across native child dispatch.
    const prologue = link ? 0xe92d4010 : 0xe92d500f;
    need(runtime.readUInt32LE(offset) === prologue, 'veneer entry differs: ' + name);
    const delta = target - address - 8;
    need(delta >= -(2 ** 25) && delta < 2 ** 25, 'branch out of range: ' + name);
    const replacement = ((link ? 0xeb000000 : 0xea000000) | ((delta >> 2) & 0xffffff)) >>> 0;
    return {address, expected, replacement, name};
  });

  need(report.patches?.length === patches.length && patches.every((patch, index) =>
    Object.keys(patch).every(key => report.patches[index]?.[key] === patch[key])),
    'patch manifest differs');
  return patches;
}
