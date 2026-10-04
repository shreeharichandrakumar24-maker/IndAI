import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';
import 'api_error.dart';

/// Thin client for the IndAI FastAPI backend — the only server this app uses.
/// Worker token auth: POST /worker-auth/login returns a Bearer token stored
/// in secure storage; every /worker/* call sends it. Prototype authentication.
class IndaiApi {
  IndaiApi({String? baseUrl, String? token})
      : _baseUrl = _initBaseUrl(baseUrl),
        _token = token;

  String _baseUrl;
  String? _token;
  void Function()? onAuthExpired;

  static String _initBaseUrl(String? customUrl) {
    if (customUrl != null && customUrl.trim().isNotEmpty) {
      try {
        return normalizeApiUrl(customUrl);
      } catch (_) {}
    }
    try {
      return normalizeApiUrl(kDefaultApiBaseUrl);
    } catch (_) {
      return 'http://10.0.2.2:8000/api';
    }
  }

  String get baseUrl => _baseUrl;

  void setBaseUrl(String url) {
    _baseUrl = normalizeApiUrl(url);
  }

  void setToken(String? token) => _token = token;
  String? get token => _token;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null && _token!.isNotEmpty) 'Authorization': 'Bearer $_token',
      };

  Uri _resolve(String path) {
    var p = path.trim();
    if (!p.startsWith('/')) {
      p = '/$p';
    }
    // If baseUrl ends with '/api' and path starts with '/api/' or is '/api', avoid duplicate '/api'
    if (_baseUrl.endsWith('/api')) {
      if (p == '/api') {
        return Uri.parse(_baseUrl);
      } else if (p.startsWith('/api/')) {
        p = p.substring(4); // e.g. /worker-auth/login
      }
    }
    return Uri.parse('$_baseUrl$p');
  }

  Future<dynamic> _get(String path, {Duration timeout = const Duration(seconds: 15)}) async {
    final uri = _resolve(path);
    final res = await http.get(uri, headers: _headers).timeout(timeout);
    if (res.statusCode == 401) throw _authErr();
    if (res.statusCode != 200) throw _err('GET', path, res);
    return jsonDecode(res.body);
  }

  Future<dynamic> _post(String path, [Map<String, dynamic>? body, Duration timeout = const Duration(seconds: 15)]) async {
    final uri = _resolve(path);
    final res = await http
        .post(uri, headers: _headers, body: body == null ? null : jsonEncode(body))
        .timeout(timeout);
    if (res.statusCode == 401) throw _authErr();
    if (res.statusCode != 200 && res.statusCode != 201) throw _err('POST', path, res);
    return jsonDecode(res.body);
  }

  Future<dynamic> _put(String path, Map<String, dynamic> body, {Duration timeout = const Duration(seconds: 15)}) async {
    final uri = _resolve(path);
    final res = await http
        .put(uri, headers: _headers, body: jsonEncode(body))
        .timeout(timeout);
    if (res.statusCode == 401) throw _authErr();
    if (res.statusCode != 200) throw _err('PUT', path, res);
    return jsonDecode(res.body);
  }

  Exception _authErr() {
    try {
      onAuthExpired?.call();
    } catch (_) {}
    return const AuthExpiredException();
  }

  Exception _err(String method, String path, http.Response res) {
    var detail = '';
    try {
      final j = jsonDecode(res.body);
      if (j is Map && j['detail'] != null) detail = ': ${j['detail']}';
    } catch (_) {}
    if (res.statusCode == 429) {
      return const ApiException(429, 'Too many attempts, try again later.');
    }
    return ApiException(res.statusCode, '$method $path -> ${res.statusCode}$detail');
  }

  /// Test connection to the backend /api/health endpoint with a 5-second timeout.
  Future<Map<String, dynamic>> testConnection([String? candidateUrl]) async {
    final targetBase = candidateUrl != null && candidateUrl.trim().isNotEmpty
        ? normalizeApiUrl(candidateUrl)
        : _baseUrl;

    final testUri = Uri.parse(
      targetBase.endsWith('/api') ? '$targetBase/health' : '$targetBase/api/health',
    );

    try {
      final res = await http.get(testUri).timeout(const Duration(seconds: 5));
      if (res.statusCode == 200) {
        final body = jsonDecode(res.body);
        final status = body is Map && body['status'] != null ? body['status'].toString() : 'ok';
        final message = body is Map && body['message'] != null ? body['message'].toString() : 'IndAI API is running';
        return {
          'success': true,
          'status': status,
          'message': message,
          'url': testUri.toString(),
        };
      } else {
        throw ApiException(res.statusCode, 'HTTP ${res.statusCode} ${res.reasonPhrase ?? ''}');
      }
    } catch (e) {
      final classified = classifyApiError(e, targetUrl: testUri.toString());
      return {
        'success': false,
        'error': classified,
        'url': testUri.toString(),
      };
    }
  }

  // ---- worker auth (prototype, token) ----
  Future<Map<String, dynamic>> workerLogin(String identifier, String password) async {
    final data = await _post('/api/worker-auth/login', {'identifier': identifier, 'password': password});
    return Map<String, dynamic>.from(data as Map);
  }

  Future<void> changePassword(String current, String next) async {
    await _post('/api/worker-auth/change-password', {'current_password': current, 'new_password': next});
  }

  // ---- worker self-service (all Bearer-token scoped) ----
  Future<Map<String, dynamic>> workerMe() async {
    final data = await _get('/api/worker/me');
    return Map<String, dynamic>.from(data as Map);
  }

  Future<List<dynamic>> workerTasks() async {
    final data = await _get('/api/worker/tasks');
    return data is List ? data : [];
  }

  Future<List<dynamic>> workerAlerts() async {
    final data = await _get('/api/worker/alerts');
    return data is List ? data : [];
  }

  Future<Map<String, dynamic>> workerTask(String id) async {
    final data = await _get('/api/worker/tasks/$id');
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> workerTaskStatus(String id, String status) async {
    final data = await _put('/api/worker/tasks/$id/status', {'status': status});
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> workerTaskProgress(String id, double progress) async {
    final data = await _put('/api/worker/tasks/$id/progress', {'progress': progress});
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> workerTaskOutput(String id, int quantity, {bool confirm = false}) async {
    final data = await _post('/api/worker/tasks/$id/output', {'quantity': quantity, 'confirm': confirm});
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> workerReportIncident(Map<String, dynamic> body) async {
    final data = await _post('/api/worker/incidents', body);
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> workerAvailability(String value) async {
    final data = await _put('/api/worker/availability', {'availability': value});
    return Map<String, dynamic>.from(data as Map);
  }

  // ---- shared task/production/telemetry reads (worker-scoped by backend) ----
  Future<Map<String, dynamic>> updateTask(String id, Map<String, dynamic> body) async {
    final data = await _put('/api/tasks/$id', body);
    return Map<String, dynamic>.from(data as Map);
  }

  Future<List<dynamic>> runsForOrder(String orderId) async {
    final data = await _get('/api/production?order_id=$orderId');
    return data is List ? data : [];
  }

  Future<Map<String, dynamic>> updateRun(String id, Map<String, dynamic> body) async {
    final data = await _put('/api/production/$id', body);
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>?> latestTelemetry(String machineId) async {
    final data = await _get('/api/telemetry/$machineId?limit=1');
    if (data is List && data.isNotEmpty) return Map<String, dynamic>.from(data.first as Map);
    return null;
  }

  Future<void> registerPushToken(String token) async {
    await _post('/api/push-tokens', {'token': token, 'platform': 'android'});
  }
}

class ApiException implements Exception {
  final int statusCode;
  final String message;
  const ApiException(this.statusCode, this.message);

  @override
  String toString() => message;
}

class AuthExpiredException implements Exception {
  const AuthExpiredException();
  @override
  String toString() => 'AuthExpired';
}

