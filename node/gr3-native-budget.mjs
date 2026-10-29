// Seven style LUT/icon banks and native preview curves remain immutable ROM.
// Latest main border budget:1120 KiB. Half-frame appends a 9,612-byte
// native icon/directory/descriptor. Reserve one bounded 16 KiB increment.
// Overlay allocation, preimages, full section and MMU checks remain intact.
// Full half-frame+border diagnostic build measured 1,170,620 bytes, 8,624
// above its non-debug counterpart. One further bounded 16 KiB allowance keeps
// the same full readback and overflow rejection checks for diagnostic code.
export const MAX_NATIVE_RTOS_GROWTH=1152*1024;
