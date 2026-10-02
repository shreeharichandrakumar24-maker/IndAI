import 'package:supabase_flutter/supabase_flutter.dart';

// Backend (FastAPI) base URL + Supabase project for auth.
// Android emulator: 10.0.2.2 maps to the dev machine's localhost.
// Physical device on the same Wi-Fi: use the machine's LAN IP instead.
const String kApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);
const String kSupabaseUrl = String.fromEnvironment(
  'SUPABASE_URL',
  defaultValue: 'https://qxhwsuzzdwjmpfdqwwri.supabase.co',
);
const String kSupabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');

SupabaseClient get supabase => Supabase.instance.client;
