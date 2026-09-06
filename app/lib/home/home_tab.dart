/// What the app opens on — stage 4.
///
/// Two things to start and one to resume, and nothing else. A home screen that
/// lists everything the app can do is a menu; the point of this one is that a
/// patient with a fever can see what to press without reading the whole screen.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
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
    final bundle = ref.watch(currentBundleProvider);

    // §4 again, in its new home. A bundle naming a contract this build cannot
    // produce stops the intake before it starts — and it stops *only* the
    // intake. Documents, past visits and the profile still work, which they did
    // not when this check lived on the one screen the app opened with.
    final mustUpdate = bundle != null && !bundle.isUsable;

    return ListView(
      padding: const EdgeInsets.all(Sizes.gutter),
      children: [
        const SizedBox(height: Sizes.gutter),
        Semantics(
          header: true,
          child: Text(
            strings.appTitle,
            style: Theme.of(context).textTheme.titleLarge,
          ),
        ),
        const SizedBox(height: Sizes.gutter),
        if (mustUpdate)
          Padding(
            padding: const EdgeInsets.only(bottom: Sizes.gap),
            child: Text(
              strings.updateRequired,
              key: const Key('home.updateRequired'),
              style: Theme.of(context).textTheme.bodyLarge,
            ),
          ),
        const _ResumeCard(),
        _ActionCard(
          buttonKey: const Key('home.newIntake'),
          icon: Icons.assignment_outlined,
          title: strings.newIntakeTitle,
          subtitle: strings.newIntakeSubtitle,
          onTap: mustUpdate
              ? null
              // Straight to the hospital chooser: the patient is signed in
              // by the time this screen exists, so the sign-in branch the old
              // start screen carried has nothing left to decide.
              : () => Navigator.of(context).push(
                    MaterialPageRoute<void>(builder: (_) => const HospitalScreen()),
                  ),
        ),
        const SizedBox(height: Sizes.gap),
        _ActionCard(
          buttonKey: const Key('home.ayush'),
          icon: Icons.spa_outlined,
          title: strings.ayushTitle,
          // Says what it is before it is tapped. A card that looks live and
          // then apologises has already wasted the tap.
          subtitle: strings.notAvailableYet,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(builder: (_) => const AyushScreen()),
          ),
        ),
      ],
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
        padding: const EdgeInsets.only(bottom: Sizes.gap),
        child: Text(
          strings.draftTooOld,
          key: const Key('home.draftTooOld'),
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: Sizes.gap),
      child: _ActionCard(
        buttonKey: const Key('home.resume'),
        icon: Icons.play_arrow_outlined,
        title: strings.resumeDraft,
        subtitle: null,
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

    final flow = IntakeFlow.resume(
      database: database,
      queue: queue,
      documents: documents,
      bundle: bundle,
      draft: draft,
      appVersion: ref.read(configProvider).appVersion,
    );
    // Null when the content moved under the draft. Starting fresh is the only
    // safe answer: answers to questions that have since changed are answers
    // nobody can now read.
    if (flow == null || !context.mounted) return;
    ref.read(languageProvider.notifier).state = draft.language;
    await Navigator.of(context).push(intakeRoute(flow));
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.buttonKey,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final Key buttonKey;
  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Card(
      margin: EdgeInsets.zero,
      child: InkWell(
        key: buttonKey,
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(Sizes.gutter),
          child: Row(
            children: [
              Icon(icon, size: 32, color: colors.primary),
              const SizedBox(width: Sizes.gutter),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: Theme.of(context).textTheme.titleMedium),
                    if (subtitle != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        subtitle!,
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ],
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
