/// Past visits — stage 4, filled out in stage 5.
///
/// What this hospital holds for the signed-in patient, from
/// `GET /patients/me/history`. The patient comes from the session token, never
/// from the request, so "my visits" can only ever mean the holder of this
/// phone's session.
///
/// **This hospital only.** Retrieval across hospitals needs an ABDM consent
/// artefact and is not implemented; the backend says so in `scope_note` and
/// this screen must never imply otherwise — which is why the note is now
/// printed at the foot of the list rather than left in the JSON. A patient
/// looking at four visits has no way to know whether that is all of them.
///
/// It lists visits and their state. It does not show what a document was read
/// as, it does not show a report, and it does not interpret anything — §8's
/// rule about unverified extraction being a diagnosis surface applies here
/// exactly as it does inside an intake.
///
/// **The status pill says where the record is, not where the patient is.**
/// "With the doctor" means a physician has not yet opened it. It deliberately
/// carries no queue position and no waiting time: this app cannot see the OPD
/// queue, and a number that looked like one would be read as a promise.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../core/ui.dart';
import '../identity/history_repository.dart';
import '../intake/screens/hospital_screen.dart';
import '../l10n/strings.dart';

class VisitsTab extends ConsumerWidget {
  const VisitsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final colors = Theme.of(context).colorScheme;
    final visits = ref.watch(visitsProvider);

    return Garnish(
      child: RefreshIndicator(
      onRefresh: () async => ref.invalidate(visitsProvider),
      child: visits.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        // An empty list, never an error screen. A visits tab that cannot load
        // is a tab with nothing in it; it is not a reason to tell a patient
        // something went wrong with their records.
        error: (_, __) => const _Empty(),
        data: (rows) {
          if (rows.isEmpty) return const _Empty();

          // Newest first, then grouped under the month they fall in. Four rows
          // in a flat list read as a fragment of something; the same four under
          // "September 2026" read as a record.
          final ordered = [...rows]
            ..sort((a, b) => b.receivedAt.compareTo(a.receivedAt));

          final children = <Widget>[];
          String? lastMonth;
          for (final visit in ordered) {
            final month = _monthYear(visit.receivedAt);
            if (month != lastMonth) {
              children
                ..add(SizedBox(height: lastMonth == null ? 0 : Sizes.gap))
                ..add(_MonthLabel(month))
                ..add(const SizedBox(height: Sizes.gap));
              lastMonth = month;
            }
            children.add(_VisitTile(visit: visit));
          }

          return ListView(
            padding: const EdgeInsets.all(Sizes.gutter),
            children: [
              const SizedBox(height: Sizes.gap),
              Semantics(
                header: true,
                child: Text(
                  strings.visitsTab,
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                strings.visitsCount(ordered.length),
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: colors.onSurfaceVariant,
                    ),
              ),
              const SizedBox(height: Sizes.gutter),
              ...children,
              const SizedBox(height: Sizes.gutter),
              // The backend's own `scope_note`, on screen. See the note at the
              // top of this file.
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.info_outline,
                    size: 18,
                    color: colors.onSurfaceVariant,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      strings.visitsScopeNote,
                      key: const Key('visits.scopeNote'),
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: colors.onSurfaceVariant,
                          ),
                    ),
                  ),
                ],
              ),
            ],
          );
        },
      ),
      ),
    );
  }

  static String _monthYear(DateTime when) => '${_months[when.month - 1]} ${when.year}';
}

const _months = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const _shortMonths = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

class _MonthLabel extends StatelessWidget {
  const _MonthLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Semantics(
        header: true,
        child: Text(
          text.toUpperCase(),
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.w700,
                letterSpacing: 1.1,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
        ),
      );
}

class _VisitTile extends StatelessWidget {
  const _VisitTile({required this.visit});

  final Visit visit;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final seen = visit.seenAt != null;

    // The complaint the patient gave, in their own words where the record kept
    // them. Without it the list reads "6 September, Kayachikitsa" and says
    // nothing about which visit this was.
    final complaint = visit.complaint;
    final department = visit.department;

    return Padding(
      padding: const EdgeInsets.only(bottom: Sizes.gap),
      child: SoftCard(
        key: Key('visit.${visit.intakeId}'),
        padding: const EdgeInsets.all(Sizes.gap + 2),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            IconChip(icon: seen ? Icons.check_circle_outline : Icons.schedule),
            const SizedBox(width: Sizes.gap + 2),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    complaint ?? _pretty(department) ?? '—',
                    style: text.titleMedium,
                  ),
                  const SizedBox(height: 3),
                  Text(
                    _date(visit.receivedAt),
                    style: text.bodySmall?.copyWith(
                      color: colors.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: Sizes.gap - 4),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      _Pill(
                        label: seen ? strings.visitSeen : strings.visitAwaiting,
                        tone: colors.primary,
                        filled: seen,
                      ),
                      // The department is shown beside the complaint, not
                      // instead of it — and de-underscored, because a raw code
                      // like `kayachikitsa` is the database's word, not a
                      // patient's.
                      if (complaint != null && department != null)
                        _Pill(
                          label: _pretty(department)!,
                          tone: colors.onSurfaceVariant,
                          filled: false,
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// `kayachikitsa` → `Kayachikitsa`, `general_medicine` → `General medicine`.
  ///
  /// Presentation only. The code itself is content and is never rewritten in
  /// the record — this tidies the one place a patient reads it.
  static String? _pretty(String? code) {
    if (code == null) return null;
    final words = code.replaceAll('_', ' ').trim();
    if (words.isEmpty) return null;
    return words[0].toUpperCase() + words.substring(1);
  }

  /// Day, month, year. Deliberately not "3 days ago": a patient checking when
  /// they were last seen wants the date they can repeat to a receptionist.
  static String _date(DateTime when) =>
      '${when.day} ${_shortMonths[when.month - 1]} ${when.year}';
}

/// A small rounded label. Never the only carrier of a meaning — the icon chip
/// beside it changes with the same state.
class _Pill extends StatelessWidget {
  const _Pill({required this.label, required this.tone, required this.filled});

  final String label;
  final Color tone;
  final bool filled;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: filled ? Palette.tint : Colors.transparent,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: filled ? Colors.transparent : Palette.line),
        ),
        child: Text(
          label,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: tone,
                fontWeight: FontWeight.w600,
              ),
        ),
      );
}

class _Empty extends StatelessWidget {
  const _Empty();

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return EmptyState(
      icon: Icons.history_outlined,
      title: strings.noVisitsYet,
      titleKey: const Key('tab.empty'),
      body: strings.newIntakeSubtitle,
      action: ActionTile(
        tileKey: const Key('visits.startVisit'),
        icon: Icons.assignment_outlined,
        title: strings.newIntakeTitle,
        prominent: true,
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute<void>(builder: (_) => const HospitalScreen()),
        ),
      ),
    );
  }
}
