/// Fetching and caching the question bundle — 2/3 §4.
///
/// Cached locally with its version, refreshed on launch when online, and run
/// from cache when not. The cache is what makes the app usable on a train on
/// the way to the hospital, which is the situation it exists for.
///
/// The bundle holds no patient data — it is the questions an OPD asks — so it
/// lives in ordinary application-support storage rather than in the encrypted
/// database. Encrypting public content would cost startup time and protect
/// nothing.
library;

import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../core/api.dart';
import '../core/logging.dart';
import 'bundle.dart';

class BundleFetchResult {
  const BundleFetchResult({required this.bundle, required this.fromCache});
  final ContentBundle bundle;
  final bool fromCache;
}

class BundleRepository {
  BundleRepository({required ApiClient api, Directory? cacheDirectory})
      : _api = api,
        _cacheDirectory = cacheDirectory;

  final ApiClient _api;
  Directory? _cacheDirectory;

  static const _bodyFile = 'question_bundle.json';
  static const _etagFile = 'question_bundle.etag';

  Future<Directory> _directory() async =>
      _cacheDirectory ??= await getApplicationSupportDirectory();

  /// The current bundle.
  ///
  /// Sends the cached `ETag` as `If-None-Match`, so an unchanged bundle costs a
  /// 304 and no body — 80 KB saved on every launch, on what may be a patient's
  /// mobile data.
  ///
  /// Any failure falls back to the cache. A backend that is down must not stop
  /// a patient filling in a form they can submit later.
  Future<BundleFetchResult?> load() async {
    final cached = await _readCache();
    try {
      final etag = await _readEtag();
      final response = await _api.get<dynamic>(
        '/content/bundle',
        headers: etag == null ? null : {'If-None-Match': etag},
      );

      if (response.statusCode == 304 && cached != null) {
        return BundleFetchResult(bundle: cached, fromCache: true);
      }
      if (response.statusCode == 200 && response.data != null) {
        final body = response.data is String
            ? response.data as String
            : jsonEncode(response.data);
        final bundle = ContentBundle.parse(body);

        if (!bundle.isUsable) {
          // §4: a schema this app cannot produce. **Do not cache it**, and do
          // not let it displace a bundle that works — a backend rolling forward
          // to a newer contract would otherwise brick an app that was holding a
          // perfectly usable copy of the older one, and the backend still
          // accepts records against every version its normalizers support.
          //
          // With no cache to fall back on there is nothing to run, so the
          // unusable bundle is handed back for the UI to refuse on: §4 says
          // tell the patient to update, which needs something to check.
          logEvent('bundle_unsupported', fields: {
            'schema_version': bundle.schemaVersion,
            'bundle_format': bundle.bundleFormat,
            'have_cache': cached != null,
          });
          return cached == null
              ? BundleFetchResult(bundle: bundle, fromCache: false)
              : BundleFetchResult(bundle: cached, fromCache: true);
        }

        await _writeCache(body, response.headers.value('etag'));
        return BundleFetchResult(bundle: bundle, fromCache: false);
      }
    } on Object {
      // Offline, DNS failure, timeout, a proxy returning nonsense. All the same
      // answer: use what we have.
    }
    return cached == null ? null : BundleFetchResult(bundle: cached, fromCache: true);
  }

  Future<ContentBundle?> _readCache() async {
    try {
      final file = File(p.join((await _directory()).path, _bodyFile));
      if (!file.existsSync()) return null;
      return ContentBundle.parse(await file.readAsString());
    } on Object {
      // A corrupt cache is a cache miss, not a crash on launch.
      return null;
    }
  }

  Future<String?> _readEtag() async {
    try {
      final file = File(p.join((await _directory()).path, _etagFile));
      return file.existsSync() ? (await file.readAsString()).trim() : null;
    } on Object {
      return null;
    }
  }

  Future<void> _writeCache(String body, String? etag) async {
    try {
      final directory = await _directory();
      await directory.create(recursive: true);
      await File(p.join(directory.path, _bodyFile)).writeAsString(body);
      if (etag != null) {
        await File(p.join(directory.path, _etagFile)).writeAsString(etag);
      }
    } on Object {
      // A full disk must not fail the launch; the next one refetches.
    }
  }
}
