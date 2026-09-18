/// The language chooser — 2/3 §5 screen 1, stage 4, revised in stage 5.
///
/// Language comes first, before anything else is shown. A patient who cannot
/// read the sign-in screen cannot sign in, and the nine-language chooser is the
/// one thing that must be legible without reading.
///
/// **It is shown once, not on every launch.** It used to be the app's home
/// screen and carried the continue button, the resume prompt, the update notice
/// and sign-out with it — so a patient who had already answered "English" three
/// times was asked a fourth. The choice is remembered (`LanguageStore`) and this
/// screen appears on a first run, or when the patient opens it from their
/// profile to change the answer.
///
/// **Tap now selects; Continue commits — and this reverses an earlier
/// decision.** Tapping used to *be* the answer, on the reasoning that a Continue
/// button did nothing a second tap could not: nine buttons followed by a tenth
/// to confirm which of the nine you meant. That reasoning missed what happens
/// when the tap is wrong. Committing instantly re-renders the entire app in a
/// script the patient may not read, with no confirmation step and nothing on
/// screen they can now navigate by — and mistaps are commonest among exactly
/// the elderly patients this screen exists for. Selecting shows a tick they can
/// check and move, in a list still rendered in whatever they could read a moment
/// ago; Continue is one extra tap and is the cheapest undo in the app.
///
/// **The search box is not decoration.** Nine scripts is past the point where a
/// patient scans reliably, and a relative helping them may know only the Latin
/// name. It matches both, so "tam", "தமிழ்" and "Tamil" all find the same row.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import '../../l10n/strings.dart';

/// Endonyms — each language named in its own script.
///
/// "Hindi" written in Latin script is no help to somebody who reads only
/// Devanagari, which is exactly the person this list exists for.
const languageNames = {
  'en': 'English',
  'hi': 'हिन्दी',
  'bn': 'বাংলা',
  'ta': 'தமிழ்',
  'te': 'తెలుగు',
  'mr': 'मराठी',
  'gu': 'ગુજરાતી',
  'kn': 'ಕನ್ನಡ',
  'pa': 'ਪੰਜਾਬੀ',
};

/// The same nine in Latin script, as a *second* line only.
///
/// Never the first: the endonym is what the patient recognises. This line is
/// for the relative or the registration clerk helping them, who may read Latin
/// script and none of the other eight — and for whom "ਪੰਜਾਬੀ" is a shape.
const _languageLatinNames = {
  'en': 'English',
  'hi': 'Hindi',
  'bn': 'Bangla',
  'ta': 'Tamil',
  'te': 'Telugu',
  'mr': 'Marathi',
  'gu': 'Gujarati',
  'kn': 'Kannada',
  'pa': 'Punjabi',
};

class LanguageScreen extends ConsumerStatefulWidget {
  const LanguageScreen({super.key, this.returnWhenChosen = false});

  /// True when opened from the profile, where choosing means "go back".
  ///
  /// False on a first run, where there is nothing to go back to — the app
  /// itself is waiting on the answer, and popping would leave a black screen.
  final bool returnWhenChosen;

  @override
  ConsumerState<LanguageScreen> createState() => _LanguageScreenState();
}

class _LanguageScreenState extends ConsumerState<LanguageScreen> {
  final _search = TextEditingController();

  /// What the patient has tapped but not yet confirmed.
  ///
  /// Null until they tap. Seeded in [initState] from the language already in
  /// force, so re-opening this screen from the profile shows the current answer
  /// ticked rather than nothing.
  String? _selected;

  @override
  void initState() {
    super.initState();
    _selected = ref.read(languageProvider);
    _search.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// Rows matching what has been typed, by endonym or by Latin name.
  ///
  /// Case-folded on the Latin side only: `toLowerCase` is a no-op for the eight
  /// Indic scripts here, which have no case, and applying it is harmless.
  Iterable<MapEntry<String, String>> get _visible {
    final query = _search.text.trim().toLowerCase();
    if (query.isEmpty) return languageNames.entries;
    return languageNames.entries.where((entry) {
      final latin = (_languageLatinNames[entry.key] ?? '').toLowerCase();
      return entry.value.toLowerCase().contains(query) || latin.contains(query);
    });
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final colors = Theme.of(context).colorScheme;

    // What the phone is set to. Marked, never pre-committed: it is a guess and
    // `languageProvider` documents it as one.
    final deviceLanguage =
        WidgetsBinding.instance.platformDispatcher.locale.languageCode;

    final rows = _visible.toList();

    return Scaffold(
      appBar: AppBar(
        title: widget.returnWhenChosen ? Text(strings.profileLanguage) : null,
      ),
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
          color: Colors.white,
          boxShadow: [
            BoxShadow(
              color: Color(0x141B5E4A),
              blurRadius: 20,
              offset: Offset(0, -6),
            ),
          ],
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: FilledButton.icon(
              key: const Key('language.continue'),
              // Never disabled: `_selected` is seeded with the language already
              // in force, so there is always something to confirm. A greyed-out
              // primary button on the app's first screen reads as a broken app.
              onPressed: () => _commit(_selected ?? ref.read(languageProvider)),
              icon: const Icon(Icons.arrow_forward),
              iconAlignment: IconAlignment.end,
              label: Text(strings.continueLabel),
            ),
          ),
        ),
      ),
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
                title: strings.chooseLanguage,
                body: strings.changeLanguageAnytime,
              ),
              const SizedBox(height: Sizes.gutter),
              TextField(
                key: const Key('language.search'),
                controller: _search,
                textInputAction: TextInputAction.search,
                style: Theme.of(context).textTheme.bodyLarge,
                decoration: InputDecoration(
                  hintText: strings.searchLanguage,
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: _search.text.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.close),
                          onPressed: () => _search.clear(),
                        ),
                ),
              ),
              const SizedBox(height: Sizes.gutter),
              if (rows.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: Sizes.gutter),
                  child: Text(
                    strings.tryAgain,
                    key: const Key('language.noMatch'),
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: colors.onSurfaceVariant,
                        ),
                  ),
                ),
              for (final entry in rows)
                Padding(
                  padding: const EdgeInsets.only(bottom: Sizes.gap),
                  child: _LanguageRow(
                    // The key stays on the tappable surface, where the journey
                    // test taps it.
                    rowKey: Key('language.${entry.key}'),
                    code: entry.key,
                    endonym: entry.value,
                    latin: _languageLatinNames[entry.key],
                    selected: _selected == entry.key,
                    // One badge at most, on the row the phone itself suggests.
                    // Not "most used": this app collects no usage figures and a
                    // label implying it does is a claim nobody can check.
                    badge: entry.key == deviceLanguage
                        ? strings.languageOnThisPhone
                        : null,
                    onTap: () => setState(() => _selected = entry.key),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _commit(String code) async {
    ref.read(languageProvider.notifier).state = code;
    await ref.read(languageStoreProvider).write(code);
    ref.invalidate(storedLanguageProvider);
    if (widget.returnWhenChosen && mounted) Navigator.of(context).pop();
  }
}

/// One language: its script's initial in a chip, the endonym, the Latin name.
class _LanguageRow extends StatelessWidget {
  const _LanguageRow({
    required this.rowKey,
    required this.code,
    required this.endonym,
    required this.selected,
    required this.onTap,
    this.latin,
    this.badge,
  });

  final Key rowKey;
  final String code;
  final String endonym;
  final String? latin;
  final bool selected;
  final String? badge;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;

    // The script's own first character, which makes nine rows distinguishable
    // at a glance without nine invented icons. `runes`, so a code point outside
    // the BMP is not split in half.
    final initial = String.fromCharCode(endonym.runes.first);

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Sizes.radius),
        boxShadow: selected ? null : softShadow,
      ),
      child: Material(
        color: selected ? Palette.tint : Colors.white,
        borderRadius: BorderRadius.circular(Sizes.radius),
        child: InkWell(
          key: rowKey,
          onTap: onTap,
          borderRadius: BorderRadius.circular(Sizes.radius),
          child: Container(
            constraints: const BoxConstraints(minHeight: Sizes.actionHeight + 10),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(Sizes.radius),
              border: Border.all(
                color: selected ? colors.primary : Colors.transparent,
                width: 2,
              ),
            ),
            child: Row(
              children: [
                Container(
                  width: Sizes.chip,
                  height: Sizes.chip,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: selected ? Colors.white : Palette.tint,
                    borderRadius: BorderRadius.circular(Sizes.chip * 0.3),
                  ),
                  child: Text(
                    initial,
                    style: text.titleMedium?.copyWith(color: colors.primary),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(endonym, style: text.titleMedium),
                      if (latin != null && latin != endonym) ...[
                        const SizedBox(height: 2),
                        Text(
                          latin!,
                          style: text.bodySmall?.copyWith(
                            color: colors.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (badge != null) ...[
                  Flexible(
                    child: Text(
                      badge!,
                      textAlign: TextAlign.end,
                      style: text.bodySmall?.copyWith(color: colors.primary),
                    ),
                  ),
                  const SizedBox(width: 8),
                ],
                // Never colour alone — the shape changes too.
                Icon(
                  selected ? Icons.check_circle : Icons.circle_outlined,
                  color: selected ? colors.primary : Palette.tintStrong,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
