/// Phone sign-in — 2/3 §7.1, §7.3.
///
/// A phone number and a six-digit code. **ABHA is never mandatory** and there is
/// no account to create: §7.3's guest path is this path — a patient completes
/// intake with a phone number alone, and registration links it at the hospital.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../identity/auth_repository.dart';
import '../../l10n/strings.dart';
import 'hospital_screen.dart';

class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _phone = TextEditingController();
  final _code = TextEditingController();
  OtpChallenge? _challenge;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _phone.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _request() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final challenge = await ref.read(authProvider).requestCode(_phone.text.trim());
    if (!mounted) return;
    setState(() {
      _busy = false;
      _challenge = challenge;
      if (challenge == null) _error = Strings.of(context).tryAgain;
      // The mock sender returns the code so a demo with no signal can complete
      // a sign-in. Prefilling it is a convenience; the banner below says out
      // loud that nothing was actually sent, so a mocked delivery is never
      // presented as a real SMS.
      if (challenge?.code != null) _code.text = challenge!.code!;
    });
  }

  Future<void> _verify() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final result = await ref.read(authProvider).verify(
          challengeId: _challenge!.challengeId,
          code: _code.text.trim(),
        );
    if (!mounted) return;
    if (result.ok) {
      ref.invalidate(signedInProvider);
      await Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(builder: (_) => const HospitalScreen()),
      );
      return;
    }
    setState(() {
      _busy = false;
      _error = result.message;
    });
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(strings.signInTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            TextField(
              key: const Key('signin.phone'),
              controller: _phone,
              enabled: _challenge == null,
              keyboardType: TextInputType.phone,
              style: Theme.of(context).textTheme.bodyLarge,
              decoration: InputDecoration(labelText: strings.phoneLabel),
            ),
            const SizedBox(height: Sizes.gutter),
            if (_challenge == null)
              FilledButton(
                key: const Key('signin.send'),
                onPressed: _busy ? null : _request,
                child: Text(strings.sendCode),
              )
            else ...[
              if (_challenge!.isMocked)
                Padding(
                  padding: const EdgeInsets.only(bottom: Sizes.gap),
                  child: Text(
                    key: const Key('signin.mock_notice'),
                    strings.mockNotice,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
              TextField(
                key: const Key('signin.code'),
                controller: _code,
                keyboardType: TextInputType.number,
                style: Theme.of(context).textTheme.bodyLarge,
                decoration: InputDecoration(labelText: strings.codeLabel),
              ),
              const SizedBox(height: Sizes.gutter),
              FilledButton(
                key: const Key('signin.verify'),
                onPressed: _busy ? null : _verify,
                child: Text(strings.verifyCode),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: Sizes.gap),
              Text(
                key: const Key('signin.error'),
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
