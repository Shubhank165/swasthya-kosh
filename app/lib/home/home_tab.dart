/// What the app opens on — stage 4, restructured in stage 5.
///
/// A greeting, the one optional thing worth offering, two actions, and what has
/// happened lately. A home screen that lists everything the app can do is a
/// menu; the point of this one is that a patient with a fever can see what to
/// press without reading the whole screen.
///
/// **Which is why exactly one thing is filled.** `Start a new visit` is what a
/// patient opening this app almost always came for. A resume card, when there
/// is a draft, takes the prominence instead — finishing something already begun
/// beats starting a second thing.
///
/// **Recent activity is read, never invented.** Every row comes from a
/// provider that already backs a tab: the last visit from `visitsProvider`, the
/// document count from `patientDocumentsProvider`. Where there is nothing, it
/// says so. The temptation on a screen like this is a plausible-looking feed;
/// a patient who sees "Blood test — 2 values need attention" on their home
/// screen has been given a reading, which is §8's whole prohibition.
///
/// **There is no completion meter and no notification bell.** A percentage
/// would run backwards when somebody reports chest pain, because the interview
/// branches; and a bell that opens nothing is a control that lies. Both are in
/// the reference design and both are left out on purpose.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../core/ui.dart';
import '../intake/flow.dart';
import '../intake/intake_host.dart';
import '../intake/screens/hospital_screen.dart';
import '../l10n/strings.dart';
import '../storage/database.dart';
import 'ayush_screen.dart';

class HomeTab extends ConsumerWidget {
  const HomeTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final bundle = ref.watch(currentBundleProvider);
    final name = ref.watch(displayNameProvider).valueOrNull;

    // §4 again, in its new home. A bundle naming a contract this build cannot
    // produce stops the intake before it starts — and it stops *only* the
    // intake. Documents, past visits and the profile still work, which they did
    // not when this check lived on the one screen the app opened with.
    final mustUpdate = bundle != null && !bundle.isUsable;

    final draft = ref.watch(resumableDraftProvider).valueOrNull;
    final resumable =
        draft != null && DateTime.now().difference(draft.updatedAt) <= draftMaxAge;

    return Garnish(
      child: ListView(
        padding: const EdgeInsets.all(Sizes.gutter),
        children: [
          const SizedBox(height: Sizes.gap),
          // The wordmark, as on the welcome screen. No bell beside it: this app
          // has no notifications and a control that opens nothing is worse than
          // an empty corner.
          Row(
            children: [
              ExcludeSemantics(
                child: Icon(Icons.spa, size: 26, color: colors.primary),
              ),
              const SizedBox(width: 8),
              Text(
                strings.appTitle,
                style: text.titleMedium?.copyWith(color: colors.primary),
              ),
            ],
          ),
          const SizedBox(height: Sizes.gutter),
          Semantics(
            header: true,
            child: Text(
              // Null far more often than not, and nothing here invents one.
              name == null ? strings.greetingNoName : strings.greetingHi(name),
              style: text.headlineMedium,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            strings.homeHeadline,
            style: text.bodyMedium?.copyWith(color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: Sizes.gutter),

          if (mustUpdate) ...[
            SoftCard(
              padding: const EdgeInsets.all(Sizes.gap + 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const IconChip(icon: Icons.system_update_alt, size: 40),
                  const SizedBox(width: Sizes.gap),
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        strings.updateRequired,
                        key: const Key('home.updateRequired'),
                        style: text.bodyMedium,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: Sizes.gap),
          ],

          // The optional thing, given the tinted panel rather than a card: it
          // is offered, not asked for (SIH item 3), and should not compete with
          // the two actions below.
          const _AyushBanner(),
          const SizedBox(height: Sizes.gutter),

          const _ResumeCard(),

          _SectionLabel(strings.quickActions),
          const SizedBox(height: Sizes.gap),
          // `IntrinsicHeight`, because the two tiles must match and a `Row`
          // with `stretch` inside a `ListView` has no height to stretch to.
          // Two children, so the extra layout pass costs nothing measurable.
          IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
              Expanded(
                child: QuickAction(
                  tileKey: const Key('home.newIntake'),
                  icon: Icons.assignment_outlined,
                  title: strings.newIntakeTitle,
                  subtitle: strings.newIntakeBrief,
                  prominent: !mustUpdate && !resumable,
                  onTap: mustUpdate
                      ? null
                      // Straight to the hospital chooser: the patient is signed
                      // in by the time this screen exists.
                      : () => Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              builder: (_) => const HospitalScreen(),
                            ),
                          ),
                ),
              ),
              const SizedBox(width: Sizes.gap),
              Expanded(
                child: QuickAction(
                  tileKey: const Key('home.uploadDocuments'),
                  icon: Icons.file_upload_outlined,
                  title: strings.uploadDocuments,
                  subtitle: strings.uploadDocumentsBrief,
                  // Switches tabs rather than pushing a route. Adding a page is
                  // the Documents tab's job and it can now do it without a
                  // visit; duplicating the camera here would be a second place
                  // for the same decision to drift.
                  onTap: () => ref.read(homeTabIndexProvider.notifier).state = 1,
                ),
              ),
              ],
            ),
          ),

          const SizedBox(height: Sizes.gutter),
          _SectionLabel(strings.recentActivity),
          const SizedBox(height: Sizes.gap),
          const _RecentActivity(),

          const SizedBox(height: Sizes.gutter),
          PrivacyNote(text: strings.dataProtected),
        ],
      ),
    );
  }
}

/// A small uppercase heading over a group.
class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Semantics(
        header: true,
        child: Text(
          text,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.w700,
                letterSpacing: 1.1,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
        ),
      );
}

/// The Ayurveda self-report, offered rather than required.
class _AyushBanner extends StatelessWidget {
  const _AyushBanner();

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final text = Theme.of(context).textTheme;
    return Material(
      color: Palette.tint,
      borderRadius: BorderRadius.circular(Sizes.radiusLarge),
      child: InkWell(
        key: const Key('home.ayush'),
        borderRadius: BorderRadius.circular(Sizes.radiusLarge),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute<void>(builder: (_) => const AyushScreen()),
        ),
        child: Padding(
          padding: const EdgeInsets.all(Sizes.gutter),
          child: Row(
            children: [
              const IconChip(
                icon: Icons.spa_outlined,
                background: Colors.white,
                size: 50,
              ),
              const SizedBox(width: Sizes.gap + 2),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(strings.ayushTitle, style: text.titleMedium),
                    const SizedBox(height: 3),
                    Text(
                      // Says what it is before it is tapped, and claims no
                      // result: this screen computes no Prakriti type and the
                      // card must not imply one (SIH items 3/4).
                      strings.ayurvedaTitle,
                      style: text.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }
}

/// What has happened lately, from the providers that already know.
class _RecentActivity extends ConsumerWidget {
  const _RecentActivity();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final visits = ref.watch(visitsProvider).valueOrNull ?? const [];
    final documents = ref.watch(patientDocumentsProvider).valueOrNull ?? const [];

    final rows = <Widget>[
      if (visits.isNotEmpty)
        _ActivityRow(
          icon: Icons.assignment_turned_in_outlined,
          title: visits.first.complaint ?? visits.first.department ?? '—',
          detail: _date(visits.first.receivedAt),
          onTap: () => ref.read(homeTabIndexProvider.notifier).state = 2,
        ),
      if (documents.isNotEmpty)
        _ActivityRow(
          icon: Icons.description_outlined,
          title: strings.documentsTab,
          // A count of pages, never a word about what any of them said.
          detail: strings.reviewAddMoreDocuments(documents.length),
          onTap: () => ref.read(homeTabIndexProvider.notifier).state = 1,
        ),
    ];

    if (rows.isEmpty) {
      return Text(
        strings.nothingRecent,
        key: const Key('home.nothingRecent'),
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
      );
    }

    return Column(
      children: [
        for (final row in rows) ...[
          row,
          if (row != rows.last) const SizedBox(height: Sizes.gap),
        ],
      ],
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

class _ActivityRow extends StatelessWidget {
  const _ActivityRow({
    required this.icon,
    required this.title,
    required this.detail,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String detail;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Sizes.radius),
        boxShadow: softShadow,
      ),
      child: Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(Sizes.radius),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(Sizes.radius),
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gap + 2),
            child: Row(
              children: [
                IconChip(icon: icon, size: 40),
                const SizedBox(width: Sizes.gap),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: text.titleMedium,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        detail,
                        style: text.bodySmall?.copyWith(
                          color: colors.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right, color: colors.onSurfaceVariant),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// "Continue where you left off", moved off the language screen.
///
/// A draft older than a week says so and offers nothing: answers about how long
/// a pain has lasted go stale, and submitting week-old ones quietly is worse
/// than asking again.
class _ResumeCard extends ConsumerWidget {
  const _ResumeCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final draft = ref.watch(resumableDraftProvider).valueOrNull;
    if (draft == null) return const SizedBox.shrink();

    if (DateTime.now().difference(draft.updatedAt) > draftMaxAge) {
      return Padding(
        padding: const EdgeInsets.only(bottom: Sizes.gutter),
        child: SoftCard(
          padding: const EdgeInsets.all(Sizes.gap + 2),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const IconChip(icon: Icons.history_toggle_off, size: 40),
              const SizedBox(width: Sizes.gap),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    strings.draftTooOld,
                    key: const Key('home.draftTooOld'),
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: Sizes.gutter),
      child: ActionTile(
        tileKey: const Key('home.resume'),
        icon: Icons.play_arrow_rounded,
        title: strings.resumeDraft,
        prominent: true,
        onTap: () => _resume(context, ref, draft),
      ),
    );
  }

  Future<void> _resume(BuildContext context, WidgetRef ref, Draft draft) async {
    final bundle = ref.read(currentBundleProvider);
    if (bundle == null) return;
    final database = await ref.read(databaseProvider.future);
    final queue = await ref.read(submissionQueueProvider.future);
    final documents = await ref.read(documentStoreProvider.future);
    final patientRef = await ref.read(patientRefProvider.future);

    final flow = IntakeFlow.resume(
      database: database,
      queue: queue,
      documents: documents,
      bundle: bundle,
      draft: draft,
      appVersion: ref.read(configProvider).appVersion,
      patientRef: patientRef,
      prefill: ref.read(prefillRepositoryProvider),
    );
    // Null when the content moved under the draft. Starting fresh is the only
    // safe answer: answers to questions that have since changed are answers
    // nobody can now read.
    if (flow == null || !context.mounted) return;
    ref.read(languageProvider.notifier).state = draft.language;
    await Navigator.of(context).push(intakeRoute(flow));
  }
}
