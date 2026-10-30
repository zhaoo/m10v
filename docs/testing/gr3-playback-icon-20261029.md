# GR III playback icon repair — 2026-10-29

Status: offline repair; device playback acceptance pending. Baseline: main
`38a847b5871e2441a7934fafd38dcee50d4faef4`.

## Root cause from official instructions

The existing EXIF writer records the ten appended tones 25–34 as ImageTone
`0x10c`–`0x115`. The old playback wrappers recognize metadata key `0x25` values
`0x1000c`–`0x10015`, but nothing produced those values on a real album parse.

Official tag `0x4f` dispatch at `0x535f25c8` / `0x535f25d8` calls
`0x535c24ec`. That reader executes:

```
535c2504  bl       535d04d4       ; original EXIF SHORT reader
535c2508  sub      r0,r0,#0x100
535c250c  mov      r1,#0x25
535c2510  uxth     r0,r0
535c2514  cmp      r0,#11
535c2518  movwls   r3,#0xdd64
535c251c  movhi    r2,#0          ; all ten private tones become unknown
535c2520  movtls   r3,#0x53d2
535c2524  ldrbls   r2,[r3,r0]
...
535c2534  b        535be068       ; metadata key storage
```

Stock codes `0x100`–`0x10b` map to 1–12 through the original byte table.
The stock playback getter `0x532b44bc` reads that key through `0x535be018`;
the icon getter `0x532b6eec` invokes it. The real album call at `0x53179b7c`
then passes its result to the native icon control at `0x53179b88`.
Existing `test_gr3_ui_polish.py` metadata service stubs supplied the desired
private values directly, so they omitted the failing EXIF-to-metadata conversion.

## Change

Replace only the verified `movhi r2,#0` at `0x535c251c` (word `0x83a02000`)
with a conditional HI branch. The 20-byte bridge accepts normalized 12–21,
sets `r2 = 0x10000 | normalized`, otherwise sets zero, restores the original
`cmp r0,#11` flags, and rejoins `0x535c2520`. Restoring flags is required so
the original conditional table loads do not overwrite the private result.
All stock mappings and unknown codes retain their original behavior.

The icon/detail hooks retain generic film icon 754 and generic detail tone 11.
They never consult the current film journal, so reassignment cannot label an
old photo as the current film. No exact film identity is inferred from slot IDs.
There are no image, JPEG, RAW, ISP, or capture changes in this repair.

The Node packager checks every bridge instruction and the exact patch preimage;
the existing tamper audit now mutates this bridge as well as icon/detail bodies.

Changed files owned by this task:

- `scripts/build_gr3_film_slot_extension.py`
- playback section of `node/gr3-m10v-native-build.mjs`
- `node/gr3-settings-menu.test.mjs`
- `tests/test_gr3_playback_metadata.py`
- this note

## Verification

Python interpreter: `/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python`.
Compiler path prefix: `/opt/homebrew/opt/llvm/bin`.

1. Before the fix, `python -m unittest tests.test_gr3_playback_metadata -v`
   reproduced `AssertionError: 0 != 65548` for the first real parsed private
   ImageTone. The stock-only clamp reproduction passed.
2. After the fix: **3 dedicated ARM tests pass**. They execute original EXIF
   SHORT reading, metadata storage/getting, stock icon code and the patched
   album call. Only assertion logging and singleton-owner acquisition are
   stubbed. They cover all ten private codes, all twelve stock codes, unknown
   neighbors, repeated photo switching, fresh metadata owners, both inline and
   out-of-line EXIF SHORT storage, and generic detail output.
3. Existing `tests.test_gr3_ui_polish`: **6 pass** (including existing icon and
   detail tests).
4. `node --test node/gr3x-native-port.test.mjs`: **5 pass**.
5. Exact pinned official GR III / IIIx RTOS comparisons: reader `0x535c24ec`
   (76 bytes), EXIF SHORT reader `0x535d04d4` (28), metadata getter/setter
   `0x535be018` (168), playback tone getter `0x532b44bc` (88), and album call
   `0x53179b7c` (16) are byte-identical. IIIx differential port consumes new
   verified patches automatically; no guessed model addresses were added.

The initial broader appended-slot/pipeline/RAW and Node settings-audit runs
were interrupted by concurrent Instax asset regeneration (SD contract check,
source hash mismatch, then absent `native_profiles_full`). These are build
precondition failures, not passing regressions. Final integrated reruns are
recorded below or in the overall candidate report.

After generation stabilized, the integrated command was:

```
PATH=/opt/homebrew/opt/llvm/bin:$PATH .venv/bin/python -m unittest \
  tests.test_gr3_playback_metadata tests.test_gr3_ui_polish \
  tests.test_gr3_appended_slots tests.test_gr3_film_pipeline_current \
  tests.test_gr3_capture_released_raw -v
```

It ran 37 test methods in 105 seconds, reporting 11 failures (including
subtests) and 4 errors. Playback (3) and UI polish (6) passed. Current film
pipeline passed 17 of 18 methods, including actual task production through
24 MP zero-pixel encoding, all factory tones, new extra films, still completion,
repeat Make, disabled live preview, wrong-frame rejection and snapshot ABI.
Its independent tamper-audit subprocess errored (details to be integrated).
Appended-slot tests passed stock preset and movie/RAW-development preservation;
three methods failed and three errored in the older shared fixture (104-byte
state expectation versus actual 184-byte state, unmapped owner/cache, and
five-slot host assertions). Both released-RAW methods failed in eight subcases
at the same 104-byte fixture expectation before reaching release behavior.
These failures have not been hidden or reclassified as passing; baseline
comparison is separate from this playback-specific proof.

`PATH=/opt/homebrew/opt/llvm/bin:$PATH node --test
node/gr3-settings-menu.test.mjs` subsequently **passed** its full independent
package audit, including corruption rejection for the new metadata bridge.

## Device boundary

No physical camera was used for this repair. Confirm immediate review and album
switching after power cycling; all ten slots; stock photos interleaved with
private photos; journal reassignment after capture; details/zoom/thumbnails;
JPEG and RAW+JPEG; original RAW-only behavior. Generic recognition is expected
where the recorded slot code cannot identify the original film name. No merge,
push, deployment, or hardware acceptance is implied.
