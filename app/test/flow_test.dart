/// The flow controller — 2/3 §5, §6, §9, §15 items 4, 5, 7 and 8.
///
/// The two properties this file is really about:
///
/// **A red flag ends the intake.** Not pauses it, not warns about it. There is
/// no method that leaves the urgent stage, back refuses, and the partial record
/// is queued with `aborted_red_flag` before the patient has stopped reading the
/// screen.
///
/// **Nothing is lost between two questions.** The draft is on disk before the
/// next question is shown, so the arbitrary moment §15 item 7 kills the app at
/// is survivable wherever it lands.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:medikiosk_app/documents/document_store.dart';
import 'package:medikiosk_app/documents/prepare.dart';
import 'package:medikiosk_app/content/answer.dart';
import 'package:medikiosk_app/content/bundle.dart';
import 'package:medikiosk_app/intake/flow.dart';
import 'package:medikiosk_app/storage/database.dart';
import 'package:medikiosk_app/submit/queue.dart';

import 'bundle_fixture.dart';
import 'fake_api.dart';
import 'test_sqlite.dart';

/// Chest pain plus breathlessness, which is the rule the brief opens §6 with.
ContentBundle cardiacBundle({String schemaVersion = '0.2'}) => bundleWith(
      schemaVersion: schemaVersion,
      sections: const ['chief_complaint', 'hpi', 'ayurveda'],
      questions: [
        question(
          'chief_complaint',
          type: 'single_choice',
          options: ['chest_pain', 'fever'],
          section: 'chief_complaint',
        ),
        question('dyspnoea'),
        question('duration', type: 'number'),
        question('digestion', section: 'ayurveda'),
      ],
      core: ['chief_complaint'],
      branches: {
        'chest_pain': ['dyspnoea', 'duration'],
        'fever': ['duration'],
      },
      ayurveda: ['digestion'],
      rules: [
        {
          'rule_id': 'acute_chest_pain_with_dyspnoea',
          'severity': 'critical',
          'criteria': {
            'all': [
              {'field_id': 'chief_complaint', 'in': ['chest_pain']},
              {'field_id': 'dyspnoea', 'status': 'present'},
            ]
          },
        },
      ],
    );

void main() {
  useSystemSqlite();

  late LocalDatabase db;
  late FakeBackend backend;
  late SubmissionQueue queue;
  late DocumentStore documents;
  late FakePicker picker;
  late Directory scratch;

  setUp(() {
    db = LocalDatabase.memory();
    backend = FakeBackend();
    queue = SubmissionQueue(database: db, api: fakeApi(backend));
    scratch = Directory.systemTemp.createTempSync('medikiosk_flow');
    picker = FakePicker();
    documents = DocumentStore(database: db, directory: scratch, picker: picker);
  });

  tearDown(() async {
    await db.close();
    if (scratch.existsSync()) scratch.deleteSync(recursive: true);
  });

  Future<IntakeFlow> begin({
    ContentBundle? bundle,
    String language = 'en',
    List<ConfirmedFact> confirmed = const [],
  }) =>
      IntakeFlow.begin(
        database: db,
        queue: queue,
        documents: documents,
        confirmed: confirmed,
        bundle: bundle ?? cardiacBundle(),
        language: language,
        hospitalId: 'aiia-delhi',
        hospitalName: 'All India Institute of Ayurveda',
        reporter: 'self',
        appVersion: '1.0.0',
      );

  Future<Map<String, dynamic>> queuedRecord(String intakeId) async {
    final draft = await db.draftFor(intakeId);
    final envelope = jsonDecode(draft!.queuedPayload!) as Map<String, dynamic>;
    return envelope['record'] as Map<String, dynamic>;
  }

  group('a red flag ends the intake', () {
    late IntakeFlow flow;

    setUp(() async {
      backend.allOffline = true; // the interesting case: it has to be queued
      flow = await begin();
      await flow.answer(const CodedValue('chest_pain'), 'Chest pain');
      await flow.answer(const BoolValue(true), 'Yes');
    });

    test('stops on the urgent screen with no question showing', () {
      expect(flow.stage, FlowStage.urgent);
      expect(flow.question, isNull);
      expect(flow.firedFlag?.ruleId, 'acute_chest_pain_with_dyspnoea');
    });

    test('offers no way back into the interview', () async {
      // §6.4: not disabled, not behind a confirmation — absent.
      expect(flow.canGoBack, isFalse);
      await flow.back();
      expect(flow.stage, FlowStage.urgent);

      // Nor by the review screen's edit affordance, which is the other door.
      await flow.edit('dyspnoea');
      expect(flow.stage, FlowStage.urgent);
      expect(flow.walker.answers['dyspnoea']?.status, FieldStatus.answered);
    });

    test('queues the partial record as aborted_red_flag', () async {
      final record = await queuedRecord(flow.intakeId);
      expect(record['status'], 'aborted_red_flag');
      expect(record['red_flags'], hasLength(1));
      final hit = (record['red_flags'] as List).first as Map<String, dynamic>;
      expect(hit['rule_id'], 'acute_chest_pain_with_dyspnoea');
      expect(hit['severity'], 'critical');
    });

    test('the partial record carries the answers that sent them there', () async {
      // A patient being sent to an emergency department is exactly when the
      // hospital most wants the answers that sent them.
      final record = await queuedRecord(flow.intakeId);
      final fields = record['fields'] as Map<String, dynamic>;
      expect((fields['chief_complaint'] as Map)['value'], 'chest_pain');
      expect((fields['dyspnoea'] as Map)['value'], true);
      // And accounts for the ones it never got to, explicitly.
      expect((fields['duration'] as Map)['status'], 'not_asked');
      expect((fields['digestion'] as Map)['status'], 'not_asked');
    });

    test('the record survives the app dying on the urgent screen', () async {
      final draft = await db.draftFor(flow.intakeId);
      expect(draft!.queuedPayload, isNotNull);
      expect(await db.receiptFor(flow.intakeId), isNull);

      backend.allOffline = false;
      expect(await queue.flush(attempts: 1), 1);
    });

    test('names no condition anywhere in what it records', () async {
      // §6: the record carries a rule id and the triggering answers. A phrase
      // invented here would reach a physician's screen looking like a finding.
      final record = await queuedRecord(flow.intakeId);
      final hit = (record['red_flags'] as List).first as Map<String, dynamic>;
      expect(hit.keys, unorderedEquals(['rule_id', 'severity', 'fired_at', 'triggering_fields']));
    });
  });

  group('an intake that finishes', () {
    test('reaches review, then submits a complete record', () async {
      final flow = await begin();
      await flow.answer(const CodedValue('fever'), 'Fever');
      await flow.answer(const NumberValue(3), '3 days');
      await flow.answer(const BoolValue(true), 'Yes');

      // §5: documents (screen 9) sit between the interview and the review.
      expect(flow.stage, FlowStage.documents);
      flow.continueToReview();
      expect(flow.stage, FlowStage.review);
      await flow.submit();

      expect(flow.stage, FlowStage.submitted);
      expect(flow.queued, isFalse);
      expect(flow.referenceCode, referenceCodeFor(flow.intakeId));

      final ingest = backend.calls.firstWhere((c) => c.path.contains('/ingest'));
      expect((ingest.body as Map)['status'], 'complete');
      // §15 item 9: nothing clinical left behind.
      expect(await db.draftFor(flow.intakeId), isNull);
    });

    test('with no signal, says so plainly rather than claiming it is sent',
        () async {
      backend.allOffline = true;
      final flow = await begin();
      await flow.answer(const CodedValue('fever'), 'Fever');
      await flow.answer(const NumberValue(3), '3 days');
      await flow.answer(const BoolValue(true), 'Yes');
      flow.continueToReview();
      await flow.submit();

      expect(flow.stage, FlowStage.submitted);
      expect(flow.queued, isTrue, reason: 'a code believed registered when it is not');
      expect(await db.draftFor(flow.intakeId), isNotNull);
    });

    test('a second tap cannot assemble a second record', () async {
      final flow = await begin();
      await flow.answer(const CodedValue('fever'), 'Fever');
      await flow.answer(const NumberValue(3), '3 days');
      await flow.answer(const BoolValue(true), 'Yes');
      flow.continueToReview();

      await Future.wait([flow.submit(), flow.submit()]);
      expect(backend.callsTo('/ingest'), 1);
    });
  });

  group('the status vocabulary survives the flow', () {
    test('skip is not_asked and records the prompt that was shown', () async {
      final flow = await begin(language: 'hi');
      await flow.skip();
      final answer = flow.answers['chief_complaint']!;
      expect(answer.status, FieldStatus.notAsked);
      expect(answer.value, isNull);
      // §9: the prompt actually shown, in the language actually used. It is
      // also what tells a patient's skip from a conclusion the walker drew.
      expect(answer.askedText, 'प्रश्न chief_complaint');
      expect(answer.wasPut, isTrue);
    });

    test("I don't know is unresolved, and is never no", () async {
      final flow = await begin();
      await flow.dontKnow();
      expect(flow.answers['chief_complaint']!.status, FieldStatus.unresolved);
      expect(flow.answers['chief_complaint']!.value, isNull);
    });
  });

  group('going back', () {
    test('returns to the last question the patient actually saw', () async {
      final flow = await begin();
      await flow.answer(const CodedValue('fever'), 'Fever');
      expect(flow.question!.questionId, 'duration');

      await flow.back();
      expect(flow.question!.questionId, 'chief_complaint');
      expect(flow.answers.containsKey('chief_complaint'), isFalse);
    });

    test('is not offered on the first question', () async {
      final flow = await begin();
      expect(flow.canGoBack, isFalse);
    });

    test('changing the complaint drops the branch it no longer asks', () async {
      final flow = await begin();
      await flow.answer(const CodedValue('chest_pain'), 'Chest pain');
      await flow.answer(const BoolValue(false), 'No');
      expect(flow.answers.containsKey('dyspnoea'), isTrue);

      await flow.back();
      await flow.back();
      await flow.answer(const CodedValue('fever'), 'Fever');

      // Otherwise the record carries an answer to a question this intake no
      // longer asks, against a branch nobody walked.
      expect(flow.answers.containsKey('dyspnoea'), isFalse);
      expect(flow.question!.questionId, 'duration');
    });
  });

  group('resuming', () {
    test('lands on the same question with the answers intact', () async {
      final flow = await begin();
      await flow.answer(const CodedValue('fever'), 'Fever');
      // The app dies here. Everything below reads only what is on disk.

      final draft = await db.draftFor(flow.intakeId);
      final resumed = IntakeFlow.resume(
        database: db,
        queue: queue,
        documents: documents,
        bundle: cardiacBundle(),
        draft: draft!,
        appVersion: '1.0.0',
      );

      expect(resumed!.question!.questionId, 'duration');
      expect(resumed.intakeId, flow.intakeId);
      // The same key, so finishing after a crash is not a second intake.
      expect(resumed.idempotencyKey, flow.idempotencyKey);
      final complaint = resumed.answers['chief_complaint']!;
      expect(complaint.status, FieldStatus.answered);
      expect((complaint.value as CodedValue).code, 'fever');
      expect(complaint.originalText, 'Fever');
    });

    test('every answer type round-trips through the draft', () async {
      final flow = await begin();
      await flow.answer(const CodedValue('fever'), 'Fever');
      await flow.answer(const NumberValue(3, unit: 'day'), '3 days');

      final draft = await db.draftFor(flow.intakeId);
      final resumed = IntakeFlow.resume(
        database: db,
        queue: queue,
        documents: documents,
        bundle: cardiacBundle(),
        draft: draft!,
        appVersion: '1.0.0',
      )!;

      final duration = resumed.answers['duration']!.value! as NumberValue;
      expect(duration.value, 3);
      expect(duration.unit, 'day', reason: 'the unit hint the backend reads');
    });

    test('refuses a draft written against different content', () async {
      final flow = await begin();
      await flow.answer(const CodedValue('fever'), 'Fever');
      final draft = await db.draftFor(flow.intakeId);

      final moved = ContentBundle.parse(jsonEncode(<String, dynamic>{
        'bundle_format': '1',
        'content_version': 'questions-2026-10-01',
        'schema_version': '0.1',
        'languages': ['en'],
        'sections': ['hpi'],
        'core': ['chief_complaint'],
        'branches': <String, dynamic>{},
        'ayurveda': <String>[],
        'questions': [question('chief_complaint')],
        'red_flag_rules': <dynamic>[],
      }));

      // Answers recorded against questions that have since changed are answers
      // to questions nobody can now read.
      expect(
        IntakeFlow.resume(
          database: db,
          queue: queue,
          documents: documents,
          bundle: moved,
          draft: draft!,
          appVersion: '1.0.0',
        ),
        isNull,
      );
    });
  });

  group('the draft is written before the next question is shown', () {
    test('after every single answer', () async {
      final flow = await begin();
      await flow.answer(const CodedValue('fever'), 'Fever');

      final stored = DraftCodec.decode((await db.draftFor(flow.intakeId))!.answersJson);
      expect(stored.keys, contains('chief_complaint'));
    });
  });

  group('documents', () {
    Future<IntakeFlow> throughTheInterview() async {
      final flow = await begin();
      await flow.answer(const CodedValue('fever'), 'Fever');
      await flow.answer(const NumberValue(3), '3 days');
      await flow.answer(const BoolValue(true), 'Yes');
      return flow;
    }

    test('come after the interview and before the review', () async {
      final flow = await throughTheInterview();
      expect(flow.stage, FlowStage.documents);
      expect(flow.pages, isEmpty);
    });

    test('a captured page is stored downscaled, with no metadata', () async {
      final flow = await throughTheInterview();
      picker.next = encodeWithMetadata(sheet(width: 3000, height: 4000));

      await flow.addPage(fromCamera: true);

      expect(flow.pages, hasLength(1));
      final stored = img.decodeJpg(flow.pages.single.file.readAsBytesSync())!;
      // §8: cap the long edge, and strip EXIF including GPS. A prescription
      // photo carrying the patient's home coordinates is the leak nobody
      // thinks about.
      expect(stored.height, 2000);
      expect(stored.exif.imageIfd.isEmpty, isTrue);
    });

    test('a blurred page is refused and nothing is written', () async {
      final flow = await throughTheInterview();
      picker.next = Uint8List.fromList(
        img.encodeJpg(sheet(width: 1600, height: 2200, sharp: false)),
      );

      await flow.addPage(fromCamera: true);

      expect(flow.rejectedQuality, PageQuality.blurred);
      expect(flow.pages, isEmpty);
      // A page the patient is about to retake must leave no file behind, or
      // the queue uploads it the moment they give up and press continue.
      expect(scratch.listSync(), isEmpty);
      expect(await db.documentsFor(flow.intakeId), isEmpty);
    });

    test('removing a page deletes the file, not just the row', () async {
      final flow = await throughTheInterview();
      picker.next = Uint8List.fromList(img.encodeJpg(sheet()));
      await flow.addPage(fromCamera: false);
      final file = flow.pages.single.file;

      await flow.removePage(flow.pages.single.documentId);

      expect(flow.pages, isEmpty);
      expect(file.existsSync(), isFalse);
    });

    test('a cancelled picker changes nothing', () async {
      final flow = await throughTheInterview();
      picker.next = null;
      await flow.addPage(fromCamera: true);
      expect(flow.pages, isEmpty);
      expect(flow.rejectedQuality, isNull);
    });

    test('a page that is not an image is a message, not a crash', () async {
      final flow = await throughTheInterview();
      picker.next = Uint8List.fromList([37, 80, 68, 70, 45, 49]); // "%PDF-1"
      await flow.addPage(fromCamera: false);
      expect(flow.pages, isEmpty);
      expect(flow.rejectedQuality, isNotNull);
    });

    test('go out with the intake and are gone from the phone after', () async {
      final flow = await throughTheInterview();
      picker.next = Uint8List.fromList(img.encodeJpg(sheet()));
      await flow.addPage(fromCamera: true);
      final file = flow.pages.single.file;

      flow.continueToReview();
      await flow.submit();

      expect(backend.callsTo('/documents'), 1);
      expect(file.existsSync(), isFalse, reason: '§15 item 9');
    });
  });

  group('the returning-patient check', () {
    test('a confirmed fact is not asked again', () async {
      final flow = await begin(confirmed: const [
        ConfirmedFact(
          fieldId: 'dyspnoea',
          label: 'Breathlessness',
          value: 'yes',
          fromIntakeId: 'intake-earlier-visit',
          originallyRecorded: '2026-03-01',
        ),
      ]);
      await flow.answer(const CodedValue('chest_pain'), 'Chest pain');

      // §5: never re-asks confirmed history from scratch.
      expect(flow.answers['dyspnoea']!.status, FieldStatus.answered);
      expect(flow.answers['dyspnoea']!.originalText, 'Breathlessness');
      expect(flow.question?.questionId, isNot('dyspnoea'));

      // Answered, and answered *elsewhere*. Without this the record says the
      // patient answered a question today that nobody put to them, and a
      // physician cannot tell it from a fresh answer.
      final carried = flow.answers['dyspnoea']!.carriedForward;
      expect(carried, isNotNull);
      expect(carried!.fromIntakeId, 'intake-earlier-visit');
      expect(carried.originallyRecorded, '2026-03-01');
      expect(carried.confirmedToday, isTrue);
    });

    test('a confirmed fact produces no turn, because none was put', () async {
      final flow = await begin(confirmed: const [
        ConfirmedFact(
          fieldId: 'duration',
          label: 'Three days',
          value: '3',
          fromIntakeId: 'intake-earlier-visit',
          originallyRecorded: '2026-03-01',
        ),
      ]);
      await flow.answer(const CodedValue('fever'), 'Fever');
      await flow.answer(const BoolValue(true), 'Yes'); // the Ayurveda question
      flow.continueToReview();
      await flow.submit();

      final ingest = backend.calls.firstWhere((c) => c.path.contains('/ingest'));
      final body = ingest.body! as Map<String, dynamic>;
      final turns = body['turns'] as List<dynamic>;
      expect(
        turns.where((t) => (t as Map)['question_id'] == 'duration'),
        isEmpty,
        reason: 'inventing a turn would claim the patient was shown a question',
      );
      expect(((body['fields'] as Map)['duration'] as Map)['source_turn'], isNull);

      // 0.2's whole addition, on the wire.
      expect(
        ((body['fields'] as Map)['duration'] as Map)['carried_forward'],
        {
          'from_intake_id': 'intake-earlier-visit',
          'originally_recorded': '2026-03-01',
          'confirmed_today': true,
        },
      );
    });

    test('a 0.1 bundle never receives the 0.2 key', () async {
      // 0.1 sets `extra="forbid"`, so a `carried_forward` sent to a backend
      // that predates it fails the whole payload — and silently, because ingest
      // answers an unparseable payload with a 200 and the app checks the status
      // code. That is the defect that stored every app intake as
      // `needs_manual_review` for a fortnight; this is the guard against the
      // same shape of mistake in the other direction.
      final flow = await begin(
        bundle: cardiacBundle(schemaVersion: '0.1'),
        confirmed: const [
          ConfirmedFact(
            fieldId: 'duration',
            label: 'Three days',
            value: '3',
            fromIntakeId: 'intake-earlier-visit',
            originallyRecorded: '2026-03-01',
          ),
        ],
      );
      await flow.answer(const CodedValue('fever'), 'Fever');
      await flow.answer(const BoolValue(true), 'Yes');
      flow.continueToReview();
      await flow.submit();

      final ingest = backend.calls.firstWhere((c) => c.path.contains('/ingest'));
      final body = ingest.body! as Map<String, dynamic>;
      expect(body['schema_version'], '0.1');
      final duration = (body['fields'] as Map)['duration'] as Map;
      expect(duration.containsKey('carried_forward'), isFalse);
      // The fact itself still travels. What is dropped is the provenance the
      // older contract has no place for, not the answer.
      expect(duration['status'], 'answered');
    });

    test('a fact with no usable provenance is still carried, without the key',
        () async {
      // `verified_at` unparseable means the app does not know when the hospital
      // recorded this. 0.2 requires a real date, so the choice is between
      // dropping the provenance and failing the intake; the answer the patient
      // just confirmed is worth more than the note about where it came from.
      final flow = await begin(confirmed: const [
        ConfirmedFact(
          fieldId: 'duration',
          label: 'Three days',
          value: '3',
          fromIntakeId: 'intake-earlier-visit',
          originallyRecorded: '',
        ),
      ]);
      expect(flow.answers['duration']!.status, FieldStatus.answered);
      expect(flow.answers['duration']!.carriedForward, isNull);
    });

    test('a carried fact the bundle no longer asks is left alone', () async {
      // The hospital still holds it; it is simply not this interview's to
      // restate, and inventing a field for it would put an answer in the
      // record against a question that does not exist.
      final flow = await begin(confirmed: const [
        ConfirmedFact(
          fieldId: 'gone_from_bundle',
          label: 'x',
          value: 'y',
          fromIntakeId: 'intake-earlier-visit',
          originallyRecorded: '2026-03-01',
        ),
      ]);
      expect(flow.answers.containsKey('gone_from_bundle'), isFalse);
    });
  });
}

/// A picker that hands over bytes a test chose, with no platform channel.
class FakePicker implements PagePicker {
  Uint8List? next;

  @override
  Future<Uint8List?> pick({required bool fromCamera}) async => next;
}

/// A page of black bars on cream, which is what the preparer's blur check was
/// calibrated against.
img.Image sheet({int width = 1600, int height = 2200, bool sharp = true}) {
  final image = img.Image(width: width, height: height);
  img.fill(image, color: img.ColorRgb8(245, 245, 240));
  for (var y = 100; y < height - 100; y += 90) {
    img.fillRect(
      image,
      x1: 120,
      y1: y,
      x2: width - 120,
      y2: y + 28,
      color: img.ColorRgb8(20, 20, 20),
    );
  }
  return sharp ? image : img.gaussianBlur(image, radius: 12);
}

/// A JPEG that demonstrably carries EXIF, so the strip test asserts something.
Uint8List encodeWithMetadata(img.Image image) {
  image.exif.imageIfd['Make'] = 'MediKioskTest';
  image.exif.gpsIfd['GPSLatitude'] = 28;
  return Uint8List.fromList(img.encodeJpg(image, quality: 92));
}
