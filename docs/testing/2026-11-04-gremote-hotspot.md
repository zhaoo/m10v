# GR III 2.10 GRemote automatic connection candidate

The paired candidate consists of an Android 1.2.1 build and a GR III 2.10 firmware plus matching SD service. Use the exact official GR III input and preserve existing settings. The GR IIIx connection gate remains closed.

Device acceptance

1. Back up the current configuration, SD startup files and custom film library. Use the existing accepted firmware update procedure and keep the existing SD startup script if it already launches MCW1101. Use the candidate firmware and SERVICE.BIN together. Keep personal film data.
2. Upgrade the existing Android app. With the phone connected to the camera hotspot through system Wi-Fi, open GRemote and enter Camera → Extensions. Verify the camera connects and reads focal settings without a pairing import or a visit to the camera's focal menu.
3. Power the camera off and on. Wait over a minute before turning on Wi-Fi, reconnect from the phone and verify that the current settings appear again. Compare both focal values and the active crop against the prior configuration.
4. Change one extension and restore its prior value. Verify the camera readback and test film load on an empty slot or a slot explicitly selected for replacement.

An outstanding explicitly configured focal seed is still applied by the camera's native path. Automatic read-only initialization does not apply that seed. Until it is applied, the app may omit focal values while continuing to show other settings. The preserving upgrade candidate has no seed.

Automatic access is scoped to the camera AP. Connected clients receive a boot-local HMAC credential. The phone recognizes the network-bound Ricoh HTTP API without a pre-enrolled camera certificate. Existing signed mutations and readback remain in use.
