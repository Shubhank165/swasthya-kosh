/// Hospital and department — 2/3 §5 screen 2.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../l10n/strings.dart';
import '../../identity/abha_screen.dart';
import '../begin.dart';
import '../widgets/answer_widgets.dart';

class HospitalScreen extends ConsumerWidget {
  const HospitalScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final hospitals = ref.watch(hospitalsProvider);
    final chosen = ref.watch(selectedHospitalProvider);
    final department = ref.watch(selectedDepartmentProvider);

    return Scaffold(
      // Continue appears only once both are picked, and leads to consent —
      // never to a question. §11: nothing clinical is collected first.
      bottomNavigationBar: chosen == null || department == null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(Sizes.gutter),
                child: FilledButton(
                  key: const Key('hospital.continue'),
                  // ABHA first, because linking is what puts history within
                  // reach of screen 5 — and it is offered only to a patient who
                  // has signed in, since there is nothing to link an address to
                  // otherwise (§7.2, §7.3).
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => ref.watch(signedInProvider).valueOrNull == true
                          ? AbhaScreen(
                              onDone: () => Navigator.of(context).pushReplacement(
                                MaterialPageRoute<void>(
                                  builder: (_) => const ConsentGate(),
                                ),
                              ),
                            )
                          : const ConsentGate(),
                    ),
                  ),
                  child: Text(strings.continueLabel),
                ),
              ),
            ),
      appBar: AppBar(
        title: Text(chosen == null ? strings.chooseHospital : strings.chooseDepartment),
      ),
      body: SafeArea(
        child: hospitals.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (_, __) => Center(
            child: Padding(
              padding: const EdgeInsets.all(Sizes.gutter),
              child: Text(strings.tryAgain),
            ),
          ),
          data: (list) => ListView(
            padding: const EdgeInsets.all(Sizes.gutter),
            children: chosen == null
                ? [
                    for (final hospital in list)
                      OptionTile(
                        key: Key('hospital.${hospital.id}'),
                        label: hospital.location == null
                            ? hospital.displayName
                            : '${hospital.displayName} — ${hospital.location}',
                        onTap: () {
                          ref.read(selectedHospitalProvider.notifier).state = hospital;
                          // The hospital's own default becomes the language
                          // unless the patient already chose one on the first
                          // screen, which they did — so this is deliberately
                          // *not* applied. Left as a comment because the
                          // opposite is a tempting one-liner and would override
                          // an explicit choice with a default.
                        },
                      ),
                  ]
                : [
                    for (final department in chosen.departments)
                      OptionTile(
                        key: Key('department.${department.code}'),
                        label: department.display,
                        selected:
                            ref.watch(selectedDepartmentProvider) == department.code,
                        onTap: () => ref
                            .read(selectedDepartmentProvider.notifier)
                            .state = department.code,
                      ),
                  ],
          ),
        ),
      ),
    );
  }
}
