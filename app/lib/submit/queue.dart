/// Submitting exactly once — 2/3 §9, §10, §15 item 8.
///
/// **"Poor signal must not lose an intake."** That sentence has a second half
/// nobody writes down: poor signal must not submit one twice either. A patient
/// who taps send in a lift, walks out, and taps nothing else must end up with
/// exactly one record at the hospital — not zero, and not two that a
/// registration clerk has to reconcile while a queue forms behind them.
///
/// Three things hold that together, and each covers a failure the others do
/// not:
///
/// - **One `Idempotency-Key` per intake, generated when the intake starts.**
///   Not per attempt — a key per attempt makes every retry a new intake, which
///   is the bug this header exists to prevent. The backend replays the original
///   result for a repeated key and creates nothing.
/// - **A receipt row, written the instant the hospital accepts.** The device's
///   own record that the post already happened, so a crash between acceptance
///   and cleanup does not resend. The header covers a retry the server sees;
///   this covers one the server never hears about.
/// - **Nothing is deleted until it has been accepted.** The draft, its
///   assembled payload and its document files all survive every failure. Purge
///   is the last step, and it only runs after both the record and every
///   document are through.
///
/// The order those happen in is the whole of the correctness argument, so it is
/// written out once in [_deliver] and not restated anywhere else.
library;

import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';

import '../consent/consent_repository.dart';
import '../core/api.dart';
import '../storage/database.dart';

/// The code the patient shows at the registration desk — §7.4.
///
/// Derived from the intake id rather than issued by the backend, because it has
/// to exist on a phone that has not reached the backend yet: an intake finished
/// offline still gets a code, and the code still finds the record when the
/// queue drains. Deriving it means the desk can look it up as a prefix of the
/// intake id with no extra column and no second identifier to keep in step.
///
/// Six hex characters, grouped for reading aloud over a counter. **Not a
/// secret** — it identifies a record to staff who can already see it, and
/// anything stronger would be a password the patient has to remember.
String referenceCodeFor(String intakeId) {
  final compact = intakeId.replaceAll(RegExp(r'[^0-9a-zA-Z]'), '').toUpperCase();
  final body = compact.length <= 6
      ? compact.padRight(6, '0')
      : compact.substring(compact.length - 6);
  return 'MK-${body.substring(0, 3)}-${body.substring(3, 6)}';
}

/// What one delivery attempt concluded.
enum Delivery {
  /// The hospital has it.
  accepted,

  /// Still on the phone. Nothing was lost; it will be tried again.
  queued,

  /// There is nothing queued under that intake id.
  nothingToSend,
}

class SubmissionQueue {
  SubmissionQueue({
    required LocalDatabase database,
    required ApiClient api,
    DateTime Function() clock = DateTime.now,
  })  : _db = database,
        _api = api,
        _clock = clock;

  final LocalDatabase _db;
  final ApiClient _api;
  final DateTime Function() _clock;

  /// Intakes a delivery is currently running for.
  ///
  /// A launch-time flush and a patient tapping send can overlap, and two
  /// concurrent posts of the same intake would both be idempotent on the server
  /// but would race each other to write the receipt and purge the row out from
  /// under the other. Cheaper to not start the second one.
  final _inFlight = <String>{};

  /// Save the assembled record — and the consent that goes with it — against
  /// the draft.
  ///
  /// Deliberately separate from sending it. This is the step that makes the
  /// intake durable, and it completes before any network call is attempted, so
  /// an app killed the moment after the patient taps send still has the record
  /// to deliver.
  ///
  /// The two travel together in one envelope because they have to survive
  /// together: a consent artefact kept anywhere else would be the one thing a
  /// crash could lose, and an intake at the hospital with no record of what the
  /// patient agreed to is precisely the position §11 exists to prevent.
  Future<void> enqueue({
    required String intakeId,
    required Map<String, dynamic> payload,
    ConsentGrant? consent,
  }) =>
      _db.attachPayload(
        intakeId,
        jsonEncode({
          'record': payload,
          if (consent != null) 'consent': consent.toJson(),
        }),
      );

  /// The envelope's two halves.
  ///
  /// Written by [enqueue] and read only here; nothing outside this file knows
  /// the shape, so it can change without touching the flow.
  static (Map<String, dynamic> record, ConsentGrant? consent) _unpack(String stored) {
    final envelope = jsonDecode(stored) as Map<String, dynamic>;
    final consent = envelope['consent'];
    return (
      envelope['record'] as Map<String, dynamic>,
      consent is Map<String, dynamic> ? ConsentGrant.fromJson(consent) : null,
    );
  }

  /// One attempt at one intake, for the tap that starts it.
  ///
  /// A single attempt on purpose: the patient is looking at a spinner, and the
  /// bounded backoff [flush] uses would hold them there for the better part of
  /// a minute to reach a conclusion the submitted screen can state honestly
  /// either way. If this comes back [Delivery.queued] they are told the record
  /// is saved on the phone and will go when there is signal, which is true.
  Future<Delivery> submitNow(String intakeId) => _deliverById(intakeId, attempts: 1);

  /// Every intake waiting to go out.
  ///
  /// Called on launch and after connectivity returns. Returns how many were
  /// accepted this pass.
  Future<int> flush({int attempts = 4}) async {
    var accepted = 0;
    for (final draft in await _db.queuedDrafts()) {
      if (await _deliver(draft, attempts: attempts) == Delivery.accepted) {
        accepted += 1;
      }
    }
    return accepted;
  }

  Future<Delivery> _deliverById(String intakeId, {required int attempts}) async {
    final draft = await _db.draftFor(intakeId);
    if (draft == null) {
      // No draft can mean two very different things: nothing was ever queued,
      // or it was accepted and purged. The receipt tells them apart, and
      // reporting a purged intake as unsent would show the patient a "saved on
      // this phone" message about a record the hospital already has.
      return await _db.receiptFor(intakeId) != null
          ? Delivery.accepted
          : Delivery.nothingToSend;
    }
    return _deliver(draft, attempts: attempts);
  }

  Future<Delivery> _deliver(Draft draft, {required int attempts}) async {
    final payload = draft.queuedPayload;
    if (payload == null) return Delivery.nothingToSend;
    if (!_inFlight.add(draft.intakeId)) return Delivery.queued;
    try {
      return await _run(draft, payload, attempts: attempts);
    } finally {
      _inFlight.remove(draft.intakeId);
    }
  }

  /// The ordering that makes this exactly-once. Read it top to bottom.
  Future<Delivery> _run(
    Draft draft,
    String payload, {
    required int attempts,
  }) async {
    final (record, consent) = _unpack(payload);

    // 1. Has this already been accepted? A receipt means yes, and re-posting
    //    would be safe but pointless — go straight to finishing the cleanup
    //    that a previous pass did not get to.
    final alreadyAccepted = await _db.receiptFor(draft.intakeId) != null;

    if (!alreadyAccepted) {
      // 2. Post the record, with the key the intake was born with.
      final Response<Map<String, dynamic>> response;
      try {
        response = await ApiClient.retrying(
          () => _api.post<Map<String, dynamic>>(
            '/intakes/ingest',
            body: record,
            headers: {'Idempotency-Key': draft.idempotencyKey},
          ),
          attempts: attempts,
        );
      } on DioException {
        // No connection, or a timeout. Nothing has been lost: the payload is on
        // disk and the next flush will find it.
        return Delivery.queued;
      }

      final status = response.statusCode ?? 0;
      if (status < 200 || status >= 300) {
        // Includes 4xx. The backend answers a payload it cannot parse with a
        // 200 and `needs_manual_review`, so a 4xx here is an auth problem or a
        // route that moved — neither of which a device should resolve by
        // deleting a patient's intake. It stays queued.
        return Delivery.queued;
      }

      // 3. Accepted. Write the receipt before anything else, because from here
      //    on a crash must not cause a second post.
      await _db.saveReceipt(ReceiptsCompanion.insert(
        intakeId: draft.intakeId,
        referenceCode: referenceCodeFor(draft.intakeId),
        hospitalName: draft.hospitalName ?? draft.hospitalId,
        submittedAt: _clock(),
      ));
    }

    // 4. File the consent artefact, now that the intake it references exists.
    //    Before the documents, because a document processed under a consent
    //    that was never filed is the ordering §11 cannot tolerate.
    if (consent != null && !await _fileConsent(draft.intakeId, consent)) {
      return Delivery.accepted;
    }

    // 5. Send the documents, while their files are still on disk.
    final documentsDone = await _uploadDocuments(draft.intakeId);
    if (!documentsDone) {
      // Accepted, but the prescription photo has not arrived yet. Keeping the
      // draft row alive keeps the files alive with it; §10's "delete on submit"
      // means delete once the hospital has everything, not once it has the
      // answers.
      return Delivery.accepted;
    }

    // 6. Only now: the answers and the images leave the phone (§10). What
    //    survives is the receipt — a code and a date, which is not clinical.
    await _db.purgeIntake(draft.intakeId);
    return Delivery.accepted;
  }

  /// Record what the patient agreed to, against the intake — §11.
  ///
  /// A retry after a crash between the post and the purge can file the artefact
  /// twice. That is the acceptable direction of the two: the backend's
  /// artefacts are immutable and append-only, so a duplicate is a second,
  /// identical record of the same grant, superseding itself. The alternative —
  /// treating a failure as filed — would leave an intake with no consent record
  /// at all.
  Future<bool> _fileConsent(String intakeId, ConsentGrant consent) async {
    try {
      final response = await _api.post<Map<String, dynamic>>(
        '/consent',
        body: {'intake_id': intakeId, ...consent.toJson()},
      );
      final status = response.statusCode ?? 0;
      return status >= 200 && status < 300;
    } on DioException {
      return false;
    }
  }

  /// Upload each pending document. True when none are left.
  ///
  /// Failures here are not fatal to the submission — the record is already at
  /// the hospital, and a document that never uploads is a missing attachment
  /// rather than a missing intake.
  Future<bool> _uploadDocuments(String intakeId) async {
    var allDone = true;
    for (final document in await _db.documentsFor(intakeId)) {
      final file = File(document.filePath);
      if (!file.existsSync()) {
        // The file is gone — a device cleaner, or a purge that half ran. The
        // row describes nothing, so it goes; keeping it would block the purge
        // forever.
        await _db.dropDocument(document.documentId);
        continue;
      }
      try {
        final response = await _api.post<Map<String, dynamic>>(
          '/intakes/$intakeId/documents',
          body: FormData.fromMap({
            'kind': document.kind,
            'file': await MultipartFile.fromFile(file.path),
          }),
        );
        final status = response.statusCode ?? 0;
        if (status >= 200 && status < 300) {
          await _db.dropDocument(document.documentId);
          file.deleteSync();
          continue;
        }
      } on DioException {
        // Fall through to the attempt count.
      } on FileSystemException {
        await _db.dropDocument(document.documentId);
        continue;
      }
      await _db.noteDocumentAttempt(document.documentId, document.attempts + 1);
      allDone = false;
    }
    return allDone;
  }
}
