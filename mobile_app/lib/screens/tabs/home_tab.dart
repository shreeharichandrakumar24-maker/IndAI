import 'package:flutter/material.dart';
import '../../services/api.dart';

String _initials(String name) {
  final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
  if (parts.isEmpty) return '?';
  if (parts.length == 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

String _today() {
  final n = DateTime.now();
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${days[n.weekday - 1]}, ${n.day} ${months[n.month - 1]}';
}

/// Home tab: greeting header with avatar + date, stat cards, next deadline.
class HomeTab extends StatefulWidget {
  const HomeTab({super.key, required this.api, required this.me});
  final IndaiApi api;
  final Map<String, dynamic> me;

  @override
  State<HomeTab> createState() => _HomeTabState();
}

class _HomeTabState extends State<HomeTab> {
  Map<String, dynamic>? _stats;
  String? _nextDeadline;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final me = await widget.api.workerMe();
      if (!mounted) return;
      final st = Map<String, dynamic>.from(me['stats'] ?? {});
      setState(() {
        _stats = st;
        _nextDeadline = st['next_deadline']?.toString();
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final name = (widget.me['name'] ?? '').toString();
    final stats = _stats ?? {};
    final cards = [
      {'label': 'Assigned', 'value': (stats['assigned'] ?? '—').toString(), 'bg': Colors.blue.shade100, 'fg': Colors.blue.shade800},
      {'label': 'In progress', 'value': (stats['active'] ?? '—').toString(), 'bg': Colors.orange.shade100, 'fg': Colors.orange.shade800},
      {'label': 'Done', 'value': (stats['done'] ?? '—').toString(), 'bg': Colors.green.shade100, 'fg': Colors.green.shade800},
    ];
    return Scaffold(
      backgroundColor: const Color(0xFFF4F8FA),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Row(children: [
                CircleAvatar(
                  radius: 30,
                  backgroundColor: const Color(0xFF7FB6D9),
                  child: Text(_initials(name),
                      style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white)),
                ),
                const SizedBox(width: 14),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Hello, $name', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                  Text('${(widget.me['role'] ?? '').toString()} · ${_today()}',
                      style: const TextStyle(color: Colors.grey)),
                ])),
              ]),
              const SizedBox(height: 20),
              Row(children: [
                for (final c in cards)
                  Expanded(child: Card(
                    color: c['bg'] as Color,
                    child: Padding(padding: const EdgeInsets.symmetric(vertical: 18),
                        child: Column(children: [
                          Text(c['value'].toString(), style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: c['fg'] as Color)),
                          Text(c['label'].toString(), style: TextStyle(color: c['fg'] as Color)),
                        ])),
                  )),
              ]),
              const SizedBox(height: 8),
              Card(
                child: ListTile(
                  leading: const Icon(Icons.event, size: 32, color: Color(0xFF7FB6D9)),
                  title: const Text('Next deadline'),
                  subtitle: Text(_loading
                      ? 'Loading…'
                      : _nextDeadline != null
                          ? _nextDeadline!.substring(0, 10)
                          : 'Nothing due.'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
