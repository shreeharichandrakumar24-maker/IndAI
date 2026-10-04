import 'package:flutter/material.dart';
import '../services/api.dart';
import 'report_problem.dart';

/// Worker task detail on real data: description, skill, deadline, machine +
/// its latest telemetry (stale-marked), Start / progress / Complete, Log
/// output onto the linked production run, and Report a problem.
class WorkerTaskDetail extends StatefulWidget {
  const WorkerTaskDetail({super.key, required this.api, required this.me,
    required this.task, this.orderLabel, this.machineLabel});
  final IndaiApi api;
  final Map<String, dynamic> me;
  final Map<String, dynamic> task;
  final String? orderLabel;
  final String? machineLabel;

  @override
  State<WorkerTaskDetail> createState() => _WorkerTaskDetailState();
}

class _WorkerTaskDetailState extends State<WorkerTaskDetail> {
  late Map<String, dynamic> _t;
  Map<String, dynamic>? _telemetry;
  bool _telStale = false;
  bool _busy = false;
  String? _error;
  String? _ok;
  double _progress = 0;
  final _outputCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _t = Map<String, dynamic>.from(widget.task);
    _progress = ((_t['progress'] ?? 0) as num).toDouble().clamp(0.0, 1.0);
    _loadTelemetry();
  }

  Future<void> _loadTelemetry() async {
    final mid = _t['machine_id']?.toString();
    if (mid == null) return;
    try {
      final tel = await widget.api.latestTelemetry(mid);
      if (!mounted) return;
      var stale = true;
      if (tel != null && tel['timestamp'] != null) {
        final ts = DateTime.tryParse(tel['timestamp'].toString());
        if (ts != null) stale = DateTime.now().difference(ts).inSeconds > 90;
      }
      setState(() {
        _telemetry = tel;
        _telStale = tel == null || stale;
      });
    } catch (_) {}
  }

  Future<void> _saveProgress() async {
    setState(() {
      _busy = true;
      _error = null;
      _ok = null;
    });
    try {
      final updated = await widget.api.workerTaskProgress(
          _t['id'].toString(), double.parse(_progress.toStringAsFixed(2)));
      if (!mounted) return;
      setState(() {
        _t = updated;
        _progress = ((updated['progress'] ?? _progress) as num).toDouble().clamp(0.0, 1.0);
        _ok = 'Progress saved.';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = _friendly(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _friendly(Object e) {
    final msg = e.toString().replaceFirst('Exception: ', '');
    if (e is AuthExpiredException) return 'Session expired. Signing you out…';
    return msg;
  }

  Future<void> _advance(String status, String okMsg) async {
    setState(() {
      _busy = true;
      _error = null;
      _ok = null;
    });
    try {
      final updated = await widget.api.workerTaskStatus(_t['id'].toString(), status);
      if (!mounted) return;
      setState(() {
        _t = updated;
        _progress = ((updated['progress'] ?? _progress) as num).toDouble().clamp(0.0, 1.0);
        _ok = okMsg;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = _friendly(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _start() => _advance('IN_PROGRESS', 'Started.');

  Future<void> _complete() => _advance('DONE', 'Completed.');

  Future<void> _logOutput() async {
    final oid = _t['order_id']?.toString();
    if (oid == null) {
      setState(() => _error = 'No order linked to this task.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _ok = null;
    });
    try {
      final runs = await widget.api.runsForOrder(oid);
      Map<String, dynamic>? run;
      for (final r in runs) {
        final m = Map<String, dynamic>.from(r as Map);
        if (m['task_id']?.toString() == _t['id'].toString()) {
          run = m;
          break;
        }
      }
      run ??= runs.where((r) => (r['status'] ?? '') == 'IN_PROGRESS').map((r) => Map<String, dynamic>.from(r as Map)).firstOrNull;
      if (run == null) {
        if (mounted) setState(() => _error = 'No production run for this order yet.');
        return;
      }
      final target = (run['quantity_target'] ?? 0) as num;
      final done = (run['quantity_completed'] ?? 0) as num;
      _outputCtrl.text = '';
      if (!mounted) return;
      final qty = await showDialog<int>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Log output'),
          content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Completed so far: $done / $target'),
            const SizedBox(height: 12),
            TextField(controller: _outputCtrl, keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'New completed total')),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
            ElevatedButton(onPressed: () {
              Navigator.of(ctx).pop(int.tryParse(_outputCtrl.text.trim()));
            }, child: const Text('Save')),
          ],
        ),
      );
      if (qty == null) return;
      if (qty > target && target > 0) {
        if (!mounted) return;
        final confirm = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Over target?'),
            content: Text('$qty exceeds the target of $target. Save anyway?'),
            actions: [
              TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
              ElevatedButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Save anyway')),
            ],
          ),
        );
        if (confirm != true) return;
      }
      final updated = await widget.api.updateRun(run['id'].toString(), {'quantity_completed': qty});
      if (!mounted) return;
      setState(() => _ok = 'Output logged: ${updated['quantity_completed']} / $target.');
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = _friendly(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final st = (_t['status'] ?? 'PENDING').toString();
    return Scaffold(
      appBar: AppBar(title: Text((_t['name'] ?? 'Task').toString())),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('Status: ${st.replaceAll('_', ' ')}', style: const TextStyle(fontSize: 18)),
          const SizedBox(height: 8),
          if ((_t['description'] ?? '') != '') Text((_t['description'] ?? '').toString()),
          Text('Skill: ${(_t['required_skill'] ?? 'general').toString()}'),
          Text('Priority: ${(_t['priority'] ?? 'NORMAL').toString()}'),
          if ((_t['deadline'] ?? '') != '') Text('Due: ${(_t['deadline'] ?? '').toString().substring(0, 10)}'),
          if (widget.orderLabel != null) Text('Order: ${widget.orderLabel}'),
          if (widget.machineLabel != null) Text('Machine: ${widget.machineLabel}'),
          const SizedBox(height: 12),
          const Text('Machine readings', style: TextStyle(fontWeight: FontWeight.bold)),
          Text(_telemetry == null
              ? 'No telemetry yet.'
              : '${_telemetry!['temperature'] ?? '?'} °C · ${_telemetry!['vibration'] ?? '?'} vib · ${_telemetry!['current'] ?? '?'} A · ${_telemetry!['rpm'] ?? '?'} rpm · ${_telemetry!['machine_status'] ?? '?'}${_telStale ? ' (STALE)' : ''}'),
          const SizedBox(height: 12),
          Row(children: [
            const Text('Progress: '),
            Expanded(
              child: Slider(value: _progress, onChanged: _busy ? null : (v) => setState(() => _progress = v)),
            ),
            Text('${(_progress * 100).round()}%'),
          ]),
          SizedBox(
            height: 52,
            child: ElevatedButton(
              onPressed: _busy ? null : _saveProgress,
              child: const Text('Save progress'),
            ),
          ),
          const SizedBox(height: 8),
          if (st == 'PENDING' || st == 'IN_PROGRESS') ...[
            if (st == 'PENDING')
              SizedBox(height: 52, child: ElevatedButton(onPressed: _busy ? null : _start, child: Text(_busy ? 'Saving…' : 'Start work'))),
            if (st == 'IN_PROGRESS')
              SizedBox(height: 52, child: ElevatedButton(onPressed: _busy ? null : _complete, child: Text(_busy ? 'Saving…' : 'Complete'))),
            const SizedBox(height: 8),
            SizedBox(height: 52, child: OutlinedButton(onPressed: _busy ? null : _logOutput, child: const Text('Log output'))),
            const SizedBox(height: 8),
            SizedBox(height: 52, child: OutlinedButton(
              onPressed: _busy ? null : () async {
                await Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => ReportProblemScreen(api: widget.api, me: widget.me, task: _t),
                ));
              },
              child: const Text('Report a problem'),
            )),
          ] else
            const Text('This task is closed.'),
          if (_busy) const Padding(padding: EdgeInsets.only(top: 12), child: Center(child: CircularProgressIndicator())),
          if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
          if (_ok != null) Text(_ok!, style: const TextStyle(color: Colors.green)),
        ],
      ),
    );
  }
}

extension<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
