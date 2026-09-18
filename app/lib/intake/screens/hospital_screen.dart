/// Hospital and department — 2/3 §5 screen 2.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import '../../l10n/strings.dart';
import '../../identity/abha_screen.dart';
import '../begin.dart';
import '../widgets/answer_widgets.dart';
import '../../voice/read_aloud_button.dart';

/// An icon for a department, by the code the content uses.
///
/// **Decoration, and it has to fail quietly.** Department codes come from the
/// hospital record, not from this app, so a hospital can add one tomorrow that
/// is not in this table — which is why the fallback is a generic mark and not
/// an assertion. An icon that is merely absent costs a patient nothing; a
/// crash on an unknown department costs them the visit.
///
/// The labels are never derived from this map. What the patient reads is
/// `department.display`, which is content and is translated; these are pictures
/// beside it.
const _departmentIcons = <String, IconData>{
  'opd': Icons.local_hospital_outlined,
  'general': Icons.local_hospital_outlined,
  'general_medicine': Icons.local_hospital_outlined,
  'ayush': Icons.spa_outlined,
  'ayurveda': Icons.spa_outlined,
  'kayachikitsa': Icons.spa_outlined,
  'panchakarma': Icons.water_drop_outlined,
  'yoga': Icons.self_improvement_outlined,
  'unani': Icons.eco_outlined,
  'siddha': Icons.local_florist_outlined,
  'homeopathy': Icons.science_outlined,
  'paediatrics': Icons.child_care_outlined,
  'pediatrics': Icons.child_care_outlined,
  'obstetrics': Icons.pregnant_woman_outlined,
  'gynaecology': Icons.pregnant_woman_outlined,
  'orthopaedics': Icons.accessibility_new_outlined,
  'orthopedics': Icons.accessibility_new_outlined,
  'dermatology': Icons.healing_outlined,
  'ent': Icons.hearing_outlined,
  'dental': Icons.medical_services_outlined,
  'ophthalmology': Icons.visibility_outlined,
  'cardiology': Icons.monitor_heart_outlined,
  'other': Icons.more_horiz,
  'others': Icons.more_horiz,
};

IconData _iconFor(String code) =>
    _departmentIcons[code.toLowerCase()] ?? Icons.medical_information_outlined;

class HospitalScreen extends ConsumerWidget {
  const HospitalScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final hospitals = ref.watch(hospitalsProvider);
    final chosen = ref.watch(selectedHospitalProvider);
    final department = ref.watch(selectedDepartmentProvider);
    final language = ref.watch(languageProvider);
    final heading = chosen == null ? strings.chooseHospital : strings.chooseDepartment;

    return Scaffold(
      // Continue appears only once both are picked, and leads to consent —
      // never to a question. §11: nothing clinical is collected first.
      bottomNavigationBar: chosen == null || department == null
          ? null
          : DecoratedBox(
              decoration: const BoxDecoration(
                color: Colors.white,
                boxShadow: [
                  BoxShadow(
                    color: Color(0x141B5E4A),
                    blurRadius: 20,
                    offset: Offset(0, -6),
                  ),
                ],
              ),
              child: SafeArea(
                child: Padding(
                  padding: const EdgeInsets.all(Sizes.gutter),
                  child: FilledButton.icon(
                    key: const Key('hospital.continue'),
                    // ABHA first, because linking is what puts history within
                    // reach of screen 5 — and it is offered only to a patient
                    // who has signed in, since there is nothing to link an
                    // address to otherwise (§7.2, §7.3).
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) =>
                            ref.watch(signedInProvider).valueOrNull == true
                                ? AbhaScreen(
                                    onDone: () =>
                                        Navigator.of(context).pushReplacement(
                                      MaterialPageRoute<void>(
                                        builder: (_) => const ConsentGate(),
                                      ),
                                    ),
                                  )
                                : const ConsentGate(),
                      ),
                    ),
                    icon: const Icon(Icons.arrow_forward),
                    iconAlignment: IconAlignment.end,
                    label: Text(strings.continueLabel),
                  ),
                ),
              ),
            ),
      appBar: AppBar(),
      body: Garnish(
        child: SafeArea(
          child: hospitals.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (_, __) => Center(
              child: Padding(
                padding: const EdgeInsets.all(Sizes.gutter),
                child: Text(strings.tryAgain),
              ),
            ),
            data: (list) => ListView(
              padding: const EdgeInsets.fromLTRB(
                Sizes.gutter,
                0,
                Sizes.gutter,
                Sizes.gutter,
              ),
              children: [
                Center(
                  child: EmblemMark(
                    icon: chosen == null
                        ? Icons.apartment_outlined
                        : Icons.medical_services_outlined,
                    size: 96,
                  ),
                ),
                const SizedBox(height: Sizes.gutter),
                Semantics(
                  header: true,
                  child: Text(
                    heading,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                ),
                // The hardest words in the app to read are on this screen, and
                // it was the only question screen without a voice. A patient
                // who chose a script they cannot read reached the one page that
                // routes them to a doctor and got no help with it.
                Center(
                  child: ReadAloudButton(
                    utteranceKey:
                        chosen == null ? 'screen.hospital' : 'screen.department',
                    text: [
                      heading,
                      if (chosen == null)
                        for (final hospital in list) hospital.displayName
                      else
                        for (final department in chosen.departments)
                          department.display,
                    ].join('. '),
                    language: language,
                  ),
                ),
                const SizedBox(height: Sizes.gap),
                ...chosen == null
                    ? [
                        for (final hospital in list)
                          OptionTile(
                            key: Key('hospital.${hospital.id}'),
                            icon: Icons.apartment_outlined,
                            label: hospital.location == null
                                ? hospital.displayName
                                : '${hospital.displayName} — ${hospital.location}',
                            onTap: () {
                              ref.read(selectedHospitalProvider.notifier).state =
                                  hospital;
                              // Remembered so the Visits/Documents/Profile tabs
                              // have a hospital to scope `me/*` to on the next
                              // launch, when there is no picker on screen to
                              // set one.
                              ref.read(hospitalStoreProvider).write(hospital.id);
                              // The hospital's own default becomes the language
                              // unless the patient already chose one on the
                              // first screen, which they did — so this is
                              // deliberately *not* applied. Left as a comment
                              // because the opposite is a tempting one-liner
                              // and would override an explicit choice with a
                              // default.
                            },
                          ),
                      ]
                    : [
                        for (final department in chosen.departments)
                          OptionTile(
                            key: Key('department.${department.code}'),
                            icon: _iconFor(department.code),
                            label: department.display,
                            selected: ref.watch(selectedDepartmentProvider) ==
                                department.code,
                            onTap: () => ref
                                .read(selectedDepartmentProvider.notifier)
                                .state = department.code,
                          ),
                      ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
