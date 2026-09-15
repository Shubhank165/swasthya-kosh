import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../widgets/option_icon.dart';

/// Any stage that is a question plus a set of choices: language, who is answering, and each
/// Dashavidha question.
///
/// One screen for all three because the server already sends the same shape for each - a headline
/// and a list of `{value, label, icon}` - translated into the patient's language. The previous
/// per-stage screens each hardcoded their own Hindi and English strings, which is why choosing
/// Tamil still produced a Hindi interface: the translated text arrived and was thrown away.
///
/// Nothing here knows which stage it is drawing. That is what keeps a new question working
/// without an app release.
class ChoiceScreen extends StatefulWidget {
  const ChoiceScreen({
    super.key,
    required this.headline,
    required this.options,
    required this.onChoose,
    this.progress,
    this.onBack,
    this.onRepeat,
    this.selectedValue,
  });

  final String headline;

  /// Straight from the server: `{value, label, icon}`.
  final List<Map<String, dynamic>> options;
  final void Function(String value) onChoose;

  /// `[answered, total]` where the server counts it; null elsewhere.
  final List<int>? progress;
  final VoidCallback? onBack;
  final VoidCallback? onRepeat;
  final String? selectedValue;

  @override
  State<ChoiceScreen> createState() => _ChoiceScreenState();
}

class _ChoiceScreenState extends State<ChoiceScreen> {
  final TextEditingController _typed = TextEditingController();
  bool _typing = false;
  String? _typeError;

  @override
  void dispose() {
    _typed.dispose();
    super.dispose();
  }

  /// Resolve what the patient typed to one of the offered choices.
  ///
  /// The server validates Dashavidha answers against its own option set, so free text cannot be
  /// posted straight through - it would just come back as an error. Matching here keeps the
  /// keyboard useful (someone who reads faster than they listen can type "thin" or "3") while the
  /// answer that reaches the Jetson is still one the questionnaire defined.
  void _submitTyped() {
    final entry = _typed.text.trim().toLowerCase();
    if (entry.isEmpty) return;

    final index = int.tryParse(entry);
    if (index != null && index >= 1 && index <= widget.options.length) {
      _choose(widget.options[index - 1]);
      return;
    }

    for (final option in widget.options) {
      final label = (option['label'] as String? ?? '').toLowerCase();
      final value = (option['value'] as String? ?? '').toLowerCase();
      if (label == entry || value == entry) {
        _choose(option);
        return;
      }
    }
    for (final option in widget.options) {
      final label = (option['label'] as String? ?? '').toLowerCase();
      if (label.isNotEmpty && (label.contains(entry) || entry.contains(label))) {
        _choose(option);
        return;
      }
    }
    // Say so rather than sending something the questionnaire never offered.
    setState(() => _typeError = 'Not one of the choices - tap a picture, or type its number.');
  }

  void _choose(Map<String, dynamic> option) {
    _typed.clear();
    setState(() {
      _typing = false;
      _typeError = null;
    });
    widget.onChoose(option['value'] as String);
  }

  @override
  Widget build(BuildContext context) {
    final showProgress = widget.progress != null && widget.progress!.length == 2 && widget.progress![1] > 0;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 2),
          child: Row(
            children: [
              if (widget.onBack != null)
                IconButton(
                  onPressed: widget.onBack,
                  icon: const Icon(Icons.arrow_back_ios_new, size: 22),
                  tooltip: 'Back',
                ),
              if (showProgress)
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: LinearProgressIndicator(
                        value: widget.progress![0] / widget.progress![1],
                        minHeight: 10,
                        backgroundColor: AppTheme.warningOrange.withValues(alpha: 0.15),
                      ),
                    ),
                  ),
                )
              else
                const Spacer(),
              // A patient who cannot read has only the spoken question, so replaying it is a
              // primary control rather than something buried in a menu.
              if (widget.onRepeat != null)
                IconButton(
                  onPressed: widget.onRepeat,
                  icon: const Icon(Icons.volume_up, size: 26),
                  tooltip: 'Repeat the question',
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 6),
          child: Text(
            widget.headline,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 25, fontWeight: FontWeight.w600, height: 1.3),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
          child: Wrap(
              alignment: WrapAlignment.center,
              spacing: 12,
              runSpacing: 12,
              children: [
                if (widget.options.isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 40),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: const [
                        CircularProgressIndicator(color: AppTheme.accentCyan),
                        SizedBox(height: 16),
                        Text(
                          'Connecting to Jetson Orin Nano...\nPlease wait or verify server host',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: AppTheme.textSecondary, fontSize: 14),
                        ),
                      ],
                    ),
                  )
                else
                  for (var i = 0; i < widget.options.length; i++)
                    SizedBox(
                      width: widget.options.length > 6 ? 158 : 190,
                      child: IconOptionCard(
                        icon: widget.options[i]['icon'] as String? ?? 'circle',
                        label: widget.options[i]['label'] as String? ?? '',
                        index: i + 1,
                        selected: widget.selectedValue == widget.options[i]['value'],
                        onTap: () => _choose(widget.options[i]),
                      ),
                  ),
              ],
            ),
          ),
        // Keyboard, offered second. The pictures come first because the kiosk is built for
        // patients who cannot read, but someone literate and in a hurry should not be forced to
        // listen to nine options before answering.
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: _typing ? _typeBox(context) : Align(
            alignment: Alignment.center,
            child: TextButton.icon(
              onPressed: () => setState(() => _typing = true),
              icon: const Icon(Icons.keyboard, size: 22),
              label: const Text('Type instead', style: TextStyle(fontSize: 16)),
            ),
          ),
        ),
      ],
    );
  }

  Widget _typeBox(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 420,
          child: TextField(
            controller: _typed,
            autofocus: true,
            textInputAction: TextInputAction.done,
            style: const TextStyle(fontSize: 18),
            decoration: InputDecoration(
              labelText: 'Type your answer, or its number',
              errorText: _typeError,
              border: const OutlineInputBorder(),
              suffixIcon: IconButton(
                icon: const Icon(Icons.send),
                onPressed: _submitTyped,
                tooltip: 'Send',
              ),
            ),
            onChanged: (_) {
              if (_typeError != null) setState(() => _typeError = null);
            },
            onSubmitted: (_) => _submitTyped(),
          ),
        ),
        TextButton(
          onPressed: () => setState(() {
            _typing = false;
            _typeError = null;
          }),
          child: const Text('Close keyboard'),
        ),
      ],
    );
  }
}
