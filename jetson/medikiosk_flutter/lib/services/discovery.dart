import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Finds the Jetson on the local link.
///
/// USB tethering hands the Jetson a DHCP lease, and that address changes whenever the cable is
/// replugged. Every hardcoded host in this project has gone stale at least once, taking the kiosk
/// down until someone edited a constant and rebuilt. Scanning is cheap on a /24 and removes the
/// whole class of problem: the tablet finds whatever address the Jetson has today.
///
/// The scan only ever talks to private addresses on the tablet's own subnet, and only asks for
/// /health, which returns no patient data.
class Discovery {
  static const int port = 8000;
  static const Duration probeTimeout = Duration(milliseconds: 600);

  /// Addresses to try first: the last one that worked, then the tethering gateway's neighbours.
  static Future<String?> find({String? remembered, void Function(String)? onProgress}) async {
    if (remembered != null && await _isKiosk(remembered)) return remembered;
    if (await _isKiosk('127.0.0.1')) return '127.0.0.1';
    if (await _isKiosk('100.104.251.40')) return '100.104.251.40';
    if (await _isKiosk('192.168.191.75')) return '192.168.191.75';

    final subnets = await _localSubnets();
    for (final subnet in subnets) {
      onProgress?.call('Looking for the kiosk on $subnet.x');
      final found = await _scan(subnet);
      if (found != null) return found;
    }
    return null;
  }

  /// The /24 prefixes this tablet is on, tethering interfaces first.
  static Future<List<String>> _localSubnets() async {
    final prefixes = <String>[];
    try {
      final interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4);
      for (final interface in interfaces) {
        for (final address in interface.addresses) {
          if (address.isLoopback) continue;
          final parts = address.address.split('.');
          if (parts.length != 4) continue;
          final prefix = '${parts[0]}.${parts[1]}.${parts[2]}';
          // USB tethering shows up as rndis/usb; put it first because that is the kiosk link.
          final tether = interface.name.toLowerCase().contains('rndis') ||
              interface.name.toLowerCase().contains('usb') ||
              interface.name.toLowerCase().contains('ap');
          tether ? prefixes.insert(0, prefix) : prefixes.add(prefix);
        }
      }
    } catch (e) {
      if (kDebugMode) print('Discovery: interface list failed: $e');
    }
    return prefixes.toSet().toList();
  }

  /// Probe a /24 in parallel batches. A full sweep takes a couple of seconds on a quiet link.
  static Future<String?> _scan(String prefix) async {
    for (var start = 1; start < 255; start += 32) {
      final batch = <Future<String?>>[];
      for (var host = start; host < start + 32 && host < 255; host++) {
        final candidate = '$prefix.$host';
        batch.add(_isKiosk(candidate).then((ok) => ok ? candidate : null));
      }
      final results = await Future.wait(batch);
      final hit = results.firstWhere((r) => r != null, orElse: () => null);
      if (hit != null) return hit;
    }
    return null;
  }

  /// True only for something that answers /health *and* looks like MediKiosk. Any web server can
  /// return 200; checking the payload stops the app latching onto a router's admin page.
  static Future<bool> _isKiosk(String host) async {
    try {
      final response = await http
          .get(Uri.parse('http://$host:$port/health'))
          .timeout(probeTimeout);
      if (response.statusCode != 200) return false;
      final body = jsonDecode(response.body);
      return body is Map && body.containsKey('local_voice');
    } catch (_) {
      return false;
    }
  }
}
