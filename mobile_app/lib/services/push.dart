import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'api.dart';

/// Registers the device FCM token with the backend so plan dispatches can
/// push ("New job …"). Requires google-services.json (see README). If Firebase
/// is unconfigured this throws and the caller falls back to bell-only.
Future<void> setupPush(IndaiApi api) async {
  await Firebase.initializeApp();
  final messaging = FirebaseMessaging.instance;
  await messaging.requestPermission();
  final token = await messaging.getToken();
  if (token == null || token.isEmpty) throw Exception('No FCM token');
  await api.registerPushToken(token);
  FirebaseMessaging.onMessage.listen((_) {
    // Foreground push arrives here; the task list refreshes on next open.
    // (Local-notification display can be added with flutter_local_notifications.)
  });
}
