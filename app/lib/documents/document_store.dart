/// Capturing a page — 2/3 §8, §5 screen 9, §10.
///
/// The rule that shapes this file: **the original bytes never reach storage.**
/// What the OS camera or gallery hands over is decoded, checked, downscaled and
/// re-encoded with its metadata stripped, and only the result is written to
/// disk. A prescription photograph carrying the patient's home coordinates is
/// the privacy leak nobody thinks about, and the way to not think about it is to
/// make the original impossible to persist.
///
/// The picker is behind an interface for the ordinary reason — a platform
/// channel cannot run in a host test — and because `image_picker` hands off to
/// the OS camera app, which is why this app holds no camera permission of its
/// own.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:drift/drift.dart' show Value;
import 'package:image_picker/image_picker.dart' as picker;
import 'package:path/path.dart' as p;

import '../core/ids.dart';
import '../storage/database.dart';
import 'documents_screen.dart';
import 'prepare.dart';

/// Where the bytes come from. Injectable so host tests never touch a channel.
abstract class PagePicker {
  Future<Uint8List?> pick({required bool fromCamera});
}

class OsPagePicker implements PagePicker {
  OsPagePicker([picker.ImagePicker? images]) : _images = images ?? picker.ImagePicker();

  final picker.ImagePicker _images;

  @override
  Future<Uint8List?> pick({required bool fromCamera}) async {
    final file = await _images.pickImage(
      source: fromCamera ? picker.ImageSource.camera : picker.ImageSource.gallery,
      // Deliberately no `maxWidth`/`imageQuality` here. Letting the plugin
      // resize would re-encode the file **outside** this app's control, and
      // whether that strips EXIF is a per-platform implementation detail. The
      // downscale and the metadata strip happen in one place, where they are
      // tested.
    );
    if (file == null) return null;
    return file.readAsBytes();
  }
}

/// What adding a page concluded.
///
/// A rejection is not an error: §8 wants the patient told while the paper is
/// still in front of them, so "too blurred, take it again" is an ordinary
/// outcome with a screen already written for it.
sealed class AddPageResult {
  const AddPageResult();
}

class PageAdded extends AddPageResult {
  const PageAdded(this.page);
  final CapturedPage page;
}

class PageRejected extends AddPageResult {
  const PageRejected(this.quality);
  final PageQuality quality;
}

/// The patient cancelled the camera or the picker. Nothing to say.
class PageCancelled extends AddPageResult {
  const PageCancelled();
}

/// The bytes were not a decodable image — a PDF or a half-downloaded file out
/// of the gallery. A message, never a crash.
class PageUnreadable extends AddPageResult {
  const PageUnreadable();
}

/// Where a page lives before it belongs to a visit.
///
/// **Not a real intake, and deliberately not a hidden one.** `DocumentRecord`
/// on the backend has a NOT NULL `intake_id` and the only upload endpoint is
/// `POST /intakes/{intake_id}/documents`, so a document cannot reach the
/// hospital without a visit. The tempting fix — mint a throwaway intake so the
/// upload has something to point at — would put a phantom visit on the
/// worklist, in the metrics and in the purge path, which is the same trade
/// `ayush_profile` refused for the same reason.
///
/// So a page photographed from the Documents tab waits here, on the phone,
/// encrypted, and `IntakeFlow.begin` adopts it into the next real visit. The
/// patient is told that in as many words; nothing pretends it has been sent.
///
/// `purgeIntake` only ever runs against a real intake id, so these survive a
/// completed visit. `purgeEverything` (sign-out) takes them.
const kUnattachedIntakeId = 'unattached';

class DocumentStore {
  DocumentStore({
    required LocalDatabase database,
    required Directory directory,
    PagePicker? picker,
    DocumentPreparer preparer = const DocumentPreparer(),
    DateTime Function() clock = DateTime.now,
  })  : _db = database,
        _directory = directory,
        _picker = picker ?? OsPagePicker(),
        _preparer = preparer,
        _clock = clock;

  final LocalDatabase _db;
  final Directory _directory;
  final PagePicker _picker;
  final DocumentPreparer _preparer;
  final DateTime Function() _clock;

  Future<AddPageResult> add({
    required String intakeId,
    required bool fromCamera,
    String kind = 'other',
  }) async {
    final raw = await _picker.pick(fromCamera: fromCamera);
    if (raw == null) return const PageCancelled();

    final prepared = _preparer.prepare(raw);
    if (prepared == null) return const PageUnreadable();
    if (!prepared.isUsable) {
      // Nothing is written. A page the patient is about to retake must not
      // leave a file behind, and a rejected page that lingered in the queue
      // would upload the moment they gave up and pressed continue.
      return PageRejected(prepared.quality);
    }

    final documentId = newLocalId('doc');
    final file = File(p.join(_directory.path, '$documentId.jpg'));
    await file.parent.create(recursive: true);
    // The prepared bytes, never `raw`. This is the line that makes the EXIF
    // strip and the downscale unavoidable rather than merely usual.
    await file.writeAsBytes(prepared.bytes, flush: true);

    await _db.into(_db.pendingDocuments).insert(PendingDocumentsCompanion.insert(
          documentId: documentId,
          intakeId: intakeId,
          filePath: file.path,
          kind: Value(kind),
          capturedAt: _clock(),
        ));

    return PageAdded(CapturedPage(
      documentId: documentId,
      file: file,
      quality: prepared.quality,
    ));
  }

  /// Pages photographed outside a visit, still waiting for one.
  Future<List<CapturedPage>> unattached() => pagesFor(kUnattachedIntakeId);

  /// Give every waiting page to the visit that has just started.
  ///
  /// Called once, from `IntakeFlow.begin`. Re-keying rather than copying: there
  /// is one JPEG per page on disk and it does not move.
  Future<void> adopt(String intakeId) =>
      _db.adoptDocuments(from: kUnattachedIntakeId, to: intakeId);

  Future<List<CapturedPage>> pagesFor(String intakeId) async {
    final rows = await _db.documentsFor(intakeId);
    return [
      for (final row in rows)
        CapturedPage(
          documentId: row.documentId,
          file: File(row.filePath),
          // Stored pages passed the check on the way in; anything that did not
          // was never written. Re-deriving it here would mean decoding every
          // page on every rebuild of the screen.
          quality: PageQuality.ok,
          status: row.status == 'uploading' ? UploadStatus.uploading : UploadStatus.pending,
        ),
    ];
  }

  /// The patient deletes a page before submitting (§8).
  ///
  /// The file goes with the row. A row removed while the JPEG stays in
  /// application storage is the leak the purge path exists to prevent, and it
  /// would be a stranger one here: the patient has been told it is gone.
  Future<void> remove(String documentId) async {
    final rows = await _db.select(_db.pendingDocuments).get();
    for (final row in rows.where((r) => r.documentId == documentId)) {
      final file = File(row.filePath);
      if (file.existsSync()) {
        try {
          file.deleteSync();
        } on FileSystemException {
          // Best effort; the row goes either way.
        }
      }
    }
    await _db.dropDocument(documentId);
  }
}
