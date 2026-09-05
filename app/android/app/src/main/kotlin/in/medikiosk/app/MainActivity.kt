// `in` is a Kotlin keyword, so the package segment is backtick-escaped here.
// The Android namespace and applicationId in build.gradle carry no backticks —
// they are plain identifiers, and a backtick is not legal in either.
package `in`.medikiosk.app

import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity()
