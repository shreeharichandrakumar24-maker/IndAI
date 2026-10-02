import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api.dart';
import '../services/push.dart';
import 'task_detail.dart';

const _cacheKey = 'indai.cached.assignments';

/// My jobs list. Cached for shop-floor offline use; pull to refresh.
/// New dispatches arrive via FCM push (see push.dart) with the bell as fallback.
class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key, required this.api, required this.onSignOut});
  final IndaiApi api;
  final VoidCallback onSignOut;

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  List<dynamic> _items = [];
  bool _loading = true;
  String? _error;
  String _pushState = 'push: …';

  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    await _loadCached();
    await _refresh();
    try {
      await setupPush(widget.api);
      if (mounted) setState(() => _pushState = 'push: on');
    } catch (_) {
      if (mounted) setState(() => _pushState = 'push: off (bell only)');
    }
  }

  Future<void> _loadCached() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_cacheKey);
      if (raw != null && mounted) {
        setState(() {
          _items = List<dynamic>.from(jsonDecode(raw) as List);
          _loading = false;
        });
      }
    } catch (_) {}
  }

  Future<void> _refresh() async {
    try {
      final items = await widget.api.myAssignments();
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
        _error = null;
      });
      try {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString(_cacheKey, jsonEncode(items));
      } catch (_) {}
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        if (_items.isEmpty) _error = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Color _tone(String status) {
    switch (status) {
      case 'DONE':
        return Colors.green;
      case 'IN_PROGRESS':
        return Colors.blue;
      case 'ACCEPTED':
        return Colors.teal;
      case 'NOTIFIED':
        return Colors.orange;
      default:
        return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My jobs'),
        actions: [
          Center(child: Padding(padding: const EdgeInsets.only(right: 8), child: Text(_pushState))),
          IconButton(icon: const Icon(Icons.logout), onPressed: widget.onSignOut),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Text(_error!))
                : _items.isEmpty
                    ? const Center(child: Text('No jobs assigned. Pull down to refresh.'))
                    : ListView.builder(
                        itemCount: _items.length,
                        itemBuilder: (_, i) {
                          final a = _items[i] as Map<String, dynamic>;
                          final st = (a['status'] ?? 'NOTIFIED').toString();
                          return ListTile(
                            leading: Icon(Icons.build, color: _tone(st)),
                            title: Text('Job ${st.replaceAll('_', ' ')}'),
                            subtitle: Text('Task ${(a['task_id'] ?? '?').toString().substring(0, 8)}'
                                '${a['notified_at'] != null ? ' · sent ${a['notified_at']}' : ''}'),
                            trailing: Chip(label: Text(st), backgroundColor: _tone(st).withValues(alpha: 0.2)),
                            onTap: () async {
                              await Navigator.of(context).push(MaterialPageRoute(
                                builder: (_) => TaskDetailScreen(api: widget.api, assignment: a),
                              ));
                              _refresh();
                            },
                          );
                        },
                      ),
      ),
    );
  }
}
