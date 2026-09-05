/// Preparing a photographed document before upload — 2/3 §8.
///
/// Three things happen here and each has a reason:
///
/// **The EXIF block is stripped, including GPS.** A prescription photographed at
/// home carries the patient's home coordinates in its metadata. Nobody thinks
/// about this, the patient cannot see it, and it travels all the way into object
/// storage and out again through a signed URL. Re-encoding the pixels is the
/// only reliable way to be rid of it — editing tags out leaves whatever the
/// encoder did not understand.
///
/// **The long edge is capped.** A modern phone camera produces 12 megapixels of
/// a sheet of A5 paper. 2000px on the long edge is ample for OCR of printed and
/// handwritten prescriptions, and the difference is a patient on mobile data
/// waiting twenty seconds instead of three.
///
/// **Quality is checked while the paper is still in front of the patient.** A
/// blurred photograph discovered by the OCR worker ten minutes later is a
/// photograph nobody can retake — the patient has put the paper away and is in
/// the queue.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// What a quality check concluded.
enum PageQuality {
  ok,

  /// Below the resolution floor. OCR of handwriting needs pixels.
  tooSmall,

  /// Low edge energy — the page is out of focus or motion-blurred.
  blurred,

  /// The page appears to run off an edge of the frame.
  possiblyCropped,
}

class PreparedPage {
  const PreparedPage({
    required this.bytes,
    required this.quality,
    required this.width,
    required this.height,
  });

  final Uint8List bytes;
  final PageQuality quality;
  final int width;
  final int height;

  bool get isUsable => quality == PageQuality.ok || quality == PageQuality.possiblyCropped;
}

class DocumentPreparer {
  const DocumentPreparer({
    this.maxLongEdge = 2000,
    this.minLongEdge = 900,
    this.blurThreshold = 800.0,
  });

  final int maxLongEdge;

  /// Below this the image is refused outright. A 640px photograph of a
  /// prescription cannot be read reliably by any OCR, and accepting it means
  /// the physician sees a "could not read" three minutes before the consultation
  /// instead of a reshoot prompt now.
  final int minLongEdge;

  /// Variance-of-Laplacian threshold.
  ///
  /// **Calibrated against synthetic fixtures only.** A generated page of black
  /// bars on white scores ~11000 sharp and ~250 blurred, so 800 separates them
  /// with margin — but real prescriptions on cream paper under OPD fluorescent
  /// light will not score like that. This needs tuning against a corpus of real
  /// photographs before it is trusted, and it is listed in
  /// `docs/CLINICAL_REVIEW_QUEUE.md` for exactly that.
  ///
  /// Erring low is deliberate: refusing a usable photograph sends a patient to
  /// re-photograph a document for no reason, which they will not do twice.
  final double blurThreshold;

  /// Decode, assess, downscale and re-encode.
  ///
  /// Returns `null` when the bytes are not a decodable image at all.
  PreparedPage? prepare(Uint8List raw) {
    final img.Image? decoded;
    try {
      decoded = img.decodeImage(raw);
    } on Object {
      // `decodeImage` throws rather than returning null on truncated or
      // non-image bytes. A patient picking a PDF or a half-downloaded file out
      // of their gallery must get a message, not a crash.
      return null;
    }
    if (decoded == null) return null;

    final longEdge = math.max(decoded.width, decoded.height);
    if (longEdge < minLongEdge) {
      return PreparedPage(
        bytes: raw,
        quality: PageQuality.tooSmall,
        width: decoded.width,
        height: decoded.height,
      );
    }

    // `copyResize` is skipped when the image is already small enough, so
    // `resized` may be the same object as `decoded`. That is fine — nothing
    // else reads `decoded` afterwards — but it is why the EXIF reset below
    // happens on `resized` rather than on a copy.
    final resized = longEdge > maxLongEdge
        ? img.copyResize(
            decoded,
            width: decoded.width >= decoded.height ? maxLongEdge : null,
            height: decoded.height > decoded.width ? maxLongEdge : null,
            interpolation: img.Interpolation.average,
          )
        : decoded;

    // Sharpness is measured on the *resized* image, because that is what the
    // OCR will actually read. A 12MP photo that looks sharp at full size can be
    // mush at 2000px.
    final sharpness = _varianceOfLaplacian(resized);
    final quality = sharpness < blurThreshold
        ? PageQuality.blurred
        : (_touchesEdge(resized) ? PageQuality.possiblyCropped : PageQuality.ok);

    // **Strip the metadata explicitly.** Re-encoding alone does *not* do it:
    // `copyResize` copies the source's `ExifData` onto the new image, and the
    // JPEG encoder writes it back out — so a resized photograph still carries
    // the camera make and the GPS IFD pointer. Replacing the whole `ExifData`
    // is the only reliable clear, because the individual IFDs expose no
    // `clear()`.
    //
    // Verified by `test/documents_test.dart`, which sets a tag that
    // demonstrably survives a plain re-encode and asserts it does not survive
    // this.
    resized.exif = img.ExifData();
    final encoded = Uint8List.fromList(img.encodeJpg(resized, quality: 85));

    return PreparedPage(
      bytes: encoded,
      quality: quality,
      width: resized.width,
      height: resized.height,
    );
  }

  /// Variance of the Laplacian — the standard cheap focus measure.
  ///
  /// A sharp image has strong second derivatives at edges; a blurred one does
  /// not. Sampled on a grid rather than every pixel: this runs on a mid-range
  /// phone while the patient waits, and the statistic is stable under sampling.
  double _varianceOfLaplacian(img.Image image) {
    final step = math.max(1, math.min(image.width, image.height) ~/ 300);
    final values = <double>[];
    for (var y = step; y < image.height - step; y += step) {
      for (var x = step; x < image.width - step; x += step) {
        final centre = _luma(image, x, y);
        final laplacian = 4 * centre -
            _luma(image, x - step, y) -
            _luma(image, x + step, y) -
            _luma(image, x, y - step) -
            _luma(image, x, y + step);
        values.add(laplacian);
      }
    }
    if (values.length < 2) return 0;
    final mean = values.reduce((a, b) => a + b) / values.length;
    final variance =
        values.map((v) => (v - mean) * (v - mean)).reduce((a, b) => a + b) /
            values.length;
    return variance;
  }

  double _luma(img.Image image, int x, int y) {
    final pixel = image.getPixel(x, y);
    return 0.299 * pixel.r + 0.587 * pixel.g + 0.114 * pixel.b;
  }

  /// Does the page appear to run off the frame?
  ///
  /// A heuristic, and flagged as *possibly* cropped rather than refused: the
  /// page is usually darker than the border, so a border strip that is as dark
  /// as the page centre suggests the paper continues past the edge. Wrong often
  /// enough that it warns and never blocks.
  bool _touchesEdge(img.Image image) {
    final border = <double>[];
    final centre = <double>[];
    final inset = math.max(2, image.width ~/ 60);
    for (var x = 0; x < image.width; x += math.max(1, image.width ~/ 100)) {
      border.add(_luma(image, x, inset));
      border.add(_luma(image, x, image.height - inset - 1));
      centre.add(_luma(image, x, image.height ~/ 2));
    }
    if (border.isEmpty || centre.isEmpty) return false;
    final borderMean = border.reduce((a, b) => a + b) / border.length;
    final centreMean = centre.reduce((a, b) => a + b) / centre.length;
    return (borderMean - centreMean).abs() < 12;
  }
}
