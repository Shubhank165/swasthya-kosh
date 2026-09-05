/// The hospital and department picker — 2/3 §5 screen 2.
library;

import '../core/api.dart';

class Department {
  const Department({required this.code, required this.display});
  final String code;
  final String display;
}

class Hospital {
  const Hospital({
    required this.id,
    required this.displayName,
    required this.timezone,
    required this.defaultLanguage,
    required this.departments,
    this.location,
  });

  factory Hospital.fromJson(Map<String, dynamic> json) => Hospital(
        id: json['hospital_id'] as String,
        displayName: json['display_name'] as String,
        location: json['location'] as String?,
        timezone: json['timezone'] as String? ?? 'Asia/Kolkata',
        defaultLanguage: json['default_language'] as String? ?? 'en',
        departments: [
          for (final d in (json['departments'] as List<dynamic>? ?? []))
            Department(
              code: (d as Map<String, dynamic>)['code'] as String,
              display: d['display'] as String,
            ),
        ],
      );

  final String id;
  final String displayName;
  final String? location;
  final String timezone;
  final String defaultLanguage;
  final List<Department> departments;
}

class HospitalRepository {
  HospitalRepository({required ApiClient api}) : _api = api;
  final ApiClient _api;

  Future<List<Hospital>> list() async {
    final response = await _api.get<Map<String, dynamic>>('/hospitals');
    if (response.statusCode != 200 || response.data == null) return const [];
    return [
      for (final h in (response.data!['hospitals'] as List<dynamic>? ?? []))
        Hospital.fromJson(h as Map<String, dynamic>),
    ];
  }
}
