// Seven style LUT/icon banks and native preview curves remain immutable ROM.
// Ubuntu clang full debug deployment measured 1,115,104 bytes of RTOS growth,
// 992 bytes above the 1088 KiB macOS-tested ceiling. Reserve one bounded 16 KiB
// increment for compiler/configuration variation, without changing build flags.
// Half-frame full-feature GR III measured 1,136,756 bytes: its appended native
// 60x40 RGBA tile plus directory/descriptor costs 9,612 bytes. Reserve one
// bounded 12 KiB increment; the overlay itself remains within its 8 KiB slot.
// Whole-section, instruction, read-only MMU and non-target-byte audits remain.
export const MAX_NATIVE_RTOS_GROWTH=1116*1024;
