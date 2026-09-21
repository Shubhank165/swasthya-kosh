[app]
title = MediKiosk
package.name = medikiosk
package.domain = in.medikiosk

source.dir = .
source.include_exts = py

version = 0.1

# websocket-client is pure Python, so it needs no recipe - p4a bundles it as-is. Nothing else is
# required: the app renders server-provided JPEG frames and never lays out Indic text itself, so
# no font packages and no Pillow.
#
# kivy is left unpinned on purpose: p4a's own recipe picks the Kivy version tested against the
# Python it builds. Pinning it here overrides that pairing, which is how the first build broke.
# audiostream provides the microphone capture and PCM playback. QR decoding is deliberately NOT
# here: the Jetson already decodes ABHA cards with OpenCV, so the app posts a frame instead of
# carrying a zbar build of its own.
requirements = python3,kivy,websocket-client,audiostream

orientation = landscape
fullscreen = 1

# INTERNET is for the local link to the Jetson (USB tethering or Wi-Fi), not the public internet.
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK,RECORD_AUDIO,CAMERA

android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.allow_backup = False

# Cleartext HTTP to the Jetson's local address. Android blocks plain HTTP by default from API 28,
# and the kiosk link is a private USB/LAN address with no certificate to present. This option
# takes a FILE PATH, not an inline string - buildozer silently ignores unknown keys, so the
# earlier `android.manifest.application_arguments = ...` did nothing at all.
android.extra_manifest_application_arguments = ./extra_manifest_application_arguments.xml

# p4a master builds Python 3.14 but still regenerates Kivy's C with cython<=3.0.12, which emits
# calls to CPython internals 3.14 removed (_PyInterpreterState_GetConfig, and a 5-vs-6 argument
# mismatch). That combination does not compile. v2024.01.21 is the last release pairing Python
# 3.11 with a Cython that matches it.
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
