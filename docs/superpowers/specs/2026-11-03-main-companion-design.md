# GR III 2.10 main companion adaptation

User confirms same GR III Street Edition M10V2.10, no 2.20 or other firmware history, existing App film-loading and extension control work; explicitly requests both preserved on latest main. Baseline main/production 6e77769619ee9dc952e6b3993d052d53e0807a94; old bridge reference 5804896 based a24ccc2.

Reuse the proven signed mailbox bridge, RTOS UI owner and existing native setters. Port only bridge hunks; retain latest C41/catalog/ISP/source validation. No new transport or camera-address research. Pure-main build and optional bridge-off behavior stay unchanged. Only exact official GRIII2.10 SHA d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4 admitted for bridge.

Existing valid184-byte/v5/10-slot journals and global settings must survive upgrade even if compiled-seed receipt is missing or changed. Add explicit preserve_existing build option only for this upgrade; normal webpage seed semantics unchanged. No zoom reseed; no GET-side lazy repair of stale focal cache. Preserve no-replay/unknown-write/storage mutual exclusion and AF/shutter separation.

Alternatives: pure-main package loses App bridge and user explicitly rejected; old BIN preserves App but omits newest main, contrary to request. Selected minimal opt-in port preserves both; physical acceptance still required for exact new bytes.

Deliver matching firmware, SD service, film pack, pairing and App if camera contract changes. Retain private pairing; no private files in Git. All component hashes and build options in receipts and exact rebuild. No automatic flash, SD write, settings reset or publication. Recovery and brick safety cannot be established by offline tests. Stage WAITING_FOR_USER_VALIDATION only after checks; never publish untested package.
