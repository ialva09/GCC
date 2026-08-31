# Grand Coast Construction mobile wrapper

This is an Expo-managed React Native app. It keeps the existing Django website in a native WebView and adds:

- a white GCC logo splash held for at least one second before fading
- a sign-in-first launch flow using the existing Django login
- a native Grand Coast header with a menu button after sign-in
- a role-aware React Navigation side drawer without the Home page
- employee My Workspace tabs for Field, Manager, and Office users
- the existing Explore and Account drawer for clients
- employee bottom tabs for Dashboard, Workspace, and More
- client bottom tabs for Projects, Contact, and Workspace
- employee account actions for privacy, terms, logout, and account deletion
- Android back-button support inside the WebView

## Run locally

From PowerShell:

~~~powershell
cd C:\dev\GCC\mobile
npm start
~~~

The npm start command automatically loads mobile/.env.mobile. Set EXPO_PUBLIC_WEB_APP_URL there to the address reachable from the device:

- iOS Simulator: http://127.0.0.1:8000
- Android Emulator: http://10.0.2.2:8000
- Physical phone: http://YOUR-COMPUTER-LAN-IP:8000

Start Django separately from C:\dev\GCC\website:

~~~powershell
.\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
~~~

For a physical phone, the computer and phone must be on the same network and Windows Firewall must allow port 8000. Use HTTPS for production instead of a local HTTP URL.

The logo-only native splash is configured in app.json and is applied to development and release builds. Expo Go uses its own project loading screen, so it may briefly show the project name instead of the configured logo.

## Commands

~~~powershell
npm start
npm run android
npm run ios
npm run doctor
~~~
