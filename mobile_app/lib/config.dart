// Backend (FastAPI) base URL — the ONLY server this app talks to.
// Architecture: Flutter -> FastAPI -> Supabase. This app never contains
// Supabase URLs/keys/credentials and never calls Supabase directly.
//
// Android emulator: 10.0.2.2 maps to the dev machine's localhost.
// Physical device: use the laptop LAN IP (see README + firewall note).
// Override at build time: --dart-define=API_URL=http://<host>:8000

const String kDefaultApiBaseUrl = String.fromEnvironment(
  'API_URL',
  defaultValue: String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  ),
);

/// Legacy constant kept for backwards compatibility.
const String kApiBaseUrl = kDefaultApiBaseUrl;

/// Key for persisting the runtime server address in SharedPreferences.
const String kServerUrlStorageKey = 'indai.worker.server_url';

/// Normalizes any user-entered server address into a full API base URL.
/// Rules:
/// 1. Trim whitespace; throw FormatException if empty or invalid.
/// 2. If scheme is missing, prepend 'http://'.
/// 3. Default port to 8000 if scheme is http and no port is provided.
/// 4. Strip trailing slashes.
/// 5. Append '/api' exactly once if not already present.
String normalizeApiUrl(String input) {
  final trimmed = input.trim();
  if (trimmed.isEmpty) {
    throw const FormatException('Server address cannot be empty.');
  }

  // Prepend http:// if no scheme is present
  var withScheme = trimmed;
  if (!withScheme.startsWith('http://') && !withScheme.startsWith('https://')) {
    withScheme = 'http://$withScheme';
  }

  final uri = Uri.tryParse(withScheme);
  if (uri == null || uri.host.isEmpty || (uri.scheme != 'http' && uri.scheme != 'https')) {
    throw FormatException('Invalid server address: "$input"');
  }

  // Host validity: check for invalid characters, spaces, leading/trailing dots, percent-encoding
  if (uri.host.contains('%') ||
      uri.host.contains(' ') ||
      uri.host.startsWith('.') ||
      uri.host.endsWith('.')) {
    throw FormatException('Invalid host name: "${uri.host}"');
  }

  final scheme = uri.scheme;
  final host = uri.host;
  final port = uri.hasPort ? uri.port : (scheme == 'http' ? 8000 : null);

  // Clean path: strip trailing slashes, ensure single /api suffix
  var rawPath = uri.path.replaceAll(RegExp(r'/+$'), '');
  if (rawPath.isEmpty || rawPath == '/') {
    rawPath = '/api';
  } else if (!rawPath.endsWith('/api')) {
    rawPath = '$rawPath/api';
  }

  final portPart = (port != null && !(scheme == 'https' && port == 443) && !(scheme == 'http' && !uri.hasPort && port == 80))
      ? ':$port'
      : (uri.hasPort ? ':${uri.port}' : '');

  return '$scheme://$host$portPart$rawPath';
}

/// Returns a human-friendly display version of the server URL (without redundant /api if preferred).
String displayServerUrl(String fullApiUrl) {
  return fullApiUrl.replaceAll(RegExp(r'/api/?$'), '');
}

