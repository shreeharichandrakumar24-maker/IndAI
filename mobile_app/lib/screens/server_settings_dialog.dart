import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';
import '../services/api.dart';

/// Modal bottom sheet or dialog for configuring the backend server address at runtime.
class ServerSettingsSheet extends StatefulWidget {
  const ServerSettingsSheet({
    super.key,
    required this.api,
    required this.onSaved,
  });

  final IndaiApi api;
  final ValueChanged<String> onSaved;

  static Future<void> show(BuildContext context, IndaiApi api, ValueChanged<String> onSaved) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => ServerSettingsSheet(api: api, onSaved: onSaved),
    );
  }

  @override
  State<ServerSettingsSheet> createState() => _ServerSettingsSheetState();
}

class _ServerSettingsSheetState extends State<ServerSettingsSheet> {
  late final TextEditingController _urlController;
  bool _testing = false;
  Map<String, dynamic>? _testResult;
  String? _validationError;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: widget.api.baseUrl);
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  void _setPreset(String url) {
    setState(() {
      _urlController.text = url;
      _validationError = null;
      _testResult = null;
    });
  }

  Future<void> _testConnection() async {
    final text = _urlController.text.trim();
    if (text.isEmpty) {
      setState(() => _validationError = 'Please enter a server address first.');
      return;
    }
    setState(() {
      _testing = true;
      _testResult = null;
      _validationError = null;
    });

    try {
      final normalized = normalizeApiUrl(text);
      final res = await widget.api.testConnection(normalized);
      if (mounted) {
        setState(() {
          _testResult = res;
          _testing = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _testing = false;
          _testResult = {
            'success': false,
            'error': e is FormatException ? e.message : e.toString(),
          };
        });
      }
    }
  }

  Future<void> _save() async {
    final text = _urlController.text.trim();
    if (text.isEmpty) {
      setState(() => _validationError = 'Server address cannot be empty.');
      return;
    }
    try {
      final normalized = normalizeApiUrl(text);
      widget.api.setBaseUrl(normalized);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(kServerUrlStorageKey, normalized);
      widget.onSaved(normalized);
      if (mounted) {
        Navigator.of(context).pop();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Server updated to: $normalized'),
            backgroundColor: Colors.green.shade700,
          ),
        );
      }
    } catch (e) {
      setState(() {
        _validationError = e is FormatException ? e.message : 'Invalid address: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;
    return Container(
      padding: EdgeInsets.fromLTRB(24, 20, 24, 20 + bottomInset),
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(Icons.settings_ethernet, color: Color(0xFF7FB6D9), size: 28),
                const SizedBox(width: 12),
                const Expanded(
                  child: Text(
                    'Server Settings',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
            const SizedBox(height: 8),
            const Text(
              'Enter the backend address as host:port or full URL. Examples:\n'
              '• http://192.168.1.23:8000\n'
              '• 192.168.1.23:8000\n'
              '• 192.168.1.23',
              style: TextStyle(fontSize: 13, color: Colors.black54),
            ),
            const SizedBox(height: 16),
            const Text('Quick Choices:', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                ActionChip(
                  avatar: const Icon(Icons.phone_android, size: 16),
                  label: const Text('Emulator (10.0.2.2)'),
                  onPressed: () => _setPreset('http://10.0.2.2:8000'),
                ),
                ActionChip(
                  avatar: const Icon(Icons.usb, size: 16),
                  label: const Text('USB (127.0.0.1)'),
                  onPressed: () => _setPreset('http://127.0.0.1:8000'),
                ),
                ActionChip(
                  avatar: const Icon(Icons.wifi, size: 16),
                  label: const Text('Wi-Fi (enter IP)'),
                  onPressed: () => _setPreset('http://192.168.1.'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _urlController,
              decoration: InputDecoration(
                labelText: 'Backend Address / URL',
                hintText: 'http://192.168.1.23:8000',
                border: const OutlineInputBorder(),
                prefixIcon: const Icon(Icons.dns),
                errorText: _validationError,
                suffixIcon: IconButton(
                  icon: const Icon(Icons.clear),
                  onPressed: () => _urlController.clear(),
                ),
              ),
              autocorrect: false,
              keyboardType: TextInputType.url,
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    icon: _testing
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.network_check, size: 18),
                    label: Text(_testing ? 'Testing (5s)...' : 'Test connection'),
                    onPressed: _testing ? null : _testConnection,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton.icon(
                    icon: const Icon(Icons.save, size: 18),
                    label: const Text('Save'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF7FB6D9),
                      foregroundColor: Colors.white,
                    ),
                    onPressed: _save,
                  ),
                ),
              ],
            ),
            if (_testResult != null) ...[
              const SizedBox(height: 14),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _testResult!['success'] == true
                      ? Colors.green.shade50
                      : Colors.red.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: _testResult!['success'] == true
                        ? Colors.green.shade300
                        : Colors.red.shade300,
                  ),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      _testResult!['success'] == true ? Icons.check_circle : Icons.error_outline,
                      color: _testResult!['success'] == true ? Colors.green.shade700 : Colors.red.shade700,
                      size: 20,
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        _testResult!['success'] == true
                            ? 'Reachable: ${_testResult!['message']} (status: ${_testResult!['status']})\nURL: ${_testResult!['url']}'
                            : '${_testResult!['error']}',
                        style: TextStyle(
                          fontSize: 12,
                          color: _testResult!['success'] == true
                              ? Colors.green.shade900
                              : Colors.red.shade900,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}
