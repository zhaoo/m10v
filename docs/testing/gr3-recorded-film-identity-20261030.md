# Recorded film identity and imported names

Status: USER_VALIDATED. On 2026-10-30 the user reported the current r1 candidate passed and explicitly requested main/GitHub/Baota publication. The feedback does not specify model-by-model or exhaustive test coverage. Publication is tracked by the release workflow.

## Imported names

`m10v_menu_name` emits resources1007..1011 for slots0..4 and1111..1115
for slots5..9. The C resource getter previously rejected the second range,
although its assembly adapters already recognized it. Both ranges now map to
the correct slot. Names come from the installed immutable/custom record and
work after the source `FILMS.M10` pack is removed. Original getter stack
ownership, descriptor lifetime and register preservation remain intact.

The old getter adapter regression was vacuous (`range(1007,1007)`). It now
executes both original adapters for all ten resources. Another ARM test installs
an imported LUT in each supported slot and executes appended menu name, value
name, icon and resource descriptor adapters.

## Photograph-owned identity

Historic private ImageTone values0x10c..0x115 identify slots, not films. They
cannot recover the film after reassignment. They now use neutral film icon876,
instead of custom LUT icon754. No replay code reads the current film journal.

New records use the existing EXIF SHORT ImageTone tag:

- Built-in: `0x1000 + film_id`.
- Imported immutable record: `0x2000 + (film_id - 79) * 235 + bank - 21`,
  covering film IDs79..288 and stored immutable banks21..255, through0xe0c5.
- Mutable legacy custom banks retain the historic slot-only fallback.

The exact code comes from the validated immutable recipe snapshot at the real
processing-task producer. A dedicated ShootingInfo pool allocation grows from
0x74270 to0x74280 bytes:100 allocations add1600 bytes total. The appended16-byte
tail contains magic, generation, code and check. Membership is authenticated
against ProcessingManager's100 entries and lease status before any tail access.
Unrelated stock configuration objects retain their original extent.

Only these verified pool/lifetime sites change:

-0x53523984: dedicated pool extent initialization.
-0x535239e4: pool constructor, initializes the appended tail.
-0x53523e00 and0x53523a68: checkout/return clear identity, preserving GPR/NZCV.
-0x53510830: original full-SI copy clears the destination tail before copying
  the unchanged0x74270 stock bytes.
-0x53608080 and0x5361c0cc: JPEG/RAW ImageTone writer calls consume this SI's
  authenticated tail, or call the exact original writer when unavailable.

The existing metadata reader bridge preserves all stock mappings and adds a
separate marker for exact recorded codes. Built-in playback icons resolve by
recorded ID; imported identities use the custom artwork. Existing detail layout
is retained for both new and legacy records. It does not display the imported
record's name as a new album text field; menu/ADJ imported names are repaired.

No new SD reads, allocation, image/pixel processing or blocking work occurs at
capture submission or metadata writing. Playback does not infer identity from
current selections. Node packaging independently checks every new adapter word,
stock preimage, neutral icon descriptor/pixels, and the verified snapshot
producer requirement.

## Executed checks

- Actual ARM imported-name/resource tests:2 methods pass; ten slots and20
  original getter adapter cases.
- Playback metadata/UI tests:12 methods pass, including original EXIF reader,
  both writer callsites, changed live selection, imported bank255, cold owners,
  legacy photos, stock/unknown neighbors, unmapped foreign SI, lease return,
  flags and full original SI copy invalidation.
- Current production film pipeline:21 original methods covered successfully
  (20 initial passes plus the missing-runtime fitter case rerun successfully).
- Added real task-producer pool identity → Still Make →24MP unmapped-pixel
  encoder case:passes. It freezes before enqueue and retains identity after a
  later UI change.
- Node custom-display, settings and recorded-identity package/tamper audits:
  three pass. Missing snapshot producer and corruption of all five SI lifetime
  adapters are rejected even with rehashed runtime bytes.
- Existing GRIIIx differential port unit suite:five pass; target-address
  compatibility still requires the independently checked official inputs.

Older `test_gr3_native_fast_capture` fixtures fail at184-byte current journal
versus104-byte ctypes state, before capture assertions. The older
`test_gr3_isp_recipe_color` extracted-decoder setup fails compilation and still
uses historical owner sizes. These failures were not hidden or reclassified.

Physical verification must bind the final BIN/hash and include pool exhaustion,
repeated captures, JPEG/RAW+JPEG, factory tones, imported LUTs, selection changes,
playback after restart and absent SD pack, original legacy pictures, details and
thumbnails. Offline tests do not establish those camera results.
