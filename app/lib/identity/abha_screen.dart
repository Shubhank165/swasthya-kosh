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
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
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
    return Scaffold(
      appBar: AppBar(title: Text(strings.abhaTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            Text(strings.abhaExplanation, style: Theme.of(context).textTheme.bodyLarge),
            const SizedBox(height: Sizes.gutter),
            TextField(
              key: const Key('abha.address'),
              controller: _address,
              autocorrect: false,
              // §1 rule 8: nothing here invites dictation. This is an
              // identifier, not a clinical field, but the habit is the point.
              keyboardType: TextInputType.emailAddress,
              decoration: InputDecoration(labelText: strings.abhaAddressLabel),
            ),
            if (_notFound) ...[
              const SizedBox(height: Sizes.gap),
              Text(
                strings.abhaNotFound,
                key: const Key('abha.notFound'),
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
            if (_mocked) ...[
              const SizedBox(height: Sizes.gap),
              Text(
                strings.mockNotice,
                key: const Key('abha.mockNotice'),
                style: Theme.of(context).textTheme.bodyMedium,
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
              child: Text(strings.continueLabel),
            ),
          ],
        ),
      ),
    );
  }
}
