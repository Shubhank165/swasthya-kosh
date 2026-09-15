import 'package:flutter/material.dart';
import 'screens/kiosk_controller_screen.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MediKioskApp());
}

class MediKioskApp extends StatelessWidget {
  const MediKioskApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MediKiosk - Jetson Orin Nano Clinical Intake',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      home: const KioskControllerScreen(),
    );
  }
}
