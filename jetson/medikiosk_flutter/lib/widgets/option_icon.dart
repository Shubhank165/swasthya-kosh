import 'package:flutter/material.dart';

/// Draws the picture for one answer choice.
///
/// The kiosk is used by people who cannot read. For them the icon *is* the question - the label
/// underneath only confirms a choice they already made from the picture. So every option the
/// server sends carries an `icon` name, and this maps that name to a symbol.
///
/// Icon names come from the server rather than being decided here, so the tablet, the browser and
/// the 2.8 inch panel all show the same symbol for the same answer. An unknown name falls back to
/// a numbered circle rather than an empty box: a patient can still be told "press the second one".
class OptionIcon extends StatelessWidget {
  const OptionIcon({
    super.key,
    required this.name,
    required this.index,
    this.size = 56,
    this.color,
  });

  final String name;
  final int index;
  final double size;
  final Color? color;

  /// Server icon name -> glyph. Material icons are used deliberately: they are already drawn in a
  /// consistent weight, they scale, and they need no asset pipeline or licence review.
  static const Map<String, IconData> _glyphs = {
    // Who is answering
    'person_one': Icons.person,
    'person_two': Icons.people,

    // Body build
    'body_thin': Icons.accessibility,
    'body_medium': Icons.accessibility_new,
    'body_heavy': Icons.emoji_people,

    // Skin
    'skin_dry': Icons.grain,
    'skin_warm': Icons.local_fire_department,
    'skin_soft': Icons.water_drop,

    // Sleep
    'sleep_light': Icons.bedtime_off,
    'sleep_moderate': Icons.bedtime,
    'sleep_deep': Icons.nights_stay,

    // Weather that troubles the patient
    'weather_cold': Icons.ac_unit,
    'weather_hot': Icons.wb_sunny,
    'weather_damp': Icons.water,

    // Response to stress
    'mood_anxious': Icons.sentiment_very_dissatisfied,
    'mood_angry': Icons.mood_bad,
    'mood_quiet': Icons.sentiment_neutral,

    // Appetite and digestion
    'appetite_strong': Icons.restaurant,
    'appetite_moderate': Icons.restaurant_menu,
    'appetite_irregular': Icons.schedule,
    'appetite_poor': Icons.no_meals,

    // Physical exertion tolerated
    'exertion_high': Icons.directions_run,
    'exertion_moderate': Icons.directions_walk,
    'exertion_low': Icons.airline_seat_recline_normal,

    // Usual diet
    'diet_veg': Icons.eco,
    'diet_mixed': Icons.set_meal,
    'diet_irregular': Icons.more_time,

    // Yes / no
    'yes': Icons.check_circle,
    'no': Icons.cancel,
  };

  /// Languages are shown in their own script, which is itself the icon - a patient recognises
  /// their own writing without reading English. A generic glyph would carry less information.
  static bool isLanguage(String name) => name.startsWith('lang_');

  @override
  Widget build(BuildContext context) {
    final tint = color ?? Theme.of(context).colorScheme.primary;
    final glyph = _glyphs[name];
    if (glyph != null) {
      return Icon(glyph, size: size, color: tint);
    }
    // Unknown or language icon: a big number, so the option can still be referred to aloud.
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: tint, width: 3)),
      child: Text(
        '$index',
        style: TextStyle(fontSize: size * 0.5, fontWeight: FontWeight.bold, color: tint),
      ),
    );
  }
}

/// A single large, tappable answer: picture on top, words underneath.
///
/// Sized for a finger on a kiosk that people approach standing up, and for a patient who may be
/// elderly, in pain, or holding a child. The number in the corner matches what the kiosk says
/// aloud, so a helper can say "press three" over the phone.
class IconOptionCard extends StatelessWidget {
  const IconOptionCard({
    super.key,
    required this.icon,
    required this.label,
    required this.index,
    required this.onTap,
    this.selected = false,
  });

  final String icon;
  final String label;
  final int index;
  final VoidCallback onTap;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      button: true,
      label: label,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Container(
          constraints: const BoxConstraints(minHeight: 132, minWidth: 132),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
          decoration: BoxDecoration(
            color: selected ? scheme.primary.withValues(alpha: 0.16) : scheme.surface,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: selected ? scheme.primary : scheme.outlineVariant,
              width: selected ? 3 : 2,
            ),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '$index',
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: scheme.outline,
                    ),
                  ),
                  if (selected) Icon(Icons.check_circle, color: scheme.primary, size: 22),
                ],
              ),
              OptionIcon(name: icon, index: index, size: 52),
              const SizedBox(height: 10),
              Text(
                label,
                textAlign: TextAlign.center,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 17, height: 1.25),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
