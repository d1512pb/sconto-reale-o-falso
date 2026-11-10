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
        for (String url : new String[]{"https://d1512pb.github.io.ejemplo.com/sconto-reale-o-falso/",
                "https://d1512pb.github.io/otro/", "http://d1512pb.github.io/sconto-reale-o-falso/",
                "https://usuario@d1512pb.github.io/sconto-reale-o-falso/", "file:///index.html",
                "https://d1512pb.github.io/sconto-reale-o-falso/../otro/", "javascript:alert(1)", null}) {
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
