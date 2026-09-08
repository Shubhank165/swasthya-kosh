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
}
