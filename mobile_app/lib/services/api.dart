import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';

/// Thin client for the IndAI FastAPI backend. The Supabase access token
/// (from supabase_flutter session) authorizes every call.
class IndaiApi {
  IndaiApi(this._token);
  final String _token;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $_token',
      };

  Future<dynamic> _get(String path) async {
    final res = await http.get(Uri.parse('$kApiBaseUrl$path'), headers: _headers);
    if (res.statusCode != 200) throw Exception('GET $path -> ${res.statusCode}: ${res.body}');
    return jsonDecode(res.body);
  }

  Future<dynamic> _post(String path, [Map<String, dynamic>? body]) async {
    final res = await http.post(Uri.parse('$kApiBaseUrl$path'),
        headers: _headers, body: body == null ? null : jsonEncode(body));
    if (res.statusCode != 200) throw Exception('POST $path -> ${res.statusCode}: ${res.body}');
    return jsonDecode(res.body);
  }

  Future<dynamic> _patch(String path, Map<String, dynamic> body) async {
    final res = await http.patch(Uri.parse('$kApiBaseUrl$path'),
        headers: _headers, body: jsonEncode(body));
    if (res.statusCode != 200) throw Exception('PATCH $path -> ${res.statusCode}: ${res.body}');
    return jsonDecode(res.body);
  }

  Future<List<dynamic>> myAssignments() async {
    final data = await _get('/api/assignments/mine');
    return data is List ? data : [];
  }

  Future<Map<String, dynamic>> updateAssignment(String id, String status) async {
    final data = await _patch('/api/assignments/$id', {'status': status});
    return Map<String, dynamic>.from(data as Map);
  }

  Future<void> registerPushToken(String token) async {
    await _post('/api/push-tokens', {'token': token, 'platform': 'android'});
  }
}
