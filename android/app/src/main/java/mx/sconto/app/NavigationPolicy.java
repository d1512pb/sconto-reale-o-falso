package mx.sconto.app;

import java.net.URI;
import java.net.URISyntaxException;

final class NavigationPolicy {
    static final String START = "https://d1512pb.github.io/sconto-reale-o-falso/";

    static boolean internal(String url) {
        try {
            URI uri = new URI(url);
            String path = uri.getPath();
            return "https".equalsIgnoreCase(uri.getScheme())
                && "d1512pb.github.io".equalsIgnoreCase(uri.getHost())
                && uri.getUserInfo() == null && (uri.getPort() == -1 || uri.getPort() == 443)
                && ("/sconto-reale-o-falso/".equals(path)
                    || "/sconto-reale-o-falso/index.html".equals(path));
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
