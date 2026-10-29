// Seven style LUT/icon banks and native preview curves remain immutable ROM.
// Latest main border budget:1120 KiB. Half-frame appends a 9,612-byte
// native icon/directory/descriptor. Reserve one bounded 16 KiB increment.
// Overlay allocation, preimages, full section and MMU checks remain intact.
export const MAX_NATIVE_RTOS_GROWTH=1136*1024;
