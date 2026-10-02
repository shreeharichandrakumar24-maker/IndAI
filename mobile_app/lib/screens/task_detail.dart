import 'package:flutter/material.dart';
import '../services/api.dart';

const _flow = ['ACCEPTED', 'IN_PROGRESS', 'DONE'];

/// One assignment: details + advance button (Accept -> Start -> Done).
/// Status writes go through PATCH /api/assignments/{id} (row-checked:
/// workers can only move their own assignments).
class TaskDetailScreen extends StatefulWidget {
  const TaskDetailScreen({super.key, required this.api, required this.assignment});
  final IndaiApi api;
  final Map<String, dynamic> assignment;

  @override
  State<TaskDetailScreen> createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends State<TaskDetailScreen> {
  late String _status;
  bool _busy = false;
  String? _error;
  String? _done;

  @override
  void initState() {
    super.initState();
    _status = (widget.assignment['status'] ?? 'NOTIFIED').toString();
  }

  String? get _next {
    if (_status == 'NOTIFIED' || _status == 'UNASSIGNED') return 'ACCEPTED';
    final i = _flow.indexOf(_status);
    if (i >= 0 && i < _flow.length - 1) return _flow[i + 1];
    return null;
  }

  Future<void> _advance() async {
    final next = _next;
    if (next == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final updated = await widget.api.updateAssignment(widget.assignment['id'].toString(), next);
      setState(() {
        _status = (updated['status'] ?? next).toString();
        _done = next == 'DONE' ? 'Marked done — your manager can see it.' : null;
      });
    } catch (e) {
      setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = widget.assignment;
    return Scaffold(
      appBar: AppBar(title: const Text('Job details')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Status: ${_status.replaceAll('_', ' ')}', style: const TextStyle(fontSize: 18)),
            const SizedBox(height: 8),
            Text('Task: ${(a['task_id'] ?? '—').toString()}'),
            Text('Machine: ${(a['machine_id'] ?? '—').toString()}'),
            if (a['notified_at'] != null) Text('Sent: ${a['notified_at']}'),
            const SizedBox(height: 20),
            if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
            if (_done != null) Text(_done!, style: const TextStyle(color: Colors.green)),
            if (_next != null)
              ElevatedButton(
                onPressed: _busy ? null : _advance,
                child: Text(_busy
                    ? 'Saving…'
                    : _next == 'ACCEPTED'
                        ? 'Accept job'
                        : _next == 'IN_PROGRESS'
                            ? 'Start work'
                            : 'Mark done'),
              )
            else
              const Text('This job is complete.'),
          ],
        ),
      ),
    );
  }
}
