/// The widget the flow drives — 2/3 §5.
///
/// Deliberately thin. Every screen it shows is a stateless widget with
/// callbacks, and every decision about which one to show belongs to
/// [IntakeFlow]; this file's whole job is to turn a [FlowStage] into a widget
/// and hand the taps back. That split is what lets §15's red-flag, resume and
/// offline tests run against the flow with no widget tree at all.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../content/answer.dart';
import '../core/providers.dart';
import '../documents/documents_screen.dart';
import '../documents/prepare.dart';
import '../l10n/strings.dart';
import 'flow.dart';
import 'screens/complaint_screen.dart';
import 'screens/question_screen.dart';
import 'screens/review_screen.dart';
import 'screens/submitted_screen.dart';
import 'screens/urgent_care_screen.dart';

class IntakeHost extends ConsumerStatefulWidget {
  const IntakeHost({super.key, required this.flow});

  final IntakeFlow flow;

  @override
  ConsumerState<IntakeHost> createState() => _IntakeHostState();
}

class _IntakeHostState extends ConsumerState<IntakeHost> {
  @override
  Widget build(BuildContext context) {
    final flow = widget.flow;
    return ListenableBuilder(
      listenable: flow,
      builder: (context, _) => switch (flow.stage) {
        FlowStage.question => _question(flow),
        FlowStage.documents => _documents(flow),
        FlowStage.review => ReviewScreen(
            bundle: flow.bundle,
            answers: flow.answers,
            language: flow.language,
            onEdit: flow.edit,
            onSubmit: flow.sending ? () {} : flow.submit,
          ),
        FlowStage.urgent => UrgentCareScreen(
            // From the hospital record where one is loaded, never a constant
            // in the widget — §6. The default is 108, which is common across
            // most Indian states but is not universal.
            emergencyNumber: ref.read(configProvider).emergencyNumber,
            onShowNearestHospital: () => _showHospital(flow),
            // Acknowledging closes the app's intake. It does **not** return to
            // the interview: there is no such transition on the flow.
            onAcknowledge: () => Navigator.of(context)
                .popUntil((route) => route.isFirst),
          ),
        FlowStage.submitted => SubmittedScreen(
            referenceCode: flow.referenceCode,
            hospitalName: flow.hospitalName,
            queued: flow.queued,
            // Back to the start today; back to the home screen once there is
            // one (stage 4). Either way it is a button the patient presses,
            // not a gesture they resort to.
            onDone: () => Navigator.of(context).popUntil((route) => route.isFirst),
          ),
      },
    );
  }

  /// Screen 9 — old prescriptions and reports (§5, §8).
  ///
  /// The screen shows the image and its status, never what was read off it:
  /// unverified OCR output shown to a patient is a diagnosis surface (§8), and
  /// nothing on this path has even been uploaded yet.
  Widget _documents(IntakeFlow flow) {
    final strings = Strings.of(context);
    final rejected = flow.rejectedQuality;
    if (rejected != null) {
      // Told while the paper is still in front of them.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(switch (rejected) {
            PageQuality.blurred => strings.photoTooBlurry,
            PageQuality.tooSmall => strings.photoTooSmall,
            PageQuality.possiblyCropped => strings.photoLooksCropped,
            PageQuality.ok => strings.tryAgain,
          }),
        ));
      });
    }
    return DocumentsScreen(
      pages: flow.pages,
      onTakePhoto: () => flow.addPage(fromCamera: true),
      onChooseFromGallery: () => flow.addPage(fromCamera: false),
      onRemove: flow.removePage,
      onContinue: flow.continueToReview,
    );
  }

  Widget _question(IntakeFlow flow) {
    final question = flow.question!;
    final (done, total) = flow.sectionProgress;

    // The chief complaint gets the icon grid (§5 screen 6) — it is the first
    // clinical question and the one that decides the branch, so it is the one
    // where a patient who reads poorly most needs the help.
    if (question.fieldId == 'chief_complaint') {
      return ComplaintScreen(
        question: question,
        language: flow.language,
        onChosen: (code, label) => flow.answer(CodedValue(code), label),
      );
    }

    return QuestionScreen(
      question: question,
      language: flow.language,
      onAnswered: flow.answer,
      onDontKnow: flow.dontKnow,
      onSkip: flow.skip,
      sectionsDone: done,
      sectionsTotal: total,
      onBack: flow.canGoBack ? flow.back : null,
    );
  }

  void _showHospital(IntakeFlow flow) {
    // The nearest emergency department is a maps handoff, not a screen this app
    // draws — and it is not this app's to invent. Until the hospital record
    // carries an address, the honest thing is to show the one the patient
    // already chose rather than a guess dressed as a referral.
    final hospital = ref.read(selectedHospitalProvider);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(hospital?.location ?? flow.hospitalName)),
    );
  }
}

/// Convenience for the callers that build a flow and push it.
Route<void> intakeRoute(IntakeFlow flow) => MaterialPageRoute<void>(
      builder: (_) => IntakeHost(flow: flow),
    );
