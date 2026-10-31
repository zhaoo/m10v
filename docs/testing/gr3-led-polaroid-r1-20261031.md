# GR III 2.10 LED / Polaroid diagnostic r1

Status: WAITING_FOR_USER_VALIDATION. No push, main merge or deployment.

Baseline: GitHub main `4a89fd5d1fd3405c0f5f1fb1655709d4fe41e221`.
The successful deployment log for Actions run `41094589266` reports that exact
SHA as `DEPLOY_OK ... service=active`. Work branch: `daily/gr3-led-polaroid-fix`.
The candidate includes local uncommitted changes; HEAD alone is not its identity.

## Findings and scope

| Area | Baseline behavior | Candidate | Evidence / remaining gate |
| --- | --- | --- | --- |
| Film name and icon | Each refresh calls the SD journal loader | Prefer validated owner cache; retain cold-cache loader | ARM regression observed old caption instead of cached film before fix; final BIN verifies 20 refreshes without storage calls and immediate updated cache identity |
| Polaroid 3:2 playback | User reports one white edge | Record before/after JPEG metadata for source, main, preview, thumbnail and extra image | Root cause remains unproven; original JPEG plus matching camera logs required |
| Image processing / Half | Native ISP, border IIP, Half pair with black separator | Unchanged processing and bank guards | Current pipeline and border runtime checks; no new hardware acceptance |
| Storage and other models | Existing film / border journals and model gates | ABI unchanged; only GR III package delivered | Shared code has GR IIIx ARM coverage; no IIIx/IV device or firmware delivery claim |

`m10v_menu_name` and `m10v_menu_icon` were the concrete repeat-read path.
No LED register is patched or activity signal hidden. The camera result must
still confirm that this path explains the reported persistent blinking.
Custom LUT resource text continues to use its existing name loader.

Diagnostic batches run only at the existing capture-worker checkpoints 193
and 190 for a frozen enabled border. They contain descriptor metadata, never
CPU photo-pixel reads. Event197 tags `0x4a0...` and `0x4a1...` distinguish the
before/after snapshots. Each batch contains 12 records; logs remain bounded
63-record channel rings, so absence from a retained window proves no negative.

## Candidate identity

Build: `builds/gr3-led-polaroid-r1-20261031` via the ordinary web export chain:

```sh
node scripts/export_gr3_m10v_native.mjs --debug --border --with-hdf --universal-halation builds/gr3-led-polaroid-r1-20261031
```

BIN SHA-256: `ae391ed3daf50738c6dbab22eb055da8b4602f8ffb78485f86f3c2be61bc4664`.
Debug build_id: `4feade09`. Final packaging audited 268 hooks and runtime readback.
Manifest, receipt, configuration, generated source provenance and matching
`SD/M10V/FILMS.M10` accompany the candidate. Existing custom libraries must not
be overwritten with the built-in-only pack.

## Verification limits

73 border runtime / canvas / debug compile / runtime build / logger checks pass.
24 final-BIN current-pipeline / metadata / border checkpoint checks pass.
Final-BIN metadata and current-pipeline checks cover zero SD access during
repeated built-in name/icon refresh, updated state identity, before/after
descriptor diagnostics, native processing-task ingress and the no-pixel-work
path. CRC-page decoder checked both new diagnostic phases separately.

The following SD checks also fail on pristine main with the same errors:

- `test_native_accepts_all_63_exact_main_records_and_rejects_repaired_edits`:
  historical record SHA expectation differs from current catalog data.
- `test_node_accepts_main_builtin_and_mixed_packs_and_rejects_repaired_edits`:
  historical reconstructed pack fails current audit.

Full Node suite: 479 tests, 425 pass, 36 fail, 18 skip. All 36 failure names
also occur on pristine main. That first main run reports 44 failures because
it also lacks local border firmware fixtures for eight checks; those checks
are rerun after supplying the same official fixtures. Full failure names and
baseline comparison are retained in the generated candidate validation report.
These failures are not changed or suppressed.
There has been no physical camera test in this work session.

## Camera test and recovery

Use the included Chinese test instructions. First leave a selected film in
idle LiveView for 20 seconds. Then capture one landscape 3:2 Polaroid photo,
inspect immediate playback and album zoom, and return its original JPEG and
all existing M10V MN/CP/IO/AK log pages before further captures overwrite them.
Optional follow-ups: portrait 3:2, square Polaroid, border-off control.

Recovery uses the user's previously accepted firmware and existing card
settings. No card-format, journal deletion or configuration migration is needed.
