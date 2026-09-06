/// Bundle fixtures shared by the walker, flow and queue tests.
///
/// One place to build a bundle from, so a test that exercises the flow is
/// exercising the same content shape the walker tests do. A second private copy
/// of these helpers would be a second definition of what a question looks like,
/// which is the drift the single bundle exists to prevent.
library;

import 'dart:convert';

import 'package:medikiosk_app/content/answer.dart';
import 'package:medikiosk_app/content/bundle.dart';

ContentBundle bundleWith({
  List<Map<String, dynamic>> questions = const [],
  List<Map<String, dynamic>> rules = const [],
  List<String> core = const [],
  Map<String, List<String>> branches = const {},
  List<String> ayurveda = const [],
  List<String> ayurvedaCurrentState = const [],
  List<String> sections = const ['chief_complaint', 'hpi', 'red_flag_screen'],
  // What a current backend actually serves: `GET /content/bundle` advertises
  // the newest contract the backend accepts, and that has been 0.2 since the
  // carry-forward work landed. The fixture said 0.1 for long enough that the
  // suite was green against a payload shape no deployment was asking for.
  String schemaVersion = '0.2',
}) {
  return ContentBundle.parse(jsonEncode({
    'bundle_format': '1',
    'content_version': 'test',
    'schema_version': schemaVersion,
    'languages': ['en', 'hi'],
    'sections': sections,
    'core': core,
    'branches': branches,
    'ayurveda': ayurveda,
    'ayurveda_current_state': ayurvedaCurrentState,
    'questions': questions,
    'red_flag_rules': rules,
  }));
}

Map<String, dynamic> question(
  String id, {
  String? field,
  String type = 'yes_no_unknown',
  List<String>? options,
  Map<String, dynamic>? precondition,
  bool allowSkip = true,
  String section = 'hpi',
}) =>
    {
      'question_id': id,
      'field_id': field ?? id,
      'section': section,
      'answer_type': type,
      'required': true,
      'prompts': {'en': 'Prompt for $id', 'hi': 'प्रश्न $id'},
      'options': options,
      'precondition': precondition,
      'allow_skip': allowSkip,
      'allow_unknown': true,
    };

Answer answered(String id, AnswerValue value, {String? field, String text = 'x'}) => Answer(
      questionId: id,
      fieldId: field ?? id,
      status: FieldStatus.answered,
      value: value,
      originalText: text,
      language: 'en',
    );
