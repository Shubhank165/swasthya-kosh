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
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
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

/// A picker that returns bytes this test made, rather than opening a camera.
///
/// The only thing stubbed in the document test below. Everything downstream of
/// it — the downscale, the EXIF strip, the disk write, the multipart POST — is
/// the real path, because the multipart POST is the part that had never once
/// run against the real endpoint.
class _FixedPicker implements PagePicker {
  _FixedPicker(this.bytes);

  final Uint8List bytes;

  @override
  Future<Uint8List?> pick({required bool fromCamera}) async => bytes;
}

/// A synthetic prescription: a light page with dark text-like marks.
Uint8List _page({int width = 1600, int height = 2200}) {
  final image = img.Image(width: width, height: height);
  img.fill(image, color: img.ColorRgb8(245, 245, 240));
  for (var line = 0; line < 30; line++) {
    final y = (height * 0.1 + line * (height * 0.025)).round();
    img.fillRect(
      image,
      x1: (width * 0.1).round(),
      y1: y,
      x2: (width * 0.9).round(),
      y2: y + 8,
      color: img.ColorRgb8(20, 20, 20),
    );
  }
  return Uint8List.fromList(img.encodeJpg(image, quality: 90));
}

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

  test('a photographed document reaches the real multipart endpoint', () async {
    // 3/3 §B2. Every other path in this app was verified against a running
    // backend and each live run found something no unit test could. This one
    // had never been run: the multipart upload was exercised only against a
    // stub that accepted whatever it was handed.
    final scratch = Directory.systemTemp.createTempSync('medikiosk_live_doc');
    final db = LocalDatabase.memory();
    addTearDown(() async {
      await db.close();
      if (scratch.existsSync()) scratch.deleteSync(recursive: true);
    });

    final anonymous =
        ApiClient(config: const AppConfig(baseUrl: _baseUrl, appVersion: '1.0.0'));
    final phone = '+9197${DateTime.now().millisecondsSinceEpoch % 100000000}';
    final challenge = await anonymous.post<Map<String, dynamic>>(
      '/auth/otp/request',
      body: {'phone': phone},
    );
    expect(challenge.statusCode, 201, reason: 'is the backend running?');
    final session = await anonymous.post<Map<String, dynamic>>(
      '/auth/otp/verify',
      body: {
        'challenge_id': challenge.data!['challenge_id'],
        'code': challenge.data!['code'],
      },
    );
    expect(session.statusCode, 200);

    Hospital? chosen;
    final api = ApiClient(
      config: const AppConfig(baseUrl: _baseUrl, appVersion: '1.0.0'),
      readToken: () async => session.data!['token'] as String,
      readHospitalId: () => chosen?.id,
    );

    final bundle = ContentBundle.parse(
      (await api.get<String>('/content/bundle')).data!,
    );
    final hospitals = await HospitalRepository(api: api).list();
    final hospital = chosen = hospitals.first;

    final documents = DocumentStore(
      database: db,
      directory: scratch,
      picker: _FixedPicker(_page()),
    );
    final queue = SubmissionQueue(database: db, api: api);
    final flow = await IntakeFlow.begin(
      database: db,
      queue: queue,
      documents: documents,
      bundle: bundle,
      language: 'en',
      hospitalId: hospital.id,
      hospitalName: hospital.displayName,
      departmentCode:
          hospital.departments.isEmpty ? null : hospital.departments.first.code,
      reporter: 'self',
      appVersion: '1.0.0',
      patientRef: PatientRef.phone(session.data!['patient_ref'] as String),
    );

    var asked = 0;
    while (flow.stage == FlowStage.question && asked < 500) {
      final (value, text) = answerFor(flow.question!);
      await flow.answer(value, text);
      asked += 1;
    }
    expect(flow.stage, FlowStage.documents);

    final added = await documents.add(
      intakeId: flow.intakeId,
      fromCamera: true,
      kind: 'prescription',
    );
    expect(added, isA<PageAdded>(), reason: 'the synthetic page should pass quality');

    flow.continueToReview();
    await flow.submit();
    expect(flow.stage, FlowStage.submitted);
    expect(flow.queued, isFalse, reason: 'the hospital accepted the record');

    // The row is dropped and the file deleted only when the upload actually
    // succeeded — §10: nothing clinical stays on the device once the hospital
    // has it. So an empty document table is the assertion that the multipart
    // POST returned 2xx, and the empty directory is the assertion that the
    // photograph is gone.
    expect(await db.documentsFor(flow.intakeId), isEmpty);
    expect(
      scratch.listSync(recursive: true).whereType<File>(),
      isEmpty,
      reason: 'the photograph must not outlive its upload',
    );

    // The id the hospital filed this under, which is **not** the one the phone
    // made up: the contract asks for a UUID and this app sends `intake-<hex>`,
    // so the backend derives one. Posting the document to the local id 404s,
    // and it 404s after the record was accepted — the patient sees a successful
    // submission and the doctor never sees the prescription. That is the bug
    // this line guards.
    final receipt = await db.receiptFor(flow.intakeId);
    final serverIntakeId = receipt!.serverIntakeId;
    expect(serverIntakeId, isNotNull);
    expect(serverIntakeId, isNot(flow.intakeId));

    // And the hospital agrees it has one, asked from the other side of the wire
    // as staff — a patient session may not list another party's documents, and
    // the fact that it may not is itself worth leaving asserted here.
    final staff = Dio(BaseOptions(
      baseUrl: '$_baseUrl/api/v1',
      validateStatus: (_) => true,
      headers: {
        'X-User-Id': 'live-test-staff',
        'X-User-Role': 'staff',
        'X-Hospital-Id': hospital.id,
      },
    ));
    // The local id lists nothing, because the hospital has no such intake. It
    // answers 200 with an empty list rather than 404 — a document listing is a
    // collection, and an empty one is a valid answer — which is precisely why
    // the original bug was silent: nothing on either side raised.
    final underLocalId =
        await staff.get<dynamic>('/intakes/${flow.intakeId}/documents');
    expect(underLocalId.data, isEmpty);
    final listed = await staff.get<dynamic>('/intakes/$serverIntakeId/documents');
    expect(listed.statusCode, 200);
    expect(listed.data, hasLength(1));
    expect((listed.data as List).first['kind'], 'prescription');
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
