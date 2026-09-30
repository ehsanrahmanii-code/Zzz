package ai.titan.android;

import android.Manifest;
import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

public class MainActivity extends Activity {
    private WebView webView;
    private final Handler handler = new Handler();

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        setContentView(webView);
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        webView.setWebViewClient(new WebViewClient());

        if (android.os.Build.VERSION.SDK_INT >= 23) {
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE, Manifest.permission.READ_EXTERNAL_STORAGE}, 7001);
        }

        if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
        new Thread(() -> {
            try {
                PyObject module = Python.getInstance().getModule("titan_v45");
                module.callAttr("run_titan", false);
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "TITAN Engine: " + e.getMessage(), Toast.LENGTH_LONG).show());
            }
        }).start();

        handler.postDelayed(() -> webView.loadUrl("http://127.0.0.1:8080/"), 4500);
        handler.postDelayed(() -> webView.reload(), 9000);
    }

    @Override public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack(); else super.onBackPressed();
    }
}
