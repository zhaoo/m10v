# 撕纸叠映 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the native core and coordinate independent protocol/App tasks with superpowers:dispatching-parallel-agents. Steps use checkbox syntax.

**Goal:** Deliver an identifiable GR III 2.10 ISP-only torn-overlay experimental firmware and GRemote APK.

**Architecture:** A private owner session and per-recipe frozen metadata drive two single-plane IIP operations. The signed extension bridge controls an ephemeral session; GRemote presents its stage alongside the existing shutter controls.

**Tech Stack:** freestanding ARM C, Python/Unicorn, Node, Flutter/Dart.

**Spec:** docs/superpowers/specs/2026-11-10-torn-overlay-design.md

## Global Constraints

- Develop branches only; preserve existing dirty checkouts. No push/deploy/SD writes.
- Camera pixels use ISP/IIP only; no CPU RNG, pixel loops or LUT fallback.
- GR III 2.10 only, YC422 only; no claims of physical verification.
- Preserve existing films, slots, color, HDF, borders, stamps, RAW safety and protocol compatibility.

## Review Focus

- Cancel/destructor versus queued/running DMA must not free live buffers.
- Freeze binds true enqueue recipe/SI/generation and off snapshots cannot activate later.
- Incompatible image geometry, drive mode or special renderers fail before new pixel work.
- Unknown transaction outcomes and reconnect never replay start/cancel automatically.
- Contract and manifest gates prevent unsupported old firmware/model from enabling this feature.

## Task 1: Native session, graph and capture integration

Files: new native/gr3/m10v_torn_overlay.c/.h, scripts/build_gr3_torn_overlay.py, tests/test_gr3_torn_overlay.py; modify ISP granulation/shot/pipeline, save_trace.h, settings owner and builder/export integration.

- [x] Write and run failing host/ARM tests for owner lifetime, real freeze, two phases, off zero-work, allocation failure, duplicate and queued captures, size/orientation mismatch, no CPU planes.
- [x] Implement `m10v_torn_init(owner)`, `m10v_torn_destroy(owner)`, `m10v_torn_state(stage,generation)`, `m10v_torn_set(owner,action)`, `m10v_torn_reserve(recipe)`, `m10v_torn_freeze(recipe)`, `m10v_torn_execute(recipe,context,photo)`, `m10v_torn_encoder_admit(recipe,si)` and an authenticated generic granulation plane wrapper.
- [x] Allocate owner+0x6d00..0x6e00 and recipe+0x57d8..0x57f8 only for opted-in GR III pure-ISP builds. Link forward exports without writable append state.
- [x] Run tests through actual native graph control and final artifact; mark real hardware output unverified.

## Task 2: Extension contract and camera menu

Files: contracts/extensions-v1.json, native/companion/extensions.*, native/gr3/m10v_companion_extensions.inc, m10v_hdf_menu.c, builders and related tests.

- [x] Failing tests: 25-field canonical hash, only0/1 writes, runtime persistence, unsupported build mask, CAS generation change, menu scrolling/cancel and legacy entries preserved.
- [x] Add id24 tornSession 0..4 read/0..1 write; generation into revision. Hook state/set APIs, busy checks and new source fingerprints.
- [x] Append1218+ Chinese resources and scroll fifth root item; show stages, start/restart/cancel without persistent writes.
- [x] Run portable parser/owner, ARM menu and source/manifest tests.

## Task 3: GRemote flow and compatibility

Files: extensions protocol/controller/UI, new shared torn-session widget, shoot page, tests and pubspec version.

- [x] Failing protocol tests for new hash plus all three historical hashes; never submit read-only stages or new field to old contract.
- [x] Add Chinese session control and stage hint in shoot page, serialized refresh while foreground, reuse existing capture/focus.
- [x] Cover unknown results, disconnect, busy, stale revision, lifecycle polling cleanup; no image processing or automatic shutter.
- [x] Full flutter test/analyze and signed release APK 1.2.8+33 experimental delivery.

## Task 4: Review and package

- [x] Independent review of native ownership, contract, UI and final builder gates; fix material findings.
- [x] Run full npm/flutter and relevant Python/ARM, compare failures against clean baseline logs.
- [x] Existing export CLI creates complete no-production GR III package with original settings/identity protection, manifest, hashes and test/recovery instructions.
- [x] Report offline passing/known failing/skipped and wait for the user's hardware validation.

## 执行结果

状态：WAITING_FOR_USER_VALIDATION。28项最终候选专项通过；GRemote723通过/6跳过、分析和release构建通过。Node560通过/67失败/42跳过，失败名称集合均在开发前74项基线中；一个旧Python selected-tone encoder断言已在原HEAD独立复现。未合并main、推送、部署或写卡。

独立审阅修复：UV及stride完整预检在第一趟像素工作前完成；不可用原生快照不占会话；编码门禁保留原厂不支持分支；已提交开始的阶段推进不造成永久pending；隐藏子页和主路由分支停止轮询。

Ruling: 原厂多曝包含CPU NEON，因此采用独立ISP亮度蒙版；YC422限定和首次不提供实时合成预览属于本次已明示的测试范围。精确alpha/色边、缓存、SD与速度仍待设备验证。
