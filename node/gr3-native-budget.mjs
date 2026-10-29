// The firmware decoder accepts at most 128 MiB of decoded data. The exact
// official GR III/IIIx source decodes to 59,718,388 bytes; only RTOS can grow.
// This is a container bound, not a manually reserved native-code allowance.
// The complete appended address range is checked against the official MMU
// descriptors, and the whole candidate is independently decoded and audited.
export const MAX_DECODED_FIRMWARE_BYTES=128*1024*1024;
export const OFFICIAL_DECODED_FIRMWARE_BYTES=59718388;
export const MAX_NATIVE_RTOS_GROWTH=MAX_DECODED_FIRMWARE_BYTES-OFFICIAL_DECODED_FIRMWARE_BYTES;
