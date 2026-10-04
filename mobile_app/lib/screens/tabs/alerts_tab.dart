import 'dart:async';
import 'package:flutter/material.dart';
import '../../services/api.dart';

/// Alerts tab: OPEN incidents touching my work (own tasks/machines/orders).
/// Refreshes with the tab; pull-to-refresh anytime.
class AlertsTab extends StatefulWidget {
  const AlertsTab({super.key, required this.api});
  final IndaiApi api;

  @override
  State<AlertsTab> createState() => _AlertsTabState();
}

class _AlertsTabState extends State<AlertsTab> {
  List<dynamic> _items = [];
  bool _loading = true;
  String? _error;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _refresh();
    _poll = Timer.periodic(const Duration(seconds: 15), (_) {
      if (mounted) _refresh(background: true);
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _refresh({bool background = false}) async {
    if (!background && mounted) setState(() => _loading = true);
    try {
      final items = await widget.api.workerAlerts();
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        if (_items.isEmpty) _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Color _tone(String severity) {
    switch (severity) {
      case 'CRITICAL':
        return Colors.red;
      case 'HIGH':
        return Colors.orange;
      case 'MEDIUM':
        return Colors.amber.shade800;
      default:
        return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Alerts')),
      body: RefreshIndicator(
        onRefresh: () => _refresh(),
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(_error!),
                    const SizedBox(height: 12),
                    ElevatedButton(onPressed: () => _refresh(), child: const Text('Retry')),
                  ]))
                : _items.isEmpty
                    ? const Center(child: Padding(padding: EdgeInsets.all(24),
                        child: Text('All clear — no open alerts on your work.')))
                    : ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _items.length,
                        itemBuilder: (_, i) {
                          final a = Map<String, dynamic>.from(_items[i] as Map);
                          final sev = (a['severity'] ?? 'MEDIUM').toString();
                          return Card(
                            child: ListTile(
                              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                              leading: Icon(Icons.warning_amber_rounded, size: 36, color: _tone(sev)),
                              title: Text((a['incident_type'] ?? 'Incident').toString(),
                                  style: const TextStyle(fontWeight: FontWeight.w600)),
                              subtitle: Text((a['description'] ?? '').toString(),
                                  maxLines: 3, overflow: TextOverflow.ellipsis),
                              trailing: Text(sev, style: TextStyle(color: _tone(sev), fontWeight: FontWeight.bold)),
                            ),
                          );
                        },
                      ),
      ),
    );
  }
}
