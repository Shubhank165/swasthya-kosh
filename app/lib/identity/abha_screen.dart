/// Linking an ABHA address — 2/3 §7.2.
///
/// **Nothing on this screen is required and nothing on it can fail an intake.**
/// The primary action is to continue; linking is the secondary one. A patient
/// who taps past it, a lookup that finds nothing, and a gateway that is down all
/// arrive at the same next screen, which is the whole of "never mandatory".
///
/// The mock notice is not a debug affordance. It is on screen because a demo
/// that presents a mocked government integration as a live one is a claim
/// nobody in the room can check.
///
/// **This asks for an ABHA *address*, not the fourteen-digit number.** An
/// address is a handle — `name@sbx` — and the number is a government
/// identifier this system neither requests nor stores (see
/// `backend/app/adapters/abha/providers.py`). Designs that put a
/// `12-3456-7890-1234` field on this screen are describing a different app.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../core/ui.dart';
import '../l10n/strings.dart';

class AbhaScreen extends ConsumerStatefulWidget {
  const AbhaScreen({super.key, required this.onDone});

  /// Called whether or not anything was linked. There is no failure path out of
  /// this screen because there is no failure that matters here.
  final VoidCallback onDone;

  @override
  ConsumerState<AbhaScreen> createState() => _AbhaScreenState();
}

class _AbhaScreenState extends ConsumerState<AbhaScreen> {
  final _address = TextEditingController();
  bool _working = false;
  bool _notFound = false;
  bool _mocked = false;

  @override
  void dispose() {
    _address.dispose();
    super.dispose();
  }

  Future<void> _link() async {
    setState(() {
      _working = true;
      _notFound = false;
    });
    final result = await ref.read(abhaRepositoryProvider).link(_address.text.trim());
    if (!mounted) return;
    setState(() {
      _working = false;
      _mocked = result?.isMocked ?? false;
      _notFound = result == null || !result.verified;
    });
    if (result != null && result.verified) {
      // Linking may have brought history into reach, which is what screen 5
      // reads.
      ref.invalidate(carryForwardProvider);
      widget.onDone();
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final colors = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(),
      body: Garnish(
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(
              Sizes.gutter,
              0,
              Sizes.gutter,
              Sizes.gutter,
            ),
            children: [
              ScreenIntro(
                title: strings.abhaTitle,
                body: strings.abhaExplanation,
              ),
              const SizedBox(height: Sizes.gutter),
              const Center(
                child: EmblemMark(icon: Icons.badge_outlined, size: 116),
              ),
              const SizedBox(height: Sizes.gutter),
              SoftCard(
                child: TextField(
                  key: const Key('abha.address'),
                  controller: _address,
                  autocorrect: false,
                  // §1 rule 8: nothing here invites dictation. This is an
                  // identifier, not a clinical field, but the habit is the
                  // point.
                  keyboardType: TextInputType.emailAddress,
                  style: Theme.of(context).textTheme.bodyLarge,
                  decoration: InputDecoration(
                    labelText: strings.abhaAddressLabel,
                    prefixIcon: const Icon(Icons.alternate_email),
                    // The card is already a surface; a second one inside it
                    // would be a box in a box.
                    filled: false,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
              ),
              if (_notFound) ...[
                const SizedBox(height: Sizes.gap),
                _Note(
                  noteKey: const Key('abha.notFound'),
                  icon: Icons.search_off,
                  text: strings.abhaNotFound,
                  tone: colors.onSurfaceVariant,
                ),
              ],
              if (_mocked) ...[
                const SizedBox(height: Sizes.gap),
                _Note(
                  noteKey: const Key('abha.mockNotice'),
                  icon: Icons.info_outline,
                  text: strings.mockNotice,
                  tone: colors.error,
                ),
              ],
              const SizedBox(height: Sizes.gutter),
              // Continue is the filled button and linking is the outlined one:
              // the emphasis says which of the two the patient actually needs.
              FilledButton(
                key: const Key('abha.skip'),
                onPressed: widget.onDone,
                child: Text(strings.skipForNow),
              ),
              const SizedBox(height: Sizes.gap),
              OutlinedButton(
                key: const Key('abha.link'),
                onPressed: _working ? null : _link,
                child: _working
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(strokeWidth: 2.5),
                      )
                    : Text(strings.continueLabel),
              ),
              const SizedBox(height: Sizes.gutter),
              PrivacyNote(text: strings.dataProtected),
            ],
          ),
        ),
      ),
    );
  }
}

/// A short line with an icon, for the two things this screen sometimes says.
///
/// The key goes on the *text*, because that is the string the tests assert on
/// and a key on a wrapper would be found while pointing at nothing readable.
class _Note extends StatelessWidget {
  const _Note({
    required this.noteKey,
    required this.icon,
    required this.text,
    required this.tone,
  });

  final Key noteKey;
  final IconData icon;
  final String text;
  final Color tone;

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: tone),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              key: noteKey,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: tone),
            ),
          ),
        ],
      );
}
