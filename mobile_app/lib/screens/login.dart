import 'package:flutter/material.dart';
import '../services/api.dart';

/// Worker sign-in (prototype): one "Email, Employee ID or username" field +
/// password with show/hide. Prototype authentication - real authentication
/// is future work.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.api, required this.onSignedIn});
  final IndaiApi api;
  final Future<void> Function(String token, Map<String, dynamic> employee, bool mustChange) onSignedIn;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _id = TextEditingController();
  final _password = TextEditingController();
  bool _obscure = true;
  bool _busy = false;
  String? _error;

  Future<void> _submit() async {
    final ident = _id.text.trim();
    if (ident.isEmpty || _password.text.isEmpty) {
      setState(() => _error = 'Enter your login and password.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final res = await widget.api.workerLogin(ident, _password.text);
      await widget.onSignedIn(res['token'].toString(),
          Map<String, dynamic>.from(res['employee'] as Map), res['must_change_password'] == true);
    } catch (e) {
      var msg = e.toString().replaceFirst('Exception: ', '');
      if (msg.contains('401') || msg.contains('Invalid username or password')) {
        msg = 'Invalid username or password.';
      } else if (msg.contains('Too many attempts')) {
        msg = 'Too many attempts, try again later.';
      } else if (msg.contains('SocketException') || msg.contains('ClientException') || msg.contains('Failed host')) {
        msg = 'Cannot reach the server. Check Wi-Fi/USB and retry.';
      }
      if (mounted) setState(() => _error = msg);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 48),
              const Icon(Icons.factory, size: 72, color: Color(0xFF7FB6D9)),
              const SizedBox(height: 16),
              const Text('IndAI worker', textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
              const SizedBox(height: 4),
              const Text('Sign in with the login your manager gave you.',
                  textAlign: TextAlign.center, style: TextStyle(color: Colors.grey)),
              const SizedBox(height: 4),
              const Text('Prototype authentication - real authentication is future work.',
                  textAlign: TextAlign.center, style: TextStyle(color: Colors.grey, fontSize: 12)),
              const SizedBox(height: 24),
              TextField(controller: _id,
                  decoration: const InputDecoration(
                    labelText: 'Email, Employee ID or username',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.person),
                  ),
                  autocorrect: false),
              const SizedBox(height: 12),
              TextField(controller: _password,
                  decoration: InputDecoration(
                    labelText: 'Password',
                    border: const OutlineInputBorder(),
                    prefixIcon: const Icon(Icons.lock),
                    suffixIcon: IconButton(
                      icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                  ),
                  obscureText: _obscure,
                  onSubmitted: (_) => _submit()),
              const SizedBox(height: 16),
              if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
              const SizedBox(height: 8),
              SizedBox(
                height: 52,
                child: ElevatedButton(
                  onPressed: _busy ? null : _submit,
                  child: Text(_busy ? 'Signing in…' : 'LOGIN', style: const TextStyle(fontSize: 16)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
