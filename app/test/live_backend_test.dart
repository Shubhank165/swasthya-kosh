/// One whole intake, against a backend that is actually running — §15 item 2.
///
/// Every other test in this directory stubs the network. This one does not: it
/// fetches the real bundle the backend compiles from `clinical/questions/**`,
/// signs in through the real OTP endpoints, walks whatever questions that
/// bundle contains, and posts the assembled record to `/intakes/ingest` — which
/// either accepts it or does not.
///
/// **It is the only test that can catch a contract drift between the two
/// sides**, because it is the only one where the record is validated by the
/// backend's own normalizer rather than by a fixture this repository keeps in
/// step by hand.
///
/// It does not run by default, because it needs a backend:
///
/// ```
/// make dev-detached                       # from the repository root
/// cd app && flutter test test/live_backend_test.dart \
///     --dart-define=MEDIKIOSK_LIVE=http://localhost:8000
/// ```
///
/// Without that define it reports as skipped rather than failing, so a normal
/// `flutter test` on a laptop with nothing running stays green and honest.
library;

import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/content/answer.dart';
import 'package:medikiosk_app/content/bundle.dart';
import 'package:medikiosk_app/core/api.dart';
import 'package:medikiosk_app/core/config.dart';
import 'package:medikiosk_app/documents/document_store.dart';
import 'package:medikiosk_app/identity/hospital_repository.dart';
import 'package:medikiosk_app/intake/flow.dart';
import 'package:medikiosk_app/storage/database.dart';
import 'package:medikiosk_app/submit/record.dart';
import 'package:medikiosk_app/submit/queue.dart';

import 'test_sqlite.dart';

const _baseUrl = String.fromEnvironment('MEDIKIOSK_LIVE');

/// An answer for whichever question the walker puts next.
///
/// Every yes/no answers **no**, which is what keeps this from tripping a
/// red-flag rule and ending the intake early. That the intake *would* end early
/// is not a bug — it is §6 working — but this test is here to exercise the
/// completed path, and the aborted one is covered in `flow_test.dart`.
(AnswerValue, String) answerFor(Question question) => switch (question.answerType) {
      AnswerType.singleChoice => (
          CodedValue(question.options!.first),
          question.options!.first,
        ),
      AnswerType.multiChoice => (
          CodedListValue([question.options!.first]),
          question.options!.first,
        ),
      AnswerType.yesNoUnknown => (const BoolValue(false), 'No'),
      AnswerType.number => (const NumberValue(1), '1'),
      AnswerType.scale => (const ScaleValue(3), '3'),
      AnswerType.duration => (
          const DurationValue(n: 2, unit: 'day'),
          '2 days',
        ),
      AnswerType.date => (
          DateValue(DateTime.now().toIso8601String().substring(0, 10)),
          'today',
        ),
      AnswerType.freeText => (const TextValue('none'), 'none'),
      AnswerType.unknown => (const TextValue('none'), 'none'),
    };

void main() {
  useSystemSqlite();

  final skip = _baseUrl.isEmpty
      ? 'needs a running backend: pass --dart-define=MEDIKIOSK_LIVE=http://localhost:8000'
      : null;

  test('a whole intake reaches the hospital', () async {
    final scratch = Directory.systemTemp.createTempSync('medikiosk_live');
    final db = LocalDatabase.memory();
    addTearDown(() async {
      await db.close();
      if (scratch.existsSync()) scratch.deleteSync(recursive: true);
    });

    // --- sign in, the way the app does (§7.1) -------------------------------
    final anonymous =
        ApiClient(config: const AppConfig(baseUrl: _baseUrl, appVersion: '1.0.0'));
    final phone = '+9198${DateTime.now().millisecondsSinceEpoch % 100000000}';

    final challenge = await anonymous.post<Map<String, dynamic>>(
      '/auth/otp/request',
      body: {'phone': phone},
    );
    expect(challenge.statusCode, 201, reason: 'is the backend running?');
    final code = challenge.data!['code'] as String?;
    expect(
      code,
      isNotNull,
      reason: 'the mock OTP sender returns the code outside production',
    );

    final session = await anonymous.post<Map<String, dynamic>>(
      '/auth/otp/verify',
      body: {'challenge_id': challenge.data!['challenge_id'], 'code': code},
    );
    expect(session.statusCode, 200);
    final token = session.data!['token'] as String;

    // The hospital is chosen on screen 2 and the client picks it up from there,
    // because a patient session says *who*, not *where* (§7.1).
    Hospital? chosen;
    final api = ApiClient(
      config: const AppConfig(baseUrl: _baseUrl, appVersion: '1.0.0'),
      readToken: () async => token,
      readHospitalId: () => chosen?.id,
    );

    // --- the content both ends walk (§3, §4) --------------------------------
    final bundleResponse = await api.get<String>('/content/bundle');
    expect(bundleResponse.statusCode, 200);
    final bundle = ContentBundle.parse(bundleResponse.data!);
    expect(bundle.questions, isNotEmpty);

    final hospitals = await HospitalRepository(api: api).list();
    expect(hospitals, isNotEmpty, reason: 'run `make seed`');
    final hospital = chosen = hospitals.first;

    // --- the intake ---------------------------------------------------------
    final queue = SubmissionQueue(database: db, api: api);
    final flow = await IntakeFlow.begin(
      database: db,
      queue: queue,
      documents: DocumentStore(database: db, directory: scratch),
      bundle: bundle,
      language: 'en',
      hospitalId: hospital.id,
      hospitalName: hospital.displayName,
      departmentCode: hospital.departments.isEmpty ? null : hospital.departments.first.code,
      reporter: 'self',
      appVersion: '1.0.0',
      patientRef: PatientRef.phone(session.data!['patient_ref'] as String),
    );

    // Walk whatever the bundle actually contains. Bounded, so a walker that
    // stops advancing fails here rather than hanging a CI job.
    var asked = 0;
    while (flow.stage == FlowStage.question && asked < 500) {
      final (value, text) = answerFor(flow.question!);
      await flow.answer(value, text);
      asked += 1;
    }
    expect(asked, greaterThan(0));
    expect(
      flow.stage,
      FlowStage.documents,
      reason: 'answering no to everything should not trip a red-flag rule',
    );

    flow.continueToReview();
    await flow.submit();

    // --- what the backend made of it ----------------------------------------
    expect(flow.stage, FlowStage.submitted);
    expect(flow.queued, isFalse, reason: 'the hospital accepted it');
    // §10: nothing clinical stays on the device once it has been accepted.
    expect(await db.draftFor(flow.intakeId), isNull);

    final receipt = await db.receiptFor(flow.intakeId);
    expect(receipt!.referenceCode, flow.referenceCode);
  }, skip: skip);

  test('the same record replayed creates nothing', () async {
    // The property the `Idempotency-Key` exists for, checked against the real
    // guard rather than a fake that returns whatever it was told to.
    final api = ApiClient(config: const AppConfig(baseUrl: _baseUrl, appVersion: '1.0.0'));
    final challenge = await api.post<Map<String, dynamic>>(
      '/auth/otp/request',
      body: {'phone': '+919812345678'},
    );
    final session = await api.post<Map<String, dynamic>>(
      '/auth/otp/verify',
      body: {
        'challenge_id': challenge.data!['challenge_id'],
        'code': challenge.data!['code'],
      },
    );
    final hospitals = await HospitalRepository(api: api).list();
    final authed = Dio(BaseOptions(
      baseUrl: '$_baseUrl/api/v1',
      validateStatus: (_) => true,
      headers: {
        'Authorization': 'Bearer ${session.data!['token']}',
        'X-Hospital-Id': hospitals.first.id,
        'Idempotency-Key': 'live-test-${DateTime.now().millisecondsSinceEpoch}',
      },
    ));
    final payload = {
      'schema_version': '0.1',
      'intake_id': 'live-${DateTime.now().millisecondsSinceEpoch}',
      'source': 'app',
      'kiosk_id': null,
      'app_version': '1.0.0',
      'hospital_id': hospitals.first.id,
      'started_at': DateTime.now().toIso8601String(),
      'completed_at': DateTime.now().toIso8601String(),
      'status': 'complete',
      'language': 'en',
      'reporter': 'self',
      'patient_ref': {'type': 'guest', 'value': null},
      'turns': <dynamic>[],
      'fields': <String, dynamic>{},
      'red_flags': <dynamic>[],
      'content_version': 'live-test',
    };

    final first = await authed.post<Map<String, dynamic>>('/intakes/ingest', data: payload);
    final second = await authed.post<Map<String, dynamic>>('/intakes/ingest', data: payload);

    expect(first.statusCode, 200);
    expect(second.statusCode, 200);
    expect(second.data!['intake_id'], first.data!['intake_id']);
  }, skip: skip);
}
