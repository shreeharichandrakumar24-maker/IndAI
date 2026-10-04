import 'dart:async';
import 'package:flutter/material.dart';
import '../../services/api.dart';
import '../task_detail.dart';

/// Tasks tab: Ongoing / Finished sections with circular progress, priority
/// and deadline. Pull-to-refresh + ~15 s poll with a "new task assigned"
/// banner so admin/AI assignments appear.
class TasksTab extends StatefulWidget {
  const TasksTab({super.key, required this.api, required this.me});
  final IndaiApi api;
  final Map<String, dynamic> me;

  @override
  State<TasksTab> createState() => _TasksTabState();
}

class _TasksTabState extends State<TasksTab> {
  List<dynamic> _tasks = [];
  bool _loading = true;
  String? _error;
  Timer? _poll;
  Set<String> _knownIds = {};
  int _newCount = 0;
  bool _firstLoad = true;

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
      final tasks = await widget.api.workerTasks();
      if (!mounted) return;
      final ids = {for (final t in tasks) (t['id'] ?? '').toString()};
      final fresh = (!_firstLoad && background) ? ids.difference(_knownIds).length : 0;
      setState(() {
        _tasks = tasks;
        _loading = false;
        _error = null;
        if (fresh > 0) _newCount = fresh;
        _knownIds = ids;
        _firstLoad = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        if (_tasks.isEmpty) _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  List<Map<String, dynamic>> get _ongoing => _tasks
      .map((t) => Map<String, dynamic>.from(t as Map))
      .where((t) => ['PENDING', 'IN_PROGRESS'].contains((t['status'] ?? 'PENDING').toString()))
      .toList();

  List<Map<String, dynamic>> get _finished => _tasks
      .map((t) => Map<String, dynamic>.from(t as Map))
      .where((t) => ['DONE', 'COMPLETED', 'CANCELLED'].contains((t['status'] ?? '').toString()))
      .toList();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My tasks')),
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
                : ListView(
                    padding: const EdgeInsets.all(12),
                    children: [
                      if (_newCount > 0)
                        Card(color: Colors.amber.shade100, child: ListTile(
                          leading: const Icon(Icons.notifications_active),
                          title: Text('$_newCount new task(s) assigned'),
                          trailing: TextButton(
                            onPressed: () => setState(() {
                              _newCount = 0;
                              _knownIds = {for (final t in _tasks) (t['id'] ?? '').toString()};
                            }),
                            child: const Text('Seen'),
                          ),
                        )),
                      _section('Ongoing', _ongoing, Colors.blue),
                      _section('Finished', _finished, Colors.green),
                      if (_tasks.isEmpty)
                        const Padding(padding: EdgeInsets.all(24),
                            child: Center(child: Text('No tasks assigned yet. Pull down to refresh.'))),
                    ],
                  ),
      ),
    );
  }

  Widget _section(String title, List<Map<String, dynamic>> items, Color color) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text('$title (${items.length})',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: color))),
        ...items.map((t) {
          final pct = ((t['progress'] ?? 0) as num).toDouble().clamp(0.0, 1.0);
          final prio = (t['priority'] ?? 'NORMAL').toString();
          final prioColor = prio == 'URGENT' ? Colors.red : prio == 'HIGH' ? Colors.orange : Colors.grey;
          return Card(
            child: ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              leading: SizedBox(
                width: 52,
                height: 52,
                child: Stack(alignment: Alignment.center, children: [
                  CircularProgressIndicator(value: pct, strokeWidth: 5, backgroundColor: Colors.grey.shade200),
                  Text('${(pct * 100).round()}%', style: const TextStyle(fontSize: 11)),
                ]),
              ),
              title: Text((t['name'] ?? 'Task').toString(), style: const TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                if ((t['order_number'] ?? '') != '') Text('Order ${t['order_number']}'),
                if ((t['machine_name'] ?? '') != '') Text('Machine ${t['machine_name']}'),
                Row(children: [
                  Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(color: prioColor.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(12)),
                      child: Text(prio, style: TextStyle(fontSize: 11, color: prioColor))),
                  if ((t['deadline'] ?? '') != '') Text(' · due ${(t['deadline'] ?? '').toString().substring(0, 10)}',
                      style: const TextStyle(fontSize: 12)),
                ]),
              ]),
              onTap: () async {
                await Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => WorkerTaskDetail(api: widget.api, me: widget.me, task: t),
                ));
                _refresh();
              },
            ),
          );
        }),
      ],
    );
  }
}
