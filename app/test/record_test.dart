/// The record the app submits — 2/3 §9, §15 item 3.
///
/// §9's binding requirement is that the app's output validates against the same
/// contract the backend's normalizer tests use. Two copies of a contract drift;
/// so this test writes a golden record to `test/golden/app_record_0.1.json`, and
/// the backend's `tests/contracts/test_app_record.py` reads *that same file* and
/// runs it through the real normalizer.
///
/// Drift in either direction fails: change the Dart without regenerating and
/// this test fails; regenerate without the backend agreeing and the Python test
/// fails.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/content/answer.dart';
import 'package:medikiosk_app/content/bundle.dart';
import 'package:medikiosk_app/submit/record.dart';

ContentBundle testBundle() => ContentBundle.parse(jsonEncode({
      'bundle_format': '1',
      'content_version': 'questions-2026-09-01',
      'schema_version': '0.1',
      'languages': ['en', 'hi'],
      'sections': ['chief_complaint', 'hpi'],
      'core': ['core_intake.chief_complaint'],
      'branches': <String, dynamic>{},
      'ayurveda': <String>[],
      'questions': <dynamic>[],
      'red_flag_rules': <dynamic>[],
    }));

Map<String, dynamic> buildRecord({RedFlagHitRecord? flag}) {
  final builder = IntakeRecordBuilder(
    intakeId: '5c2f9a44-0000-4000-8000-00000000ab01',
    hospitalId: 'aiia-delhi',
    bundle: testBundle(),
    language: 'hi',
    reporter: 'self',
    appVersion: '1.0.0',
    departmentCode: 'kayachikitsa',
    patientRef: const PatientRef.phone('a1b2c3d4e5f60718'),
  );

  final answers = <String, Answer>{
    'core_intake.chief_complaint': const Answer(
      questionId: 'core_intake.chief_complaint',
      fieldId: 'chief_complaint',
      status: FieldStatus.answered,
      value: CodedValue('abdominal_pain'),
      originalText: 'पेट में दर्द',
      askedText: 'आज आप किस समस्या के लिए आए हैं?',
      language: 'hi',
    ),
    'abdominal_pain.duration': const Answer(
      questionId: 'abdominal_pain.duration',
      fieldId: 'duration',
      status: FieldStatus.answered,
      value: DurationValue(n: 3, unit: 'day'),
      originalText: '3 दिन',
      askedText: 'यह दर्द कब से है?',
      language: 'hi',
    ),
    'abdominal_pain.severity': const Answer(
      questionId: 'abdominal_pain.severity',
      fieldId: 'severity',
      status: FieldStatus.answered,
      value: ScaleValue(6),
      originalText: '6',
      askedText: 'दर्द कितना तेज़ है?',
      language: 'hi',
    ),
    // One of each unsettled status, so the golden exercises all five.
    'core_intake.tobacco': const Answer(
      questionId: 'core_intake.tobacco',
      fieldId: 'tobacco',
      status: FieldStatus.refused,
      originalText: 'यह नहीं बताना चाहता',
      askedText: 'क्या आप तंबाकू का सेवन करते हैं?',
      language: 'hi',
    ),
    'core_intake.alcohol': const Answer(
      questionId: 'core_intake.alcohol',
      fieldId: 'alcohol',
      status: FieldStatus.unresolved,
      askedText: 'क्या आप शराब पीते हैं?',
      language: 'hi',
    ),
    'core_intake.pregnancy': const Answer(
      questionId: 'core_intake.pregnancy',
      fieldId: 'pregnancy',
      status: FieldStatus.notApplicable,
      notApplicableBecause: 'sex',
      language: 'hi',
    ),
    'core_intake.breathlessness': const Answer(
      questionId: 'core_intake.breathlessness',
      fieldId: 'breathlessness',
      status: FieldStatus.notAsked,
      language: 'hi',
    ),
  };

  return IntakeRecordBuilder(
    intakeId: builder.intakeId,
    hospitalId: builder.hospitalId,
    bundle: builder.bundle,
    language: builder.language,
    reporter: builder.reporter,
    appVersion: builder.appVersion,
    departmentCode: builder.departmentCode,
    patientRef: builder.patientRef,
  ).build(
    answers: answers,
    startedAt: DateTime.utc(2026, 9, 3, 10, 14, 22),
    completedAt: DateTime.utc(2026, 9, 3, 10, 21, 5),
    abortedByRedFlag: flag,
  );
}

void main() {
  final fixture = File('../backend/tests/fixtures/kiosk/0.1.json');

  group('the app record matches the kiosk contract', () {
    test('it carries every top-level key the Jetson record carries', () {
      // One schema, one door. A key the Jetson sends and the app does not is a
      // field the normalizer will read as absent for app intakes only.
      final kiosk = jsonDecode(fixture.readAsStringSync()) as Map<String, dynamic>;
      final app = buildRecord();
      final missing = kiosk.keys.where((k) => !app.containsKey(k)).toList();
      expect(missing, isEmpty, reason: 'app record is missing $missing');
    });

    test('the voice fields are null, not absent', () {
      // §9: the contract keeps one shape, so the normalizer needs no branch for
      // where a record came from.
      final turn = (buildRecord()['turns'] as List).first as Map<String, dynamic>;
      for (final key in ['transcript', 'asr_confidence', 'rms']) {
        expect(turn.containsKey(key), isTrue, reason: '$key must be present');
        expect(turn[key], isNull, reason: '$key must be null for an app record');
      }
    });

    test('it says it came from the app, and names no kiosk', () {
      final record = buildRecord();
      expect(record['source'], 'app');
      expect(record['kiosk_id'], isNull);
      expect(record['app_version'], '1.0.0');
    });

    test('it claims no interview engine', () {
      // The app has no question engine. Naming one would claim a component that
      // is not running.
      expect(buildRecord()['engine_version'], isNull);
    });

    test('a tapped answer reports no confidence', () {
      // A tap has no confidence to report. `1.0` would make it look like a
      // perfectly-heard spoken answer to every downstream consumer.
      final fields = buildRecord()['fields'] as Map<String, dynamic>;
      for (final field in fields.values) {
        expect((field as Map<String, dynamic>).containsKey('confidence'), isFalse);
      }
    });

    test('values are bare, matching what the normalizer coerces', () {
      final fields = buildRecord()['fields'] as Map<String, dynamic>;
      expect((fields['chief_complaint'] as Map)['value'], 'abdominal_pain');
      expect((fields['duration'] as Map)['value'], {'n': 3.0, 'unit': 'day'});
      expect((fields['severity'] as Map)['value'], 6.0);
    });

    test('every unsettled field carries an explicit null value', () {
      final fields = buildRecord()['fields'] as Map<String, dynamic>;
      for (final name in ['tobacco', 'alcohol', 'pregnancy', 'breathlessness']) {
        final field = fields[name] as Map<String, dynamic>;
        expect(field.containsKey('value'), isTrue);
        expect(field['value'], isNull);
        expect(field['status'], isNot('no'));
      }
    });

    test('unasked and not-applicable fields produce no turn', () {
      // A turn claims the patient was shown a question. They were not.
      final turns = (buildRecord()['turns'] as List).cast<Map<String, dynamic>>();
      final asked = turns.map((t) => t['bound_field']).toSet();
      expect(asked, isNot(contains('breathlessness')));
      expect(asked, isNot(contains('pregnancy')));
      expect(asked, contains('tobacco'), reason: 'refused means it WAS asked');
    });

    test('a red-flag abort is submitted partial, and names no condition', () {
      final record = buildRecord(
        flag: RedFlagHitRecord(
          ruleId: 'acute_chest_pain_with_dyspnoea',
          severity: 'critical',
          firedAt: DateTime.utc(2026, 9, 3, 10, 18),
          fields: const {'dyspnoea': 'हाँ'},
        ),
      );
      expect(record['status'], 'aborted_red_flag');
      final flag = (record['red_flags'] as List).single as Map<String, dynamic>;
      expect(flag['rule_id'], 'acute_chest_pain_with_dyspnoea');
      // No label, no interpretation — the backend does not re-evaluate rules,
      // and a phrase invented here would reach a physician's screen as if it
      // were a finding.
      expect(flag.containsKey('label'), isFalse);
      expect(record['fields'], isNotEmpty,
          reason: 'the answers that sent them to A&E are the ones most worth having');
    });
  });

  test('the golden record is current', () {
    // Regenerate with: UPDATE_GOLDEN=1 flutter test test/record_test.dart
    final golden = File('test/golden/app_record_0.1.json');
    final encoded = const JsonEncoder.withIndent('  ').convert(buildRecord());
    if (Platform.environment['UPDATE_GOLDEN'] == '1' || !golden.existsSync()) {
      golden.parent.createSync(recursive: true);
      golden.writeAsStringSync('$encoded\n');
    }
    expect(golden.readAsStringSync().trim(), encoded.trim(),
        reason: 'the backend reads this file; regenerate with UPDATE_GOLDEN=1');
  });
}
