/// Identifiers this device makes for itself.
///
/// Random, and **never derived from anything about the patient**. An intake id
/// that encoded a phone number would put a phone number into a log line the
/// first time anybody logged an id, and ids are the one thing that gets logged
/// freely precisely because they are supposed to mean nothing on their own.
library;

import 'dart:math';

String newLocalId(String prefix, {Random? random}) {
  final source = random ?? Random.secure();
  final bytes = List.generate(16, (_) => source.nextInt(256));
  final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '$prefix-$hex';
}
