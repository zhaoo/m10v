// Seven style LUT/icon banks and native preview curves remain immutable ROM.
// The border candidate adds 19,196 bytes of verified native code. Its measured
// composed growth is 1,133,692 bytes, 3,196 above the former 1104 KiB bound.
// Reserve one further 16 KiB increment. Full RTOS mapping, all patch preimages,
// whole-section readback, and non-target-byte audits still apply.
export const MAX_NATIVE_RTOS_GROWTH=1120*1024;
