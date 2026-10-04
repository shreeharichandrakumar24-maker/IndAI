import 'package:flutter/material.dart';
import '../../services/api.dart';

const _allowedAvailability = ['AVAILABLE', 'BUSY', 'UNAVAILABLE'];

String _initials(String name) {
  final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
  if (parts.isEmpty) return '?';
  if (parts.length == 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

/// Profile tab: full details, skills/certifications, availability switch,
/// change password, sign out.
class ProfileTab extends StatefulWidget {
  const ProfileTab({super.key, required this.api, required this.me, required this.onSignOut, required this.onChanged});
  final IndaiApi api;
  final Map<String, dynamic> me;
  final VoidCallback onSignOut;
  final Future<void> Function(Map<String, dynamic> employee) onChanged;

  @override
  State<ProfileTab> createState() => _ProfileTabState();
}

class _ProfileTabState extends State<ProfileTab> {
  late Map<String, dynamic> _me;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _me = Map<String, dynamic>.from(widget.me);
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final fresh = await widget.api.workerMe();
      if (!mounted) return;
      setState(() {
        _me = fresh;
        _error = null;
      });
      await widget.onChanged(fresh);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    }
  }

  String _listText(dynamic v) {
    if (v is Map && v['items'] is List) return (v['items'] as List).join(', ');
    if (v is String) return v;
    return '—';
  }

  Future<void> _setAvailability(String value) async {
    if (!_allowedAvailability.contains(value)) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.workerAvailability(value);
      final full = await widget.api.workerMe();
      if (!mounted) return;
      setState(() => _me = full);
      await widget.onChanged(full);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final name = (_me['name'] ?? '').toString();
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Row(children: [
              CircleAvatar(radius: 34, backgroundColor: const Color(0xFF7FB6D9),
                  child: Text(_initials(name),
                      style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: Colors.white))),
              const SizedBox(width: 14),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                Text((_me['role'] ?? '').toString(), style: const TextStyle(color: Colors.grey)),
                Text('ID: ${(_me['employee_code'] ?? _me['id'] ?? '').toString()}',
                    style: const TextStyle(color: Colors.grey, fontSize: 12)),
              ])),
            ]),
            const SizedBox(height: 16),
            Card(child: Column(children: [
              ListTile(title: const Text('Email'), subtitle: Text((_me['email'] ?? '—').toString())),
              ListTile(title: const Text('Shift'), subtitle: Text((_me['shift'] ?? '—').toString())),
              ListTile(title: const Text('Status'), subtitle: Text((_me['status'] ?? '—').toString())),
              ListTile(title: const Text('Skills'), subtitle: Text(_listText(_me['skills']))),
              ListTile(title: const Text('Certifications'), subtitle: Text(_listText(_me['certifications']))),
            ])),
            const SizedBox(height: 12),
            const Text('Availability', style: TextStyle(fontWeight: FontWeight.bold)),
            const Text('Allocation uses this value.', style: TextStyle(color: Colors.grey, fontSize: 12)),
            DropdownButtonFormField<String>(
              key: ValueKey(_me['availability']),
              initialValue: _allowedAvailability.contains((_me['availability'] ?? '').toString())
                  ? (_me['availability'] ?? 'AVAILABLE').toString()
                  : 'AVAILABLE',
              decoration: const InputDecoration(border: OutlineInputBorder()),
              items: _allowedAvailability.map((a) => DropdownMenuItem(value: a, child: Text(a))).toList(),
              onChanged: _busy ? null : (v) {
                if (v != null && v != _me['availability']) _setAvailability(v);
              },
            ),
            if (_busy) const Padding(padding: EdgeInsets.only(top: 12), child: Center(child: CircularProgressIndicator())),
            if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 24),
            OutlinedButton.icon(onPressed: widget.onSignOut,
                icon: const Icon(Icons.logout), label: const Text('Sign out')),
            const SizedBox(height: 24),
            const Text('Prototype authentication - real authentication is future work.',
                style: TextStyle(color: Colors.grey, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}
