package mx.sconto.app;

import java.net.URI;
import java.net.URISyntaxException;

final class NavigationPolicy {
    // v3 · demo final: la app y la API del modelo se sirven desde el mismo origen en Fly.io.
    static final String HOST = "sconto-v2-api.fly.dev";
    static final String START = "https://" + HOST + "/";

    static boolean internal(String url) {
        try {
            URI uri = new URI(url);
            String path = uri.getPath();
            return "https".equalsIgnoreCase(uri.getScheme())
                && HOST.equalsIgnoreCase(uri.getHost())
                && uri.getUserInfo() == null && (uri.getPort() == -1 || uri.getPort() == 443)
                && ("/".equals(path) || "/index.html".equals(path));
        } catch (URISyntaxException | NullPointerException error) {
            return false;
        }
    }

    static boolean external(String url) {
        try {
            URI uri = new URI(url);
            return ("https".equalsIgnoreCase(uri.getScheme()) || "http".equalsIgnoreCase(uri.getScheme()))
                && uri.getHost() != null && uri.getUserInfo() == null;
        } catch (URISyntaxException | NullPointerException error) {
            return false;
        }
    }
}
