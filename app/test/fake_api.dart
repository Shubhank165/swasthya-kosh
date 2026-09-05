/// A dio adapter that answers without a network — for the queue and flow tests.
///
/// Deliberately not a mock of [ApiClient]: the queue's correctness argument is
/// about headers, status codes and what happens when a request throws, and a
/// mock of the client would let all three be asserted against a stub of itself.
/// This stops one layer lower, so the `Idempotency-Key` a test reads is the one
/// dio actually put on the wire.
library;

import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:medikiosk_app/core/api.dart';

class Call {
  Call(this.method, this.path, this.headers, this.body);
  final String method;
  final String path;
  final Map<String, dynamic> headers;
  final Object? body;

  String? get idempotencyKey => headers['Idempotency-Key']?.toString();
}

class FakeBackend implements HttpClientAdapter {
  FakeBackend();

  final calls = <Call>[];

  /// Paths that should fail as if there were no signal.
  final offline = <String>{};

  /// Whole-backend outage, which is what a patient in a lift has.
  bool allOffline = false;

  /// Status to answer with, per path prefix.
  final statuses = <String, int>{};

  /// Body to answer with, per path prefix. Anything not listed gets the small
  /// generic object below, which is enough for the ingest and consent routes.
  final bodies = <String, String>{};

  int callsTo(String path) => calls.where((c) => c.path.contains(path)).length;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    calls.add(Call(options.method, options.path, options.headers, options.data));

    if (allOffline || offline.any(options.path.contains)) {
      throw DioException.connectionError(
        requestOptions: options,
        reason: 'no signal',
      );
    }

    final status = statuses.entries
            .firstWhere(
              (e) => options.path.contains(e.key),
              orElse: () => const MapEntry('', 200),
            )
            .value;

    final body = bodies.entries
        .firstWhere(
          (e) => options.path.contains(e.key),
          orElse: () => const MapEntry('', ''),
        )
        .value;

    return ResponseBody.fromString(
      body.isEmpty
          ? jsonEncode({
              'intake_id': 'x',
              'status': 'stored',
              'consent_id': 'c',
              'verified': true,
              'source': 'mock',
            })
          : body,
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

ApiClient fakeApi(FakeBackend backend) {
  final dio = Dio(BaseOptions(
    baseUrl: 'http://test.invalid/api/v1',
    validateStatus: (_) => true,
  ))
    ..httpClientAdapter = backend;
  return ApiClient.withDio(dio);
}
