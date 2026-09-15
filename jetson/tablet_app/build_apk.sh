#!/bin/bash
# Build the MediKiosk tablet APK. Run inside WSL Ubuntu (or any Linux host with a JDK).
#
#   ~/medikiosk-build/app/build_apk.sh
#
# The first run downloads the Android SDK and NDK (several GB) and takes 20-40 minutes.
# Subsequent runs are incremental and take a couple of minutes.
set -euo pipefail

# WSL interop appends the entire Windows PATH, which contains spaces and parentheses. That breaks
# buildozer's subprocess quoting and lets Windows executables shadow the Linux toolchain, so the
# PATH is rebuilt from scratch here rather than inherited.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

VENV=${VENV:-$HOME/medikiosk-build/.venv}
if [ -d "$VENV" ]; then
  # shellcheck disable=SC1091
  . "$VENV/bin/activate"
fi

# Google's SDK licences must be accepted before build-tools will install. Buildozer prompts for
# them on stdin, which a detached build has none of, so it silently skips build-tools and then
# fails much later with the confusing "Aidl not found, please install it."
#
# --sdk_root is not optional: the cmdline-tools build buildozer downloads (6514223) cannot work
# out its own location and dies with "Could not create settings" plus a bare
# IllegalArgumentException if it is left off.
SDK_ROOT=$HOME/.buildozer/android/platform/android-sdk
if [ -x "$SDK_ROOT/tools/bin/sdkmanager" ]; then
  yes | "$SDK_ROOT/tools/bin/sdkmanager" --sdk_root="$SDK_ROOT" --licenses > /dev/null 2>&1 || true
fi

cd "$(dirname "$0")"
exec buildozer -v android debug
