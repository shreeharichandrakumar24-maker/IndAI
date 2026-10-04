import 'package:flutter/material.dart';
import '../services/api.dart';

/// Forced password change (first login when must_change_password is true).
class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key, required this.api, required this.onDone});
  final IndaiApi api;
  final VoidCallback onDone;

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _submit() async {
    if (_next.text.length < 8) {
      setState(() => _error = 'New password must be at least 8 characters.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.changePassword(_current.text, _next.text);
      widget.onDone();
    } catch (e) {
      var msg = e.toString().replaceFirst('Exception: ', '');
      if (msg.contains('401')) msg = 'Current password is wrong.';
      if (mounted) setState(() => _error = msg);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Set a new password')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Your manager asked you to change the temporary password.'),
            const SizedBox(height: 16),
            TextField(controller: _current, decoration: const InputDecoration(labelText: 'Current password', border: OutlineInputBorder()), obscureText: true),
            const SizedBox(height: 12),
            TextField(controller: _next, decoration: const InputDecoration(labelText: 'New password (min 8 chars)', border: OutlineInputBorder()), obscureText: true, onSubmitted: (_) => _submit()),
            const SizedBox(height: 16),
            if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
            ElevatedButton(onPressed: _busy ? null : _submit, child: Text(_busy ? 'Saving…' : 'Save password')),
          ],
        ),
      ),
    );
  }
}
