/// Shared presentation widgets — 2/3 §14.
///
/// Every widget here was a copy-pasted `Container` on two or more screens
/// before it was a class. That is the whole bar for adding one: a thing that
/// appears twice and must not drift, not a thing that might be reused one day.
///
/// **None of these decide anything.** They take what to show and a callback,
/// and they have no access to providers, no navigation and no clinical
/// vocabulary. A widget in this file cannot record an answer, cannot know a
/// question's status, and cannot tell "I don't know" from "Skip" — which is the
/// property that keeps §4's distinction living in `answer_actions.dart` where
/// it is documented, rather than leaking into a shared row that renders both.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'theme.dart';

/// The headline block a screen opens with.
///
/// Marked as a header for assistive technology in one place, because the three
/// screens that hand-rolled this had it right twice.
class ScreenIntro extends StatelessWidget {
  const ScreenIntro({
    super.key,
    required this.title,
    this.body,
    this.align = TextAlign.start,
  });

  final String title;
  final String? body;
  final TextAlign align;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: align == TextAlign.center
          ? CrossAxisAlignment.center
          : CrossAxisAlignment.start,
      children: [
        Semantics(
          header: true,
          child: Text(title, textAlign: align, style: text.headlineMedium),
        ),
        if (body != null) ...[
          const SizedBox(height: Sizes.gap),
          Text(
            body!,
            textAlign: align,
            style: text.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ],
    );
  }
}

/// A white surface on the app's one shadow.
///
/// The base of every card-shaped thing here. It takes no border: on a tinted
/// page the shadow is what separates it, and adding a hairline as well is how a
/// screen ends up looking like a form.
class SoftCard extends StatelessWidget {
  const SoftCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(Sizes.gutter),
    this.color = Colors.white,
    this.borderColor,
    this.radius = Sizes.radius,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color color;

  /// Only for a selected state, which needs to survive a screenshot, a
  /// greyscale printout and deuteranopia. Null everywhere else.
  final Color? borderColor;
  final double radius;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: padding,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(radius),
          boxShadow: softShadow,
          border: borderColor == null
              ? null
              : Border.all(color: borderColor!, width: 2),
        ),
        child: child,
      );
}

/// A pale rounded surface used to group things.
///
/// Decoration only. It carries no state and means nothing clinically — see the
/// note on [Palette.tint]. No shadow: this one is a recess, not a card.
class TintPanel extends StatelessWidget {
  const TintPanel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(Sizes.gutter),
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: padding,
        decoration: BoxDecoration(
          color: Palette.tint,
          borderRadius: BorderRadius.circular(Sizes.radiusLarge),
        ),
        child: child,
      );
}

/// The rounded mint square an icon sits in.
///
/// Every list row in this app has one, at one size, in one colour. An icon
/// floating loose in a row reads as decoration; an icon in a chip reads as the
/// row's subject, and the chip is what makes nine rows scan as a list rather
/// than as nine paragraphs.
class IconChip extends StatelessWidget {
  const IconChip({
    super.key,
    required this.icon,
    this.background,
    this.foreground,
    this.size = Sizes.chip,
  });

  final IconData icon;
  final Color? background;
  final Color? foreground;
  final double size;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: background ?? Palette.tint,
          borderRadius: BorderRadius.circular(size * 0.3),
        ),
        child: Icon(
          icon,
          size: size * 0.52,
          color: foreground ?? Theme.of(context).colorScheme.primary,
        ),
      );
}

/// One tappable row in a list the patient is choosing from.
///
/// **The selected state is not colour alone.** A filled tick sits at the end of
/// the chosen row as well as the tint behind it and a heavier border around it,
/// because a patient with deuteranopia reading a pale green row against a white
/// one is being asked to see a difference they cannot. §14.
class ChoiceRow extends StatelessWidget {
  const ChoiceRow({
    super.key,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.icon,
    this.selected = false,
    this.rowKey,
  });

  final String title;
  final String? subtitle;
  final IconData? icon;
  final bool selected;
  final VoidCallback? onTap;

  /// Kept as a field rather than the widget's own `key` so a test can find the
  /// tappable surface, which is what it actually taps.
  final Key? rowKey;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
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
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(Sizes.radius),
              border: Border.all(
                color: selected ? colors.primary : Colors.transparent,
                width: 2,
              ),
            ),
            child: Row(
              children: [
                if (icon != null) ...[
                  IconChip(
                    icon: icon!,
                    background: selected ? Colors.white : Palette.tint,
                  ),
                  const SizedBox(width: 14),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(title, style: text.titleMedium),
                      if (subtitle != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          subtitle!,
                          style: text.bodySmall?.copyWith(
                            color: colors.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 10),
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

/// A card that starts something: icon, what it is, what it does, chevron.
class ActionTile extends StatelessWidget {
  const ActionTile({
    super.key,
    required this.icon,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.tileKey,
    this.prominent = false,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;
  final Key? tileKey;

  /// The one action the screen expects. Filled rather than white, so a patient
  /// who reads nothing still knows where to press.
  ///
  /// At most one per screen. Two prominent cards is none.
  final bool prominent;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final disabled = onTap == null;
    final filled = prominent && !disabled;

    final foreground = disabled
        ? colors.onSurfaceVariant
        : filled
            ? Colors.white
            : colors.onSurface;
    final background = disabled
        ? Palette.tint
        : filled
            ? colors.primary
            : Colors.white;

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Sizes.radius),
        boxShadow: disabled ? null : softShadow,
      ),
      child: Material(
        color: background,
        borderRadius: BorderRadius.circular(Sizes.radius),
        child: InkWell(
          key: tileKey,
          onTap: onTap,
          borderRadius: BorderRadius.circular(Sizes.radius),
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: Row(
              children: [
                IconChip(
                  icon: icon,
                  background: filled ? Colors.white24 : Palette.tint,
                  foreground: filled ? Colors.white : colors.primary,
                ),
                const SizedBox(width: Sizes.gap + 2),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        style: text.titleMedium?.copyWith(color: foreground),
                      ),
                      if (subtitle != null) ...[
                        const SizedBox(height: 3),
                        Text(
                          subtitle!,
                          style: text.bodySmall?.copyWith(
                            color: filled
                                ? Colors.white.withAlpha(220)
                                : colors.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                Icon(Icons.chevron_right, color: foreground),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// How far through a run of questions the patient is.
///
/// **Sections and counts, never a percentage.** A percentage implies a
/// precision the branching does not have: answering "chest pain" adds twenty
/// questions and would make progress go backwards. The bar is a rough shape;
/// the label beside it is the honest number, and it is the one a patient reads.
class StepProgress extends StatelessWidget {
  const StepProgress({
    super.key,
    required this.label,
    required this.done,
    required this.total,
  });

  final String label;
  final int done;
  final int total;

  @override
  Widget build(BuildContext context) {
    final value = total <= 0 ? 0.0 : (done / total).clamp(0.0, 1.0);
    return Semantics(
      // The bar is decoration; this sentence is what a screen reader announces.
      label: label,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(value: value),
          ),
          const SizedBox(height: 8),
          ExcludeSemantics(
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The quiet reassurance line, with its padlock.
class PrivacyNote extends StatelessWidget {
  const PrivacyNote({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(Icons.lock_outline, size: 18, color: colors.onSurfaceVariant),
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            text,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: colors.onSurfaceVariant,
                ),
          ),
        ),
      ],
    );
  }
}

/// The decorative emblem on the screens that open a flow.
///
/// Drawn, not an asset. The APK already carries 240 MB of speech models and an
/// illustration would have to exist in the repo, be licensed, and be legible at
/// 200% text scale; three circles and an icon are none of those problems.
class EmblemMark extends StatelessWidget {
  const EmblemMark({
    super.key,
    required this.icon,
    this.size = 132,
    this.color,
  });

  final IconData icon;
  final double size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final tone = color ?? Theme.of(context).colorScheme.primary;
    return ExcludeSemantics(
      child: SizedBox(
        width: size,
        height: size,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Container(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: tone.withAlpha(18),
              ),
            ),
            Container(
              width: size * 0.72,
              height: size * 0.72,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: tone.withAlpha(34),
              ),
            ),
            Icon(icon, size: size * 0.36, color: tone),
          ],
        ),
      ),
    );
  }
}

/// Soft botanical accents behind a screen's content.
///
/// The reference designs carry a leaf motif in the corners, which is doing real
/// work: it is what makes a clinical form read as an AYUSH one without a single
/// word of branding. Drawn from `Icons.eco` at low alpha rather than shipped as
/// artwork, for the same reason [EmblemMark] is.
///
/// Wrap a screen's body: `Garnish(child: ...)`. It is `IgnorePointer` and
/// `ExcludeSemantics` throughout, so nothing here can catch a tap meant for the
/// content or be read out to somebody who cannot see it.
class Garnish extends StatelessWidget {
  const Garnish({super.key, required this.child, this.dense = false});

  final Widget child;

  /// More leaves, for the near-empty screens (welcome, submitted) where the
  /// page would otherwise be white space.
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final tone = Theme.of(context).colorScheme.primary;
    return Stack(
      children: [
        Positioned(
          top: -30,
          right: -40,
          child: _Leaf(size: 190, tone: tone, turns: -0.1, alpha: 14),
        ),
        Positioned(
          bottom: -50,
          left: -55,
          child: _Leaf(size: 220, tone: tone, turns: 0.35, alpha: 12),
        ),
        if (dense)
          Positioned(
            top: 150,
            left: -30,
            child: _Leaf(size: 110, tone: tone, turns: 0.6, alpha: 10),
          ),
        child,
      ],
    );
  }
}

class _Leaf extends StatelessWidget {
  const _Leaf({
    required this.size,
    required this.tone,
    required this.turns,
    required this.alpha,
  });

  final double size;
  final Color tone;
  final double turns;
  final int alpha;

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: ExcludeSemantics(
          child: Transform.rotate(
            angle: turns * 2 * math.pi,
            child: Icon(Icons.eco, size: size, color: tone.withAlpha(alpha)),
          ),
        ),
      );
}

/// What a tab shows when the patient has nothing in it yet.
///
/// **An empty tab is not an error, and it is not a dead end either.** Both
/// mistakes were live here: the tabs used to render one grey sentence in the
/// middle of a white screen, which reads as something having gone wrong, and
/// offered nothing to do about it. So: a mark, the plain fact, one line saying
/// what would fill it, and the action that does.
///
/// Stays a `ListView` rather than a `Center`, because these tabs sit inside a
/// `RefreshIndicator` and pull-to-refresh needs something scrollable to pull.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.body,
    this.action,
    this.titleKey,
  });

  final IconData icon;
  final String title;
  final String? body;
  final Widget? action;

  /// Goes on the title text, which is the string the tab's tests look for.
  final Key? titleKey;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.symmetric(
        horizontal: Sizes.gutter,
        vertical: Sizes.gutter * 2,
      ),
      children: [
        const SizedBox(height: Sizes.gutter),
        Center(child: EmblemMark(icon: icon, size: 126)),
        const SizedBox(height: Sizes.gutter),
        Text(
          title,
          key: titleKey,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleLarge,
        ),
        if (body != null) ...[
          const SizedBox(height: Sizes.gap),
          Text(
            body!,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: colors.onSurfaceVariant,
                ),
          ),
        ],
        if (action != null) ...[
          const SizedBox(height: Sizes.gutter * 1.5),
          action!,
        ],
      ],
    );
  }
}

/// The avatar-and-greeting strip at the top of a tab.
///
/// **It takes the name rather than reading one**, like everything else in this
/// file — the store it would come from is device-local and the caller owns that
/// decision. `name` is null far more often than not: a patient who has set
/// nothing gets [fallback], and nothing here invents a name to fill the space.
///
/// The avatar is the first letter when there is a name and a generic mark when
/// there is not. No photograph: this app holds none, and a placeholder face
/// would imply it could.
class GreetingHeader extends StatelessWidget {
  const GreetingHeader({
    super.key,
    required this.greeting,
    required this.fallback,
    required this.subtitle,
    this.name,
    this.trailing,
  });

  /// Already interpolated by the caller, e.g. "Hi, Mansi".
  final String greeting;

  /// Shown instead when [name] is null.
  final String fallback;
  final String subtitle;
  final String? name;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    // `runes`, not `[0]`: a UTF-16 index splits anything outside the BMP, and
    // `characters` would pull in a package this file does not declare. A code
    // point is right for every script the app offers.
    final trimmed = name?.trim() ?? '';
    final initial = trimmed.isEmpty
        ? null
        : String.fromCharCode(trimmed.runes.first).toUpperCase();

    return Row(
      children: [
        Container(
          width: 52,
          height: 52,
          alignment: Alignment.center,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            color: Palette.tintStrong,
          ),
          child: initial == null
              ? Icon(Icons.person_outline, color: colors.primary, size: 28)
              : Text(
                  initial,
                  style: text.titleLarge?.copyWith(color: colors.primary),
                ),
        ),
        const SizedBox(width: Sizes.gap + 2),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Semantics(
                header: true,
                child: Text(
                  name == null ? fallback : greeting,
                  style: text.titleMedium,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                subtitle,
                style: text.bodySmall?.copyWith(color: colors.onSurfaceVariant),
              ),
            ],
          ),
        ),
        if (trailing != null) trailing!,
      ],
    );
  }
}

/// A square-ish tile in a two-up grid: icon above, then what it does.
///
/// The stacked cousin of [ActionTile]. Two of these side by side fit a phone
/// where two full-width rows would push everything below them off screen, and
/// the icon sitting above the label rather than beside it is what lets the
/// title wrap to two lines without the tile becoming a paragraph.
///
/// **It stretches to its sibling's height.** A pair whose captions differ by a
/// line reads as a mistake, so the caller wraps the row in `IntrinsicHeight`
/// and this fills whatever that settles on.
class QuickAction extends StatelessWidget {
  const QuickAction({
    super.key,
    required this.icon,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.tileKey,
    this.prominent = false,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;
  final Key? tileKey;

  /// At most one per screen, same rule as [ActionTile].
  final bool prominent;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final disabled = onTap == null;
    final filled = prominent && !disabled;

    final foreground = disabled
        ? colors.onSurfaceVariant
        : filled
            ? Colors.white
            : colors.onSurface;

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Sizes.radius),
        boxShadow: disabled ? null : softShadow,
      ),
      child: Material(
        color: disabled
            ? Palette.tint
            : filled
                ? colors.primary
                : Colors.white,
        borderRadius: BorderRadius.circular(Sizes.radius),
        child: InkWell(
          key: tileKey,
          onTap: onTap,
          borderRadius: BorderRadius.circular(Sizes.radius),
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gap + 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                IconChip(
                  icon: icon,
                  size: 42,
                  background: filled ? Colors.white24 : Palette.tint,
                  foreground: filled ? Colors.white : colors.primary,
                ),
                const SizedBox(height: Sizes.gap + 2),
                Text(
                  title,
                  style: text.titleMedium?.copyWith(color: foreground),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    subtitle!,
                    // Wraps in full. It used to cap at two lines and ellipsise,
                    // which produced "Answer a few questions before y…" — a
                    // caption cut mid-word says less than no caption, and at
                    // 200% text scale it cut after three words. Callers pass a
                    // short subtitle for this shape instead; `IntrinsicHeight`
                    // around the row keeps both tiles the same height however
                    // many lines they take.
                    style: text.bodySmall?.copyWith(
                      color: filled
                          ? Colors.white.withAlpha(220)
                          : colors.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
