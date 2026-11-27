package mx.sconto.app;

import org.junit.Test;
import static org.junit.Assert.*;

public class NavigationPolicyTest {
    @Test public void conservaRutasDeSconto() {
        assertTrue(NavigationPolicy.internal(NavigationPolicy.START));
        assertTrue(NavigationPolicy.internal(NavigationPolicy.START + "#/producto/P4-917?tienda=sears"));
        assertTrue(NavigationPolicy.internal(NavigationPolicy.START + "index.html"));
    }
    @Test public void noConfiaEnDominiosParecidosNiRutasAjenas() {
        for (String url : new String[]{"https://sconto-v2-api.fly.dev.ejemplo.com/",
                "https://sconto-v2-api.fly.dev/docs", "http://sconto-v2-api.fly.dev/",
                "https://usuario@sconto-v2-api.fly.dev/", "file:///index.html",
                "https://sconto-v2-api.fly.dev/../otro/", "javascript:alert(1)", null}) {
            assertFalse(url, NavigationPolicy.internal(url));
        }
    }
    @Test public void enlacesExternosSoloEnNavegador() {
        assertTrue(NavigationPolicy.external("https://www.sears.com.mx/producto/3625607/"));
        for (String url : new String[]{"intent://prueba", "file:///sdcard/archivo", "javascript:alert(1)",
                "data:text/html,prueba", "https://usuario:clave@ejemplo.com", "sin url", null}) {
            assertFalse(url, NavigationPolicy.external(url));
        }
    }
}
