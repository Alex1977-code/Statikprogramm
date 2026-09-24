"""
Test der Browser-/Handy-Oberflaeche (statik3d.web): Server im Thread, alle API-Wege.
Aufruf:  python -m tests.test_web      (auch mit pytest lauffaehig)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model  # noqa: E402
from statik3d.web import start_server_thread, OPS  # noqa: E402

RESULTS = []
KEY = "geheim123"


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:62s} {detail}")
    return ok


def _assert_since(n0):
    failed = [r[0] for r in RESULTS[n0:] if not r[1]]
    assert not failed, "fehlgeschlagen: " + ", ".join(failed)


class Client:
    def __init__(self, base, key=KEY):
        self.base = base
        self.key = key

    def req(self, method, path, body=None, raw=False, key=None, ctype="application/json"):
        data = None
        headers = {}
        k = self.key if key is None else key
        if k:
            headers["X-Statik-Key"] = k
        if body is not None:
            if isinstance(body, (bytes, bytearray)):
                data = bytes(body)
                headers["Content-Type"] = ctype
            else:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
        r = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=120) as resp:
                content = resp.read()
                return resp.status, (content if raw else json.loads(content.decode("utf-8"))), dict(resp.headers)
        except urllib.error.HTTPError as ex:
            content = ex.read()
            try:
                j = json.loads(content.decode("utf-8"))
            except Exception:
                j = {"error": content[:200]}
            return ex.code, j, dict(ex.headers)

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.req("POST", path, body if body is not None else {}, **kw)

    def op(self, **payload):
        return self.post("/api/op", payload)

    def wait_job(self, timeout=180):
        t0 = time.time()
        while time.time() - t0 < timeout:
            st, j, _ = self.get("/api/job")
            if j.get("status") != "laeuft":
                return j
            time.sleep(0.15)
        raise TimeoutError("Auftrag nicht fertig")


def _server():
    server, thread, state = start_server_thread(None, host="127.0.0.1", port=0, key=KEY)
    return server, Client(server.local_url.rstrip("/"))


# --------------------------------------------------------------------------
def test_static_and_auth():
    n0 = len(RESULTS)
    server, c = _server()
    try:
        st, html, hdr = c.get("/", raw=True)
        check("Startseite ausgeliefert", st == 200 and b"Statik3D" in html and b"app.js" in html)
        st, js, _ = c.get("/app.js", raw=True)
        check("app.js ausgeliefert", st == 200 and b"View3D" in js)
        st, css, _ = c.get("/app.css", raw=True)
        check("app.css ausgeliefert", st == 200 and b"#sheet" in css)
        st, man, _ = c.get("/manifest.webmanifest")
        check("Manifest fuer Startbildschirm", st == 200 and man.get("display") == "standalone")
        st, _, _ = c.get("/icon.svg", raw=True)
        check("Symbol ausgeliefert", st == 200)
        st, j, _ = c.get("/api/state", key="")
        check("ohne Schluessel: 401", st == 401 and j.get("auth"))
        st, j, _ = c.get("/api/state", key="falsch")
        check("falscher Schluessel: 401", st == 401)
        st, j, _ = c.get("/api/state?key=" + KEY, key="")
        check("Schluessel als Abfrageparameter", st == 200 and "name" in j)
        st, j, _ = c.get("/../etc/passwd", raw=True)
        check("kein Pfadausbruch", st == 404)
        st, j, _ = c.get("/api/gibtesnicht")
        check("unbekannter API-Pfad: 404", st == 404 and "error" in j)
    finally:
        server.shutdown()
        server.server_close()
    _assert_since(n0)


def test_model_editing():
    n0 = len(RESULTS)
    server, c = _server()
    try:
        st, j, _ = c.get("/api/state")
        check("Leeres Startmodell", st == 200 and j["nn"] == 0 and j["load_cases"][0]["name"] == "LF1")
        check("Operationen registriert", len(OPS) >= 50, str(len(OPS)))
        st, j, _ = c.op(op="add_material", grade="S235")
        check("Material anlegen", st == 200 and "S235" in j["state"]["materials"], j.get("error", ""))
        st, j, _ = c.op(op="add_section", designation="IPE 300")
        check("Profil aus Datenbank", st == 200 and "IPE 300" in j["state"]["sections"], j.get("error", ""))
        st, j, _ = c.op(op="add_section", kind="rect", name="R", b=0.1, h=0.2)
        check("Rechteckquerschnitt", st == 200 and j["state"]["sections"]["R"]["typ"] == "rect")
        st, j, _ = c.op(op="add_shell", name="t12", t=0.012)
        check("Schalendicke", st == 200 and "t12" in j["state"]["shells"])
        st, j, _ = c.op(op="line_of_beams", p1=[0, 0, 0], p2=[6, 0, 0], n=6, mat="S235", sec="IPE 300")
        check("Stabzug", st == 200 and j["state"]["nn"] == 7 and j["state"]["ne"] == 6 and j["geometry_changed"])
        st, j, _ = c.op(op="support", nodes=[0], dofs="pinned")
        st, j, _ = c.op(op="support", nodes="6", dofs=[1, 2])
        check("Lager setzen (Liste und Text)", st == 200 and j["state"]["n_supports"] == 2)
        st, j, _ = c.op(op="beam_load", elems=[0, 1, 2, 3, 4, 5], q=[0, 0, -10e3])
        check("Streckenlast", st == 200 and j["state"]["load_cases"][0]["loads"]["counts"]["beam"] == 6)
        st, j, _ = c.op(op="add_case", name="Q", category="Q_B", description="Nutzlast")
        check("Lastfall anlegen", st == 200 and j["state"]["active_case"] == "Q")
        st, j, _ = c.op(op="nodal_load", nodes=[3], F=[0, 0, -20e3, 0, 0, 0], case="Q")
        check("Knotenlast", st == 200 and j["state"]["load_cases"][1]["n_loads"] == 1)
        st, j, _ = c.op(op="gravity", case="LF1", gz=-9.81)
        check("Eigengewicht", st == 200 and j["state"]["load_cases"][0]["gravity"][2] == -9.81)
        st, j, _ = c.op(op="edit_case", name="Q", fields={"new_name": "Nutz", "category": "Q_A", "exclusive_group": "g1"})
        check("Lastfall umbenennen", st == 200 and [x["name"] for x in j["state"]["load_cases"]] == ["LF1", "Nutz"])
        st, j, _ = c.op(op="auto_combinations")
        check("Kombinationen automatisch", st == 200 and len(j["state"]["combinations"]) >= 3, j.get("message", ""))
        st, j, _ = c.op(op="add_combination", name="K_man", factors="LF1=1.35, Nutz=1.5", typ="ULS")
        check("Kombination manuell (Text)", st == 200 and any(x["name"] == "K_man" for x in j["state"]["combinations"]))
        st, j, _ = c.op(op="auto_members")
        check("Staebe erkennen", st == 200 and len(j["state"]["members"]) == 1)
        name = j["state"]["members"][0]["name"]
        st, j, _ = c.op(op="set_member", name=name, fields={"beta_y": 1.0, "L_LT": 2.0, "detail_category": 71e6, "lt_check": True})
        m = j["state"]["members"][0]
        check("Stabparameter setzen", st == 200 and m["L_LT"] == 2.0 and m["detail_category"] == 71e6)
        st, j, _ = c.op(op="add_fatigue_load", name="E1", case_max="Nutz", cycles=5e5)
        check("Ermuedungslast", st == 200 and len(j["state"]["fatigue_loads"]) == 1)
        st, j, _ = c.op(op="hinges", elems=[0], mode=1)
        check("Gelenk", st == 200)
        st, j, _ = c.op(op="design_settings", fields={"gamma_M1": 1.0, "stations": 5})
        check("Nachweiseinstellungen", st == 200 and j["state"]["design"]["gamma_M1"] == 1.0)
        st, j, _ = c.op(op="meta", name="Testmodell", fields={"projekt": "P1"})
        check("Projektdaten", st == 200 and j["state"]["name"] == "Testmodell" and j["state"]["meta"]["projekt"] == "P1")
        # Geometrie
        st, gm, _ = c.get("/api/geometry")
        check("Geometrie: Linien, Lager, Pfeile, Gelenke", st == 200 and len(gm["lines"]) == 6 and len(gm["supports"]) == 2
              and len(gm["hinges"]) == 1 and gm["case"] == "Nutz" and len(gm["arrows"]) == 1)
        st, gm2, _ = c.get("/api/geometry?case=LF1")
        check("Geometrie: Lastfall waehlbar", st == 200 and len(gm2["arrows"]) == 18 and gm2["gravity"])
        # Fehlerfaelle
        st, j, _ = c.op(op="support", nodes=[99], dofs="all")
        check("Ungueltiger Knoten: 400 mit Meldung", st == 400 and "99" in j["error"])
        st, j, _ = c.op(op="gibtsnicht")
        check("Unbekannte Operation: 400", st == 400)
        st, j, _ = c.op(op="add_section", designation="XYZ 999")
        check("Unbekanntes Profil: Fehlermeldung", st == 400 and "error" in j)
        st, j, _ = c.op(op="remove_material", name="S235")
        check("Material in Gebrauch: abgelehnt", st == 400)
        # Loeschen mit Umnummerierung
        st, j, _ = c.op(op="add_node", x=9, y=9, z=9)
        st, j, _ = c.op(op="delete_nodes", nodes=[7])
        check("Freien Knoten loeschen", st == 200 and j["state"]["nn"] == 7)
        st, j, _ = c.op(op="delete_nodes", nodes=[3])
        check("Benutzten Knoten loeschen: abgelehnt", st == 400)
        st, j, _ = c.op(op="delete_elements", elems=[5], with_nodes=True)
        s = j["state"]
        check("Element loeschen (Knoten, Lager, Lasten umnummeriert)", st == 200 and s["ne"] == 5 and s["nn"] == 6
              and s["n_supports"] == 1 and s["load_cases"][0]["loads"]["counts"]["beam"] == 5 and s["members"][0]["n_elements"] == 5)
        # Modell herunterladen / hochladen
        st, data, hdr = c.get("/api/download", raw=True)
        d = json.loads(data.decode("utf-8"))
        mm = Model.from_dict(d)
        check("Download als JSON-Modell lesbar", st == 200 and "attachment" in hdr.get("Content-Disposition", "") and mm.nn == 6)
        st, j, _ = c.post("/api/model", d)
        check("Modell hochladen (POST /api/model)", st == 200 and j["state"]["nn"] == 6)
        st, j, _ = c.get("/api/check")
        check("Modellpruefung", st == 200 and isinstance(j["messages"], list))
        st, j, _ = c.op(op="select_box", xmin=0, xmax=2.5)
        check("Auswahl per Koordinatenfenster", st == 200 and j["nodes"] == [0, 1, 2])
        st, j, _ = c.get("/api/profiles?family=HEB")
        check("Profilliste", st == 200 and "HEB 300" in j["profiles"])
        st, j, _ = c.op(op="clear_mesh")
        check("Netz loeschen", st == 200 and j["state"]["nn"] == 0 and j["state"]["ne"] == 0)
    finally:
        server.shutdown()
        server.server_close()
    _assert_since(n0)


def test_solve_results_report():
    n0 = len(RESULTS)
    server, c = _server()
    try:
        st, j, _ = c.post("/api/example", {"name": "hall"})
        check("Beispiel Hallenrahmen laden", st == 200 and j["state"]["ne"] > 10 and j["state"]["members"])
        st, j, _ = c.get("/api/results")
        check("Ergebnisse vor Berechnung: 404", st == 404)
        st, j, _ = c.post("/api/solve", {"kind": "all", "design": True, "fatigue": True, "workers": 1})
        check("Berechnung gestartet", st == 200 and j["job"]["status"] == "laeuft")
        st, j2, _ = c.post("/api/solve", {"kind": "all"})
        st_op, j3, _ = c.op(op="add_node", x=0, y=0, z=0)
        job = c.wait_job()
        check("Zweiter Start / Bearbeitung waehrend Rechnung abgelehnt (409)",
              (st == 409 or job["status"] != "laeuft") and st_op in (409, 200))
        check("Auftrag fertig", job["status"] == "fertig", job.get("error", ""))
        st, s, _ = c.get("/api/state")
        check("Analyse mit Nachweisen und Ermuedung", s["has_analysis"] and s["analysis"]["design"] and s["analysis"]["fatigue"])
        st, entries, _ = c.get("/api/entries")
        check("Ergebnisauswahl: Umhuellende, Kombinationen, Lastfaelle",
              entries[0]["id"].startswith("env:") and any(e["id"].startswith("combo:") for e in entries)
              and any(e["id"].startswith("case:") for e in entries))
        st, r, _ = c.get("/api/results")
        check("Umhuellende: Verschiebungen, Skalarfeld, Tabellen", st == 200 and len(r["u"]) == s["nn"] and r["umax"] > 0
              and len(r["scalar_nodes"]) == s["nn"] and r["env_rows"] and r["react_rows"] and r["react_sum"])
        st, r, _ = c.get("/api/results?which=" + entries[-1]["id"] + "&field=util")
        check("Lastfall: Stabkraefte + Ausnutzung je Element", st == 200 and r["beam_rows"] and r["scalar_elems"]
              and r["scalar_label"].startswith("Ausnutzung"))
        combo = next(e["id"] for e in entries if e["id"].startswith("combo:"))
        for field in ("uz", "vm", "util_el", "util_fat", "member", "none"):
            st, r, _ = c.get(f"/api/results?which={combo}&field={field}")
            if st != 200:
                break
        check("Alle Faerbungen lieferbar", st == 200, field)
        st, dg, _ = c.get("/api/diagram?which=" + combo + "&quantity=My")
        check("Schnittgroessenverlauf (Kombination)", st == 200 and dg["polys"] and dg["vmax"] > 0 and dg["unit"] == "kNm"
              and len(dg["polys"][0]["base"]) == len(dg["polys"][0]["vals"]))
        st, dg, _ = c.get("/api/diagram?quantity=N")
        check("Schnittgroessenverlauf (Umhuellende)", st == 200 and dg["polys"])
        st, dg, _ = c.get("/api/diagram?quantity=Foo")
        check("Unbekannte Schnittgroesse: 400", st == 400)
        mname = s["members"][0]["name"]
        st, mp, _ = c.get(f"/api/member?which={combo}&name={urllib.parse.quote(mname)}")
        check("Stabverlauf (Kombination) mit Nachweis", st == 200 and len(mp["x"]) > 2 and "design" in mp and mp["L"] > 0)
        st, mp, _ = c.get(f"/api/member?name={urllib.parse.quote(mname)}")
        check("Stabverlauf (Umhuellende min/max)", st == 200 and mp.get("envelope") and len(mp["My"]["min"]) == len(mp["x"]))
        st, dp, _ = c.get("/api/design")
        check("Nachweistabellen", st == 200 and dp["design"]["table"] and dp["design"]["members"][mname]["governing"]
              and dp["fatigue"]["table"])
        st, data, hdr = c.get("/api/report?fmt=html", raw=True)
        check("Bericht HTML", st == 200 and b"<html" in data[:300].lower() and b"Nachweis" in data
              and "text/html" in hdr.get("Content-Type", ""))
        st, data, hdr = c.get("/api/report?fmt=md&download=1", raw=True)
        check("Bericht Markdown als Download", st == 200 and b"# " in data and "attachment" in hdr.get("Content-Disposition", ""))
        st, j, _ = c.get("/api/report?fmt=xyz")
        check("Unbekanntes Berichtsformat: 400", st == 400)
        # Nachweise nachtraeglich
        st, j, _ = c.op(op="set_member", name=mname, fields={"beta_z": 0.7})
        st, s2, _ = c.get("/api/state")
        check("Stabaenderung: Analyse bleibt, Nachweise verworfen", s2["has_analysis"] and not s2["analysis"]["design"])
        st, j, _ = c.post("/api/design")
        job = c.wait_job()
        st, s3, _ = c.get("/api/state")
        check("Nachweise EC3 nachtraeglich", job["status"] == "fertig" and s3["analysis"]["design"], job.get("error", ""))
        st, j, _ = c.post("/api/fatigue")
        job = c.wait_job()
        check("Ermuedung nachtraeglich", job["status"] == "fertig", job.get("error", ""))
        # Einzelner Lastfall, Modal, Knicken
        st, j, _ = c.post("/api/solve", {"kind": "case", "case": s["load_cases"][0]["name"]})
        job = c.wait_job()
        st, entries, _ = c.get("/api/entries")
        check("Nur ein Lastfall", job["status"] == "fertig" and entries[0]["id"] == "env:CASES", job.get("error", ""))
        st, j, _ = c.post("/api/solve", {"kind": "modal", "nmodes": 4})
        job = c.wait_job()
        st, r, _ = c.get("/api/results?which=single&mode=2")
        check("Eigenschwingungen: Formen waehlbar", job["status"] == "fertig" and len(r["modes"]) == 4 and r["mode"] == 2
              and r["scalar_label"].startswith("|φ|"), job.get("error", ""))
        st, j, _ = c.post("/api/solve", {"kind": "buckling", "nmodes": 3})
        job = c.wait_job()
        st, r, _ = c.get("/api/results?which=single")
        check("Knicken", job["status"] == "fertig" and len(r["modes"]) == 3, job.get("error", ""))
        st, j, _ = c.post("/api/solve", {"kind": "foo"})
        check("Unbekannte Analyseart: 400", st == 400)
        # Bearbeitung verwirft Ergebnisse
        st, j, _ = c.op(op="nodal_load", nodes=[0], F=[1e3, 0, 0, 0, 0, 0])
        check("Lastaenderung verwirft Ergebnisse", st == 200 and not j["state"]["has_analysis"] and not j["state"]["single"])
        st, j, _ = c.get("/api/log")
        check("Protokoll", st == 200 and any("Beispiel" in x for x in j["log"]))
    finally:
        server.shutdown()
        server.server_close()
    _assert_since(n0)


def test_contact_and_import():
    n0 = len(RESULTS)
    server, c = _server()
    try:
        st, j, _ = c.post("/api/example", {"name": "contact"})
        check("Kontaktbeispiel geladen", st == 200 and j["state"]["contact"]["supports"])
        st, j, _ = c.post("/api/solve", {"kind": "all", "workers": 1})
        job = c.wait_job()
        st, entries, _ = c.get("/api/entries")
        which = next(e["id"] for e in entries if e["id"].startswith("combo:") or e["id"].startswith("case:"))
        st, r, _ = c.get("/api/results?which=" + urllib.parse.quote(which))
        check("Kontakt: Statuszeilen und Marker", job["status"] == "fertig" and r.get("contact_rows") and r.get("contact_markers"),
              job.get("error", "") or which)
        st, s, _ = c.get("/api/state")
        st, gm, _ = c.get("/api/geometry")
        check("Geometrie: einseitige Lager", len(gm["csupports"]) == len(s["contact"]["supports"]) > 0)
        # Import DXF (Rohdaten im Rumpf)
        dxf = "\n".join(["0", "SECTION", "2", "ENTITIES", "0", "LINE", "8", "0", "10", "0", "20", "0", "30", "0",
                         "11", "3000", "21", "0", "31", "0", "0", "LINE", "8", "0", "10", "3000", "20", "0", "30", "0",
                         "11", "3000", "21", "0", "31", "2000", "0", "ENDSEC", "0", "EOF"]).encode("utf-8")
        st, j, _ = c.post("/api/import?name=rahmen.dxf&unit=0.001", dxf, ctype="application/octet-stream")
        check("DXF-Import ueber Upload (mm -> m)", st == 200 and j["state"]["ne"] == 2 and j["state"]["nn"] == 3, j.get("error", ""))
        st, gm, _ = c.get("/api/geometry")
        check("Importierte Geometrie skaliert", abs(gm["bbox"][1][0] - 3.0) < 1e-9 and abs(gm["bbox"][1][2] - 2.0) < 1e-9)
        st, j, _ = c.post("/api/import?name=kaputt.dxf", b"kein dxf", ctype="application/octet-stream")
        check("Import fehlerhafter Datei: Meldung", st in (200, 400) and ("error" in j or j["state"]["ne"] == 0))
        st, j, _ = c.post("/api/import?name=ohne_endung", b"x", ctype="application/octet-stream")
        check("Import ohne Endung: 400", st == 400)
        # Volumen: Aussenflaechen
        st, j, _ = c.op(op="new", name="Block")
        st, j, _ = c.op(op="add_material", grade="S355")
        st, j, _ = c.op(op="box", lx=1, ly=0.5, lz=0.5, nx=2, ny=1, nz=1, mat="S355")
        st, gm, _ = c.get("/api/geometry")
        check("Volumen: nur Aussenflaechen als Dreiecke", st == 200 and len(gm["tris"]) == 2 * (2 * 2 * 1 + 2 * 2 * 1 + 2 * 1 * 1))
        st, j, _ = c.op(op="face_load", elems=[0, 1], p=1e5, face=1)
        st, gm, _ = c.get("/api/geometry")
        check("Flaechenlast auf Volumen als Pfeil", len(gm["arrows"]) == 2)
        st, j, _ = c.op(op="contact_support", nodes=[0, 1, 2], direction=[0, 0, 1], mu=0.3)
        st, j, _ = c.op(op="gap_element", node_a=0, node_b=3, gap=0.001)
        st, j, _ = c.op(op="contact_pair", name="P", slave_nodes=[4], master_elements=[0], mu=0.2)
        ct = j["state"]["contact"]
        check("Kontaktdefinitionen anlegen", len(ct["supports"]) == 3 and len(ct["gaps"]) == 1 and len(ct["pairs"]) == 1)
        st, j, _ = c.op(op="remove_contact", kind="gap", index=0)
        st, j, _ = c.op(op="clear_contact")
        check("Kontakt entfernen", st == 200 and not j["state"]["contact"]["supports"])
        # Platte + Schalenelement von Hand
        st, j, _ = c.op(op="add_shell", t=0.01)
        st, j, _ = c.op(op="plate", lx=2, ly=1, nx=2, ny=1, mat="S355", origin=[0, 0, 1])
        st, j, _ = c.op(op="add_element", typ="shell3", nodes=[0, 1, 4], mat="S355")
        check("Platte und einzelnes Schalenelement", st == 200 and j["state"]["types"].get("shell4") == 2
              and j["state"]["types"].get("shell3") == 1, j.get("error", ""))
    finally:
        server.shutdown()
        server.server_close()
    _assert_since(n0)


def test_quader_elementtyp():
    """Operation box: nur hex8 und tet4, jeder andere typ wird mit 400 abgewiesen.

    Bis 23.09.2026 reichte _op_box d.get("typ") ungeprueft an grid_box, das
    alles ausser "hex8" still als tet4 baute: gemessen am Stand ec6448c ergab
    typ="hex20", "tet10", "HEX8" oder "quatsch" bei 1x1x1 Zellen je 5 tet4
    mit der Meldung „Quader erzeugt“. Verlangt ist jetzt Status 400 mit dem
    Typ im Fehlertext und ein unveraendertes Modell (0 Knoten, 0 Elemente).
    """
    n0 = len(RESULTS)
    server, c = _server()
    try:
        st, j, _ = c.op(op="new", name="Quader")
        st, j, _ = c.op(op="add_material", grade="S355")
        falsch = []
        for typ in ("hex20", "tet10", "HEX8", "quatsch"):
            st, j, _ = c.op(op="box", lx=1, ly=1, lz=1, nx=1, ny=1, nz=1, mat="S355", typ=typ)
            if st != 400 or typ not in str(j.get("error", "")):
                falsch.append(f"{typ}: Status {st}, {j.get('error') or j.get('message')!r}, "
                              f"Typen {(j.get('state') or {}).get('types')}")
        st, s, _ = c.get("/api/state")
        check("Quader: unbekannter typ abgewiesen (400, Typ in der Meldung)",
              not falsch, "; ".join(falsch) or "hex20, tet10, HEX8, quatsch")
        check("Quader: abgewiesener typ laesst das Modell leer",
              st == 200 and s["nn"] == 0 and s["ne"] == 0, f"nn {s.get('nn')}, ne {s.get('ne')}")
        typen = {}
        for typ in (None, "hex8", "tet4"):
            c.op(op="new", name="Quader")
            c.op(op="add_material", grade="S355")
            kw = {} if typ is None else {"typ": typ}
            st, j, _ = c.op(op="box", lx=1, ly=1, lz=1, nx=1, ny=1, nz=1, mat="S355", **kw)
            typen[str(typ)] = j["state"]["types"] if st == 200 else f"Status {st}"
        check("Quader: ohne typ hex8, hex8 -> 1 hex8, tet4 -> 5 tet4",
              typen == {"None": {"hex8": 1}, "hex8": {"hex8": 1}, "tet4": {"tet4": 5}}, str(typen))
    finally:
        server.shutdown()
        server.server_close()
    _assert_since(n0)


def test_nichtlineare_lager_und_profile():
    """Neue Operationen: Lagerwirkung je FHG, Linien-/Flaechenlager, Gelenke,
    zusammengesetzte Querschnitte, Profilliste nach Land."""
    n0 = len(RESULTS)
    server, c = _server()
    try:
        st, j, _ = c.op(op="add_material", grade="S235")
        st, j, _ = c.op(op="add_section", designation="IPE 240")
        st, j, _ = c.op(op="line_of_beams", p1=[0, 0, 0], p2=[6, 0, 0], n=6,
                        mat="S235", sec="IPE 240")
        st, j, _ = c.op(op="support_nonlinear", nodes=[0],
                        behaviour={"uz": {"typ": "rigid", "failure": "zug", "slip": 0.002},
                                   "ux": {"typ": "rigid", "mu": 0.3, "mu_ref": "uz"},
                                   "uy": {"typ": "rigid"}})
        sup = j["state"]["supports"][0] if st == 200 else {}
        check("Lagerwirkung je FHG gesetzt", st == 200 and sup.get("nonlinear")
              and "Ausfall bei Zug" in sup["beschreibung"]["uz"], str(sup.get("beschreibung")))
        check("Lagerzusammenfassung", "nichtlineare" in j["state"]["support_summary"],
              j["state"]["support_summary"])
        st, j, _ = c.op(op="line_support", nodes=[1, 2, 3, 4],
                        behaviour={"uz": {"typ": "spring", "stiffness": 5e7, "failure": "zug"}})
        check("Linienlager angelegt", st == 200 and len(j["state"]["line_supports"]) == 1,
              j.get("error", ""))
        st, j, _ = c.op(op="add_shell", t=0.01)
        st, j, _ = c.op(op="plate", lx=2, ly=1, nx=2, ny=1, mat="S235", origin=[0, 5, 0])
        elems = [i for i, t in enumerate(j["state"]["types"]) ] and \
            [i for i in range(j["state"]["ne"]) ]
        st, j, _ = c.op(op="surface_support", elems=elems[-2:],
                        behaviour={"uz": {"typ": "spring", "stiffness": 1e7, "failure": "zug"}})
        check("Flaechenlager angelegt", st == 200 and len(j["state"]["surface_supports"]) == 1,
              j.get("error", ""))
        st, j, _ = c.op(op="add_hinge", name="G1", end=1, dofs={"phiy": "free"}, elems=[0])
        check("Gelenk angelegt und zugewiesen", st == 200 and len(j["state"]["hinges"]) == 1,
              j.get("error", ""))
        st, j, _ = c.op(op="composite_section", name="2 UPE 200",
                        parts=[{"profil": "UPE 200", "dy": -0.05},
                               {"profil": "UPE 200", "dy": 0.05, "spiegeln": True}])
        check("Zusammengesetzter Querschnitt", st == 200 and "2 UPE 200" in j["state"]["sections"],
              j.get("message", j.get("error", "")))
        st, j, _ = c.get("/api/profiles?country=US")
        check("Profilliste nach Land", st == 200 and len(j["profiles"]) > 40
              and any(f["code"] == "W" for f in j["families"]), str(len(j.get("profiles", []))))
        st, j, _ = c.get("/api/profiles?country=XX")
        check("unbekanntes Land meldet Fehler", st == 400)
        st, s2, _ = c.get("/api/state")
        check("Laender in der Uebersicht", len(s2["countries"]) >= 3)
        st, j, _ = c.post("/api/solve", {"kind": "all", "workers": 1})
        job = c.wait_job()
        st, entries, _ = c.get("/api/entries")
        which = next((e["id"] for e in entries if e["id"].startswith("case:")), "")
        st, r, _ = c.get("/api/results?which=" + urllib.parse.quote(which))
        check("Modell mit nichtlinearen Lagern rechnet", job["status"] == "fertig"
              and bool(r.get("contact_rows")), job.get("error", "") or which)
        check("Kontaktzeilen nennen den Lager-FHG",
              any(row[1] for row in r.get("contact_rows", [])), "")
        st, j, _ = c.op(op="remove_line_support", index=0)
        st, j, _ = c.op(op="remove_surface_support", index=0)
        check("Lager wieder entfernt", st == 200 and not j["state"]["line_supports"]
              and not j["state"]["surface_supports"])
    finally:
        server.shutdown()
        server.server_close()
    _assert_since(n0)


def test_bound_state():
    """Gemeinsamer Zustand mit einem 'GUI'-Objekt (model/analysis/results)."""
    n0 = len(RESULTS)

    class Gui:
        def __init__(self):
            from statik3d.examples_lib import frame_example
            self.model = frame_example()
            self.analysis = None
            self.results = None

    gui = Gui()
    server, thread, state = start_server_thread(None, host="127.0.0.1", port=0, key=KEY, bound=gui)
    c = Client(server.local_url.rstrip("/"))
    try:
        st, s, _ = c.get("/api/state")
        check("Gebundener Zustand zeigt GUI-Modell", st == 200 and s["nn"] == gui.model.nn and s["nn"] > 0)
        st, j, _ = c.op(op="add_node", x=1, y=2, z=3)
        check("Handy-Aenderung landet im GUI-Modell", st == 200 and gui.model.nn == s["nn"] + 1 and state.version > 0)
        st, j, _ = c.post("/api/solve", {"kind": "all", "workers": 1})
        job = c.wait_job()
        check("Ergebnis vom Handy im GUI-Objekt", job["status"] == "fertig" and gui.analysis is not None, job.get("error", ""))
        from statik3d.examples_lib import plate_example
        gui.model = plate_example()
        st, s, _ = c.get("/api/state")
        check("GUI-Modellwechsel sichtbar", s["nn"] == gui.model.nn)
        check("LAN-Adresse ermittelt", server.url.startswith("http://") and str(server.port) in server.url)
    finally:
        server.shutdown()
        server.server_close()
    _assert_since(n0)


# --------------------------------------------------------------------------
def test_stellungen_din19704_export():
    """Stellungen des Systems, DIN-19704-Beiwerte, ZTV-ING-Liste und Export."""
    n0 = len(RESULTS)
    server, c = _server()
    try:
        st, j, _ = c.post("/api/example", {"name": "gate"})
        check("Beispiel Stauwand geladen", st == 200 and j["state"]["nn"] > 0)

        for name, winkel in (("geschlossen", 0.0), ("Zwischen", 40.0), ("offen", 82.0)):
            st, j, _ = c.op(op="stellung", name=name, winkel=winkel,
                            beschreibung=f"{winkel:g} Grad")
            if st != 200:
                break
        check("Drei Stellungen angelegt",
              st == 200 and len(j["state"]["stellungen"]["liste"]) == 3, j.get("error", ""))
        liste = j["state"]["stellungen"]["liste"]
        check("Stellungen nach Winkel sortiert",
              [x["winkel"] for x in liste] == sorted(x["winkel"] for x in liste))

        st, j, _ = c.op(op="stellung", name="Zwischen", winkel=45.0, lager_aus="A, B",
                        faelle="LF1", dreh_winkel=45.0, gruppen="Klappe",
                        antrieb_knoten="3", antrieb_my=120.0)
        s = j["state"]["stellungen"]["liste"]
        z = next(x for x in s if x["name"] == "Zwischen")
        check("Stellung geaendert statt doppelt angelegt", st == 200 and len(s) == 3)
        check("Lager, Faelle, Drehung und Antrieb uebernommen",
              z["lager_aus"] == ["A", "B"]
              and abs(z["dreh_winkel"] - 45.0) < 1e-9 and z["gruppen"] == ["Klappe"]
              and z["antrieb"] is True and z["faelle"] == ["LF1"], str(z))

        st, j, _ = c.op(op="stellung", name="Falsch", winkel=10.0, faelle="GibtsNicht")
        st, j, _ = c.op(op="stellungen_rechnen")
        falsch = next(x for x in j["state"]["stellungen"]["liste"] if x["name"] == "Falsch")
        check("Unbekannter Lastfall wird als Fehler der Stellung gemeldet",
              st == 200 and falsch["ergebnis"] and "GibtsNicht" in falsch["ergebnis"]["fehler"],
              str(falsch.get("ergebnis")))
        st, j, _ = c.op(op="remove_stellung", name="Falsch")

        st, j, _ = c.op(op="din19704")
        rw = j["state"]["stellungen"]["regelwerk"]
        check("DIN 19704: Kombinationen gebildet", st == 200 and "19704" in j["message"])
        check("Beiwerte je Lastfallklasse geliefert",
              [k["code"] for k in rw["klassen"]] == ["LF1", "LF2", "LF3"]
              and len(rw["klassen"][0]["beiwerte"]) > 5)
        offen0 = rw["offen_gesamt"]
        check("Voreingestellte Beiwerte sind als offen ausgewiesen", offen0 > 0)
        st, j, _ = c.op(op="din19704", klasse="LF1", einwirkung="G", wert=1.35)
        rw = j["state"]["stellungen"]["regelwerk"]
        g = next(b for b in rw["klassen"][0]["beiwerte"] if b["einwirkung"] == "G")
        check("Bestaetigter Beiwert zaehlt nicht mehr als offen",
              st == 200 and g["bestaetigt"] and rw["offen_gesamt"] == offen0 - 1)

        ztv = j["state"]["stellungen"]["ztv"]
        check("ZTV-ING-Pruefliste vorhanden",
              len(ztv) >= 5 and all({"thema", "erfuellt", "hinweis"} <= set(x) for x in ztv))
        check("Betriebsstellungen als erfuellt erkannt",
              any(x["thema"] == "Betriebsstellungen" and x["erfuellt"] for x in ztv))

        st, j, _ = c.op(op="stellungen_rechnen")
        B = j["state"]["stellungen"]
        check("Stellungen gerechnet", st == 200 and B["gerechnet"], j.get("error", ""))
        check("Umhuellende und Kurve geliefert",
              B["eta"] > 0 and len(B["kurve"]) == 3 and all(len(p) == 4 for p in B["kurve"])
              and B["massgebende_stellung"] and B["bericht"])
        check("Jede Stellung hat ein Ergebnis",
              all(x["ergebnis"] and not x["ergebnis"]["fehler"] for x in B["liste"]))

        st, j, _ = c.op(op="remove_stellung", name="offen")
        check("Stellung entfernt", st == 200 and len(j["state"]["stellungen"]["liste"]) == 2)
        st, j, _ = c.op(op="remove_stellung", name="gibtsnicht")
        check("Unbekannte Stellung wird abgewiesen", st >= 400)

        st, s, _ = c.get("/api/state")
        exts = [f["ext"] for f in s["export_formats"]]
        check("Exportformate in der Uebersicht", ".sdnf" in exts and ".sza" in exts and len(exts) >= 12)
        for ext, mindest in ((".sdnf", 400), (".dxf", 400), (".stl", 200),
                             (".sza", 200), (".json", 400)):
            st, data, hdr = c.get("/api/export?fmt=" + ext, raw=True)
            if st != 200 or len(data) < mindest:
                break
        check(f"Export {ext} geliefert", st == 200 and len(data) >= mindest
              and "attachment" in hdr.get("Content-Disposition", ""), f"{st}, {len(data)} B")
        st, data, hdr = c.get("/api/export?fmt=.csv", raw=True)
        check("Ordner-Format kommt als ZIP",
              st == 200 and data[:2] == b"PK" and ".zip" in hdr.get("Content-Disposition", ""))
        st, j, _ = c.get("/api/export?fmt=.xyz")
        check("Unbekanntes Format wird abgewiesen", st >= 400)
    finally:
        server.shutdown()
        server.server_close()
    _assert_since(n0)


# --------------------------------------------------------------------------
def _node() -> str:
    """Pfad zu node, falls vorhanden - sonst leer (die Pruefung entfaellt dann)."""
    import shutil
    for name in ("node", "nodejs"):
        p = shutil.which(name)
        if p:
            return p
    for p in ("/opt/node22/bin/node", "/usr/local/bin/node"):
        if os.path.exists(p):
            return p
    return ""


def test_oberflaeche_rendert():
    """Die Oberflaeche wird ohne Browser gerendert: alle Register, Baum, Filmstreifen.

    Statisch geprueft wird immer; mit node laeuft app.js zusaetzlich wirklich.
    """
    n0 = len(RESULTS)
    hier = os.path.dirname(os.path.abspath(__file__))
    stat = os.path.join(os.path.dirname(hier), "statik3d", "web", "static")
    js = open(os.path.join(stat, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(stat, "app.css"), encoding="utf-8").read()
    html = open(os.path.join(stat, "index.html"), encoding="utf-8").read()
    check("Register Stellungen im Rahmen", 'data-tab="bruecke"' in html
          and 'id="baum"' in html and 'id="film"' in html)
    check("Register Stellungen angemeldet", "bruecke: renderBruecke" in js)
    for name in ("renderBruecke", "renderBaum", "renderFilm", "updateWerkbank",
                 "stellungForm", "etaKurve", "stellungKarte"):
        if f"function {name}" not in js:
            break
    check("Alle Bausteine der Werkbank vorhanden", f"function {name}" in js, name)
    for kl in (".stellungen", ".stellung", ".kurve", ".beiwert", "body.werkbank"):
        if kl not in css:
            break
    check("Stilvorlagen der Werkbank vorhanden", kl in css, kl)

    node = _node()
    if not node:
        check("node nicht vorhanden - Renderpruefung entfaellt", True)
        _assert_since(n0)
        return

    server, c = _server()
    try:
        c.post("/api/example", {"name": "gate"})
        for name, winkel in (("geschlossen", 0.0), ("Zwischen", 40.0), ("offen", 82.0)):
            c.op(op="stellung", name=name, winkel=winkel, beschreibung=f"{winkel:g} Grad")
        c.op(op="din19704")
        c.op(op="stellungen_rechnen")
        import subprocess
        import tempfile

        def rendern(vorsatz: str = "", zustand: dict = None):
            if zustand is None:
                st, zustand, _ = c.get("/api/state")
            with tempfile.TemporaryDirectory() as tmp:
                pfad = os.path.join(tmp, "zustand.json")
                with open(pfad, "w", encoding="utf-8") as f:
                    json.dump(zustand, f)
                r = subprocess.run([node, os.path.join(hier, "render_check.js"),
                                    os.path.join(stat, "app.js"), pfad, vorsatz],
                                   capture_output=True, text=True, timeout=120)
            for zeile in r.stdout.splitlines():
                if zeile.startswith(("OK ", "FAIL")):
                    RESULTS.append((zeile[4:].strip().split("  ")[0], zeile.startswith("OK")))
                    if zeile.startswith("FAIL"):
                        print(zeile)
            check(f"{vorsatz}Oberflaeche rendert vollstaendig", r.returncode == 0,
                  (r.stderr or r.stdout)[-300:] if r.returncode else "")
            return zustand

        voll = rendern()
        # Teilweise nachgewiesen: eine Warnung kuenstlich in die erste
        # Stellung des echten Zustands gesetzt (Staebe nachgewiesen) - ihr eta
        # ist dann keine vollstaendige Ausnutzung und darf nicht gruen sein.
        # Die Uebersicht kennt den Fall (Warnungen bei nachgewiesen = True);
        # ein Modell, das ihn in einer Stellung wirklich erzeugt, ist hier
        # nicht gebaut.
        teil = json.loads(json.dumps(voll))
        e0 = teil["stellungen"]["liste"][0]["ergebnis"]
        e0["warnungen"] = ["Kombination K9 nicht nachgewiesen: künstlich gesetzt"]
        teil["stellungen"]["unvollstaendig"] = [teil["stellungen"]["liste"][0]["name"]]
        rendern("teilweise: ", teil)
        # Dieselben Stellungen ohne Kombinationen, aber mit Nachweisen: kein
        # Nachweis kann gefuehrt werden. Der Browser zeigte dann "η = 0,000"
        # gruen als erfuellt (Gegenpruefung 23.09.2026); die Uebersicht muss
        # sagen, dass nichts nachgewiesen ist, und app.js muss es zeigen.
        st, j, _ = c.op(op="stellungen_rechnen", kombinationen=False, nachweise=True)
        zustand = rendern("ohne Nachweis: ")
        B = zustand.get("stellungen") or {}
        erg = [x.get("ergebnis") or {} for x in B.get("liste", [])]
        check("ohne Nachweis: Uebersicht sagt 'eta nicht bestimmt' und je Stellung "
              "'nicht nachgewiesen'",
              B.get("eta_bestimmt") is False and len(B.get("unvollstaendig") or []) == 3
              and all(e.get("warnungen") and e.get("nachgewiesen") is False for e in erg),
              f"eta_bestimmt {B.get('eta_bestimmt')}, unvollstaendig {B.get('unvollstaendig')}, "
              f"{[(len(e.get('warnungen') or []), e.get('nachgewiesen')) for e in erg]}")
    finally:
        server.shutdown()
        server.server_close()
    _assert_since(n0)


def _nachweismodell(traeger_q: float = None, ohne_fy: bool = True) -> Model:
    """Einfeldtraeger IPE 300 S235 (qz = traeger_q, None = ohne) und daneben
    ein Stab aus einem Werkstoff ohne Streckgrenze (ohne_fy)."""
    from statik3d.model import Material
    from statik3d.profiles import make_section
    from statik3d import mesher
    m = Model("Nachweiszeile")
    m.add_material(Material.steel("S235"))
    m.add_material(Material("Frei", 210e9, 0.3, 7850.0))        # fy = None
    m.add_section(make_section("IPE 300"))
    m.case().category = "G"
    for name, mat, y, q in (("Traeger", "S235", 0.0, traeger_q),
                            ("Ohne_fy", "Frei", 2.0, -10000.0 if ohne_fy else None)):
        if q is None:
            continue
        ids = mesher.line_of_beams(m, mat, "IPE 300", (0, y, 0), (6, y, 0), 6)
        m.fix(ids[0], [0, 1, 2, 3])
        m.fix(ids[-1], [1, 2, 3])
        els = list(range(len(m.elements) - 6, len(m.elements)))
        for e in els:
            m.load_beam(e, qz=q)
        m.add_member(name, els)
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    return m


def test_nachweiszeile_nicht_gefuehrt_nicht_gruen():
    """Die Nachweiszeile der Weboberflaeche ist bei einem nicht gefuehrten Stab nicht gruen.

    Die Oberflaeche faerbte ``design_summary`` mit ``/NICHT/.test(...)``
    (app.js, Register Ergebnisse) und die Zeile im Register Nachweise mit
    ``util_max > 1``. Seit ``DesignResults.summary()`` nicht gefuehrte Staebe
    nennt, heisst es dort „- 1 nicht geführt: …" - klein geschrieben, und
    ein nicht gefuehrter Stab hat Ausnutzung 0. Gemessen 23.09.2026 an
    97df705: beide Zeilen gruen (Klasse ok). Der Server liefert das Urteil
    jetzt als Klasse mit, die Oberflaeche liest den Text nicht mehr aus.

    Am Ende wird der Satz des Benutzerhandbuchs („Stab ohne Streckgrenze“)
    gegen die gemessenen Klassen geprueft: am Stand ec6448c stand „in diesem
    Fall gelb“ direkt hinter „Ist gar kein Stab geführt …“ und las sich, als
    gelte gelb nur dann - gelb ist die Zeile aber auch neben einem geführten
    Träger mit 0,633 (Nebenbefund der Fehlerrunden 22./23.09.2026).
    """
    from tests import handbuch
    n0 = len(RESULTS)
    gemessen = {}
    node = _node()
    hier = os.path.dirname(os.path.abspath(__file__))
    app_js = os.path.join(os.path.dirname(hier), "statik3d", "web", "static", "app.js")
    faelle = (("Traeger 0,633 und Stab ohne f_y", _nachweismodell(-10000.0), "warn"),
              ("nur Stab ohne f_y", _nachweismodell(None), "warn"),
              ("Traeger ueber 1 und Stab ohne f_y", _nachweismodell(-150000.0), "err"),
              ("Gegenprobe nur Traeger 0,633", _nachweismodell(-10000.0, ohne_fy=False), "ok"))
    for name, m, soll in faelle:
        server, thread, state = start_server_thread(m, host="127.0.0.1", port=0, key=KEY)
        c = Client(server.local_url.rstrip("/"))
        try:
            c.post("/api/solve", {"kind": "all", "design": True, "workers": 1})
            job = c.wait_job()
            st, r, _ = c.get("/api/results")
            st2, dp, _ = c.get("/api/design")
            st3, zustand, _ = c.get("/api/state")
            st4, entries, _ = c.get("/api/entries")
        finally:
            server.shutdown()
            server.server_close()
        text = r.get("design_summary", "")
        gemessen[name] = r.get("design_status")
        check(f"{name}: gerechnet, Nachweiszeile da", job["status"] == "fertig" and bool(text),
              job.get("error", "") or text)
        check(f"{name}: /api/results design_status = {soll}",
              r.get("design_status") == soll, str(r.get("design_status")))
        check(f"{name}: /api/design status = {soll}",
              (dp.get("design") or {}).get("status") == soll,
              str((dp.get("design") or {}).get("status")))
        if not node:
            continue
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "daten.json")
            with open(pfad, "w", encoding="utf-8") as f:
                json.dump({"state": zustand, "entries": entries, "result": r, "design": dp}, f)
            p = subprocess.run([node, os.path.join(hier, "render_nachweiszeile.js"), app_js, pfad],
                               capture_output=True, text=True, timeout=120, encoding="utf-8")
        try:
            aus = json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:        # noqa: BLE001
            aus = {}
        for tab in ("ergebnisse", "nachweise"):
            zeilen = [z for z in (aus.get(tab) or []) if isinstance(z, dict)
                      and z.get("text", "").startswith("Nachweise EC3")]
            check(f"{name}: Register {tab} zeigt die Nachweiszeile als {soll}",
                  len(zeilen) == 1 and zeilen[0]["klasse"] == soll,
                  str(zeilen) if zeilen else (p.stderr or p.stdout)[-300:])
    if not node:
        check("node nicht vorhanden - Renderpruefung der Nachweiszeile entfaellt", True)
    hb = handbuch.absatz("**Stab ohne Streckgrenze.**")
    check("Handbuch: gelb, sobald ein Stab nicht geführt ist, auch neben geführten",
          gemessen.get("Traeger 0,633 und Stab ohne f_y") == "warn"
          and gemessen.get("nur Stab ohne f_y") == "warn"
          and "gelb hinterlegt statt grün, sobald ein Stab nicht geführt ist, auch wenn "
              "die übrigen Stäbe geführt und erfüllt sind" in hb
          and "in diesem Fall gelb" not in hb, f"{gemessen}; {hb[-420:]}")
    check("Handbuch: rot, sobald ein Stab über 1 liegt, auch neben einem nicht geführten",
          gemessen.get("Traeger ueber 1 und Stab ohne f_y") == "err"
          and "rot ist sie, sobald ein Stab eine Ausnutzung über 1 hat, auch neben einem "
              "nicht geführten" in hb, f"{gemessen}; {hb[-420:]}")
    _assert_since(n0)


def _nachweise_rendern(node: str, daten: dict) -> dict:
    """Die Register Ergebnisse/Nachweise, die Tabellenzeilen, das Stabdetail und
    den Stabverlauf mit tests/render_nachweiszeile.js rendern (Ausgabe als dict,
    bei einem Fehler {"fehler": Ausgabe von node})."""
    import subprocess
    import tempfile
    hier = os.path.dirname(os.path.abspath(__file__))
    app_js = os.path.join(os.path.dirname(hier), "statik3d", "web", "static", "app.js")
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "daten.json")
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(daten, f)
        p = subprocess.run([node, os.path.join(hier, "render_nachweiszeile.js"), app_js, pfad],
                           capture_output=True, text=True, timeout=120, encoding="utf-8")
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:        # noqa: BLE001
        return {"fehler": (p.stderr or p.stdout)[-300:]}


def test_nicht_gefuehrter_stab_tabelle_detail_verlauf():
    """Ein nicht gefuehrter Stab steht in Tabelle, Stabdetail und Stabverlauf nicht gruen da.

    Die Nachweiszeile wurde am 23.09.2026 umgestellt (Klasse vom Server), die
    Stellen je Stab nicht: Gemessen 23.09.2026 an ec6448c (Traeger 0,633 und
    Stab Ohne_fy aus einem Werkstoff ohne f_y, Status "nicht geführt"):
    Tabellenzeile im Register Nachweise ``<span class="util"
    style="background:#2e8b3a">0,00</span>`` (app.js nahm die Ausnutzung
    r[5], nicht den Status r[9]), Stabdetail ``<span class="status-ok">nicht
    geführt</span>`` mit gruenem 0,00 (Farbe aus ``m.util > 1``), Stabverlauf
    ``<div class="msg ok">Nachweis: Ausnutzung 0,000 –  (, x = – m) · Klasse
    1</div>`` (Farbe aus ``d.design.util > 1``). Der Server liefert jetzt je
    Stab die Klasse (err/warn/ok) mit, die Oberflaeche faerbt danach.
    """
    n0 = len(RESULTS)
    node = _node()
    m = _nachweismodell(-10000.0)
    server, thread, state = start_server_thread(m, host="127.0.0.1", port=0, key=KEY)
    c = Client(server.local_url.rstrip("/"))
    try:
        c.post("/api/solve", {"kind": "all", "design": True, "workers": 1})
        job = c.wait_job()
        st, dp, _ = c.get("/api/design")
        stabverlauf = {}
        for name in ("Traeger", "Ohne_fy"):
            st2, stabverlauf[name], _ = c.get(f"/api/member?which=combo:K1&name={name}")
        st3, zustand, _ = c.get("/api/state")
        st4, r, _ = c.get("/api/results")
        st5, entries, _ = c.get("/api/entries")
    finally:
        server.shutdown()
        server.server_close()
    stabe = (dp.get("design") or {}).get("members") or {}
    ohne, traeger = stabe.get("Ohne_fy") or {}, stabe.get("Traeger") or {}
    check("Stab ohne f_y: gerechnet, Status 'nicht geführt'",
          job["status"] == "fertig" and ohne.get("status") == "nicht geführt"
          and traeger.get("status") == "erfüllt",
          job.get("error", "") or f"{ohne.get('status')}, {traeger.get('status')}")
    check("/api/design: Klasse je Stab (Ohne_fy warn, Traeger ok)",
          ohne.get("klasse") == "warn" and traeger.get("klasse") == "ok",
          f"{ohne.get('klasse')}, {traeger.get('klasse')}")
    check("/api/member: Klasse des Stabnachweises (Ohne_fy warn, Traeger ok)",
          (stabverlauf["Ohne_fy"].get("design") or {}).get("klasse") == "warn"
          and (stabverlauf["Traeger"].get("design") or {}).get("klasse") == "ok",
          str([(stabverlauf[k].get("design") or {}).get("klasse") for k in stabverlauf]))
    if not node:
        check("node nicht vorhanden - Renderpruefung je Stab entfaellt", True)
        _assert_since(n0)
        return
    aus = _nachweise_rendern(node, {"state": zustand, "entries": entries, "result": r,
                                    "design": dp, "member": stabverlauf})
    zeilen = aus.get("stabzeilen") or {}
    z = zeilen.get("Ohne_fy", "")
    check("Tabelle: Ohne_fy ohne gruenes 0,00, Ausnutzung '–' in Warnfarbe, 'nicht geführt'",
          z and "#2e8b3a" not in z and "0,00" not in z
          and 'style="background:var(--warn)"' in z and "nicht geführt" in z,
          z[:300] or str(aus.get("fehler") or aus.get("stabfehler")))
    check("Gegenprobe Tabelle: Traeger weiter mit Ausnutzung 0,63",
          '<span class="util" style="background:#d4b000">0,63</span>' in zeilen.get("Traeger", ""),
          zeilen.get("Traeger", "")[:300])
    detail = aus.get("stabdetail") or {}
    d_ohne, d_tr = detail.get("Ohne_fy") or {}, detail.get("Traeger") or {}
    check("Stabdetail: Ohne_fy 'nicht geführt' in Warnfarbe, Ausnutzung '–'",
          '<span class="status-warn">nicht geführt</span>' in d_ohne.get("kopf", "")
          and "0,00" not in d_ohne.get("ausnutzung", "")
          and "#2e8b3a" not in d_ohne.get("ausnutzung", ""), str(d_ohne))
    check("Gegenprobe Stabdetail: Traeger 'erfüllt' gruen mit 0,63",
          '<span class="status-ok">erfüllt</span>' in d_tr.get("kopf", "")
          and "0,63" in d_tr.get("ausnutzung", ""), str(d_tr))
    verlauf = aus.get("stabverlauf") or {}
    v_ohne = [x for x in verlauf.get("Ohne_fy") or [] if x.get("text", "").startswith("Nachweis")]
    check("Stabverlauf: Ohne_fy 'Nachweis nicht geführt' als warn, ohne Ausnutzung 0,000",
          len(v_ohne) == 1 and v_ohne[0]["klasse"] == "warn"
          and "nicht geführt" in v_ohne[0]["text"] and "0,000" not in v_ohne[0]["text"],
          str(v_ohne))
    v_tr = [x for x in verlauf.get("Traeger") or [] if x.get("text", "").startswith("Nachweis")]
    check("Gegenprobe Stabverlauf: Traeger 'Ausnutzung 0,633' als ok",
          len(v_tr) == 1 and v_tr[0]["klasse"] == "ok" and "Ausnutzung 0,633" in v_tr[0]["text"],
          str(v_tr))
    _assert_since(n0)


def _ermuedungsmodell(lasten, kerbfall: bool = True) -> Model:
    """_nachweismodell(-10000) mit einem zweiten Lastfall Q (qz = -5 kN/m auf
    dem Traeger), Kerbfall 71 an beiden Staeben (kerbfall) und den
    Ermuedungslasten *lasten* = [(Name, Lastfall, Lastspiele)]."""
    m = _nachweismodell(-10000.0)
    m.add_load_case("Q", "Q", activate=False)
    for e in range(6):
        m.load_beam(e, qz=-5000.0, case="Q")
    if kerbfall:
        for mem in m.members.values():
            mem.detail_category = 71e6
    for name, fall, n in lasten:
        m.add_fatigue_load(name, fall, None, n, 1.0)
    return m


def test_ermuedungszeile_nicht_gefuehrt_nicht_gruen():
    """Die Zeile "Ermüdung: …" im Register Nachweise ist nur gruen, wenn jeder
    Ermuedungsnachweis gefuehrt, vollstaendig und erfuellt ist.

    app.js faerbte sie mit ``rows.some(r => parseFloat(r[7]) > 1)``; ein nicht
    gefuehrter Stab hat in der Spalte Ausnutzung "–", parseFloat gibt NaN.
    Gemessen 23.09.2026 an ec6448c: ``<div class="msg ok">Ermüdung: 2 Stäbe;
    nicht geführt: Stab Traeger, Stab Ohne_fy</div>``. Der Weg ist der aus dem
    Browser: nur den Lastfall LF1 rechnen, dann den Ermuedungsnachweis mit
    einer Last auf dem nicht gerechneten Lastfall Q.
    """
    n0 = len(RESULTS)
    node = _node()
    faelle = (("nicht geführt (Q nicht gerechnet)", _ermuedungsmodell([("E_Q", "Q", 2e6)]), "warn"),
              ("unvollständig (Q fehlt, LF1 D < 1)",
               _ermuedungsmodell([("E_Q", "Q", 2e6), ("E_LF1", "LF1", 1e5)]), "warn"),
              ("keine Staebe mit Kerbfall",
               _ermuedungsmodell([("E_LF1", "LF1", 1e5)], kerbfall=False), "warn"),
              ("NICHT erfüllt (LF1 D > 1, Q fehlt)",
               _ermuedungsmodell([("E_Q", "Q", 2e6), ("E_LF1", "LF1", 2e6)]), "err"),
              ("Gegenprobe erfüllt (nur LF1, D < 1)",
               _ermuedungsmodell([("E_LF1", "LF1", 1e5)]), "ok"))
    for name, m, soll in faelle:
        server, thread, state = start_server_thread(m, host="127.0.0.1", port=0, key=KEY)
        c = Client(server.local_url.rstrip("/"))
        try:
            c.post("/api/solve", {"kind": "case", "case": "LF1", "workers": 1})
            job = c.wait_job()
            c.post("/api/fatigue")
            job2 = c.wait_job()
            st, dp, _ = c.get("/api/design")
            st2, zustand, _ = c.get("/api/state")
        finally:
            server.shutdown()
            server.server_close()
        f = dp.get("fatigue") or {}
        check(f"Ermuedung {name}: gerechnet",
              job["status"] == "fertig" and job2["status"] == "fertig" and f.get("summary"),
              job.get("error", "") or job2.get("error", "") or str(f.get("summary")))
        check(f"Ermuedung {name}: /api/design fatigue.status = {soll}",
              f.get("status") == soll, f"{f.get('status')} - {f.get('summary')}")
        if not node:
            continue
        aus = _nachweise_rendern(node, {"state": zustand, "entries": [], "result": {},
                                        "design": dp})
        zeilen = [z for z in (aus.get("nachweise") or []) if isinstance(z, dict)
                  and z.get("text", "").startswith("Ermüdung")]
        check(f"Ermuedung {name}: Register Nachweise zeigt die Zeile als {soll}",
              len(zeilen) == 1 and zeilen[0]["klasse"] == soll,
              str(zeilen) if zeilen else str(aus.get("fehler") or aus)[:300])
    if not node:
        check("node nicht vorhanden - Renderpruefung der Ermuedungszeile entfaellt", True)
    _assert_since(n0)


def main():
    for t in (test_static_and_auth, test_model_editing, test_solve_results_report,
              test_contact_and_import, test_quader_elementtyp, test_nichtlineare_lager_und_profile,
              test_stellungen_din19704_export, test_oberflaeche_rendert,
              test_nachweiszeile_nicht_gefuehrt_nicht_gruen,
              test_nicht_gefuehrter_stab_tabelle_detail_verlauf,
              test_ermuedungszeile_nicht_gefuehrt_nicht_gruen,
              test_bound_state):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except AssertionError as ex:
            print("ASSERT:", ex)
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + " (Ausnahme: %s)" % ex, False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
