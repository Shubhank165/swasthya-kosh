/// The bundle walker — 2/3 §15 items 4, 5 and 6.
///
/// These are the safety tests. Everything else in the app is a renderer around
/// this file, so if the walker collapses a status or misses a red flag, no
/// amount of correct UI helps.
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/content/answer.dart';
import 'package:medikiosk_app/content/bundle.dart';
import 'package:medikiosk_app/content/walker.dart';

import 'bundle_fixture.dart';

void main() {
  group('the five statuses stay distinct', () {
    test('skip records not_asked, not no', () {
      final walker = IntakeWalker(
        bundle: bundleWith(questions: [question('a')], core: ['a']),
        language: 'en',
      );
      walker.record(const Answer(
        questionId: 'a',
        fieldId: 'a',
        status: FieldStatus.notAsked,
        language: 'en',
      ));
      final json = walker.answers['a']!.toJson();
      expect(json['status'], 'not_asked');
      expect(json['value'], isNull);
    });

    test("I don't know records unresolved, not no", () {
      final walker = IntakeWalker(
        bundle: bundleWith(questions: [question('a')], core: ['a']),
        language: 'en',
      );
      walker.record(const Answer(
        questionId: 'a',
        fieldId: 'a',
        status: FieldStatus.unresolved,
        language: 'en',
      ));
      expect(walker.answers['a']!.toJson()['status'], 'unresolved');
    });

    test('a failed precondition records not_applicable, and is not omitted', () {
      // §4: a question whose precondition fails is *recorded* not_applicable
      // with the failing condition — never simply left out. An absence is a
      // hole a reader has to interpret; a status is a statement.
      final walker = IntakeWalker(
        bundle: bundleWith(
          questions: [
            question('sex', type: 'single_choice', options: ['female', 'male']),
            question('pregnancy', precondition: {
              'all': [
                {'field_id': 'sex', 'in': ['female']}
              ]
            }),
          ],
          core: ['sex', 'pregnancy'],
        ),
        language: 'en',
      );
      walker.record(answered('sex', const CodedValue('male')));
      walker.next();
      final recorded = walker.answers['pregnancy']!;
      expect(recorded.status, FieldStatus.notApplicable);
      expect(recorded.notApplicableBecause, contains('sex'));
    });

    test('no status ever serialises as "no" or disappears', () {
      for (final status in FieldStatus.values) {
        final json = Answer(
          questionId: 'q',
          fieldId: 'q',
          status: status,
          language: 'en',
        ).toJson();
        expect(json['status'], isNotNull);
        expect(json['status'], isNot('no'));
        expect(json.containsKey('value'), isTrue,
            reason: 'value is an explicit null, never an absent key');
      }
    });

    test('the five wire names match the backend contract exactly', () {
      expect(
        FieldStatus.values.map((s) => s.wire).toSet(),
        {'answered', 'unresolved', 'not_asked', 'not_applicable', 'refused'},
      );
    });
  });

  group('red flags', () {
    ContentBundle chestPainBundle() => bundleWith(
          questions: [
            question('chief_complaint',
                type: 'single_choice',
                options: ['chest_pain', 'fever'],
                section: 'chief_complaint'),
            question('dyspnoea', section: 'red_flag_screen'),
            question('diaphoresis', section: 'red_flag_screen'),
            question('later'),
          ],
          core: ['chief_complaint'],
          branches: {
            'chest_pain': ['dyspnoea', 'diaphoresis', 'later']
          },
          rules: [
            {
              'rule_id': 'acute_chest_pain_with_dyspnoea',
              'severity': 'critical',
              'criteria': {
                'all': [
                  {'field_id': 'chief_complaint', 'in': ['chest_pain']},
                  {
                    'any': [
                      {'field_id': 'dyspnoea', 'status': 'present'},
                      {'field_id': 'diaphoresis', 'status': 'present'},
                    ]
                  },
                ]
              },
            }
          ],
        );

    test('a firing rule stops the intake', () {
      final walker = IntakeWalker(bundle: chestPainBundle(), language: 'en');
      walker.record(answered('chief_complaint', const CodedValue('chest_pain')));
      final outcome = walker.record(answered('dyspnoea', const BoolValue(true)));

      expect(outcome, WalkOutcome.redFlag);
      expect(walker.firedFlag!.ruleId, 'acute_chest_pain_with_dyspnoea');
      // §6.1: no further questions. There is no "continue anyway".
      expect(walker.next(), isNull);
    });

    test('the disjunction is a disjunction', () {
      // Flattening `(dyspnoea OR diaphoresis)` into the enclosing `all` would
      // require both symptoms — a strictly narrower rule, on the criterion that
      // exists to catch a heart attack in a waiting room.
      final walker = IntakeWalker(bundle: chestPainBundle(), language: 'en');
      walker.record(answered('chief_complaint', const CodedValue('chest_pain')));
      walker.record(answered('dyspnoea', const BoolValue(false)));
      final outcome = walker.record(answered('diaphoresis', const BoolValue(true)));
      expect(outcome, WalkOutcome.redFlag);
    });

    test('a rule does not fire on a half-answered record', () {
      final walker = IntakeWalker(bundle: chestPainBundle(), language: 'en');
      final outcome = walker.record(answered('dyspnoea', const BoolValue(true)));
      expect(outcome, isNot(WalkOutcome.redFlag),
          reason: 'no complaint chosen yet, so the rule is not yet knowable');
    });

    test("\"I don't know\" never clears a rule", () {
      // The single most dangerous shortcut available: treating unresolved as
      // `false` would silently clear a red flag the patient simply could not
      // answer.
      final walker = IntakeWalker(bundle: chestPainBundle(), language: 'en');
      walker.record(answered('chief_complaint', const CodedValue('chest_pain')));
      walker.record(const Answer(
        questionId: 'dyspnoea',
        fieldId: 'dyspnoea',
        status: FieldStatus.unresolved,
        language: 'en',
      ));
      final outcome = walker.record(answered('diaphoresis', const BoolValue(true)));
      expect(outcome, WalkOutcome.redFlag);
    });

    test('answering no does not fire it', () {
      final walker = IntakeWalker(bundle: chestPainBundle(), language: 'en');
      walker.record(answered('chief_complaint', const CodedValue('chest_pain')));
      walker.record(answered('dyspnoea', const BoolValue(false)));
      final outcome = walker.record(answered('diaphoresis', const BoolValue(false)));
      expect(outcome, isNot(WalkOutcome.redFlag));
    });

    test('the hit carries the answers that triggered it', () {
      final walker = IntakeWalker(bundle: chestPainBundle(), language: 'en');
      walker.record(answered('chief_complaint', const CodedValue('chest_pain'),
          text: 'Chest pain'));
      walker.record(answered('dyspnoea', const BoolValue(true), text: 'Yes'));
      expect(walker.firedFlag!.fields, containsPair('dyspnoea', 'Yes'));
    });
  });

  group('degrading on an unfamiliar bundle', () {
    test('an unknown answer_type does not crash and records not_asked', () {
      final walker = IntakeWalker(
        bundle: bundleWith(
          questions: [
            question('weird', type: 'holographic_projection'),
            question('normal'),
          ],
          core: ['weird', 'normal'],
        ),
        language: 'en',
      );
      final next = walker.next();
      expect(next!.questionId, 'normal');
      expect(walker.answers['weird']!.status, FieldStatus.notAsked);
    });

    test('an unknown question_id in a branch does not crash', () {
      final walker = IntakeWalker(
        bundle: bundleWith(
          questions: [question('chief_complaint', type: 'single_choice', options: ['fever'])],
          core: ['chief_complaint'],
          branches: {
            'fever': ['a_question_this_bundle_does_not_carry']
          },
        ),
        language: 'en',
      );
      walker.record(answered('chief_complaint', const CodedValue('fever')));
      expect(walker.next(), isNull);
      expect(
        walker.answers['a_question_this_bundle_does_not_carry']!.status,
        FieldStatus.notAsked,
      );
    });

    test('a question with no prompt in the chosen language is not asked', () {
      // Falling back to English would put an English clinical question in front
      // of a patient who chose Tamil and record the answer as though they had
      // understood it.
      final bundle = ContentBundle.parse(jsonEncode({
        'bundle_format': '1',
        'content_version': 'test',
        'schema_version': '0.1',
        'languages': ['en'],
        'sections': ['hpi'],
        'core': ['a'],
        'branches': <String, dynamic>{},
        'ayurveda': <String>[],
        'questions': [
          {
            'question_id': 'a',
            'field_id': 'a',
            'section': 'hpi',
            'answer_type': 'yes_no_unknown',
            'required': true,
            'prompts': {'en': 'Only English'},
            'options': null,
            'precondition': null,
            'allow_skip': true,
            'allow_unknown': true,
          }
        ],
        'red_flag_rules': <dynamic>[],
      }));
      final walker = IntakeWalker(bundle: bundle, language: 'ta');
      expect(walker.next(), isNull);
      expect(walker.answers['a']!.status, FieldStatus.notAsked);
    });

    test('a schema version this app cannot produce is refused outright', () {
      // §4: refuse to start, tell the user to update. Do not attempt partial
      // compatibility — a record that is half of a newer contract is one the
      // backend either rejects or, worse, accepts and misreads.
      final bundle = ContentBundle.parse(jsonEncode({
        'bundle_format': '1',
        'schema_version': '0.9',
        'languages': ['en'],
        'questions': <dynamic>[],
        'red_flag_rules': <dynamic>[],
      }));
      expect(bundle.isUsable, isFalse);
    });

    test('a bundle format from the future is refused outright', () {
      final bundle = ContentBundle.parse(jsonEncode({
        'bundle_format': '99',
        'schema_version': '0.1',
        'languages': ['en'],
        'questions': <dynamic>[],
        'red_flag_rules': <dynamic>[],
      }));
      expect(bundle.isUsable, isFalse);
    });
  });

  group('walking', () {
    test('the branch follows the chosen complaint', () {
      final walker = IntakeWalker(
        bundle: bundleWith(
          questions: [
            question('chief_complaint',
                type: 'single_choice', options: ['fever', 'headache']),
            question('fever_q'),
            question('headache_q'),
          ],
          core: ['chief_complaint'],
          branches: {
            'fever': ['fever_q'],
            'headache': ['headache_q'],
          },
        ),
        language: 'en',
      );
      walker.record(answered('chief_complaint', const CodedValue('fever')));
      expect(walker.next()!.questionId, 'fever_q');
      expect(walker.plan, isNot(contains('headache_q')));
    });

    test('closing out accounts for every planned question', () {
      // A question never reached is `not_asked` explicitly. A reader must never
      // have to distinguish "not asked" from "the app forgot".
      final walker = IntakeWalker(
        bundle: bundleWith(questions: [question('a'), question('b')], core: ['a', 'b']),
        language: 'en',
      );
      walker.record(answered('a', const BoolValue(true)));
      walker.closeOut();
      expect(walker.answers.keys, containsAll(['a', 'b']));
      expect(walker.answers['b']!.status, FieldStatus.notAsked);
    });

    test('progress counts sections, never a percentage', () {
      final walker = IntakeWalker(
        bundle: bundleWith(
          questions: [
            question('cc', type: 'single_choice', options: ['fever'], section: 'chief_complaint'),
            question('h1', section: 'hpi'),
          ],
          core: ['cc', 'h1'],
        ),
        language: 'en',
      );
      expect(walker.sectionProgress, (0, 2));
      walker.record(answered('cc', const CodedValue('fever')));
      expect(walker.sectionProgress, (1, 2));
    });

    test('the prompt shown is recorded in the language it was shown in', () {
      final walker = IntakeWalker(
        bundle: bundleWith(questions: [question('a')], core: ['a']),
        language: 'hi',
      );
      final q = walker.next()!;
      expect(q.promptFor('hi'), 'प्रश्न a');
    });
  });

  group('the Ayurveda section on a return visit', () {
    ContentBundle module() => bundleWith(
          questions: [
            question('complaint', field: 'chief_complaint', type: 'single_choice',
                options: ['fever'], section: 'chief_complaint'),
            question('agni', section: 'hpi'),
            question('nidra', section: 'hpi'),
            question('vihara', section: 'hpi'),
          ],
          core: ['complaint'],
          ayurveda: ['agni', 'nidra', 'vihara'],
          ayurvedaCurrentState: ['agni', 'nidra'],
        );

    test('a first visit gets the full module', () {
      final walker = IntakeWalker(bundle: module(), language: 'en');
      expect(walker.plan, containsAll(['agni', 'nidra', 'vihara']));
    });

    test('a return visit gets the current-state subset', () {
      // §5 screen 8. What a patient reports about their own constitution does
      // not change between two visits a fortnight apart; Agni, Nidra and
      // Koshtha are exactly what the Vaidya wants today's answer to.
      final walker =
          IntakeWalker(bundle: module(), language: 'en', returnVisit: true);
      expect(walker.plan, contains('agni'));
      expect(walker.plan, isNot(contains('vihara')));
    });

    test('a bundle that names no subset falls back to the full module', () {
      // An older backend, or content where no clinician has marked one. A
      // returning patient answering nine questions is slower; one asked none of
      // them arrives with no Agni, Nidra or Koshtha at all.
      final older = bundleWith(
        questions: [question('agni'), question('vihara')],
        ayurveda: ['agni', 'vihara'],
      );
      final walker =
          IntakeWalker(bundle: older, language: 'en', returnVisit: true);
      expect(walker.plan, containsAll(['agni', 'vihara']));
    });

    test('the subset is what the record accounts for, not the full module', () {
      final walker =
          IntakeWalker(bundle: module(), language: 'en', returnVisit: true);
      walker.closeOut();
      // A question that was never in the plan is not `not_asked` — it was not
      // part of this intake at all, and claiming it was put and skipped would
      // be a different statement.
      expect(walker.answers.containsKey('vihara'), isFalse);
    });
  });
}
