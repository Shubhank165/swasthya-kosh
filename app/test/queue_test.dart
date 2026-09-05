/// Submitting exactly once — 2/3 §9, §10, §15 items 8 and 9.
///
/// The failure this file exists to prevent has two halves, and the second is
/// the one that gets forgotten: **poor signal must not lose an intake, and it
/// must not submit one twice either.** A patient who taps send in a lift and
/// walks out must end up with exactly one record at the hospital — not zero,
/// and not two for a clerk to reconcile with a queue forming behind them.
library;

import 'dart:convert';
import 'dart:io';

import 'package:drift/drift.dart' show Value;
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/consent/consent_repository.dart';
import 'package:medikiosk_app/storage/database.dart';
import 'package:medikiosk_app/submit/queue.dart';

import 'fake_api.dart';
import 'test_sqlite.dart';

void main() {
  useSystemSqlite();

  late LocalDatabase db;
  late FakeBackend backend;
  late SubmissionQueue queue;
  late Directory scratch;

  setUp(() {
    db = LocalDatabase.memory();
    backend = FakeBackend();
    queue = SubmissionQueue(database: db, api: fakeApi(backend));
    scratch = Directory.systemTemp.createTempSync('medikiosk_queue');
  });

  tearDown(() async {
    await db.close();
    if (scratch.existsSync()) scratch.deleteSync(recursive: true);
  });

  Future<void> seedDraft(String id, {String key = 'idem-1'}) =>
      db.saveDraft(DraftsCompanion.insert(
        intakeId: id,
        hospitalId: 'aiia-delhi',
        hospitalName: const Value('All India Institute of Ayurveda'),
        language: 'hi',
        reporter: 'self',
        answersJson: '{}',
        contentVersion: 'questions-2026-09-01',
        startedAt: DateTime.now(),
        updatedAt: DateTime.now(),
        idempotencyKey: key,
      ));

  Map<String, dynamic> record(String id) => {
        'schema_version': '0.1',
        'intake_id': id,
        'source': 'app',
        'status': 'complete',
      };

  group('the reference code', () {
    test('is derived from the intake id, not issued by the backend', () {
      // It has to exist on a phone that has not reached the backend yet: an
      // intake finished offline still gets a code, and the code still finds the
      // record once the queue drains.
      final code = referenceCodeFor('intake-0123456789abcdef');
      expect(code, referenceCodeFor('intake-0123456789abcdef'));
      expect(code, matches(RegExp(r'^MK-[0-9A-Z]{3}-[0-9A-Z]{3}$')));
    });

    test('is readable aloud over a counter', () {
      expect(referenceCodeFor('intake-abc'), startsWith('MK-'));
      // Short ids do not produce a short code, which would be unreadable in a
      // column of codes that are all six characters.
      expect(referenceCodeFor('x').length, referenceCodeFor('intake-abc').length);
    });
  });

  group('a submission that gets through', () {
    test('writes a receipt, then clears the intake from the phone', () async {
      await seedDraft('intake-1');
      await queue.enqueue(intakeId: 'intake-1', payload: record('intake-1'));

      expect(await queue.submitNow('intake-1'), Delivery.accepted);

      // §10: what survives is a reference code and a date. Not the answers.
      final receipt = await db.receiptFor('intake-1');
      expect(receipt, isNotNull);
      expect(receipt!.referenceCode, referenceCodeFor('intake-1'));
      expect(receipt.hospitalName, 'All India Institute of Ayurveda');
      expect(await db.draftFor('intake-1'), isNull);
    });

    test('carries the intake key, not a key per attempt', () async {
      await seedDraft('intake-1', key: 'idem-once');
      await queue.enqueue(intakeId: 'intake-1', payload: record('intake-1'));
      await queue.submitNow('intake-1');

      final ingest = backend.calls.firstWhere((c) => c.path.contains('/ingest'));
      expect(ingest.idempotencyKey, 'idem-once');
    });
  });

  group('a submission with no signal', () {
    test('loses nothing', () async {
      backend.allOffline = true;
      await seedDraft('intake-1');
      await queue.enqueue(intakeId: 'intake-1', payload: record('intake-1'));

      expect(await queue.submitNow('intake-1'), Delivery.queued);

      final draft = await db.draftFor('intake-1');
      expect(draft, isNotNull);
      expect(draft!.queuedPayload, isNotNull, reason: 'the assembled record survives');
      expect(await db.receiptFor('intake-1'), isNull);
    });

    test('goes out exactly once when the signal comes back', () async {
      backend.allOffline = true;
      await seedDraft('intake-1');
      await queue.enqueue(intakeId: 'intake-1', payload: record('intake-1'));
      await queue.submitNow('intake-1');
      expect(backend.callsTo('/ingest'), 1, reason: 'the failed attempt');

      backend.allOffline = false;
      expect(await queue.flush(attempts: 1), 1);
      expect(backend.callsTo('/ingest'), 2);

      // And nothing on any later launch. This is the half that matters: the
      // draft is gone, so there is nothing to post a third time.
      expect(await queue.flush(attempts: 1), 0);
      expect(backend.callsTo('/ingest'), 2);
    });

    test('a 4xx keeps it rather than dropping it', () async {
      // The backend answers an unparseable payload with a 200 and
      // `needs_manual_review`, so a 4xx here is an expired token or a route
      // that moved — neither of which a device resolves by deleting a
      // patient's intake.
      backend.statuses['/ingest'] = 401;
      await seedDraft('intake-1');
      await queue.enqueue(intakeId: 'intake-1', payload: record('intake-1'));

      expect(await queue.submitNow('intake-1'), Delivery.queued);
      expect(await db.draftFor('intake-1'), isNotNull);
    });
  });

  group('a crash between acceptance and cleanup', () {
    test('does not post the record a second time', () async {
      // The state a crash leaves: the receipt written, the draft not yet
      // purged. Without the receipt check this is a duplicate intake.
      await seedDraft('intake-1');
      await queue.enqueue(intakeId: 'intake-1', payload: record('intake-1'));
      await db.saveReceipt(ReceiptsCompanion.insert(
        intakeId: 'intake-1',
        referenceCode: referenceCodeFor('intake-1'),
        hospitalName: 'aiia-delhi',
        submittedAt: DateTime.now(),
      ));

      expect(await queue.flush(attempts: 1), 1);
      expect(backend.callsTo('/ingest'), 0, reason: 'it was already accepted');
      expect(await db.draftFor('intake-1'), isNull, reason: 'the cleanup finished');
    });

    test('an intake already purged reports as sent, not as unsent', () async {
      await db.saveReceipt(ReceiptsCompanion.insert(
        intakeId: 'intake-1',
        referenceCode: 'MK-000-001',
        hospitalName: 'aiia-delhi',
        submittedAt: DateTime.now(),
      ));
      // Telling the patient "saved on this phone" about a record the hospital
      // already has is a lie in the more alarming direction.
      expect(await queue.submitNow('intake-1'), Delivery.accepted);
    });
  });

  group('documents', () {
    Future<File> seedDocument(String intakeId, String id) async {
      final file = File('${scratch.path}/$id.jpg')..writeAsBytesSync([1, 2, 3]);
      await db.into(db.pendingDocuments).insert(PendingDocumentsCompanion.insert(
            documentId: id,
            intakeId: intakeId,
            filePath: file.path,
            capturedAt: DateTime.now(),
          ));
      return file;
    }

    test('go up before the intake is cleared, and then are gone', () async {
      await seedDraft('intake-1');
      final file = await seedDocument('intake-1', 'doc-1');
      await queue.enqueue(intakeId: 'intake-1', payload: record('intake-1'));

      expect(await queue.submitNow('intake-1'), Delivery.accepted);
      expect(backend.callsTo('/documents'), 1);
      // §15 item 9: no image remains on the device after a successful submit.
      expect(file.existsSync(), isFalse);
      expect(await db.documentsFor('intake-1'), isEmpty);
    });

    test('a photo that will not upload keeps the intake alive', () async {
      backend.offline.add('/documents');
      await seedDraft('intake-1');
      final file = await seedDocument('intake-1', 'doc-1');
      await queue.enqueue(intakeId: 'intake-1', payload: record('intake-1'));

      // The answers are at the hospital, so the patient is told it is sent.
      expect(await queue.submitNow('intake-1'), Delivery.accepted);
      // But the prescription photo is not, and purging now would lose it.
      // "Delete on submit" means once the hospital has everything.
      expect(file.existsSync(), isTrue);
      expect(await db.draftFor('intake-1'), isNotNull);

      backend.offline.clear();
      await queue.flush(attempts: 1);
      expect(backend.callsTo('/ingest'), 1, reason: 'the record was not re-sent');
      expect(file.existsSync(), isFalse);
      expect(await db.draftFor('intake-1'), isNull);
    });
  });

  group('consent', () {
    const grant = ConsentGrant(
      consentVersion: '1',
      language: 'hi',
      noticeText: 'the notice as shown',
      granted: ['history_intake'],
      refused: ['document_processing'],
      grantingParty: 'self',
    );

    test('is filed against the intake once the intake exists', () async {
      await seedDraft('intake-1');
      await queue.enqueue(
        intakeId: 'intake-1',
        payload: record('intake-1'),
        consent: grant,
      );
      await queue.submitNow('intake-1');

      final consent = backend.calls.firstWhere((c) => c.path.contains('/consent'));
      final body = jsonDecode(jsonEncode(consent.body)) as Map<String, dynamic>;
      expect(body['intake_id'], 'intake-1');
      expect(body['notice_text'], 'the notice as shown');
      // Refused is named, not inferred from absence: "refused" and "never
      // offered" are different things to a regulator.
      expect(body['refused_purposes'], ['document_processing']);

      // Ordering: the artefact references an intake, so it cannot be filed
      // before the record that creates one.
      final order = backend.calls.map((c) => c.path).toList();
      expect(order.indexOf('/intakes/ingest'), lessThan(order.indexWhere((p) => p.contains('/consent'))));
    });

    test('a consent that will not file blocks the purge', () async {
      // An intake at the hospital with no record of what the patient agreed to
      // is exactly the position §11 exists to prevent. Keeping the draft keeps
      // the grant.
      backend.offline.add('/consent');
      await seedDraft('intake-1');
      await queue.enqueue(
        intakeId: 'intake-1',
        payload: record('intake-1'),
        consent: grant,
      );

      expect(await queue.submitNow('intake-1'), Delivery.accepted);
      expect(await db.draftFor('intake-1'), isNotNull);

      backend.offline.clear();
      await queue.flush(attempts: 1);
      expect(backend.callsTo('/intakes/ingest'), 1);
      expect(await db.draftFor('intake-1'), isNull);
    });
  });
}
