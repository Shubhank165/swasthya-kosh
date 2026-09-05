/// Consent — 2/3 §11.
///
/// **Layered, and each grant is a separate explicit action.** One checkbox
/// covering "collect, share, store, link to ABHA and use for research" is not
/// consent under the DPDP Act 2023 and is not consent in any ordinary sense
/// either; a patient must be able to agree to being treated without agreeing to
/// their data being used to improve a product.
///
/// **Audio playback stays available even though this app is touch-only.** This
/// is the one place audio is warranted, and it is *output*, never input: a
/// literate app user may still be an elderly relative filling the form for
/// someone else, and consent is the screen where not understanding matters
/// most.
library;

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';

import '../core/theme.dart';
import '../l10n/strings.dart';

/// One thing the patient is being asked to agree to.
class ConsentPurpose {
  const ConsentPurpose({
    required this.code,
    required this.text,
    required this.required,
  });

  final String code;
  final String text;

  /// Required purposes gate the intake; optional ones default to **off** and
  /// never gate anything (§11).
  final bool required;
}

class ConsentScreen extends StatefulWidget {
  const ConsentScreen({
    super.key,
    required this.purposes,
    required this.language,
    required this.onGranted,
    this.speaker,
  });

  final List<ConsentPurpose> purposes;
  final String language;

  /// Called with the codes the patient granted.
  final void Function(Set<String> granted) onGranted;

  /// Injectable so widget tests do not reach a platform channel.
  final FlutterTts? speaker;

  @override
  State<ConsentScreen> createState() => _ConsentScreenState();
}

class _ConsentScreenState extends State<ConsentScreen> {
  final _granted = <String>{};
  FlutterTts? _tts;
  bool _speaking = false;

  @override
  void initState() {
    super.initState();
    // Required purposes start **unticked**. Pre-ticking them would make the
    // patient's action a dismissal rather than a grant, which is the thing
    // §11's "separate, explicit action" wording exists to prevent.
    _tts = widget.speaker;
  }

  @override
  void dispose() {
    _tts?.stop();
    super.dispose();
  }

  bool get _canProceed => widget.purposes
      .where((p) => p.required)
      .every((p) => _granted.contains(p.code));

  Future<void> _speak(String text) async {
    final tts = _tts ??= FlutterTts();
    if (_speaking) {
      await tts.stop();
      if (mounted) setState(() => _speaking = false);
      return;
    }
    setState(() => _speaking = true);
    await tts.setLanguage(widget.language);
    await tts.speak(text);
    if (mounted) setState(() => _speaking = false);
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final required = widget.purposes.where((p) => p.required).toList();
    final optional = widget.purposes.where((p) => !p.required).toList();

    return Scaffold(
      appBar: AppBar(title: Text(strings.consentTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            _heading(context, strings.consentRequiredHeading),
            for (final purpose in required) _tile(purpose),
            const SizedBox(height: Sizes.gutter),
            _heading(context, strings.consentOptionalHeading),
            for (final purpose in optional) _tile(purpose),
            const SizedBox(height: Sizes.gutter),
            FilledButton(
              key: const Key('consent.continue'),
              onPressed: _canProceed
                  ? () => widget.onGranted(Set.unmodifiable(_granted))
                  : null,
              child: Text(strings.continueLabel),
            ),
          ],
        ),
      ),
    );
  }

  Widget _heading(BuildContext context, String text) => Padding(
        padding: const EdgeInsets.only(bottom: Sizes.gap),
        child: Semantics(
          header: true,
          child: Text(text, style: Theme.of(context).textTheme.labelLarge),
        ),
      );

  Widget _tile(ConsentPurpose purpose) {
    final strings = Strings.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: Sizes.gap),
      child: Padding(
        padding: const EdgeInsets.all(Sizes.gap),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(purpose.text, style: Theme.of(context).textTheme.bodyLarge),
            const SizedBox(height: Sizes.gap),
            Row(
              children: [
                // Output only. There is no counterpart button that listens.
                TextButton.icon(
                  key: Key('consent.listen.${purpose.code}'),
                  onPressed: () => _speak(purpose.text),
                  icon: Icon(_speaking ? Icons.stop : Icons.volume_up),
                  label: Text(_speaking ? strings.stopListening : strings.listenToThis),
                ),
                const Spacer(),
                Switch(
                  key: Key('consent.switch.${purpose.code}'),
                  value: _granted.contains(purpose.code),
                  onChanged: (on) => setState(() {
                    if (on) {
                      _granted.add(purpose.code);
                    } else {
                      _granted.remove(purpose.code);
                    }
                  }),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
