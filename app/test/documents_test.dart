/// Preparing a photographed document — 2/3 §8, §15 item 10.
///
/// The load-bearing test is the GPS one. A prescription photographed at home
/// carries the patient's home coordinates in its EXIF block; the patient cannot
/// see it, nobody thinks about it, and it travels into object storage and back
/// out through a signed URL.
library;

import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:medikiosk_app/documents/prepare.dart';

/// A synthetic "document": a light page with dark text-like marks, so the
/// sharpness measure has real edges to find.
img.Image page({int width = 1600, int height = 2200, bool sharp = true}) {
  final image = img.Image(width: width, height: height);
  img.fill(image, color: img.ColorRgb8(245, 245, 240));
  for (var line = 0; line < 30; line++) {
    final y = (height * 0.1 + line * (height * 0.025)).round();
    img.fillRect(
      image,
      x1: (width * 0.1).round(),
      y1: y,
      x2: (width * 0.9).round(),
      y2: y + 8,
      color: img.ColorRgb8(20, 20, 20),
    );
  }
  return sharp ? image : img.gaussianBlur(image, radius: 12);
}

/// A JPEG carrying camera metadata.
///
/// `Make` is used as the probe rather than a GPS coordinate because the `image`
/// package's JPEG encoder does not round-trip a synthetic GPS sub-IFD, so a GPS
/// fixture would assert nothing. `Make` demonstrably *does* survive a plain
/// re-encode — which is the property under test: metadata that would otherwise
/// pass straight through the pipeline. A real phone photograph carries GPS in
/// the same EXIF block that carries `Make`, and the fix clears the block
/// wholesale rather than tag by tag.
Uint8List encodeWithMetadata(img.Image image) {
  image.exif.imageIfd['Make'] = 'TestPhone';
  image.exif.imageIfd['Model'] = 'TP-1';
  image.exif.gpsIfd[1] = 'N';
  return Uint8List.fromList(img.encodeJpg(image, quality: 92));
}

void main() {
  const preparer = DocumentPreparer();

  group('privacy', () {
    test('the fixture proves metadata would otherwise survive', () {
      // Without this, the two tests below could pass against a pipeline that
      // never had any metadata to strip.
      final original = encodeWithMetadata(page());
      expect(img.decodeJpg(original)!.exif.imageIfd.isEmpty, isFalse);
    });

    test('re-encoding alone does NOT strip it — which is why the code is explicit',
        () {
      // The bug this test exists to prevent coming back. `copyResize` copies
      // the source's ExifData onto the new image and the encoder writes it out
      // again, so "we re-encode, therefore EXIF is gone" is false.
      final original = img.decodeJpg(encodeWithMetadata(page()))!;
      final naive = img.copyResize(original, width: 800);
      final result = img.decodeJpg(Uint8List.fromList(img.encodeJpg(naive)))!;
      expect(result.exif.imageIfd.isEmpty, isFalse,
          reason: 'if this ever passes, the explicit strip may look unnecessary');
    });

    test('preparation leaves no EXIF at all', () {
      // §8, and the reason it is the whole block rather than named tags: a
      // prescription photographed at home carries the patient's home
      // coordinates, and stripping tag by tag leaves whatever the encoder did
      // not understand.
      final prepared = preparer.prepare(encodeWithMetadata(page()))!;
      final result = img.decodeJpg(prepared.bytes)!;
      expect(result.exif.imageIfd.isEmpty, isTrue, reason: 'camera make/model');
      expect(result.exif.gpsIfd.isEmpty, isTrue, reason: 'location');
      expect(result.exif.exifIfd.isEmpty, isTrue);
      expect(result.exif.isEmpty, isTrue);
    });
  });

  group('downscaling', () {
    test('the long edge is capped', () {
      // 12 megapixels of an A5 sheet is twenty seconds of a patient's mobile
      // data for no OCR benefit.
      final prepared = preparer.prepare(
        Uint8List.fromList(img.encodeJpg(page(width: 4000, height: 5200))),
      )!;
      expect(prepared.height, 2000);
      expect(prepared.width, lessThan(2000));
    });

    test('a portrait page keeps its aspect ratio', () {
      final prepared = preparer.prepare(
        Uint8List.fromList(img.encodeJpg(page(width: 3000, height: 4000))),
      )!;
      final ratio = prepared.width / prepared.height;
      expect(ratio, closeTo(3000 / 4000, 0.01));
    });

    test('a landscape page is capped on its width', () {
      final prepared = preparer.prepare(
        Uint8List.fromList(img.encodeJpg(page(width: 4000, height: 3000))),
      )!;
      expect(prepared.width, 2000);
    });

    test('an already-small page is not upscaled', () {
      final prepared = preparer.prepare(
        Uint8List.fromList(img.encodeJpg(page(width: 1200, height: 1600))),
      )!;
      expect(prepared.width, 1200);
    });

    test('preparation makes the upload smaller', () {
      final original = Uint8List.fromList(
        img.encodeJpg(page(width: 4000, height: 5200), quality: 100),
      );
      final prepared = preparer.prepare(original)!;
      expect(prepared.bytes.length, lessThan(original.length));
    });
  });

  group('quality, checked while the paper is still in front of the patient', () {
    test('a sharp page passes', () {
      final prepared = preparer.prepare(
        Uint8List.fromList(img.encodeJpg(page())),
      )!;
      expect(prepared.quality, isNot(PageQuality.blurred));
      expect(prepared.isUsable, isTrue);
    });

    test('a blurred page is caught', () {
      // Discovered by the OCR worker ten minutes later, this is a photograph
      // nobody can retake: the patient has put the paper away and is in the
      // queue.
      final prepared = preparer.prepare(
        Uint8List.fromList(img.encodeJpg(page(sharp: false))),
      )!;
      expect(prepared.quality, PageQuality.blurred);
      expect(prepared.isUsable, isFalse);
    });

    test('a page below the resolution floor is refused', () {
      final prepared = preparer.prepare(
        Uint8List.fromList(img.encodeJpg(page(width: 500, height: 640))),
      )!;
      expect(prepared.quality, PageQuality.tooSmall);
      expect(prepared.isUsable, isFalse);
    });

    test('a possibly-cropped page warns but does not block', () {
      // The heuristic is wrong often enough that refusing on it would send
      // patients to re-photograph perfectly good documents.
      final cropped = PreparedPage(
        bytes: Uint8List.fromList([]),
        quality: PageQuality.possiblyCropped,
        width: 2000,
        height: 1400,
      );
      expect(cropped.isUsable, isTrue);
    });

    test('bytes that are not an image return null rather than throwing', () {
      // A patient picking a PDF or a corrupt file from the gallery must get a
      // message, not a crash.
      expect(preparer.prepare(Uint8List.fromList([0, 1, 2, 3, 4])), isNull);
    });
  });
}
