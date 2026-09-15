/// The HTTP client — 2/3 §13.
///
/// One dio instance with an auth interceptor and bounded retry. Two properties
/// are worth stating because they are easy to lose later:
///
/// **No clinical text is ever logged.** Not a prompt, not an answer, not a
/// response body. The `LogInterceptor` dio ships with prints request and
/// response bodies by default, which for this app is a patient's medical
/// history in logcat — so it is deliberately not installed. What replaces it is
/// `core/logging.dart`, which logs the method, the path and the status code and
/// has no way to accept a body even by accident.
///
/// **Retry is bounded and idempotent-only.** A POST that may have been received
/// is not retried blindly; submission carries an `Idempotency-Key` so a retry is
/// safe, and that key is generated once per intake rather than once per attempt.
library;

import 'dart:async';

import 'package:dio/dio.dart';

import 'config.dart';
import 'logging.dart';

typedef TokenReader = Future<String?> Function();

/// The hospital the patient has chosen, at the moment a request goes out.
///
/// A callback rather than a value because it changes mid-session: the client is
/// built before screen 2 and the choice is made on it.
typedef HospitalReader = String? Function();

class ApiClient {
  ApiClient({
    required AppConfig config,
    TokenReader? readToken,
    HospitalReader? readHospitalId,
  })
      : _dio = Dio(BaseOptions(
          baseUrl: '${config.baseUrl}/api/v1',
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 30),
          sendTimeout: const Duration(seconds: 60),
          // Never throw on a status code; callers decide. A 304 on the bundle
          // is a success, and an exception for it would be absurd.
          validateStatus: (_) => true,
          headers: {'Accept': 'application/json'},
        )) {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await readToken?.call();
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        }

        // **A patient session says who, not where.** A kiosk's token is bound
        // to one hospital; a patient may complete an intake for any hospital
        // they choose, so the backend takes the hospital from this header and
        // refuses a patient request without it. Sending it is not optional —
        // an app that omits it can sign in and then do nothing at all, which
        // is the integration gap the live end-to-end test exists to catch.
        final hospitalId = readHospitalId?.call();
        if (hospitalId != null && hospitalId.isNotEmpty) {
          options.headers['X-Hospital-Id'] = hospitalId;
        }
        handler.next(options);
      },
      onResponse: (response, handler) {
        logEvent('http', fields: {
          'method': response.requestOptions.method,
          'path': response.requestOptions.path,
          'status': response.statusCode,
        });
        handler.next(response);
      },
      onError: (error, handler) {
        logEvent('http_error', fields: {
          'method': error.requestOptions.method,
          'path': error.requestOptions.path,
          // The type, never `error.message`: a dio message can carry the
          // response body, and the response body is a patient's record.
          'type': error.type.name,
        });
        handler.next(error);
      },
    ));
  }

  ApiClient.withDio(this._dio);

  final Dio _dio;
  Dio get raw => _dio;

  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? query,
    Map<String, String>? headers,
  }) =>
      _dio.get<T>(path, queryParameters: query, options: Options(headers: headers));

  Future<Response<T>> post<T>(
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) =>
      _dio.post<T>(path, data: body, options: Options(headers: headers));

  /// The one destructive verb this client offers.
  ///
  /// No body and no query: the only route that uses it takes its subject from
  /// the session token, so there is nothing to pass and nothing to aim wrongly.
  Future<Response<T>> delete<T>(
    String path, {
    Map<String, String>? headers,
  }) =>
      _dio.delete<T>(path, options: Options(headers: headers));

  /// A bounded retry with exponential backoff.
  ///
  /// Retries only what can succeed later: a timeout, a connection failure, or a
  /// 5xx. A 4xx is the server saying the request itself is wrong, and repeating
  /// it produces the same answer more slowly — the same reasoning the backend's
  /// Pub/Sub worker uses to choose between 204 and 500.
  static Future<Response<T>> retrying<T>(
    Future<Response<T>> Function() send, {
    int attempts = 4,
    Duration initialDelay = const Duration(seconds: 1),
  }) async {
    var delay = initialDelay;
    Object? lastError;
    for (var attempt = 0; attempt < attempts; attempt++) {
      try {
        final response = await send();
        final status = response.statusCode ?? 0;
        if (status < 500) return response;
        lastError = response;
      } on DioException catch (error) {
        if (error.type == DioExceptionType.badResponse) rethrow;
        lastError = error;
      }
      if (attempt < attempts - 1) {
        await Future<void>.delayed(delay);
        delay *= 2;
      }
    }
    if (lastError is Response<T>) return lastError;
    throw lastError ?? Exception('request failed');
  }
}
