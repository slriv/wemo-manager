# WeMo Manager Android app

Android companion app for connecting a factory-reset WeMo device to Wi-Fi and adding it
to WeMo Manager.

## Requirements

- Node.js 20 or later
- Android Studio with Android SDK and JDK 21
- A running WeMo Manager server reachable from the phone

## Build

Install JavaScript dependencies and synchronize the Capacitor project:

```bash
npm install
npm run sync
```

Open `android/` in Android Studio and build the debug APK, or run:

```bash
cd android
./gradlew assembleDebug
```

The APK is written to:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

From the repository root, `make apk` synchronizes Capacitor, builds the debug APK, and
stages it at `app/static/wemo-manager.apk` for download from the manager setup page.

## Install

Transfer the debug APK to an Android device and install it. Android may require enabling
installation from the chosen file manager or browser.

## Configure and use

1. Open the app and enter the WeMo Manager server URL.
2. Join the factory-reset device's Wi-Fi access point.
3. In the app, choose the home Wi-Fi network and submit its credentials.
4. Rejoin the home Wi-Fi network and complete device detection in WeMo Manager.

The server URL is stored locally on the device.

## Versioning

Update `versionCode` and `versionName` in `android/app/build.gradle` before releasing a
new APK.

## License

MIT. See the repository `LICENSE` file.
