import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:indai_worker/config.dart';
import 'package:indai_worker/services/api_error.dart';

void main() {
  group('normalizeApiUrl tests', () {
    test('normalizes raw IP without port or scheme', () {
      expect(normalizeApiUrl('192.168.1.23'), 'http://192.168.1.23:8000/api');
    });

    test('normalizes raw IP with port and without scheme', () {
      expect(normalizeApiUrl('192.168.1.23:8000'), 'http://192.168.1.23:8000/api');
    });

    test('normalizes full HTTP URL with trailing slash', () {
      expect(normalizeApiUrl('http://192.168.1.23:8000/'), 'http://192.168.1.23:8000/api');
    });

    test('preserves HTTPS URL with /api path', () {
      expect(normalizeApiUrl('https://x.example.com/api'), 'https://x.example.com/api');
    });

    test('appends /api to HTTPS URL without /api', () {
      expect(normalizeApiUrl('https://x.example.com'), 'https://x.example.com/api');
    });

    test('normalizes emulator address correctly', () {
      expect(normalizeApiUrl('10.0.2.2'), 'http://10.0.2.2:8000/api');
      expect(normalizeApiUrl('http://10.0.2.2:8000'), 'http://10.0.2.2:8000/api');
      expect(normalizeApiUrl('http://10.0.2.2:8000/api'), 'http://10.0.2.2:8000/api');
      expect(normalizeApiUrl('http://10.0.2.2:8000/api/'), 'http://10.0.2.2:8000/api');
    });

    test('normalizes USB localhost address correctly', () {
      expect(normalizeApiUrl('127.0.0.1'), 'http://127.0.0.1:8000/api');
      expect(normalizeApiUrl('127.0.0.1:8000'), 'http://127.0.0.1:8000/api');
      expect(normalizeApiUrl('http://127.0.0.1:8000'), 'http://127.0.0.1:8000/api');
    });

    test('throws FormatException on empty string', () {
      expect(() => normalizeApiUrl(''), throwsA(isA<FormatException>()));
      expect(() => normalizeApiUrl('   '), throwsA(isA<FormatException>()));
    });

    test('throws FormatException on garbage inputs', () {
      expect(() => normalizeApiUrl('http://'), throwsA(isA<FormatException>()));
      expect(() => normalizeApiUrl(':::invalid'), throwsA(isA<FormatException>()));
      expect(() => normalizeApiUrl('http://.invalid'), throwsA(isA<FormatException>()));
      expect(() => normalizeApiUrl('http://invalid host:8000'), throwsA(isA<FormatException>()));
    });
  });

  group('classifyApiError tests', () {
    const testUrl = 'http://192.168.1.23:8000/api';

    test('(a) classifies SocketException / connection refused', () {
      const error = SocketException('Connection refused', osError: OSError('Connection refused', 111));
      final msg = classifyApiError(error, targetUrl: testUrl);
      expect(msg, contains('Cannot reach the server at http://192.168.1.23:8000/api'));
      expect(msg, contains('start-backend.ps1'));
      expect(msg, contains('allow-backend-firewall.ps1'));
      expect(msg, contains('same Wi-Fi'));
    });

    test('(b) classifies TimeoutException', () {
      final error = TimeoutException('The request timed out');
      final msg = classifyApiError(error, targetUrl: testUrl);
      expect(msg, contains('Connection to http://192.168.1.23:8000/api timed out'));
      expect(msg, contains('hotspot'));
    });

    test('(c) classifies Cleartext HTTP blocked error', () {
      final error = Exception('CLEARTEXT communication to 192.168.1.23 not permitted by network security policy');
      final msg = classifyApiError(error, targetUrl: testUrl);
      expect(msg, contains('Android blocked cleartext HTTP'));
      expect(msg, contains('network_security_config.xml'));
    });

    test('(d) classifies DNS / invalid host FormatException', () {
      const error = FormatException('Invalid host name: "bad..host"');
      final msg = classifyApiError(error, targetUrl: testUrl);
      expect(msg, contains('Could not resolve server address'));
      expect(msg, contains('Server settings'));
    });

    test('(e) classifies 401 Unauthorized', () {
      final msg = classifyApiError(Exception('Unauthorized'), targetUrl: testUrl, statusCode: 401);
      expect(msg, equals('Invalid username or password.'));
    });

    test('(f) classifies 429 Too Many Requests', () {
      final msg = classifyApiError(Exception('Too Many Requests'), targetUrl: testUrl, statusCode: 429);
      expect(msg, equals('Too many attempts, try again later.'));
    });

    test('(g) classifies 500 Server Error', () {
      final msg = classifyApiError(Exception('Internal Server Error'), targetUrl: testUrl, statusCode: 500);
      expect(msg, contains('Server error (HTTP 500)'));
      expect(msg, contains('backend console/logs'));
    });
  });
}
