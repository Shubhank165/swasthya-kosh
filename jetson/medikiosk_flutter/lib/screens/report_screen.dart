import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';

class ReportScreen extends StatelessWidget {
  final Map<String, dynamic>? reportData;
  final PatientProfile profile;
  final List<ClinicalAnswerRecord> clinicalAnswers;
  final List<String> extractedDocumentLines;
  final VoidCallback onNewPatient;

  const ReportScreen({
    super.key,
    this.reportData,
    required this.profile,
    required this.clinicalAnswers,
    required this.extractedDocumentLines,
    required this.onNewPatient,
  });

  @override
  Widget build(BuildContext context) {
    final routing = reportData?['routing'] as Map<String, dynamic>? ?? {};
    final queue = routing['queue'] as String? ?? 'General Medicine OPD';
    final priority = routing['priority'] as String? ?? 'ROUTINE';
    // Constitution comes from the server's scored 58-item Ayush questionnaire, never from a
    // tally computed in Dart. `prakriti` is null until enough of it is answered, and the section
    // is simply absent then - a dosha printed on a slip is a clinical claim.
    final prakritiData = reportData?['prakriti'] as Map<String, dynamic>?;
    final prakritiName = prakritiData?['prakriti'] as String?;
    final prakritiHindi = prakritiData?['prakriti_hi'] as String?;
    final prakritiMarks = prakritiData?['marks'] as Map<String, dynamic>?;
    final prakritiReviewed = prakritiData?['scoring_reviewed'] == true;
    final prakritiRecordedAt = prakritiData?['recorded_at'] as String?;

    Color priorityColor = AppTheme.successGreen;
    Color priorityBg = AppTheme.successLight;
    if (priority.toUpperCase().contains('EMERGENCY')) {
      priorityColor = AppTheme.alertRed;
      priorityBg = AppTheme.alertLight;
    } else if (priority.toUpperCase().contains('URGENT')) {
      priorityColor = AppTheme.warningOrange;
      priorityBg = AppTheme.warningLight;
    }

    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
        child: Container(
          constraints: const BoxConstraints(maxWidth: 860),
          decoration: BoxDecoration(
            color: AppTheme.surface,
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: AppTheme.surfaceBorder),
            boxShadow: AppTheme.elevatedCardShadow,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Top Header Band
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 22),
                decoration: const BoxDecoration(
                  color: AppTheme.surfaceHighlight,
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(28),
                    topRight: Radius.circular(28),
                  ),
                  border: Border(bottom: BorderSide(color: AppTheme.surfaceBorder)),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppTheme.primaryBlue.withAlpha(20),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Icon(Icons.receipt_long_rounded, color: AppTheme.primaryBlue, size: 30),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: const [
                          Text(
                            'चिकित्सा सारांश पर्ची / Clinical Intake Slip',
                            style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'MediKiosk Smart Intake • All Answers & Extracted Findings',
                            style: TextStyle(fontSize: 12, color: AppTheme.textSecondary),
                          ),
                        ],
                      ),
                    ),
                    // OPD Token Badge
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                      decoration: BoxDecoration(
                        color: AppTheme.primaryBlue,
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Column(
                        children: const [
                          Text('TOKEN', style: TextStyle(fontSize: 10, color: Colors.white70, fontWeight: FontWeight.bold)),
                          Text('#A-104', style: TextStyle(fontSize: 18, color: Colors.white, fontWeight: FontWeight.bold)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

              Padding(
                padding: const EdgeInsets.all(28),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Patient Demographic Grid
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        color: AppTheme.surfaceHighlight,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: AppTheme.surfaceBorder),
                      ),
                      child: Row(
                        children: [
                          _buildPatientCol('मरीज़ का नाम (Patient)', profile.name, Icons.person_rounded),
                          _buildDivider(),
                          _buildPatientCol('उम्र / लिंग (Age/Sex)', '${profile.age ?? 35} yrs / ${profile.gender}', Icons.wc_rounded),
                          _buildDivider(),
                          _buildPatientCol('आभा नंबर (ABHA ID)', profile.maskedAbha, Icons.credit_card_rounded),
                        ],
                      ),
                    ),

                    const SizedBox(height: 20),

                    // Triage & Routing Queue Banner
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        color: priorityBg,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: priorityColor, width: 1.5),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Row(
                              children: [
                                Icon(Icons.local_hospital_rounded, color: priorityColor, size: 24),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      const Text('ओपीडी विभाग (Queue)', style: TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
                                      Text(
                                        queue,
                                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Container(width: 1.5, height: 36, margin: const EdgeInsets.symmetric(horizontal: 10), color: priorityColor.withAlpha(80)),
                          Expanded(
                            child: Row(
                              children: [
                                Icon(Icons.priority_high_rounded, color: priorityColor, size: 24),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      const Text('प्राथमिकता (Priority)', style: TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
                                      Text(
                                        priority,
                                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: priorityColor),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 24),

                    // SECTION 1: All Answers from the Session
                    const Text(
                      'मरीज़ द्वारा दिए गए सभी उत्तर (Intake Answers Record)',
                      style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                    ),
                    const SizedBox(height: 10),

                    if (clinicalAnswers.isEmpty)
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: AppTheme.surfaceHighlight,
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: const Row(
                          children: [
                            Icon(Icons.info_outline, color: AppTheme.textSecondary, size: 20),
                            SizedBox(width: 10),
                            // Expanded, or the sentence overflows the row and the slip prints
                            // the debug stripes instead. The Prakriti pathway skips the
                            // interview, so this is the normal state there, not an edge case.
                            Expanded(
                              child: Text(
                                'Standard consultation requested without preliminary triage answers.',
                                style: TextStyle(fontSize: 13, color: AppTheme.textSecondary),
                              ),
                            ),
                          ],
                        ),
                      )
                    else
                      Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AppTheme.surfaceBorder),
                        ),
                        child: Column(
                          children: clinicalAnswers.asMap().entries.map((entry) {
                            final idx = entry.key;
                            final ans = entry.value;
                            final isEven = idx % 2 == 0;

                            return Container(
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                              color: isEven ? Colors.white : AppTheme.surfaceHighlight,
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  CircleAvatar(
                                    radius: 12,
                                    backgroundColor: AppTheme.primaryBlue.withAlpha(20),
                                    child: Text('${idx + 1}', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTheme.primaryBlue)),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    flex: 3,
                                    child: Text(
                                      ans.questionText,
                                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppTheme.textPrimary),
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    flex: 2,
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                      decoration: BoxDecoration(
                                        color: AppTheme.primaryBlue.withAlpha(15),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Text(
                                        ans.answerText,
                                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.primaryDark),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          }).toList(),
                        ),
                      ),

                    const SizedBox(height: 24),

                    // SECTION 2: Extracted Text from Documents (PP-OCRv5)
                    if (extractedDocumentLines.isNotEmpty) ...[
                      const Text(
                        'दस्तावेज़ से निकाला गया टेक्स्ट (Extracted OCR Text)',
                        style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                      ),
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: AppTheme.tealLight.withAlpha(40),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AppTheme.tealAccent.withAlpha(80)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: const [
                                Icon(Icons.document_scanner_rounded, color: AppTheme.tealAccent, size: 20),
                                SizedBox(width: 8),
                                Text(
                                  'Scanned Prescription / Lab Records:',
                                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.tealAccent),
                                ),
                              ],
                            ),
                            const Divider(height: 16),
                            ...extractedDocumentLines.map((line) => Padding(
                              padding: const EdgeInsets.symmetric(vertical: 2),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text('• ', style: TextStyle(color: AppTheme.tealAccent, fontWeight: FontWeight.bold)),
                                  Expanded(
                                    child: Text(
                                      line,
                                      style: const TextStyle(fontSize: 13, color: AppTheme.textPrimary, height: 1.3),
                                    ),
                                  ),
                                ],
                              ),
                            )),
                          ],
                        ),
                      ),
                      const SizedBox(height: 24),
                    ],

                    // SECTION 3: Ayurveda Prakriti Summary (if assessed)
                    if (prakritiName != null) ...[
                      const Text(
                        'आयुर्वेद प्रकृति विश्लेषण (Prakriti Analysis)',
                        style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                      ),
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.all(18),
                        decoration: BoxDecoration(
                          color: AppTheme.warningLight.withAlpha(40),
                          borderRadius: BorderRadius.circular(18),
                          border: Border.all(color: AppTheme.warningOrange.withAlpha(90)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.spa_rounded, color: AppTheme.warningOrange, size: 24),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    'प्रकृति (Prakriti): ${prakritiHindi ?? prakritiName} / $prakritiName',
                                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                                  ),
                                ),
                              ],
                            ),
                            if (prakritiMarks != null) ...[
                              const SizedBox(height: 8),
                              Text(
                                'अंक (Marks) — Vata ${prakritiMarks['vata'] ?? 0} · '
                                'Pitta ${prakritiMarks['pitta'] ?? 0} · '
                                'Kapha ${prakritiMarks['kapha'] ?? 0}',
                                style: const TextStyle(fontSize: 13, color: AppTheme.textSecondary, height: 1.3),
                              ),
                            ],
                            if (prakritiRecordedAt != null) ...[
                              const SizedBox(height: 6),
                              Text(
                                'Recorded: ${prakritiRecordedAt.split('T').first} — asked once in a lifetime',
                                style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
                              ),
                            ],
                            // The item weights are reconstructed from the classical sources the
                            // CCRAS manual cites, not its licensed scoring table. Saying so on the
                            // slip is the difference between a finding and a suggestion.
                            if (!prakritiReviewed) ...[
                              const SizedBox(height: 8),
                              Container(
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(color: AppTheme.surfaceBorder),
                                ),
                                child: const Text(
                                  'अनंतिम / Provisional — scoring awaiting vaidya review',
                                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: AppTheme.textPrimary),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                      const SizedBox(height: 28),
                    ],

                    // Footer Instructions
                    Center(
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                        decoration: BoxDecoration(
                          color: AppTheme.surfaceHighlight,
                          borderRadius: BorderRadius.circular(30),
                        ),
                        child: const Text(
                          'कृपया प्रतीक्षा क्षेत्र में बैठें। टोकन नंबर से आपको बुलाया जाएगा।\n(Please wait in the OPD lounge. Your token will be announced.)',
                          style: TextStyle(fontSize: 13, color: AppTheme.textSecondary, height: 1.3),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),

                    const SizedBox(height: 28),

                    // Actions Row (Print Slip & New Patient)
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: () {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('🖨️ Printing Intake Slip to Kiosk Thermal Printer...'),
                                  backgroundColor: AppTheme.primaryBlue,
                                ),
                              );
                            },
                            style: OutlinedButton.styleFrom(
                              padding: const EdgeInsets.symmetric(vertical: 16),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                            ),
                            icon: const Icon(Icons.print_rounded, size: 20),
                            label: const Text('पर्ची प्रिंट करें (Print Slip)', style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
                          ),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: ElevatedButton.icon(
                            onPressed: onNewPatient,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.primaryBlue,
                              padding: const EdgeInsets.symmetric(vertical: 16),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                            ),
                            icon: const Icon(Icons.person_add_alt_1_rounded, size: 22),
                            label: const Text('नया मरीज़ (New Patient)', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPatientCol(String label, String value, IconData icon) {
    return Expanded(
      child: Row(
        children: [
          Icon(icon, size: 20, color: AppTheme.primaryBlue),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
                Text(value, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: AppTheme.textPrimary), maxLines: 1, overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDivider() {
    return Container(
      width: 1.5,
      height: 34,
      margin: const EdgeInsets.symmetric(horizontal: 12),
      color: AppTheme.surfaceBorder,
    );
  }
}
