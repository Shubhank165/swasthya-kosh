/// Profile — stage 4.
///
/// Deliberately thin. This app holds a phone number, a language and possibly an
/// ABHA address; it does not hold a name, a photograph, an address or a date of
/// birth, and a profile screen that looked like it should is an invitation to
/// start collecting them.
///
/// Nothing clinical appears here. What a patient answered belongs to the visit
/// it was answered in, which is the Visits tab.
///
/// **The destructive action keeps its own group, below a gap.** Erasure and
/// sign-out do very different things and a patient reaching for "leave this
/// phone" must not land on "destroy my medical record"; the styling here makes
/// that separation visible rather than relying on the reader noticing which
/// word is red.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../core/ui.dart';
import '../identity/abha_screen.dart';
import '../intake/screens/start_screen.dart';
import '../l10n/strings.dart';

class ProfileTab extends ConsumerWidget {
  const ProfileTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final colors = Theme.of(context).colorScheme;
    final language = ref.watch(languageProvider);

    return Garnish(
      child: ListView(
      padding: const EdgeInsets.all(Sizes.gutter),
      children: [
        const SizedBox(height: Sizes.gap),
        Semantics(
          header: true,
          child: Text(
            strings.profileTab,
            style: Theme.of(context).textTheme.headlineMedium,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          strings.profileSubtitle,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: colors.onSurfaceVariant,
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
        _ProfileRow(
          rowKey: const Key('profile.name'),
          icon: Icons.person_outline,
          label: strings.profileName,
          // The name itself when set; otherwise the sentence that says why it
          // is safe to set one. Never a placeholder that looks like a value.
          value: ref.watch(displayNameProvider).valueOrNull ??
              strings.profileNameOnDevice,
          onTap: () => _editName(context, ref, strings),
        ),
        const SizedBox(height: Sizes.gap),

        _ProfileRow(
          rowKey: const Key('profile.phone'),
          icon: Icons.phone_outlined,
          label: strings.profilePhone,
          value: ref.watch(signedInPhoneProvider).valueOrNull ?? '—',
        ),
        const SizedBox(height: Sizes.gap),

        _ProfileRow(
          rowKey: const Key('profile.language'),
          icon: Icons.translate_outlined,
          label: strings.profileLanguage,
          value: languageNames[language] ?? language,
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
        const SizedBox(height: Sizes.gap),

        _ProfileRow(
          rowKey: const Key('profile.abha'),
          icon: Icons.badge_outlined,
          label: strings.profileAbha,
          value: strings.notLinked,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              // Linked or not, the only way out of that screen is back to
              // here — §7.2 has no failure path worth a second screen.
              builder: (_) => AbhaScreen(onDone: () => Navigator.of(context).pop()),
            ),
          ),
        ),

        const SizedBox(height: Sizes.gutter * 2),

        // Erasure — `consent_v1.yaml` promises every patient "you can ask us to
        // delete what we recorded, at any time". This is that, without the walk
        // to the registration desk.
        //
        // Below sign-out rather than above it, and visually separated: the two
        // buttons do very different things and a patient reaching for "leave
        // this phone" must not land on "destroy my medical record". Sign-out is
        // the one people press often, so it keeps the position they expect.
        _ProfileRow(
          rowKey: const Key('profile.deleteHistory'),
          icon: Icons.delete_forever_outlined,
          label: strings.profileDeleteHistory,
          value: strings.profileDeleteSubtitle,
          tone: colors.error,
          onTap: () => _confirmErasure(context, ref, strings),
        ),

        const SizedBox(height: Sizes.gutter),
        OutlinedButton(
          key: const Key('profile.signOut'),
          // §10: this wipes the device, not just the token. A patient on a
          // borrowed phone must be able to leave nothing behind.
          onPressed: () async {
            await ref.read(authProvider).signOut();
            await ref.read(displayNameStoreProvider).clear();
            await ref.read(languageStoreProvider).clear();
            await ref.read(hospitalStoreProvider).clear();
            ref.read(selectedHospitalProvider.notifier).state = null;
            ref
              ..invalidate(displayNameProvider)
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
        const SizedBox(height: Sizes.gutter),
        PrivacyNote(text: strings.dataProtected),
      ],
      ),
    );
  }

  /// Set or change the greeting name.
  ///
  /// **Nothing here reaches the backend.** The store is device-local and the
  /// intake payload has no field for a name; this is what the home screen says
  /// good morning to and nothing else. Clearing the box removes it.
  Future<void> _editName(
    BuildContext context,
    WidgetRef ref,
    Strings strings,
  ) async {
    final saved = await showDialog<String>(
      context: context,
      builder: (_) => _NameDialog(
        initial: ref.read(displayNameProvider).valueOrNull ?? '',
      ),
    );
    if (saved == null) return;
    await ref.read(displayNameStoreProvider).write(saved);
    ref.invalidate(displayNameProvider);
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

/// One setting: what it is, what it currently says, and a chevron if it opens.
///
/// A row with no `onTap` gets no chevron. A chevron that leads nowhere is a
/// promise the screen does not keep, and on this screen the only rows that lead
/// nowhere are the ones showing something the patient cannot change here.
class _ProfileRow extends StatelessWidget {
  const _ProfileRow({
    required this.rowKey,
    required this.icon,
    required this.label,
    required this.value,
    this.onTap,
    this.tone,
  });

  final Key rowKey;
  final IconData icon;
  final String label;
  final String value;
  final VoidCallback? onTap;

  /// Non-null only for the destructive row.
  final Color? tone;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final accent = tone ?? colors.onSurface;

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Sizes.radius),
        boxShadow: softShadow,
      ),
      child: Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(Sizes.radius),
        child: InkWell(
          key: rowKey,
          onTap: onTap,
          borderRadius: BorderRadius.circular(Sizes.radius),
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gap + 2),
            child: Row(
              children: [
                IconChip(
                  icon: icon,
                  background: tone == null ? Palette.tint : Palette.urgentSurface,
                  foreground: tone ?? colors.primary,
                ),
                const SizedBox(width: Sizes.gap + 2),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        label,
                        style: text.titleMedium?.copyWith(color: accent),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        value,
                        style: text.bodySmall?.copyWith(
                          color: colors.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                if (onTap != null)
                  Icon(Icons.chevron_right, color: colors.onSurfaceVariant),
              ],
            ),
          ),
        ),
      ),
    );
  }
}


/// The name dialog, which owns its controller.
///
/// **The controller has to live and die with the dialog.** It used to be built
/// beside `showDialog` and disposed the moment that future completed — but that
/// future completes when the route is *popped*, not when it is gone. The dialog
/// keeps building through its exit animation, and a `TextField` rebuilding
/// against a disposed controller tears down the subtree mid-frame, which
/// surfaces as a framework assertion a long way from the cause.
///
/// A `StatefulWidget` disposes in `dispose`, which runs when the route is
/// actually finished. That is the whole fix, and it is why this is a widget
/// rather than four lines in a method.
class _NameDialog extends StatefulWidget {
  const _NameDialog({required this.initial});

  final String initial;

  @override
  State<_NameDialog> createState() => _NameDialogState();
}

class _NameDialogState extends State<_NameDialog> {
  late final TextEditingController _controller =
      TextEditingController(text: widget.initial);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _save() => Navigator.of(context).pop(_controller.text);

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return AlertDialog(
      title: Text(strings.profileName),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            key: const Key('profile.nameField'),
            controller: _controller,
            autofocus: true,
            textCapitalization: TextCapitalization.words,
            textInputAction: TextInputAction.done,
            style: Theme.of(context).textTheme.bodyLarge,
            decoration: InputDecoration(labelText: strings.profileName),
            // Enter saves, so the patient never has to find the button.
            onSubmitted: (_) => _save(),
          ),
          const SizedBox(height: Sizes.gap),
          Text(
            strings.profileNameOnDevice,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(strings.cancelLabel),
        ),
        TextButton(
          key: const Key('profile.nameSave'),
          onPressed: _save,
          child: Text(strings.saveLabel),
        ),
      ],
    );
  }
}
