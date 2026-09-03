"""
Bedienung im Browser und auf dem Handy.

    python -m statik3d.web                                  # Port 8080, alle Netzschnittstellen
    python -m statik3d.web --beispiel hall --schluessel geheim
    python run_web.py --modell halle.json --port 8000

Der Rechenkern laeuft auf dem PC oder einem Server; Handy, Tablet und Browser
bedienen ihn ueber die mobile Oberflaeche in statik3d/web/static. Es wird nur
die Python-Standardbibliothek benoetigt (http.server, json).

    from statik3d.web import start_server_thread
    server, thread, state = start_server_thread(model, port=8080, key="geheim")
    print(server.url)
    server.shutdown()
"""
from .server import (State, WebServer, make_server, start_server_thread, serve,  # noqa: F401
                     lan_ip, qr_ascii, apply_op, OPS, state_summary, geometry,
                     result_payload, diagram_payload, member_payload, design_payload,
                     ApiError)

__all__ = ["State", "WebServer", "make_server", "start_server_thread", "serve", "lan_ip",
           "qr_ascii", "apply_op", "OPS", "state_summary", "geometry", "result_payload",
           "diagram_payload", "member_payload", "design_payload", "ApiError"]
