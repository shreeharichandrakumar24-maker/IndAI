import 'dart:async';
import 'dart:io';

/// Classifies API errors into user-friendly messages with actionable guidance,
/// naming the attempted target URL and avoiding exposing secrets or passwords.
String classifyApiError(Object error, {String? targetUrl, int? statusCode}) {
  final target = targetUrl != null && targetUrl.isNotEmpty ? targetUrl : 'the server';
  final errorStr = error.toString();

  // (e) 401 Unauthorized / wrong credentials
  if (statusCode == 401 ||
      errorStr.contains('401') ||
      errorStr.contains('Invalid username or password') ||
      errorStr.contains('Sign-in required')) {
    return 'Invalid username or password.';
  }

  // (f) 429 Rate limited
  if (statusCode == 429 || errorStr.contains('429') || errorStr.contains('Too many attempts')) {
    return 'Too many attempts, try again later.';
  }

  // (g) Server error 5xx
  if (statusCode != null && statusCode >= 500) {
    return 'Server error (HTTP $statusCode) at $target.\nPlease check backend console/logs.';
  }
  if (errorStr.contains(' 500') || errorStr.contains(' 502') || errorStr.contains(' 503') || errorStr.contains(' 504')) {
    return 'Server error at $target.\nPlease check backend console/logs.';
  }

  // (c) Cleartext HTTP blocked by Android network security policy
  if (errorStr.toLowerCase().contains('cleartext') ||
      errorStr.contains('CLEARTEXT communication to') ||
      errorStr.contains('not permitted by network security policy')) {
    return 'Android blocked cleartext HTTP to $target.\n\nFix: Ensure cleartextTrafficPermitted="true" in Android network security config (network_security_config.xml).';
  }

  // (b) Timeout
  if (error is TimeoutException ||
      errorStr.contains('TimeoutException') ||
      errorStr.toLowerCase().contains('timed out') ||
      errorStr.contains('Connection timed out')) {
    return 'Connection to $target timed out (5s).\n\nPossible fixes:\n• Phone and laptop must be on the same Wi-Fi\n• Allow port 8000 in Windows Firewall (scripts/allow-backend-firewall.ps1)\n• If on college/public Wi-Fi (client isolation), use a phone hotspot';
  }

  // (d) DNS / Invalid host / FormatException
  if (error is FormatException ||
      errorStr.contains('FormatException') ||
      errorStr.contains('Failed host lookup') ||
      errorStr.contains('Name or service not known') ||
      errorStr.contains('Invalid host name') ||
      errorStr.contains('Invalid server address')) {
    return 'Could not resolve server address: $target.\n\nFix: Check the IP address or host format in Server settings.';
  }

  // (a) Cannot connect / Refused / Unreachable host
  if (error is SocketException ||
      errorStr.contains('SocketException') ||
      errorStr.contains('Connection refused') ||
      errorStr.contains('Network is unreachable') ||
      errorStr.contains('No route to host') ||
      errorStr.contains('Connection reset') ||
      errorStr.contains('ClientException')) {
    return 'Cannot reach the server at $target.\n\nPossible fixes:\n• Ensure the backend is running (start-backend.ps1)\n• Phone and laptop must be on the same Wi-Fi\n• Allow port 8000 in Windows Firewall (scripts/allow-backend-firewall.ps1)\n• If using USB debugging, run adb reverse tcp:8000 tcp:8000 (scripts/usb-reverse.ps1)';
  }

  // Fallback cleanly without raw exception prefix
  final cleaned = errorStr.replaceFirst('Exception: ', '').trim();
  if (cleaned.isNotEmpty) {
    return '$cleaned (Target: $target)';
  }
  return 'Could not connect to $target. Please verify connection and retry.';
}
