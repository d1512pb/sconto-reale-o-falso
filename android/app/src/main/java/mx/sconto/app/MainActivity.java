package mx.sconto.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Message;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import android.window.OnBackInvokedDispatcher;

public final class MainActivity extends Activity {
    private WebView web;
    private LinearLayout errorPanel;
    private ProgressBar progreso;
    private boolean cargaFallida;
    private String ultimaPagina = NavigationPolicy.START;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(246, 247, 241));
        setContentView(root);
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                Insets espacios = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
                view.setPadding(espacios.left, espacios.top, espacios.right, espacios.bottom);
                return WindowInsets.CONSUMED;
            });
            getWindow().getInsetsController().setSystemBarsAppearance(
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
        }
        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(246, 247, 241));
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        progreso = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progreso.setIndeterminate(true);
        root.addView(progreso, new FrameLayout.LayoutParams(-1, dp(3), Gravity.TOP));
        crearError(root);
        configurarWeb();
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::volver);
        }
        if (state == null || web.restoreState(state) == null) web.loadUrl(NavigationPolicy.START);
    }

    private int dp(int valor) { return Math.round(valor * getResources().getDisplayMetrics().density); }

    private void crearError(FrameLayout root) {
        errorPanel = new LinearLayout(this);
        errorPanel.setOrientation(LinearLayout.VERTICAL);
        errorPanel.setGravity(Gravity.CENTER);
        errorPanel.setPadding(dp(28), dp(28), dp(28), dp(28));
        errorPanel.setBackgroundColor(Color.rgb(246, 247, 241));
        TextView titulo = new TextView(this);
        titulo.setText(R.string.app_name);
        titulo.setTextSize(30);
        titulo.setTextColor(Color.rgb(36, 93, 77));
        TextView mensaje = new TextView(this);
        mensaje.setText(R.string.error_conexion);
        mensaje.setTextSize(17);
        mensaje.setPadding(0, dp(18), 0, dp(18));
        Button reintentar = new Button(this);
        reintentar.setText(R.string.reintentar);
        reintentar.setOnClickListener(v -> web.loadUrl(ultimaPagina));
        errorPanel.addView(titulo);
        errorPanel.addView(mensaje);
        errorPanel.addView(reintentar);
        root.addView(errorPanel, new FrameLayout.LayoutParams(-1, -1));
        errorPanel.setVisibility(View.GONE);
    }

    private void configurarWeb() {
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSafeBrowsingEnabled(true);
        settings.setSupportMultipleWindows(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setUserAgentString(settings.getUserAgentString() + " ScontoAndroid/" + BuildConfig.VERSION_NAME);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (NavigationPolicy.internal(url)) return false;
                if (request.isForMainFrame()) abrirExterno(url);
                return true;
            }

            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                if (NavigationPolicy.internal(url)) ultimaPagina = url;
                cargaFallida = false;
                errorPanel.setVisibility(View.GONE);
                progreso.setVisibility(View.VISIBLE);
            }

            @Override public void onPageFinished(WebView view, String url) {
                progreso.setVisibility(View.GONE);
                if (!cargaFallida && NavigationPolicy.internal(url)) {
                    view.evaluateJavascript("document.getElementById('instalar')?.setAttribute('hidden','');", null);
                }
            }

            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) mostrarError();
            }

            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 400) mostrarError();
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onCreateWindow(WebView view, boolean dialog, boolean userGesture, Message result) {
                if (!userGesture) return false;
                WebView popup = new WebView(MainActivity.this);
                popup.setWebViewClient(new WebViewClient() {
                    @Override public boolean shouldOverrideUrlLoading(WebView child, WebResourceRequest request) {
                        String url = request.getUrl().toString();
                        if (NavigationPolicy.internal(url)) web.loadUrl(url); else abrirExterno(url);
                        child.post(child::destroy);
                        return true;
                    }
                });
                ((WebView.WebViewTransport) result.obj).setWebView(popup);
                result.sendToTarget();
                return true;
            }
        });
    }

    private void mostrarError() {
        cargaFallida = true;
        progreso.setVisibility(View.GONE);
        errorPanel.setVisibility(View.VISIBLE);
    }

    private void abrirExterno(String url) {
        if (!NavigationPolicy.external(url)) return;
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)).addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException error) {
            Toast.makeText(this, R.string.sin_navegador, Toast.LENGTH_LONG).show();
        }
    }

    private void volver() {
        if (web.canGoBack()) web.goBack(); else finish();
    }

    // Respaldo anterior a API 33; las versiones nuevas usan el callback registrado en onCreate.
    @SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed() { volver(); }

    @Override protected void onSaveInstanceState(Bundle state) {
        web.saveState(state);
        super.onSaveInstanceState(state);
    }

    @Override protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }
}
