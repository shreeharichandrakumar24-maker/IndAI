import 'package:flutter/material.dart';
import '../services/api.dart';

const _severities = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

/// Report a problem: creates a real WORKER_REPORT incident linked to the
/// worker's own machine/task/order. Title prefixed "[Worker report]" with
/// the worker's name in the description (backend rule).
class ReportProblemScreen extends StatefulWidget {
  const ReportProblemScreen({super.key, required this.api, required this.me, required this.task});
  final IndaiApi api;
  final Map<String, dynamic> me;
  final Map<String, dynamic> task;

  @override
  State<ReportProblemScreen> createState() => _ReportProblemScreenState();
}

class _ReportProblemScreenState extends State<ReportProblemScreen> {
  String _severity = 'MEDIUM';
  final _desc = TextEditingController();
  bool _busy = false;
  String? _error;
  String? _doneId;

  Future<void> _submit() async {
    final what = _desc.text.trim();
    if (what.isEmpty) {
      setState(() => _error = 'Describe the problem first.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final body = <String, dynamic>{
        'severity': _severity,
        'description': '[Worker report] $what (by ${(widget.me['name'] ?? 'worker').toString()})',
      };
      for (final k in ['machine_id', 'task_id', 'order_id']) {
        final v = widget.task[k]?.toString();
        if (v != null && v.isNotEmpty) body[k] = v;
      }
      final created = await widget.api.workerReportIncident(body);
      if (!mounted) return;
      setState(() => _doneId = (created['id'] ?? '').toString().substring(0, 8));
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Report a problem')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Task: ${(widget.task['name'] ?? '').toString()}'),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: _severity,
              decoration: const InputDecoration(labelText: 'How urgent?', border: OutlineInputBorder()),
              items: _severities.map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
              onChanged: _busy ? null : (v) => setState(() => _severity = v ?? 'MEDIUM'),
            ),
            const SizedBox(height: 12),
            TextField(controller: _desc, maxLines: 4,
                decoration: const InputDecoration(labelText: "What's wrong?", border: OutlineInputBorder())),
            const SizedBox(height: 16),
            if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
            if (_doneId != null && _doneId!.isNotEmpty)
              Text('Reported ($_doneId). Your manager can see it.', style: const TextStyle(color: Colors.green)),
            SizedBox(
              height: 52,
              child: ElevatedButton(
                onPressed: _busy ? null : _submit,
                child: Text(_busy ? 'Sending…' : 'Send report'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
