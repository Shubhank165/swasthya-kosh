/// Point host tests at the system SQLite.
///
/// On a device the library comes from `sqlcipher_flutter_libs`, which is the
/// only SQLite package this app depends on — see the note in `pubspec.yaml`. A
/// `flutter test` run on the host has none, and `libsqlite3.so` without a
/// version suffix is a `-dev` package that CI machines do not necessarily
/// have.
///
/// The schema and every query are identical either way, so tests that run here
/// test the same code. What they do *not* cover is encryption — that is a
/// property of the file on disk on a real device, and is asserted at runtime by
/// the `cipher_version` check in `LocalDatabase.open`.
library;

import 'dart:ffi';
import 'dart:io';

import 'package:sqlite3/open.dart';

var _done = false;

void useSystemSqlite() {
  if (_done) return;
  _done = true;
  if (!Platform.isLinux) return;
  open.overrideFor(OperatingSystem.linux, () {
    for (final candidate in [
      'libsqlite3.so.0',
      '/usr/lib/x86_64-linux-gnu/libsqlite3.so.0',
      'libsqlite3.so',
    ]) {
      try {
        return DynamicLibrary.open(candidate);
      } on ArgumentError {
        continue;
      }
    }
    throw StateError('no system libsqlite3 found for host tests');
  });
}
