import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'config.dart';
import 'services/api.dart';
import 'screens/login.dart';
import 'screens/tasks.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // kSupabaseAnonKey is publishable by design. For local builds pass
  // --dart-define=SUPABASE_ANON_KEY=... (see README); CI injects it too.
  // DEV ONLY: with DEV_BYPASS_AUTH=true, auth init is skipped (no login).
  const devBypass = bool.fromEnvironment('DEV_BYPASS_AUTH', defaultValue: false);
  if (!devBypass) {
    await Supabase.initialize(url: kSupabaseUrl, publishableKey: kSupabaseAnonKey);
  }
  runApp(const IndaiWorkerApp());
}

class IndaiWorkerApp extends StatefulWidget {
  const IndaiWorkerApp({super.key});

  @override
  State<IndaiWorkerApp> createState() => _IndaiWorkerAppState();
}

class _IndaiWorkerAppState extends State<IndaiWorkerApp> {
  IndaiApi? _api;

  @override
  void initState() {
    super.initState();
    _attach();
    // DEV ONLY: Supabase is not initialized in bypass mode — the instance
    // getter throws, which previously crashed startup to a white screen.
    const devBypass = bool.fromEnvironment('DEV_BYPASS_AUTH', defaultValue: false);
    if (!devBypass) {
      Supabase.instance.client.auth.onAuthStateChange.listen((_) => _attach());
    }
  }

  void _attach() {
    // DEV ONLY: DEV_BYPASS_AUTH=true skips login (backend AUTH_DISABLED).
    const devBypass = bool.fromEnvironment('DEV_BYPASS_AUTH', defaultValue: false);
    if (devBypass) {
      setState(() => _api = IndaiApi('dev'));
      return;
    }
    final token = Supabase.instance.client.auth.currentSession?.accessToken;
    setState(() => _api = token == null ? null : IndaiApi(token));
  }

  Future<void> _signOut() async {
    // DEV ONLY: no session exists in bypass mode — nothing to sign out of.
    const devBypass = bool.fromEnvironment('DEV_BYPASS_AUTH', defaultValue: false);
    if (devBypass) return;
    await Supabase.instance.client.auth.signOut();
    setState(() => _api = null);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'IndAI worker',
      theme: ThemeData(colorSchemeSeed: Colors.amber, useMaterial3: true),
      home: _api == null
          ? LoginScreen(onSignedIn: _attach)
          : TasksScreen(api: _api!, onSignOut: _signOut),
    );
  }
}
