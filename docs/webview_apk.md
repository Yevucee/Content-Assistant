# Optional: personal WebView APK (Android)

The web UI is a normal site at your `APP_BASE_URL`. You can load it in a small Android app so it opens in full screen with your icon.

## Steps (Android Studio)

1. **New project** — Empty Activity, minimum SDK 24+, Kotlin.  
2. **Layout** — Single `WebView` filling the screen, with `WebChromeClient` if you use file pickers later.  
3. **Url** — Replace with your `APP_BASE_URL` (same as Railway in production), e.g. `https://example.up.railway.app/`.

4. **Manifest** — Internet permission, `usesCleartextTraffic` only if you use HTTP in dev; production should be HTTPS.  
5. **WebView** — enable JavaScript; consider `setDomStorageEnabled(true)` for forms.

## Example `MainActivity.kt` (illustration only)

```kotlin
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val wv = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            loadUrl("https://YOUR-APP.up.railway.app/app")
        }
        setContentView(wv)
    }
}
```

Keep this app **private** (sideload or internal track) unless you harden the hosted URL. No extra code in the Content Harness repository is required for this flow.
