/// What this app is allowed to log — 2/3 §10, §16.
///
/// **No clinical text, ever.** Not a prompt, not an answer, not a response
/// body, not a patient's own words. "Do not put clinical data in logs, crash
/// reports or analytics" is a hard rule, and the way to keep a hard rule is to
/// make the compliant thing the only convenient one: this takes an event name
/// and a map of small scalars, and there is no `log(String message)` to reach
/// for when in a hurry.
///
/// Identifiers are fine and are the reason `core/ids.dart` makes them random:
/// an intake id means nothing to anyone who does not already hold the record.
///
/// There is no crash reporter wired to this, deliberately (§10: "default to not
/// wiring one"). If one is ever added, it attaches here, where the payload is
/// already known to be free of clinical content.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';

/// Emit one structured event.
///
/// [fields] must contain identifiers, counts, status codes, versions and
/// booleans — never anything a patient said or was asked. Values are
/// `toString`ed, so passing a rich object logs whatever its `toString` happens
/// to include; pass scalars.
void logEvent(String event, {Map<String, Object?> fields = const {}}) {
  if (kReleaseMode) {
    // Nothing at all in a release build. The events below are for a developer
    // watching a debug run; shipping them would put a stream of intake ids into
    // logcat on a patient's phone for no one's benefit.
    return;
  }
  final line = <String, Object?>{
    'event': event,
    for (final entry in fields.entries) entry.key: entry.value?.toString(),
  };
  debugPrint(jsonEncode(line));
}
