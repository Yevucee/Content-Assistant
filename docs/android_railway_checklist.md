# Android / phone use with a hosted API (e.g. Railway)

Use this checklist so your phone and your deployment stay aligned.

1. **Public API URL**  
   Set **`APP_BASE_URL`** on the server to your HTTPS origin (e.g. `https://<service>.up.railway.app`). The app uses it for links in the review UI. Do **not** use `http://127.0.0.1:8000` for a hosted service.

2. **LLM from Railway**  
   Set **`OPENAI_BASE_URL`**, **`OPENAI_API_KEY`**, and **`DEFAULT_MODEL`** to values the **server** can reach. The OpenAI-compatible endpoint must be **reachable from your Railway region**, not `http://127.0.0.1:...` on the container unless you add a tunnel. See [railway.md](railway.md).

3. **Phone access**  
   On your Android device, open **`APP_BASE_URL`** in the browser, or add the **PWA to the home screen** (after the manifest is deployed). A thin WebView APK can load the same URL; see [webview_apk.md](webview_apk.md).

4. **Security**  
   The built-in UI is not behind login. Treat your production URL as private, or add edge/auth at your host.
