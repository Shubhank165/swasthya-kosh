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
library;

import 'dart:io';

import 'package:flutter/material.dart';

import '../core/theme.dart';
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
      appBar: AppBar(title: Text(strings.documentsTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            for (final page in pages) _pageCard(context, page),
            const SizedBox(height: Sizes.gap),
            OutlinedButton.icon(
              key: const Key('documents.camera'),
              onPressed: onTakePhoto,
              icon: const Icon(Icons.photo_camera_outlined),
              label: Text(strings.takePhoto),
            ),
            const SizedBox(height: Sizes.gap),
            OutlinedButton.icon(
              key: const Key('documents.gallery'),
              onPressed: onChooseFromGallery,
              icon: const Icon(Icons.photo_library_outlined),
              label: Text(strings.chooseFromGallery),
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

    return Card(
      key: Key('document.${page.documentId}'),
      margin: const EdgeInsets.only(bottom: Sizes.gap),
      child: Padding(
        padding: const EdgeInsets.all(Sizes.gap),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
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
              child: Text(
                message,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: isProblem ? scheme.error : null,
                    ),
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
