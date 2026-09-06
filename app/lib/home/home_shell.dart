/// The app's home — stage 4.
///
/// Until now signing in dropped the patient straight into an interview. That is
/// what a kiosk does, because a kiosk is a machine you walk up to *in order to*
/// answer questions and then walk away from. A phone is not: it is opened
/// between visits, to look something up, to add a report that arrived by email,
/// to check what was said last time.
///
/// So the intake becomes one thing the app does rather than the only thing, and
/// the four destinations below are the others. Nothing clinical happens here —
/// every tab either lists what already exists or starts a flow that does.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/theme.dart';
import '../l10n/strings.dart';
import 'documents_tab.dart';
import 'home_tab.dart';
import 'profile_tab.dart';
import 'visits_tab.dart';

class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({super.key});

  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Scaffold(
      // `IndexedStack`, not a rebuild per tap: a half-scrolled document list
      // should still be half-scrolled when the patient comes back to it, and
      // the visits tab should not re-fetch every time somebody looks at their
      // profile.
      body: SafeArea(
        child: IndexedStack(
          index: _index,
          children: const [
            HomeTab(),
            DocumentsTab(),
            VisitsTab(),
            ProfileTab(),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        // Labels always shown. §14: an icon alone is a guess for a patient who
        // reads Devanagari and has never used this app before, and the tab bar
        // is the one control on screen at all times.
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        height: Sizes.minTouchTarget * 1.6,
        destinations: [
          NavigationDestination(
            key: const Key('tab.home'),
            icon: const Icon(Icons.home_outlined),
            selectedIcon: const Icon(Icons.home),
            label: strings.homeTab,
          ),
          NavigationDestination(
            key: const Key('tab.documents'),
            icon: const Icon(Icons.folder_outlined),
            selectedIcon: const Icon(Icons.folder),
            label: strings.documentsTab,
          ),
          NavigationDestination(
            key: const Key('tab.visits'),
            icon: const Icon(Icons.history_outlined),
            selectedIcon: const Icon(Icons.history),
            label: strings.visitsTab,
          ),
          NavigationDestination(
            key: const Key('tab.profile'),
            icon: const Icon(Icons.person_outline),
            selectedIcon: const Icon(Icons.person),
            label: strings.profileTab,
          ),
        ],
      ),
    );
  }
}
