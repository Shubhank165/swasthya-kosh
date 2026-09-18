/// Local storage — 2/3 §10.
///
/// **Encrypted at rest, and cleared on submit.** Health answers, drafts and
/// queued submissions live here; the key is in Keychain / Keystore
/// (`core/secure_key.dart`) and never in this file.
///
/// The phone is not a medical record store. Once an intake is accepted by the
/// hospital, everything about it is deleted from the device except a reference
/// code and a date — which is what the patient shows at the registration desk,
/// and is not clinical.
library;

import 'dart:convert';
import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqlcipher_flutter_libs/sqlcipher_flutter_libs.dart';
import 'package:sqlite3/open.dart' as sqlite_open;

part 'database.g.dart';

/// An intake in progress or awaiting submission.
class Drafts extends Table {
  TextColumn get intakeId => text()();
  TextColumn get hospitalId => text()();

  /// The hospital's display name, carried so a receipt written days later by
  /// the background queue can name the hospital the patient chose rather than
  /// its id. Nullable because drafts written before this column existed have
  /// none, and a resumed draft is worth more than a tidy schema.
  TextColumn get hospitalName => text().nullable()();
  TextColumn get departmentCode => text().nullable()();
  TextColumn get language => text()();
  TextColumn get reporter => text()();

  /// The answers so far, as JSON. Opaque to the database on purpose: the schema
  /// of an answer is the bundle's business, and a column per field would need a
  /// migration every time a clinician edits a pathway.
  TextColumn get answersJson => text()();
  TextColumn get contentVersion => text()();

  /// Whether this hospital had seen the patient before when the intake started
  /// — §5 screen 8. Stored rather than re-derived, because a resumed intake
  /// must keep the plan it began with: re-deciding it would change which
  /// questions remain halfway through.
  BoolColumn get returnVisit => boolean().withDefault(const Constant(false))();
  DateTimeColumn get startedAt => dateTime()();
  DateTimeColumn get updatedAt => dateTime()();

  /// Set once the record has been assembled and is waiting to go out.
  TextColumn get queuedPayload => text().nullable()();

  /// Generated once per intake, not per attempt — §9. A key per attempt would
  /// make every retry a new intake.
  TextColumn get idempotencyKey => text()();

  @override
  Set<Column> get primaryKey => {intakeId};
}

/// A photographed document waiting to upload.
class PendingDocuments extends Table {
  TextColumn get documentId => text()();
  TextColumn get intakeId => text()();

  /// Path on disk. The bytes are not in the database: a 500 KB JPEG per row
  /// would make the encrypted database large and slow to open, and the file
  /// is deleted alongside the row.
  TextColumn get filePath => text()();
  TextColumn get kind => text().withDefault(const Constant('other'))();
  TextColumn get status => text().withDefault(const Constant('pending'))();
  IntColumn get attempts => integer().withDefault(const Constant(0))();
  DateTimeColumn get capturedAt => dateTime()();

  @override
  Set<Column> get primaryKey => {documentId};
}

/// What survives a successful submit.
///
/// A reference code and a date. Deliberately not a table of past intakes: §10
/// says the phone is not a medical record store, and a patient's history lives
/// at the hospital where a physician can see it in context.
class Receipts extends Table {
  TextColumn get intakeId => text()();
  TextColumn get referenceCode => text()();
  TextColumn get hospitalName => text()();
  DateTimeColumn get submittedAt => dateTime()();

  /// The id **the backend** filed this intake under.
  ///
  /// Usually the same as `intakeId` and occasionally not: the kiosk contract
  /// specifies a UUID, and where the client sends something else the backend
  /// derives a stable UUID from it rather than rejecting a completed interview.
  /// Everything posted *after* ingest — the consent artefact, the document
  /// upload — has to address the intake by the id the hospital has, not the one
  /// the phone made up.
  ///
  /// Persisted rather than held in memory because the upload can be retried
  /// days later, from a cold start, after the response that carried it is long
  /// gone. Nullable for receipts written before this column existed.
  TextColumn get serverIntakeId => text().nullable()();

  @override
  Set<Column> get primaryKey => {intakeId};
}

@DriftDatabase(tables: [Drafts, PendingDocuments, Receipts])
class LocalDatabase extends _$LocalDatabase {
  LocalDatabase(super.executor);

  /// For tests: an unencrypted in-memory database.
  ///
  /// Encryption is a property of the file on disk; the schema and every query
  /// are identical either way, so testing against memory tests the same code.
  ///
  /// The library override runs first, and it has to. On a host `flutter test`
  /// the system SQLite is there and this is a no-op, so it was never needed —
  /// but on a device there is no `libsqlite3.so`, because this app ships
  /// SQLCipher and deliberately not `sqlite3_flutter_libs` beside it. The first
  /// query threw `Failed to load dynamic library 'libsqlite3.so'` before a
  /// single screen rendered, which is why `integration_test/journey_test.dart`
  /// could not run on hardware at all until it was found by running it there.
  LocalDatabase.memory() : super(_memoryExecutor());

  static QueryExecutor _memoryExecutor() {
    _useCipherOnAndroid();
    return NativeDatabase.memory();
  }

  /// Point sqlite3 at the SQLCipher build.
  ///
  /// Idempotent, and called before **every** connection this class opens. Done
  /// late, the first connection uses the system SQLite and silently produces a
  /// plaintext database that later connections cannot read — the worst of both
  /// outcomes — or, where there is no system SQLite, fails to open at all.
  static void _useCipherOnAndroid() {
    sqlite_open.open
        .overrideFor(sqlite_open.OperatingSystem.android, openCipherOnAndroid);
  }

  @override
  int get schemaVersion => 4;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (m) => m.createAll(),
        onUpgrade: (m, from, to) async {
          if (from < 2) await m.addColumn(drafts, drafts.hospitalName);
          if (from < 3) await m.addColumn(drafts, drafts.returnVisit);
          if (from < 4) await m.addColumn(receipts, receipts.serverIntakeId);
        },
      );

  static Future<LocalDatabase> open({required String encryptionKey}) async {
    _useCipherOnAndroid();

    final directory = await getApplicationDocumentsDirectory();
    final file = File(p.join(directory.path, 'medikiosk.db'));
    return LocalDatabase(NativeDatabase(
      file,
      setup: (raw) {
        // The key, before any other statement.
        //
        // Interpolated into the pragma because SQLCipher's `PRAGMA key` takes
        // no bound parameter. Safe here and only here: the key is base64url
        // from `DatabaseKey`, whose alphabet is `A-Za-z0-9-_` and so contains
        // no quote to break out with. Never interpolate a value of any other
        // provenance into this statement.
        raw.execute("PRAGMA key = '$encryptionKey';");

        // Prove encryption is actually on rather than assuming it. Without
        // SQLCipher present this pragma returns nothing, and the alternative to
        // failing here is a file full of patients' health answers in plaintext.
        final cipher = raw.select('PRAGMA cipher_version;');
        if (cipher.isEmpty) {
          throw StateError(
            'SQLCipher is not active. Refusing to store health answers in a '
            'plaintext database.',
          );
        }
      },
    ));
  }

  // --- drafts ---------------------------------------------------------------

  Future<Draft?> draftFor(String intakeId) =>
      (select(drafts)..where((d) => d.intakeId.equals(intakeId)))
          .getSingleOrNull();

  /// The most recent draft, for the resume prompt (§5).
  Future<Draft?> latestDraft() => (select(drafts)
        ..orderBy([(d) => OrderingTerm.desc(d.updatedAt)])
        ..limit(1))
      .getSingleOrNull();

  Future<void> saveDraft(DraftsCompanion draft) =>
      into(drafts).insertOnConflictUpdate(draft);

  // --- submission queue -----------------------------------------------------

  /// Drafts with an assembled record waiting to go out — §9.
  ///
  /// Ordered oldest first so a backlog drains in the order the patients
  /// finished, which is the order the registration desk will see them.
  Future<List<Draft>> queuedDrafts() => (select(drafts)
        ..where((d) => d.queuedPayload.isNotNull())
        ..orderBy([(d) => OrderingTerm.asc(d.updatedAt)]))
      .get();

  Future<void> attachPayload(String intakeId, String payload) =>
      (update(drafts)..where((d) => d.intakeId.equals(intakeId)))
          .write(DraftsCompanion(queuedPayload: Value(payload)));

  /// The record that an intake was accepted.
  ///
  /// **This row is what makes submission exactly-once.** It is written the
  /// moment the hospital returns a success and before anything else is cleaned
  /// up, so a crash between acceptance and purge leaves evidence that the post
  /// already happened. The `Idempotency-Key` covers the same ground on the
  /// server; this covers it on the device, and the two failure modes are
  /// different enough to want both.
  Future<Receipt?> receiptFor(String intakeId) =>
      (select(receipts)..where((r) => r.intakeId.equals(intakeId)))
          .getSingleOrNull();

  Future<void> saveReceipt(ReceiptsCompanion receipt) =>
      into(receipts).insertOnConflictUpdate(receipt);

  Future<List<PendingDocument>> documentsFor(String intakeId) =>
      (select(pendingDocuments)..where((d) => d.intakeId.equals(intakeId))).get();

  Future<void> dropDocument(String documentId) =>
      (delete(pendingDocuments)..where((d) => d.documentId.equals(documentId))).go();

  /// Hand every page captured outside a visit to the visit that just started.
  ///
  /// A row's `intake_id` is what decides where the page uploads and what
  /// `purgeIntake` will later delete, so moving the page *is* re-keying the
  /// row. Nothing about the file changes — it was already prepared, stripped
  /// and downscaled on the way in.
  Future<void> adoptDocuments({required String from, required String to}) =>
      (update(pendingDocuments)..where((d) => d.intakeId.equals(from)))
          .write(PendingDocumentsCompanion(intakeId: Value(to)));

  Future<void> noteDocumentAttempt(String documentId, int attempts) =>
      (update(pendingDocuments)..where((d) => d.documentId.equals(documentId)))
          .write(PendingDocumentsCompanion(attempts: Value(attempts)));

  /// Everything about one intake, gone.
  ///
  /// Called on a successful submit and on sign-out. Deletes the document files
  /// as well as the rows — a row removed while a JPEG of a prescription stays
  /// in application storage is the leak this method exists to prevent.
  Future<void> purgeIntake(String intakeId) async {
    final pending = await (select(pendingDocuments)
          ..where((d) => d.intakeId.equals(intakeId)))
        .get();
    for (final document in pending) {
      final file = File(document.filePath);
      if (file.existsSync()) {
        try {
          file.deleteSync();
        } on FileSystemException {
          // Best effort. The row goes either way; a file we cannot delete is
          // worth knowing about but must not block the purge.
        }
      }
    }
    await (delete(pendingDocuments)..where((d) => d.intakeId.equals(intakeId))).go();
    await (delete(drafts)..where((d) => d.intakeId.equals(intakeId))).go();
  }

  /// Sign-out (§10). Everything, including receipts.
  Future<void> purgeEverything() async {
    final all = await select(drafts).get();
    for (final draft in all) {
      await purgeIntake(draft.intakeId);
    }
    await delete(pendingDocuments).go();
    await delete(drafts).go();
    await delete(receipts).go();
  }

  /// Drafts older than [maxAge].
  ///
  /// §5: a draft older than seven days prompts a restart, because clinical
  /// answers go stale — "how long have you had this pain?" answered last week
  /// is wrong today, and silently submitting it would be worse than asking
  /// again.
  Future<List<Draft>> staleDrafts({Duration maxAge = const Duration(days: 7)}) async {
    final cutoff = DateTime.now().subtract(maxAge);
    return (select(drafts)..where((d) => d.updatedAt.isSmallerThanValue(cutoff)))
        .get();
  }
}

/// Encode and decode the answers blob.
///
/// Kept beside the table rather than in the walker: the walker does not know
/// there is a database, and should not.
abstract final class DraftCodec {
  static String encode(Map<String, Map<String, dynamic>> answers) =>
      jsonEncode(answers);

  static Map<String, dynamic> decode(String raw) {
    final decoded = jsonDecode(raw);
    return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
  }
}
