import 'package:flutter/material.dart';
import '../services/api.dart';
import 'tabs/home_tab.dart';
import 'tabs/tasks_tab.dart';
import 'tabs/alerts_tab.dart';
import 'tabs/profile_tab.dart';

/// Home shell: bottom navigation across Home / Tasks / Alerts / Profile.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.api, required this.me, required this.onSignOut});
  final IndaiApi api;
  final Map<String, dynamic> me;
  final VoidCallback onSignOut;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _tab = 0;
  late Map<String, dynamic> _me;

  @override
  void initState() {
    super.initState();
    _me = Map<String, dynamic>.from(widget.me);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _tab,
        children: [
          HomeTab(api: widget.api, me: _me),
          TasksTab(api: widget.api, me: _me),
          AlertsTab(api: widget.api),
          ProfileTab(api: widget.api, me: _me, onSignOut: widget.onSignOut,
              onChanged: (fresh) async {
                setState(() => _me = fresh);
              }),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined, size: 30), selectedIcon: Icon(Icons.home, size: 30), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.build_outlined, size: 30), selectedIcon: Icon(Icons.build, size: 30), label: 'Tasks'),
          NavigationDestination(icon: Icon(Icons.notifications_outlined, size: 30), selectedIcon: Icon(Icons.notifications, size: 30), label: 'Alerts'),
          NavigationDestination(icon: Icon(Icons.person_outlined, size: 30), selectedIcon: Icon(Icons.person, size: 30), label: 'Profile'),
        ],
      ),
    );
  }
}
