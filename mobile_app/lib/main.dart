import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'config.dart';
import 'services/api.dart';
import 'screens/login.dart';
import 'screens/change_password.dart';
import 'screens/home.dart';

const _tokenKey = 'indai.worker.token';
const _profileKey = 'indai.worker.profile';

const _storage = FlutterSecureStorage();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const IndaiWorkerApp());
}

class IndaiWorkerApp extends StatefulWidget {
  const IndaiWorkerApp({super.key});

  @override
  State<IndaiWorkerApp> createState() => _IndaiWorkerAppState();
}

class _IndaiWorkerAppState extends State<IndaiWorkerApp> {
  final IndaiApi _api = IndaiApi();
  Map<String, dynamic>? _me;
  bool _mustChange = false;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _api.onAuthExpired = _onAuthExpired;
    _restore();
  }

  Future<void> _restore() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      // Restore persisted server URL if configured
      final storedServerUrl = prefs.getString(kServerUrlStorageKey);
      if (storedServerUrl != null && storedServerUrl.trim().isNotEmpty) {
        try {
          _api.setBaseUrl(storedServerUrl);
        } catch (_) {}
      }

      final token = await _storage.read(key: _tokenKey);
      if (token != null && token.isNotEmpty) {
        _api.setToken(token);
        try {
          final me = await _api.workerMe();
          if (!mounted) return;
          setState(() {
            _me = me;
            _mustChange = false;
          });
          await _cacheProfile(me);
          return;
        } catch (_) {
          // Token invalid -> fall through to login (clean logout).
          await _storage.delete(key: _tokenKey);
          _api.setToken(null);
        }
      }
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _cacheProfile(Map<String, dynamic> me) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_profileKey, jsonEncode(me));
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _signedIn(String token, Map<String, dynamic> employee, bool mustChange) async {
    try {
      await _storage.write(key: _tokenKey, value: token);
    } catch (_) {}
    _api.setToken(token);
    setState(() {
      _me = employee;
      _mustChange = mustChange;
      _loading = false;
    });
    await _cacheProfile(employee);
  }

  Future<void> _passwordChanged() async {
    setState(() => _mustChange = false);
  }

  Future<void> _signOut() async {
    try {
      await _storage.delete(key: _tokenKey);
    } catch (_) {}
    _api.setToken(null);
    setState(() {
      _me = null;
      _mustChange = false;
    });
  }

  void _onAuthExpired() {
    _signOut();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'IndAI worker',
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF7FB6D9),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFF4F8FA),
        cardTheme: CardThemeData(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        ),
      ),
      home: _loading
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _me == null
              ? LoginScreen(api: _api, onSignedIn: _signedIn)
              : _mustChange
                  ? ChangePasswordScreen(api: _api, onDone: _passwordChanged)
                  : HomeScreen(api: _api, me: _me!, onSignOut: _signOut),
    );
  }
}
