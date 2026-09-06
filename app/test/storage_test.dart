/// Local storage — 2/3 §10, §15 item 9.
///
/// The property that matters: **after a successful submit, no clinical data and
/// no image remains on the device.** The phone is not a medical record store,
/// and a patient's history belongs where a physician can see it in context.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/storage/database.dart';

import 'test_sqlite.dart';

void main() {
  useSystemSqlite();

  late LocalDatabase db;
  late Directory scratch;

  setUp(() {
    db = LocalDatabase.memory();
    scratch = Directory.systemTemp.createTempSync('medikiosk_test');
  });

  tearDown(() async {
    await db.close();
    if (scratch.existsSync()) scratch.deleteSync(recursive: true);
  });

  DraftsCompanion draft(String id, {DateTime? updatedAt}) => DraftsCompanion.insert(
        intakeId: id,
        hospitalId: 'aiia-delhi',
        language: 'hi',
        reporter: 'self',
        answersJson: '{"chief_complaint":{"status":"answered"}}',
        contentVersion: 'questions-2026-09-01',
        startedAt: DateTime.now(),
        updatedAt: updatedAt ?? DateTime.now(),
        idempotencyKey: 'key-$id',
      );

  File writeImage(String name) {
    final file = File('${scratch.path}/$name')..writeAsBytesSync([1, 2, 3, 4]);
    return file;
  }

  group('drafts', () {
    test('a draft round-trips', () async {
      await db.saveDraft(draft('intake-1'));
      final loaded = await db.draftFor('intake-1');
      expect(loaded!.language, 'hi');
      expect(loaded.idempotencyKey, 'key-intake-1');
    });

    test('saving twice updates rather than duplicating', () async {
      await db.saveDraft(draft('intake-1'));
      await db.saveDraft(draft('intake-1'));
      expect((await db.select(db.drafts).get()).length, 1);
    });

    test('the latest draft is the one offered for resume', () async {
      await db.saveDraft(draft('old',
          updatedAt: DateTime.now().subtract(const Duration(hours: 2))));
      await db.saveDraft(draft('recent'));
      expect((await db.latestDraft())!.intakeId, 'recent');
    });

    test('a draft older than a week is reported stale', () async {
      // §5: clinical answers go stale. "How long have you had this pain?"
      // answered last week is wrong today, and submitting it silently would be
      // worse than asking again.
      await db.saveDraft(draft('fresh'));
      await db.saveDraft(draft('ancient',
          updatedAt: DateTime.now().subtract(const Duration(days: 8))));

      final stale = await db.staleDrafts();
      expect(stale.map((d) => d.intakeId), ['ancient']);
    });

    test('the one-week boundary is not crossed early', () async {
      await db.saveDraft(draft('six_days',
          updatedAt: DateTime.now().subtract(const Duration(days: 6))));
      expect(await db.staleDrafts(), isEmpty);
    });
  });

  group('clearing on submit', () {
    test('nothing about the intake survives, rows or files', () async {
      final image = writeImage('scan.jpg');
      await db.saveDraft(draft('intake-1'));
      await db.into(db.pendingDocuments).insert(PendingDocumentsCompanion.insert(
            documentId: 'doc-1',
            intakeId: 'intake-1',
            filePath: image.path,
            capturedAt: DateTime.now(),
          ));

      await db.purgeIntake('intake-1');

      expect(await db.draftFor('intake-1'), isNull);
      expect(await db.select(db.pendingDocuments).get(), isEmpty);
      expect(image.existsSync(), isFalse,
          reason: 'a row deleted while the JPEG survives is the leak this prevents');
    });

    test('another intake is untouched', () async {
      await db.saveDraft(draft('mine'));
      await db.saveDraft(draft('someone_elses'));
      await db.purgeIntake('mine');
      expect(await db.draftFor('someone_elses'), isNotNull);
    });

    test('a missing file does not stop the purge', () async {
      // Best effort on the file; the row goes either way.
      await db.saveDraft(draft('intake-1'));
      await db.into(db.pendingDocuments).insert(PendingDocumentsCompanion.insert(
            documentId: 'doc-1',
            intakeId: 'intake-1',
            filePath: '${scratch.path}/never_existed.jpg',
            capturedAt: DateTime.now(),
          ));
      await db.purgeIntake('intake-1');
      expect(await db.draftFor('intake-1'), isNull);
    });

    test('a receipt is what survives, and it is not clinical', () async {
      // §7.4: a reference code to show at the registration desk. No answers, no
      // complaint, no diagnosis — nothing a stranger picking up the phone
      // learns anything medical from.
      await db.into(db.receipts).insert(ReceiptsCompanion.insert(
            intakeId: 'intake-1',
            referenceCode: 'MK-4821',
            hospitalName: 'AIIA, New Delhi',
            submittedAt: DateTime.now(),
          ));
      final receipt = await db.select(db.receipts).getSingle();
      expect(receipt.referenceCode, 'MK-4821');

      final columns = db.receipts.$columns.map((c) => c.name).toSet();
      expect(columns, {
        'intake_id',
        'reference_code',
        'hospital_name',
        'submitted_at',
        // An identifier the hospital chose, kept so a document uploaded days
        // later can still be addressed to the right intake. Not clinical: it
        // is an opaque id, exactly like `intake_id` beside it.
        'server_intake_id',
      });
    });
  });

  group('sign-out', () {
    test('everything goes, including receipts', () async {
      final image = writeImage('scan.jpg');
      await db.saveDraft(draft('intake-1'));
      await db.into(db.pendingDocuments).insert(PendingDocumentsCompanion.insert(
            documentId: 'doc-1',
            intakeId: 'intake-1',
            filePath: image.path,
            capturedAt: DateTime.now(),
          ));
      await db.into(db.receipts).insert(ReceiptsCompanion.insert(
            intakeId: 'intake-1',
            referenceCode: 'MK-1',
            hospitalName: 'AIIA',
            submittedAt: DateTime.now(),
          ));

      await db.purgeEverything();

      expect(await db.select(db.drafts).get(), isEmpty);
      expect(await db.select(db.pendingDocuments).get(), isEmpty);
      expect(await db.select(db.receipts).get(), isEmpty);
      expect(image.existsSync(), isFalse);
    });
  });

  group('the schema holds no clinical text in a column of its own', () {
    test('answers are one opaque blob', () async {
      // A column per field would need a migration every time a clinician edits
      // a pathway, and would put question ids in a schema that outlives them.
      final columns = db.drafts.$columns.map((c) => c.name).toSet();
      expect(columns.contains('answers_json'), isTrue);
      expect(
        columns.where((c) => c.contains('complaint') || c.contains('severity')),
        isEmpty,
      );
    });
  });
}
