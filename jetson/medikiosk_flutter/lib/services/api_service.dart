import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

class ApiService {
  final String host;
  final int port;

  ApiService({this.host = '127.0.0.1', this.port = 8000});

  String get baseUrl => 'http://$host:$port';

  Future<Map<String, dynamic>> checkHealth() async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl/health'))
          .timeout(const Duration(seconds: 4));
      if (response.statusCode == 200) {
        return jsonDecode(response.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return {'status': 'down'};
  }

  /// The patient's slip as PDF bytes. Same ownership headers as a scan.
  Future<Uint8List> slipPdf({required Map<String, String> headers}) async {
    final response = await http.get(Uri.parse('$baseUrl/api/slip.pdf'), headers: headers)
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) throw Exception('Slip not ready (${response.statusCode})');
    return response.bodyBytes;
  }

  Future<Map<String, dynamic>> scanAbhaCard(Uint8List imageBytes, {required Map<String, String> headers}) async {
    try {
      final uri = Uri.parse('$baseUrl/api/abha-scan');
      final request = http.MultipartRequest('POST', uri)
        ..followRedirects = false
        ..headers.addAll(headers)
        ..files.add(
          http.MultipartFile.fromBytes(
            'image',
            imageBytes,
            filename: 'abha_scan.jpg',
            contentType: MediaType('image', 'jpeg'),
          ),
        );

      final streamedResponse =
          await request.send().timeout(const Duration(seconds: 15));
      final response = await http.Response.fromStream(streamedResponse).timeout(const Duration(seconds: 30));

      final body = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode == 200) return body;
      return {'error': body['detail'] ?? 'Scan failed (${response.statusCode})'};
    } catch (e) {
      return {'found': false, 'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> scanDocument(Uint8List imageBytes, {required Map<String, String> headers}) async {
    try {
      final uri = Uri.parse('$baseUrl/api/ocr');
      final request = http.MultipartRequest('POST', uri)
        ..followRedirects = false
        ..headers.addAll(headers)
        ..files.add(
          http.MultipartFile.fromBytes(
            'image',
            imageBytes,
            filename: 'document_scan.jpg',
            contentType: MediaType('image', 'jpeg'),
          ),
        );

      final streamedResponse =
          await request.send().timeout(const Duration(seconds: 30));
      final response = await http.Response.fromStream(streamedResponse).timeout(const Duration(seconds: 30));

      final body = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode == 200) return body;
      return {'error': body['detail'] ?? 'Scan failed (${response.statusCode})'};
    } catch (e) {
      return {'lines': <String>[], 'error': e.toString()};
    }
  }
}
