/// Past visits — stage 4.
///
/// What this hospital holds for the signed-in patient, from
/// `GET /patients/me/history`. The patient comes from the session token, never
/// from the request, so "my visits" can only ever mean the holder of this
/// phone's session.
///
/// **This hospital only.** Retrieval across hospitals needs an ABDM consent
/// artefact and is not implemented; the backend says so in `scope_note` and
/// this screen must never imply otherwise.
///
/// It lists visits and their state. It does not show what a document was read
/// as, it does not show a report, and it does not interpret anything — §8's
/// rule about unverified extraction being a diagnosis surface applies here
/// exactly as it does inside an intake.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../identity/history_repository.dart';
import '../l10n/strings.dart';

class VisitsTab extends ConsumerWidget {
  const VisitsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final visits = ref.watch(visitsProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(visitsProvider),
      child: visits.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        // An empty list, never an error screen. A visits tab that cannot load
        // is a tab with nothing in it; it is not a reason to tell a patient
        // something went wrong with their records.
        error: (_, __) => _Empty(message: strings.noVisitsYet),
        data: (rows) => rows.isEmpty
            ? _Empty(message: strings.noVisitsYet)
            : ListView.builder(
                padding: const EdgeInsets.all(Sizes.gutter),
                itemCount: rows.length,
                itemBuilder: (context, i) => _VisitTile(visit: rows[i]),
              ),
      ),
    );
  }
}

class _VisitTile extends StatelessWidget {
  const _VisitTile({required this.visit});

  final Visit visit;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: Sizes.gap),
      child: ListTile(
        key: Key('visit.${visit.intakeId}'),
        leading: Icon(
          visit.seenAt != null ? Icons.check_circle_outline : Icons.schedule,
          color: Theme.of(context).colorScheme.primary,
        ),
        // The complaint the patient gave, in their own words where the record
        // kept them. Without it the list reads "6 September, Kayachikitsa" and
        // says nothing about which visit this was.
        title: Text(visit.complaint ?? visit.department ?? '—'),
        subtitle: Text(_date(visit.receivedAt)),
      ),
    );
  }

  /// Day, month, year. Deliberately not "3 days ago": a patient checking when
  /// they were last seen wants the date they can repeat to a receptionist.
  static String _date(DateTime when) {
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
        // A scrollable, so pull-to-refresh still works on an empty tab.
        padding: const EdgeInsets.all(Sizes.gutter * 2),
        children: [
          const SizedBox(height: Sizes.gutter * 3),
          Text(
            message,
            key: const Key('tab.empty'),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyLarge,
          ),
        ],
      );
}
