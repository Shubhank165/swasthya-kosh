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
import '../../core/ui.dart';
import '../../identity/auth_repository.dart';
import '../../l10n/strings.dart';

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
          // Passed so the Profile tab can show the number the session was
          // issued against. The backend stores a peppered HMAC (§7.1) and
          // could not send the digits back if it wanted to, so this screen is
          // the only place they can be kept.
          phone: _phone.text.trim(),
        );
    if (!mounted) return;
    if (result.ok) {
      // Invalidating is the whole navigation. `Root` renders this screen
      // because nobody is signed in; once that is no longer true it renders
      // the home shell instead.
      //
      // This used to push the hospital picker, which dropped a patient who
      // had just signed in straight into the first step of a new visit — past
      // their own visits, documents and profile, with the only way back being
      // the system back gesture. Signing in is not the same act as starting a
      // visit, and the home screen is where a patient decides which one they
      // came for.
      ref.invalidate(signedInProvider);
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
    final colors = Theme.of(context).colorScheme;
    final awaitingCode = _challenge != null;

    return Scaffold(
      body: Garnish(
        child: SafeArea(
          child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            const SizedBox(height: Sizes.gutter),
            const Center(child: EmblemMark(icon: Icons.sms_outlined, size: 108)),
            const SizedBox(height: Sizes.gutter),
            ScreenIntro(
              title: strings.signInTitle,
              // Two sentences, and which one shows depends on where the patient
              // is. "We sent a code" before it has been sent is the kind of
              // small lie that makes someone wait for an SMS that is not
              // coming.
              body: awaitingCode ? strings.signInCodeSent : strings.signInSubtitle,
            ),
            const SizedBox(height: Sizes.gutter),
            TextField(
              key: const Key('signin.phone'),
              controller: _phone,
              enabled: _challenge == null,
              keyboardType: TextInputType.phone,
              style: Theme.of(context).textTheme.bodyLarge,
              decoration: InputDecoration(
                labelText: strings.phoneLabel,
                prefixIcon: const Icon(Icons.phone_outlined),
              ),
            ),
            const SizedBox(height: Sizes.gutter),
            if (_challenge == null)
              FilledButton(
                key: const Key('signin.send'),
                onPressed: _busy ? null : _request,
                child: _busy
                    ? const _ButtonSpinner()
                    : Text(strings.sendCode),
              )
            else ...[
              if (_challenge!.isMocked)
                Padding(
                  padding: const EdgeInsets.only(bottom: Sizes.gap),
                  child: _Notice(
                    noticeKey: const Key('signin.mock_notice'),
                    icon: Icons.info_outline,
                    text: strings.mockNotice,
                    tone: colors.error,
                  ),
                ),
              TextField(
                key: const Key('signin.code'),
                controller: _code,
                keyboardType: TextInputType.number,
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                      letterSpacing: 6,
                      fontWeight: FontWeight.w600,
                    ),
                decoration: InputDecoration(
                  labelText: strings.codeLabel,
                  prefixIcon: const Icon(Icons.lock_outline),
                ),
              ),
              const SizedBox(height: Sizes.gutter),
              FilledButton(
                key: const Key('signin.verify'),
                onPressed: _busy ? null : _verify,
                child: _busy
                    ? const _ButtonSpinner()
                    : Text(strings.verifyCode),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: Sizes.gap),
              _Notice(
                noticeKey: const Key('signin.error'),
                icon: Icons.error_outline,
                text: _error!,
                tone: colors.error,
              ),
            ],
            const SizedBox(height: Sizes.gutter),
            PrivacyNote(text: strings.dataProtected),
          ],
          ),
        ),
      ),
    );
  }
}

/// A short coloured line with an icon, for the two things this screen has to
/// say that are not labels: the demo-mode notice and an error.
///
/// The key is passed through to the *text*, because both notices are asserted
/// on by key in `screens_test.dart` and a key on a wrapper would still be found
/// but would no longer point at the string being checked.
class _Notice extends StatelessWidget {
  const _Notice({
    required this.noticeKey,
    required this.icon,
    required this.text,
    required this.tone,
  });

  final Key noticeKey;
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
              key: noticeKey,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: tone),
            ),
          ),
        ],
      );
}

class _ButtonSpinner extends StatelessWidget {
  const _ButtonSpinner();

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 22,
        height: 22,
        child: CircularProgressIndicator(
          strokeWidth: 2.5,
          color: Theme.of(context).colorScheme.onPrimary,
        ),
      );
}
