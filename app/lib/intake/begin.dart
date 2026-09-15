/// Getting from "which hospital" to the first question — 2/3 §5 screens 3, 4.
///
/// Consent, then who the intake is for, then the interview. The order is §11's
/// and is not negotiable: **nothing clinical is collected before consent is
/// granted**, so the consent screen sits between the hospital picker and the
/// first question rather than anywhere more convenient.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../consent/consent_repository.dart';
import '../consent/consent_screen.dart';
import '../core/providers.dart';
import '../core/theme.dart';
import '../l10n/strings.dart';
import 'flow.dart';
import 'intake_host.dart';
import 'screens/reporter_screen.dart';
import 'screens/returning_patient_screen.dart';

/// Screen 3 — consent (§11).
class ConsentGate extends ConsumerWidget {
  const ConsentGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final language = ref.watch(languageProvider);
    final notice = ref.watch(consentNoticeProvider);

    return notice.when(
      loading: () => const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (_, __) => _message(context, strings.tryAgain),
      data: (notice) {
        if (notice == null) return _message(context, strings.tryAgain);

        // A notice the patient cannot read is not a notice. Agreement to text
        // in a language they did not choose is not consent, so this stops
        // rather than falling back to English — and it names the languages
        // that do have a notice, in their own scripts, so the way out is
        // legible even to somebody who cannot read the sentence.
        if (!notice.isCompleteIn(language)) {
          return _message(context, strings.consentNotTranslated);
        }

        final readable = notice.readableIn(language);
        return ConsentScreen(
          purposes: [
            for (final purpose in readable)
              ConsentPurpose(
                code: purpose.code,
                text: [
                  purpose.labelFor(language)!,
                  if (purpose.descriptionFor(language) case final body?) body,
                ].join('\n'),
                required: purpose.required,
              ),
          ],
          language: language,
          onGranted: (granted) {
            ref.read(consentGrantProvider.notifier).state = ConsentGrant(
              consentVersion: notice.version,
              language: language,
              // The text as assembled for the screen, not a summary of it. The
              // backend hashes this, and a hash of a paraphrase proves nothing.
              noticeText: notice.noticeTextIn(language),
              granted: granted.toList()..sort(),
              // Named, not inferred from absence: "refused" and "never offered"
              // are different things to a regulator.
              refused: [
                for (final purpose in readable)
                  if (!granted.contains(purpose.code)) purpose.code,
              ]..sort(),
              // Filled in properly once the reporter is known — the person
              // tapping is the granting party.
              grantingParty: ref.read(reporterProvider),
            );
            Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const ReporterGate()),
            );
          },
        );
      },
    );
  }

  Widget _message(BuildContext context, String text) => Scaffold(
        appBar: AppBar(title: Text(Strings.of(context).consentTitle)),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: Text(
              text,
              key: const Key('consent.blocked'),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
          ),
        ),
      );
}

/// Screen 4 — who the intake is for.
class ReporterGate extends ConsumerWidget {
  const ReporterGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => ReporterScreen(
        onChosen: (reporter, {required bool guardianConsent}) {
          ref.read(reporterProvider.notifier).state = reporter;
          // §11: for a minor what is recorded is that a guardian consented —
          // no birth date is collected to compute an age. Carried onto the
          // artefact rather than left implied by a coincidence of the two
          // vocabularies.
          ref.read(grantingPartyProvider.notifier).state =
              guardianConsent ? 'parent_guardian' : reporter;
          Navigator.of(context).push(
            MaterialPageRoute<void>(builder: (_) => const ReturningPatientGate()),
          );
        },
      );
}

/// Screen 5 — the returning-patient check, then the interview.
///
/// Skipped entirely when there is nothing to confirm, which is every guest and
/// every first visit. A screen that says "we hold nothing about you" would be
/// an extra tap to tell somebody something they know.
class ReturningPatientGate extends ConsumerStatefulWidget {
  const ReturningPatientGate({super.key});

  @override
  ConsumerState<ReturningPatientGate> createState() => _ReturningPatientGateState();
}

class _ReturningPatientGateState extends ConsumerState<ReturningPatientGate> {
  bool _starting = false;

  @override
  Widget build(BuildContext context) {
    if (_starting) return const _Working();

    final carried = ref.watch(carryForwardProvider);
    return carried.when(
      loading: () => const _Working(),
      // A history that will not load is a history that is skipped: the intake
      // asks everything from scratch, which is slower and completely safe. It
      // must never block.
      error: (_, __) => _startOnce(const []),
      data: (facts) {
        if (facts.isEmpty) return _startOnce(const []);
        return ReturningPatientScreen(
          items: [
            for (final fact in facts)
              CarriedItem(
                fieldId: fact.fieldId,
                label: '${fact.label}: ${fact.value}',
                // The date the hospital last had it confirmed. Rendered as a
                // plain date rather than "3 months ago": "still correct?" is
                // only a fair question if the patient can see how old the
                // record is, and a relative phrase in nine languages is a
                // translation problem for no gain.
                recordedOn: fact.verifiedAt == null
                    ? ''
                    : fact.verifiedAt!.toIso8601String().substring(0, 10),
              ),
          ],
          onDone: (decisions) => _begin([
            // Only a Yes stops the question being asked again. "No longer
            // correct" and "not sure" both fall through to the interview,
            // because a fact the patient doubts is not a fact — and it is
            // certainly not a `no`.
            for (final fact in facts)
              if (decisions[fact.fieldId] == CarryDecision.stillCorrect)
                ConfirmedFact(
                  fieldId: fact.fieldId,
                  label: fact.label,
                  value: fact.value,
                  fromIntakeId: fact.intakeId,
                  // The date the hospital's record was last confirmed by a
                  // physician, which is the date the patient was just shown and
                  // asked about. The app is not told when the fact was first
                  // written down; verification is the older date it does know,
                  // and claiming a more precise one would be inventing it.
                  originallyRecorded: fact.verifiedAt == null
                      ? ''
                      : fact.verifiedAt!.toIso8601String().substring(0, 10),
                ),
          ]),
        );
      },
    );
  }

  /// Start without a screen, exactly once, after this frame.
  Widget _startOnce(List<ConfirmedFact> confirmed) {
    if (!_starting) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _begin(confirmed));
    }
    return const _Working();
  }

  Future<void> _begin(List<ConfirmedFact> confirmed) async {
    if (_starting) return;
    setState(() => _starting = true);

    final bundle = ref.read(currentBundleProvider);
    final hospital = ref.read(selectedHospitalProvider);
    final queue = await ref.read(submissionQueueProvider.future);
    final database = await ref.read(databaseProvider.future);
    final documents = await ref.read(documentStoreProvider.future);

    if (bundle == null || !bundle.isUsable || hospital == null) {
      if (mounted) Navigator.of(context).popUntil((route) => route.isFirst);
      return;
    }

    final consent = ref.read(consentGrantProvider);
    final grantingParty = ref.read(grantingPartyProvider);
    final reporter = ref.read(reporterProvider);
    final patientRef = await ref.read(patientRefProvider.future);

    final flow = await IntakeFlow.begin(
      database: database,
      queue: queue,
      documents: documents,
      bundle: bundle,
      language: ref.read(languageProvider),
      hospitalId: hospital.id,
      hospitalName: hospital.displayName,
      departmentCode: ref.read(selectedDepartmentProvider),
      reporter: reporter,
      appVersion: ref.read(configProvider).appVersion,
      confirmed: confirmed,
      patientRef: patientRef,
      // A hospital that already holds facts about this patient has seen them
      // before, which is what makes the Ayurveda section the current-state
      // subset rather than the full module (§5 screen 8).
      returnVisit: confirmed.isNotEmpty || ref.read(carryForwardProvider).valueOrNull?.isNotEmpty == true,
      prefill: ref.read(prefillRepositoryProvider),
      consent: consent == null
          ? null
          : ConsentGrant(
              consentVersion: consent.consentVersion,
              language: consent.language,
              noticeText: consent.noticeText,
              granted: consent.granted,
              refused: consent.refused,
              grantingParty: grantingParty,
            ),
    );

    if (!mounted) return;
    Navigator.of(context).pushReplacement(intakeRoute(flow));
  }
}

class _Working extends StatelessWidget {
  const _Working();

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: CircularProgressIndicator()));
}
