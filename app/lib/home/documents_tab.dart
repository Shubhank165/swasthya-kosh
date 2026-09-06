/// Everything the patient has sent this hospital — stage 4.
///
/// **It shows the page, never the reading.** §8 is the whole design of this
/// screen: a value extracted from a prescription and shown back to the patient
/// without a physician in between is a diagnosis surface, and it is one whether
/// the model was right or wrong. So a row here says what the document is, when
/// it was added and whether the hospital has processed it — and where it was
/// refused, why, which is the one piece of feedback a patient can act on by
/// photographing it again.
///
/// The endpoint behind it (`GET /patients/me/documents`) returns strictly less
/// than the staff one for the same reason.
///
/// **Adding happens inside a visit, not here.** A document belongs to an
/// intake — that is what gives a doctor the answers to read it against — so the
/// button below starts one rather than inventing a loose upload with nothing
/// attached to it.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../documents/patient_documents.dart';
import '../l10n/strings.dart';

class DocumentsTab extends ConsumerWidget {
  const DocumentsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final documents = ref.watch(patientDocumentsProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(patientDocumentsProvider),
      child: documents.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, __) => _Empty(message: strings.noDocumentsYet),
        data: (rows) => rows.isEmpty
            ? _Empty(message: strings.noDocumentsYet)
            : ListView.builder(
                padding: const EdgeInsets.all(Sizes.gutter),
                itemCount: rows.length,
                itemBuilder: (context, i) => _DocumentTile(document: rows[i]),
              ),
      ),
    );
  }
}

class _DocumentTile extends StatelessWidget {
  const _DocumentTile({required this.document});

  final PatientDocument document;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: Sizes.gap),
      child: ListTile(
        key: Key('document.${document.documentId}'),
        leading: Icon(
          document.rejected ? Icons.error_outline : Icons.description_outlined,
          color: document.rejected ? colors.error : colors.primary,
        ),
        // The document's own type, which is a classification of the paper and
        // not a statement about the patient. Nothing read *off* the paper
        // appears anywhere on this screen.
        title: Text(_kind(document.kind)),
        subtitle: Text(
          document.rejected
              // The refusal reason is about the photograph — blurred, cropped,
              // too dark. It is written by the quality gate, never by the model
              // that reads the text.
              ? (document.rejectionReason ?? '')
              : _date(document.uploadedAt),
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

class _Empty extends StatelessWidget {
  const _Empty({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(Sizes.gutter * 2),
        children: [
          const SizedBox(height: Sizes.gutter * 3),
          Text(
            message,
            key: const Key('documents.empty'),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyLarge,
          ),
        ],
      );
}
