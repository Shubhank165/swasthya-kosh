/// Profile — stage 4.
///
/// Deliberately thin. This app holds a phone number, a language and possibly an
/// ABHA address; it does not hold a name, a photograph, an address or a date of
/// birth, and a profile screen that looked like it should is an invitation to
/// start collecting them.
///
/// Nothing clinical appears here. What a patient answered belongs to the visit
/// it was answered in, which is the Visits tab.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../identity/abha_screen.dart';
import '../intake/screens/start_screen.dart';
import '../l10n/strings.dart';

class ProfileTab extends ConsumerWidget {
  const ProfileTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final language = ref.watch(languageProvider);

    return ListView(
      padding: const EdgeInsets.all(Sizes.gutter),
      children: [
        const SizedBox(height: Sizes.gutter),
        Semantics(
          header: true,
          child: Text(
            strings.profileTab,
            style: Theme.of(context).textTheme.titleLarge,
          ),
        ),
        const SizedBox(height: Sizes.gutter),

        // The number the session was issued against, and the only identifier
        // this app knows the patient by.
        //
        // Shown from the sign-in the patient performed on this device, not read
        // back from the server: what the backend stores is a peppered HMAC of
        // the number (§7.1) and it could not send the digits back if it wanted
        // to.
        ListTile(
          key: const Key('profile.phone'),
          leading: const Icon(Icons.phone_outlined),
          title: Text(strings.profilePhone),
          subtitle: Text(ref.watch(signedInPhoneProvider).valueOrNull ?? '—'),
        ),

        ListTile(
          key: const Key('profile.language'),
          leading: const Icon(Icons.translate_outlined),
          title: Text(strings.profileLanguage),
          subtitle: Text(languageNames[language] ?? language),
          trailing: const Icon(Icons.chevron_right),
          // The chooser it opens is the same screen the first launch shows —
          // one list of endonyms, one place it is defined. A second copy would
          // drift, and the copy a patient sees on day one is the one that has
          // to stay legible without reading.
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => const LanguageScreen(returnWhenChosen: true),
            ),
          ),
        ),

        ListTile(
          key: const Key('profile.abha'),
          leading: const Icon(Icons.badge_outlined),
          title: Text(strings.profileAbha),
          subtitle: Text(strings.notLinked),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              // Linked or not, the only way out of that screen is back to
              // here — §7.2 has no failure path worth a second screen.
              builder: (_) => AbhaScreen(onDone: () => Navigator.of(context).pop()),
            ),
          ),
        ),

        const Divider(height: Sizes.gutter * 2),

        // Erasure — `consent_v1.yaml` promises every patient "you can ask us to
        // delete what we recorded, at any time". This is that, without the walk
        // to the registration desk.
        //
        // Below sign-out rather than above it, and visually separated: the two
        // buttons do very different things and a patient reaching for "leave
        // this phone" must not land on "destroy my medical record". Sign-out is
        // the one people press often, so it keeps the position they expect.
        ListTile(
          key: const Key('profile.deleteHistory'),
          leading: Icon(
            Icons.delete_forever_outlined,
            color: Theme.of(context).colorScheme.error,
          ),
          title: Text(
            strings.profileDeleteHistory,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
          subtitle: Text(strings.profileDeleteSubtitle),
          onTap: () => _confirmErasure(context, ref, strings),
        ),

        const SizedBox(height: Sizes.gutter),
        OutlinedButton(
          key: const Key('profile.signOut'),
          // §10: this wipes the device, not just the token. A patient on a
          // borrowed phone must be able to leave nothing behind.
          onPressed: () async {
            await ref.read(authProvider).signOut();
            await ref.read(languageStoreProvider).clear();
            await ref.read(hospitalStoreProvider).clear();
            ref.read(selectedHospitalProvider.notifier).state = null;
            ref
              ..invalidate(signedInProvider)
              ..invalidate(storedLanguageProvider)
              ..invalidate(resumableDraftProvider)
              ..invalidate(hospitalContextProvider)
              ..invalidate(visitsProvider)
              ..invalidate(patientDocumentsProvider)
              ..invalidate(carryForwardProvider);
          },
          child: Text(strings.signOut),
        ),
      ],
    );
  }

  /// Ask, then erase, then say what happened.
  ///
  /// The dialog names what goes — visits, answers, documents, the Ayurveda
  /// assessment — rather than asking "are you sure?", because a patient cannot
  /// consent to a consequence nobody has stated. The destructive action is the
  /// second button and is not the default; the safe one is worded as a choice
  /// ("Keep my history") rather than as a dismissal, so the way out is as
  /// legible as the way through.
  Future<void> _confirmErasure(
    BuildContext context,
    WidgetRef ref,
    Strings strings,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(strings.deleteHistoryTitle),
        content: Text(strings.deleteHistoryBody),
        actions: [
          TextButton(
            key: const Key('profile.deleteCancel'),
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(strings.deleteHistoryCancel),
          ),
          TextButton(
            key: const Key('profile.deleteConfirm'),
            style: TextButton.styleFrom(
              foregroundColor: Theme.of(dialogContext).colorScheme.error,
            ),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(strings.deleteHistoryConfirm),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    final summary = await ref.read(erasureRepositoryProvider).eraseHistory();
    if (!context.mounted) return;

    // Four outcomes, four sentences. "Deleted" over the top of a failed request
    // is the one thing this screen must never say, because the patient has no
    // way to find out otherwise.
    final String message;
    if (summary == null) {
      message = strings.deleteHistoryFailed;
    } else if (!summary.complete) {
      message = strings.deleteHistoryPartial;
    } else if (summary.erasedNothing) {
      message = strings.deleteHistoryNothing;
    } else {
      message = strings.deleteHistoryDone;
    }

    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));

    // Everything that reads the record is now stale. Invalidated rather than
    // refreshed so a screen showing a deleted visit cannot linger behind this
    // one.
    ref
      ..invalidate(visitsProvider)
      ..invalidate(patientDocumentsProvider)
      ..invalidate(carryForwardProvider)
      ..invalidate(resumableDraftProvider);
  }
}
