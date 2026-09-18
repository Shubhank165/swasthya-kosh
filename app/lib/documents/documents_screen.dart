/// Old prescriptions and reports — 2/3 §5 screen 9, §8.
///
/// **The patient sees the image and its status, never its contents.** §8 is
/// explicit: "Never display extracted clinical values back to the patient as
/// fact." Confirming a medicine name is the *physician's* confirmation loop; the
/// same text shown to a patient is an unverified OCR reading presented as their
/// medical record, which is a diagnosis surface.
///
/// So the states here are `sending` / `being read` / `received` / `take it
/// again`. There is no state that shows what the reading said.
///
/// **The progress checklist is about the transfer, not the paper.** The
/// reference design for this screen ticks off "Text detected", "Medicines
/// identified", "Dates identified" — which is the forbidden thing wearing a
/// progress bar, because a patient reading "medicines identified" has been told
/// the machine understood their prescription. The three steps here are sending,
/// being read, received: true statements about where the file is, and they are
/// the strings this app already had.
library;

import 'dart:io';

import 'package:flutter/material.dart';

import '../core/theme.dart';
import '../core/ui.dart';
import '../l10n/strings.dart';
import 'prepare.dart';

/// A page the patient has added.
class CapturedPage {
  const CapturedPage({
    required this.documentId,
    required this.file,
    required this.quality,
    this.status = UploadStatus.pending,
  });

  final String documentId;
  final File file;
  final PageQuality quality;
  final UploadStatus status;
}

enum UploadStatus { pending, uploading, processing, done, failed }

class DocumentsScreen extends StatelessWidget {
  const DocumentsScreen({
    super.key,
    required this.pages,
    required this.onTakePhoto,
    required this.onChooseFromGallery,
    required this.onRemove,
    required this.onContinue,
  });

  final List<CapturedPage> pages;
  final VoidCallback onTakePhoto;
  final VoidCallback onChooseFromGallery;
  final void Function(String documentId) onRemove;
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Scaffold(
      appBar: AppBar(),
      body: Garnish(
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(
              Sizes.gutter,
              0,
              Sizes.gutter,
              Sizes.gutter,
            ),
            children: [
              ScreenIntro(title: strings.documentsTitle),
              const SizedBox(height: Sizes.gutter),
              if (pages.isEmpty) ...[
                const Center(
                  child: EmblemMark(icon: Icons.document_scanner_outlined, size: 124),
                ),
                const SizedBox(height: Sizes.gutter),
              ],
              for (final page in pages) _pageCard(context, page),
              const SizedBox(height: Sizes.gap),
              _AddRow(
                rowKey: const Key('documents.camera'),
                icon: Icons.photo_camera_outlined,
                label: strings.takePhoto,
                onTap: onTakePhoto,
              ),
              const SizedBox(height: Sizes.gap),
              _AddRow(
                rowKey: const Key('documents.gallery'),
                icon: Icons.photo_library_outlined,
                label: strings.chooseFromGallery,
                onTap: onChooseFromGallery,
              ),
              const SizedBox(height: Sizes.gutter),
              FilledButton(
                key: const Key('documents.continue'),
                onPressed: onContinue,
                child: Text(strings.continueLabel),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _pageCard(BuildContext context, CapturedPage page) {
    final strings = Strings.of(context);
    final scheme = Theme.of(context).colorScheme;

    // Quality problems outrank upload state: a blurred page needs retaking now,
    // while the paper is still in the patient's hand.
    final (message, isProblem) = switch (page.quality) {
      PageQuality.blurred => (strings.photoTooBlurry, true),
      PageQuality.tooSmall => (strings.photoTooSmall, true),
      PageQuality.possiblyCropped => (strings.photoLooksCropped, true),
      PageQuality.ok => (
          switch (page.status) {
            UploadStatus.pending || UploadStatus.uploading => strings.statusUploading,
            UploadStatus.processing => strings.statusProcessing,
            UploadStatus.done => strings.statusDone,
            UploadStatus.failed => strings.tryAgain,
          },
          false,
        ),
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: Sizes.gap),
      child: SoftCard(
        key: Key('document.${page.documentId}'),
        padding: const EdgeInsets.all(Sizes.gap),
        borderColor: isProblem ? scheme.error : null,
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.file(
                page.file,
                width: 72,
                height: 96,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const SizedBox(width: 72, height: 96),
              ),
            ),
            const SizedBox(width: Sizes.gap),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    message,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: isProblem ? scheme.error : null,
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                  if (!isProblem) ...[
                    const SizedBox(height: Sizes.gap),
                    _TransferSteps(status: page.status),
                  ],
                ],
              ),
            ),
            IconButton(
              key: Key('document.remove.${page.documentId}'),
              tooltip: strings.removeDocument,
              icon: const Icon(Icons.delete_outline),
              onPressed: () => onRemove(page.documentId),
            ),
          ],
        ),
      ),
    );
  }
}

/// Where this page has got to, as three ticks.
///
/// Says only where the file is. See the note at the top of this file for why it
/// says nothing about what is on the page.
class _TransferSteps extends StatelessWidget {
  const _TransferSteps({required this.status});

  final UploadStatus status;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final reached = switch (status) {
      UploadStatus.pending || UploadStatus.uploading => 0,
      UploadStatus.processing => 1,
      UploadStatus.done => 2,
      UploadStatus.failed => 0,
    };
    final labels = [
      strings.statusUploading,
      strings.statusProcessing,
      strings.statusDone,
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < labels.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  i <= reached ? Icons.check_circle : Icons.circle_outlined,
                  size: 16,
                  color: i <= reached
                      ? Theme.of(context).colorScheme.primary
                      : Palette.tintStrong,
                ),
                const SizedBox(width: 8),
                Text(
                  labels[i],
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

/// One way of adding a page: an icon chip, a label, and the whole row tappable.
class _AddRow extends StatelessWidget {
  const _AddRow({
    required this.rowKey,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final Key rowKey;
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ActionTile(
        // Not a `ChoiceRow`: these are two ways of doing the same thing, not
        // two options one of which is currently chosen, and a radio circle on
        // the end would say otherwise.
        tileKey: rowKey,
        icon: icon,
        title: label,
        onTap: onTap,
      );
}
