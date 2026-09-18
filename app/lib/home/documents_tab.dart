/// Everything the patient has sent this hospital, and everything waiting to go
/// — stage 4, extended in stage 5.
///
/// **It shows the page, never the reading.** §8 is the whole design of this
/// screen: a value extracted from a prescription and shown back to the patient
/// without a physician in between is a diagnosis surface, and it is one whether
/// the model was right or wrong. So a row here says what the document is, when
/// it was added and whether the hospital has processed it — and where it was
/// refused, why, which is the one piece of feedback a patient can act on by
/// photographing it again. The three lines under "why it helps" obey the same
/// rule: they are about delivery, ordering and legibility, never about what any
/// paper said.
///
/// **Capturing happens here; sending still happens in a visit.** Tapping the
/// button used to start the whole questionnaire, because `DocumentRecord` has a
/// NOT NULL `intake_id` and there is no endpoint that takes a document without
/// one. Now the camera opens immediately, the page is prepared and held
/// encrypted on the device under [kUnattachedIntakeId], and
/// `IntakeFlow.begin` adopts it into the next visit the patient starts.
///
/// The screen says so, plainly, and does not describe a waiting page as sent.
/// A patient who believes the hospital has their discharge summary when it is
/// still on their phone is worse off than one who has been told to start a
/// visit.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../core/ui.dart';
import '../documents/document_store.dart';
import '../documents/documents_screen.dart';
import '../documents/patient_documents.dart';
import '../documents/prepare.dart';
import '../l10n/strings.dart';

/// Pages captured but not yet attached to a visit.
///
/// Autodisposed and invalidated by hand after every capture, because the store
/// writes straight to the database and nothing else would tell this screen.
final unattachedPagesProvider = FutureProvider<List<CapturedPage>>((ref) async {
  final store = await ref.watch(documentStoreProvider.future);
  return store.unattached();
});

class DocumentsTab extends ConsumerWidget {
  const DocumentsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final sent = ref.watch(patientDocumentsProvider);
    final waiting = ref.watch(unattachedPagesProvider).valueOrNull ?? const [];

    return Garnish(
      child: RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(patientDocumentsProvider);
        ref.invalidate(unattachedPagesProvider);
      },
      child: ListView(
        padding: const EdgeInsets.all(Sizes.gutter),
        children: [
          const SizedBox(height: Sizes.gap),
          const _Greeting(),
          const SizedBox(height: Sizes.gutter),
          ...sent.when(
            loading: () => const [Center(child: CircularProgressIndicator())],
            // An empty list, never an error screen. A tab that cannot load is a
            // tab with nothing in it; it is not a reason to tell a patient
            // something went wrong with their records.
            error: (_, __) => const <Widget>[],
            data: (rows) => [
              for (final row in rows) _SentTile(document: row),
              if (rows.isNotEmpty) const SizedBox(height: Sizes.gutter),
            ],
          ),
          for (final page in waiting) _WaitingTile(page: page),
          if (waiting.isNotEmpty) ...[
            const SizedBox(height: Sizes.gap),
            TintPanel(
              padding: const EdgeInsets.all(Sizes.gap + 4),
              child: Row(
                children: [
                  Icon(
                    Icons.schedule_send_outlined,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(width: Sizes.gap),
                  Expanded(
                    child: Text(
                      strings.documentsWaiting(waiting.length),
                      key: const Key('documents.waiting'),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: Sizes.gutter),
          ],
          if (sent.valueOrNull?.isEmpty != false && waiting.isEmpty) ...[
            const Center(
              child: EmblemMark(icon: Icons.folder_open_outlined, size: 132),
            ),
            const SizedBox(height: Sizes.gutter),
            Text(
              strings.noDocumentsYet,
              key: const Key('documents.empty'),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: Sizes.gap),
            Text(
              strings.documentsIntro,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
            const SizedBox(height: Sizes.gutter),
          ],
          const _CaptureButton(),
          const SizedBox(height: Sizes.gutter * 1.5),
          Text(
            strings.whyItHelps,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.1,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: Sizes.gap),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _Benefit(icon: Icons.send_outlined, label: strings.helpsRead),
              _Benefit(icon: Icons.schedule_outlined, label: strings.helpsTimeline),
              _Benefit(icon: Icons.visibility_outlined, label: strings.helpsChecked),
            ],
          ),
        ],
      ),
      ),
    );
  }
}

class _Greeting extends ConsumerWidget {
  const _Greeting();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final name = ref.watch(displayNameProvider).valueOrNull;
    return GreetingHeader(
      name: name,
      greeting: strings.greetingHi(name ?? ''),
      fallback: strings.greetingNoName,
      subtitle: strings.greetingSubtitle,
    );
  }
}

/// Camera or gallery, then straight into the local store.
///
/// Two taps, not one: the camera is the common case and gets the filled button,
/// the gallery is the fallback for a photograph already taken and gets a quiet
/// one underneath.
class _CaptureButton extends ConsumerWidget {
  const _CaptureButton();

  Future<void> _capture(
    BuildContext context,
    WidgetRef ref, {
    required bool fromCamera,
  }) async {
    final strings = Strings.of(context);
    final store = await ref.read(documentStoreProvider.future);
    final result = await store.add(
      // Not a visit. See the note on [kUnattachedIntakeId].
      intakeId: kUnattachedIntakeId,
      fromCamera: fromCamera,
    );
    if (!context.mounted) return;

    // Quality problems are told to the patient now, while the paper is still in
    // their hand. Nothing is stored for a rejected page, so there is nothing to
    // clean up and nothing that could upload later.
    final String? complaint = switch (result) {
      PageRejected(quality: PageQuality.blurred) => strings.photoTooBlurry,
      PageRejected(quality: PageQuality.tooSmall) => strings.photoTooSmall,
      PageRejected(quality: PageQuality.possiblyCropped) => strings.photoLooksCropped,
      PageRejected() => strings.tryAgain,
      PageUnreadable() => strings.tryAgain,
      PageCancelled() => null,
      PageAdded() => null,
    };
    if (complaint != null) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(complaint)));
    }
    ref.invalidate(unattachedPagesProvider);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FilledButton.icon(
          key: const Key('documents.capture'),
          onPressed: () => _capture(context, ref, fromCamera: true),
          icon: const Icon(Icons.document_scanner_outlined),
          label: Text(strings.scanOrUpload),
        ),
        const SizedBox(height: Sizes.gap),
        TextButton.icon(
          key: const Key('documents.fromGallery'),
          onPressed: () => _capture(context, ref, fromCamera: false),
          icon: const Icon(Icons.photo_library_outlined),
          label: Text(strings.chooseFromGallery),
        ),
      ],
    );
  }
}

/// One of the three reasons under the button.
class _Benefit extends StatelessWidget {
  const _Benefit({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => Expanded(
        child: Column(
          children: [
            IconChip(icon: icon, size: 44),
            const SizedBox(height: 8),
            Text(
              label,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
      );
}

/// A page on the phone, not yet attached to a visit.
class _WaitingTile extends ConsumerWidget {
  const _WaitingTile({required this.page});

  final CapturedPage page;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: Sizes.gap),
      child: SoftCard(
        padding: const EdgeInsets.all(Sizes.gap),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.file(
                page.file,
                width: 60,
                height: 80,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const SizedBox(width: 60, height: 80),
              ),
            ),
            const SizedBox(width: Sizes.gap),
            Expanded(
              child: Text(
                strings.statusUploading,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
            IconButton(
              key: Key('document.remove.${page.documentId}'),
              tooltip: strings.removeDocument,
              icon: const Icon(Icons.delete_outline),
              onPressed: () async {
                final store = await ref.read(documentStoreProvider.future);
                await store.remove(page.documentId);
                ref.invalidate(unattachedPagesProvider);
              },
            ),
          ],
        ),
      ),
    );
  }
}

/// A document the hospital already has.
class _SentTile extends StatelessWidget {
  const _SentTile({required this.document});

  final PatientDocument document;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final rejected = document.rejected;

    return Padding(
      padding: const EdgeInsets.only(bottom: Sizes.gap),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(Sizes.radius),
          boxShadow: softShadow,
        ),
        child: Material(
          color: Colors.white,
          borderRadius: BorderRadius.circular(Sizes.radius),
          child: InkWell(
            key: Key('document.${document.documentId}'),
            borderRadius: BorderRadius.circular(Sizes.radius),
            // Tapping opens the patient's own scan — the image they
            // photographed, not a reading of it. A row with no stored image (a
            // device-produced reading) is not tappable.
            onTap: document.viewable
                ? () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => _DocumentView(
                          title: _kind(document.kind),
                          url: document.url!,
                        ),
                      ),
                    )
                : null,
            child: Container(
              padding: const EdgeInsets.all(Sizes.gap + 2),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(Sizes.radius),
                border: Border.all(
                  color: rejected ? colors.error : Colors.transparent,
                  width: 2,
                ),
              ),
              child: Row(
                children: [
                  IconChip(
                    icon: rejected
                        ? Icons.error_outline
                        : Icons.description_outlined,
                    background: rejected ? Palette.urgentSurface : Palette.tint,
                    foreground: rejected ? colors.error : colors.primary,
                  ),
                  const SizedBox(width: Sizes.gap + 2),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // The document's own type, which is a classification of
                        // the paper and not a statement about the patient.
                        // Nothing read *off* the paper appears on this screen.
                        Text(_kind(document.kind), style: text.titleMedium),
                        const SizedBox(height: 3),
                        Text(
                          rejected
                              // The refusal reason is about the photograph —
                              // blurred, cropped, too dark. Written by the
                              // quality gate, never by the model that reads the
                              // text.
                              ? (document.rejectionReason ?? '')
                              : _date(document.uploadedAt),
                          style: text.bodySmall?.copyWith(
                            color: rejected
                                ? colors.error
                                : colors.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (document.viewable)
                    Icon(
                      Icons.visibility_outlined,
                      color: colors.onSurfaceVariant,
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  static String _kind(String code) {
    final words = code.replaceAll('_', ' ').trim();
    if (words.isEmpty) return code;
    return words[0].toUpperCase() + words.substring(1);
  }

  static String _date(DateTime? when) {
    if (when == null) return '';
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    return '${when.day} ${months[when.month - 1]} ${when.year}';
  }
}

/// The patient's own uploaded scan, full screen and zoomable.
///
/// `Image.network` straight off the signed URL — the upload path already
/// downscaled and stripped it to a JPEG (§8), so there is nothing else to
/// render and no PDF case to handle. A dead or expired link shows a plain
/// message and a way back, never a stack trace.
class _DocumentView extends StatelessWidget {
  const _DocumentView({required this.title, required this.url});

  final String title;
  final String url;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      backgroundColor: Colors.black,
      body: Center(
        child: InteractiveViewer(
          maxScale: 5,
          child: Image.network(
            url,
            fit: BoxFit.contain,
            loadingBuilder: (context, child, progress) => progress == null
                ? child
                : const Center(child: CircularProgressIndicator()),
            errorBuilder: (context, _, __) => Padding(
              padding: const EdgeInsets.all(Sizes.gutter * 2),
              child: Text(
                strings.documentUnavailable,
                key: const Key('document.unavailable'),
                textAlign: TextAlign.center,
                style: Theme.of(context)
                    .textTheme
                    .bodyLarge
                    ?.copyWith(color: Colors.white70),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
