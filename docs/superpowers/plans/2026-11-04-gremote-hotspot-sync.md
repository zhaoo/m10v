# GRemote hotspot sync implementation plan

**Goal:** On GR III 2.10, a fresh Android GRemote install discovers M10V over the camera hotspot and reads settings after a cold boot.

1. Add a native-app bootstrap route for the public package. Restrict it to the verified camera AP, exact authority and explicit app header. Issue a boot-local HMAC credential and keep the signed read/write and replay contracts. Retain legacy package compatibility in the App.
2. On the native owner, initialize the focal RAM cache from existing settings when the camera is idle. Do not write the journal, apply a seed, change the live crop or hide other settings if focal is unavailable.
3. Bind discovery to the App's camera connection and foreground lifecycle. Use an in-memory key. Refresh existing controllers through their normal entry points.
4. Verify network admission, legacy fallback, cold start, signed operations, GR III candidate build and package. After device acceptance, release the paired Android App and M10V sources and verify Baota.
