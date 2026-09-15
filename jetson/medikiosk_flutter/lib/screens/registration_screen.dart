import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/camera_service.dart';
import '../theme/app_theme.dart';
import '../widgets/camera_pane.dart';

class RegistrationScreen extends StatefulWidget {
  final PatientProfile initialProfile;
  final CameraService cameraService;
  final ValueChanged<PatientProfile> onRegister;
  final VoidCallback onScanCard;
  final bool isScanning;
  final String? scanError;

  const RegistrationScreen({
    super.key,
    required this.initialProfile,
    required this.cameraService,
    required this.onRegister,
    required this.onScanCard,
    this.isScanning = false,
    this.scanError,
  });

  @override
  State<RegistrationScreen> createState() => _RegistrationScreenState();
}

class _RegistrationScreenState extends State<RegistrationScreen> {
  late TextEditingController _nameController;
  late TextEditingController _abhaController;
  late TextEditingController _ageController;
  late String _selectedGender;
  bool _showScanner = false;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.initialProfile.name);
    _abhaController = TextEditingController(text: widget.initialProfile.abhaNumber ?? '');
    _ageController = TextEditingController(text: (widget.initialProfile.age ?? 35).toString());
    _selectedGender = widget.initialProfile.gender;
  }

  @override
  void dispose() {
    _nameController.dispose();
    _abhaController.dispose();
    _ageController.dispose();
    super.dispose();
  }

  void _submit() {
    final profile = PatientProfile(
      name: _nameController.text.trim().isEmpty ? 'Patient / मरीज़' : _nameController.text.trim(),
      age: int.tryParse(_ageController.text.trim()) ?? 35,
      gender: _selectedGender,
      abhaNumber: _abhaController.text.trim().isEmpty ? null : _abhaController.text.trim(),
      isWalkIn: _abhaController.text.trim().isEmpty,
    );
    widget.onRegister(profile);
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Container(
          constraints: const BoxConstraints(maxWidth: 840),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final isNarrow = constraints.maxWidth < 680;

              return Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Header Card
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
                    decoration: BoxDecoration(
                      color: AppTheme.surface,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: AppTheme.surfaceBorder),
                      boxShadow: AppTheme.cardShadow,
                    ),
                    child: isNarrow
                        ? Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Row(
                                children: [
                                  Container(
                                    padding: const EdgeInsets.all(8),
                                    decoration: BoxDecoration(
                                      color: AppTheme.primaryBlue.withAlpha(25),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: const Icon(
                                      Icons.badge_rounded,
                                      color: AppTheme.primaryBlue,
                                      size: 24,
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  const Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          'मरीज़ पंजीकरण / Registration',
                                          style: TextStyle(
                                            fontSize: 18,
                                            fontWeight: FontWeight.bold,
                                            color: AppTheme.textPrimary,
                                          ),
                                        ),
                                        Text(
                                          'Enter details or scan ABHA • विवरण भरें',
                                          style: TextStyle(
                                            fontSize: 12,
                                            color: AppTheme.textSecondary,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 10),
                              TextButton.icon(
                                onPressed: () {
                                  _nameController.text = 'Walk-in Patient';
                                  _abhaController.clear();
                                  _submit();
                                },
                                style: TextButton.styleFrom(
                                  backgroundColor: AppTheme.surfaceHighlight,
                                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                ),
                                icon: const Icon(Icons.flash_on_rounded, color: AppTheme.warningOrange, size: 18),
                                label: const Text(
                                  'Skip / बिना आभा आगे बढ़ें (Quick Walk-in)',
                                  style: TextStyle(color: AppTheme.textPrimary, fontWeight: FontWeight.w600, fontSize: 12),
                                ),
                              ),
                            ],
                          )
                        : Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  color: AppTheme.primaryBlue.withAlpha(25),
                                  borderRadius: BorderRadius.circular(14),
                                ),
                                child: const Icon(
                                  Icons.badge_rounded,
                                  color: AppTheme.primaryBlue,
                                  size: 28,
                                ),
                              ),
                              const SizedBox(width: 14),
                              const Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'मरीज़ पंजीकरण / Patient Registration',
                                      style: TextStyle(
                                        fontSize: 20,
                                        fontWeight: FontWeight.bold,
                                        color: AppTheme.textPrimary,
                                      ),
                                    ),
                                    SizedBox(height: 2),
                                    Text(
                                      'Enter details or scan your ABHA health card • विवरण दर्ज करें',
                                      style: TextStyle(
                                        fontSize: 13,
                                        color: AppTheme.textSecondary,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              TextButton.icon(
                                onPressed: () {
                                  _nameController.text = 'Walk-in Patient';
                                  _abhaController.clear();
                                  _submit();
                                },
                                style: TextButton.styleFrom(
                                  backgroundColor: AppTheme.surfaceHighlight,
                                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                ),
                                icon: const Icon(Icons.flash_on_rounded, color: AppTheme.warningOrange, size: 18),
                                label: const Text(
                                  'Skip (Quick Walk-in)',
                                  style: TextStyle(color: AppTheme.textPrimary, fontWeight: FontWeight.w600, fontSize: 13),
                                ),
                              ),
                            ],
                          ),
                  ),

                  const SizedBox(height: 16),

                  // Form Content Grid (Responsive: Column on narrow, Row on wide)
                  isNarrow
                      ? Column(
                          children: [
                            _buildDemographicsCard(constraints.maxWidth),
                            if (_showScanner) ...[
                              const SizedBox(height: 16),
                              _buildAbhaScannerCard(),
                            ],
                          ],
                        )
                      : Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(flex: 3, child: _buildDemographicsCard(constraints.maxWidth)),
                            const SizedBox(width: 16),
                            Expanded(flex: 2, child: _buildAbhaScannerCard()),
                          ],
                        ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _buildDemographicsCard(double maxWidth) {
    final isCompact = maxWidth < 460;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: AppTheme.surfaceBorder),
        boxShadow: AppTheme.cardShadow,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Basic Details • सामान्य जानकारी',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
          ),
          const SizedBox(height: 14),

          // Name Field
          TextField(
            controller: _nameController,
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppTheme.textPrimary),
            decoration: const InputDecoration(
              labelText: 'Patient Name / मरीज़ का नाम',
              prefixIcon: Icon(Icons.person_outline_rounded, color: AppTheme.primaryBlue, size: 20),
            ),
          ),
          const SizedBox(height: 14),

          // Age & Gender (Responsive)
          isCompact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TextField(
                      controller: _ageController,
                      keyboardType: TextInputType.number,
                      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppTheme.textPrimary),
                      decoration: const InputDecoration(
                        labelText: 'Age / उम्र',
                        prefixIcon: Icon(Icons.cake_outlined, color: AppTheme.primaryBlue, size: 20),
                      ),
                    ),
                    const SizedBox(height: 12),
                    _buildGenderSelector(),
                  ],
                )
              : Row(
                  children: [
                    SizedBox(
                      width: 120,
                      child: TextField(
                        controller: _ageController,
                        keyboardType: TextInputType.number,
                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppTheme.textPrimary),
                        decoration: const InputDecoration(
                          labelText: 'Age / उम्र',
                          prefixIcon: Icon(Icons.cake_outlined, color: AppTheme.primaryBlue, size: 20),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(child: _buildGenderSelector()),
                  ],
                ),
          const SizedBox(height: 16),

          // ABHA ID Input
          TextField(
            controller: _abhaController,
            keyboardType: TextInputType.number,
            style: const TextStyle(fontSize: 16, letterSpacing: 1.1, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
            decoration: InputDecoration(
              labelText: 'ABHA ID / आभा नंबर (Optional)',
              hintText: '12-3456-7890-1234',
              prefixIcon: const Icon(Icons.credit_card_rounded, color: AppTheme.tealAccent, size: 20),
              suffixIcon: IconButton(
                icon: Icon(_showScanner ? Icons.keyboard_rounded : Icons.qr_code_scanner_rounded, color: AppTheme.primaryBlue),
                tooltip: _showScanner ? 'Hide Camera' : 'Scan Card',
                onPressed: () {
                  setState(() => _showScanner = !_showScanner);
                  if (_showScanner) widget.onScanCard();
                },
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Submit Action
          SizedBox(
            width: double.infinity,
            height: 52,
            child: ElevatedButton.icon(
              onPressed: _submit,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primaryBlue,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              ),
              icon: const Icon(Icons.arrow_forward_rounded, size: 20),
              label: const Text(
                'पंजीकरण पूरा करें (Continue to Assessment)',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGenderSelector() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Gender / लिंग', style: TextStyle(fontSize: 12, color: AppTheme.textSecondary)),
        const SizedBox(height: 6),
        Row(
          children: ['Male', 'Female', 'Other'].map((g) {
            final isSel = _selectedGender == g;
            return Expanded(
              child: GestureDetector(
                onTap: () => setState(() => _selectedGender = g),
                child: Container(
                  margin: const EdgeInsets.symmetric(horizontal: 2),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(
                    color: isSel ? AppTheme.primaryBlue : AppTheme.surfaceHighlight,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: isSel ? AppTheme.primaryBlue : AppTheme.surfaceBorder,
                    ),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    g == 'Male' ? 'पुरुष' : (g == 'Female' ? 'महिला' : 'अन्य'),
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      color: isSel ? Colors.white : AppTheme.textSecondary,
                    ),
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _buildAbhaScannerCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: AppTheme.surfaceBorder),
        boxShadow: AppTheme.cardShadow,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Row(
            children: [
              Icon(Icons.qr_code_scanner_rounded, color: AppTheme.tealAccent, size: 22),
              SizedBox(width: 8),
              Text(
                'ABHA Card Scanner',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
              ),
            ],
          ),
          const SizedBox(height: 12),
          CameraPane(
            service: widget.cameraService,
            onCapture: widget.onScanCard,
            captureLabel: 'Scan ABHA Card',
            busy: widget.isScanning,
            error: widget.scanError,
            height: 200,
          ),
          const SizedBox(height: 10),
          const Text(
            'Hold card facing camera • कार्ड कैमरे के सामने रखें',
            style: TextStyle(fontSize: 11, color: AppTheme.textMuted),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
