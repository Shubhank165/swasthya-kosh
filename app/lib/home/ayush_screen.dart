/// The AYUSH assessment — stage 4, and not built yet.
///
/// **A placeholder that says so, in as many words.** This app already has one
/// mocked integration (ABHA, §7.2) and the rule it follows is the rule here: a
/// feature that is not real must be visibly not real, on screen, to the person
/// using it. A greyed-out button with no explanation invites the assumption
/// that it worked and produced nothing.
///
/// What goes here is not decided yet — the assessment's content is coming from
/// the team, and inventing questions to fill the gap would put engineer-authored
/// clinical content in front of a patient, which is the one thing
/// `CLINICAL_REVIEW_QUEUE.md` exists to prevent.
library;

import 'package:flutter/material.dart';

import '../core/theme.dart';
import '../l10n/strings.dart';

class AyushScreen extends StatelessWidget {
  const AyushScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(strings.ayushTitle)),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(Sizes.gutter),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.spa_outlined,
                size: 64,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(height: Sizes.gutter),
              Text(
                strings.notAvailableYet,
                key: const Key('ayush.notAvailable'),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
