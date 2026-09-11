"""
Kerbfaelle vorschlagen (DIN EN 1993-1-9) - aus dem, was das Modell weiss.

Die Datei eines Fremdprogramms fuehrt keine Kerbfaelle (Drehlager, RFEM 6:
64 Zugstaebe und 108 Volumen, keiner davon mit Kerbfall). Was sich aus dem
Modell ableiten laesst, in dieser Reihenfolge:

* **Schweissnaehte** des Modells -> Kerbfall der Naht (``schweissnaehte``),
  der unguenstigste je Stab. Er geht jedem Vorschlag vor.
* **Zugstab** (Fachwerkstab mit Rundquerschnitt): 50 N/mm2 - Tabelle 8.1,
  Kerbfall 14: Schrauben und Stangen mit gewalztem oder geschnittenem
  Gewinde unter Zug.
* **Gewalzter Querschnitt** (I, RHS, CHS, Rechteck, Rundstahl als Balken):
  160 N/mm2 - Tabelle 8.1, Kerbfall 1: gewalzte Erzeugnisse mit bearbeiteten
  Kanten - der Grundwerkstoff. Anschluesse, Steifen und Naehte mindern ihn; das
  Programm kennt sie nur, wenn sie als Schweissnaht oder Anschluss
  eingegeben sind. Darum ist das ein Vorschlag, kein Befund.
* **Volumenkoerper**: 160 N/mm2 als Grundwerkstoff mit dem Konzept
  "Strukturspannung" - die Spannung im Element ist keine Nennspannung, und
  Naehte oder Kerben im Koerper mindern den Kerbfall. An **verschweissten
  Beruehrungsstellen** - Knoten, die ein anderer Koerper teilt, ohne
  Kontaktbedingung zwischen beiden - 90 N/mm2 (Anhang B, Tabelle B.1,
  Detail 7: Kreuzstoss mit tragenden Kehlnaehten, Strukturspannung; voll
  durchgeschweisst waere Detail 3 mit 100). Anweisung vom 11.09.2026: dort
  sind die Volumen meist verschweisst, wenn kein Kontakt eingegeben wurde.
  Am Drehlager: 47 gemeinsame Flaechen zwischen 25 Koerperpaaren, keine
  davon von einer der 12 Kontaktbedingungen genannt.

Jeder Vorschlag traegt die Marke ``kerbfall_vorschlag``; eine Eingabe in
Maske oder Tabelle loescht sie. Eingegebene (bestaetigte) Werte bleiben.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: Tabelle 8.1, Kerbfall 14: Stange mit Gewinde unter Zug [Pa]
ZUGSTAB = 50e6
#: Tabelle 8.1, Kerbfall 1: gewalzte Erzeugnisse, Grundwerkstoff [Pa]
GRUNDWERKSTOFF = 160e6
#: Anhang B, Tabelle B.1, Detail 7: Kreuzstoss mit tragenden Kehlnaehten
#: (Strukturspannung) - fuer verschweisste Beruehrungsstellen von Volumen [Pa]
NAHT_STRUKTUR = 90e6
#: Querschnittstypen, die als gewalzt gelten (Section.typ); "circle" nur,
#: wenn der Stab kein Zugstab ist (der bekommt den Gewindestangen-Kerbfall)
GEWALZT = ("I", "RHS", "CHS", "rect", "circle")


@dataclass
class Vorschlag:
    art: str            # "stab" | "koerper"
    name: str
    kerbfall: float     # [Pa]
    grund: str
    konzept: str = ""   # nur Koerper: Nennspannung | Strukturspannung | Kerbspannung
    kerbfall_naht: float = 0.0   # nur Koerper: an verschweissten Beruehrungsstellen


def vorschlag_stab(model, mem) -> Optional[Vorschlag]:
    """Der Vorschlag fuer einen Stab aus Elementtyp und Querschnitt - oder None."""
    if not mem.elements or mem.elements[0] >= len(model.elements):
        return None
    e = model.elements[mem.elements[0]]
    sec = model.sections.get(e.sec)
    typ = str(getattr(sec, "typ", "") or "") if sec is not None else ""
    if e.typ == "truss" and typ == "circle":
        return Vorschlag("stab", mem.name, ZUGSTAB,
                         "Zugstab mit Rundquerschnitt: Stange mit Gewinde unter Zug "
                         "(Tab. 8.1, Kerbfall 14)")
    if typ in GEWALZT:
        return Vorschlag("stab", mem.name, GRUNDWERKSTOFF,
                         f"gewalzter Querschnitt {getattr(sec, 'name', e.sec)}: Grundwerkstoff "
                         "(Tab. 8.1, Kerbfall 1) - Anschlüsse, Steifen und Nähte mindern")
    return None


def vorschlag_koerper(model, k) -> Vorschlag:
    """Der Vorschlag fuer einen Volumenkoerper: Grundwerkstoff, Strukturspannung."""
    return Vorschlag("koerper", k.name, GRUNDWERKSTOFF,
                     "Volumen: Grundwerkstoff (Tab. 8.1, Kerbfall 1) für die Strukturspannung im "
                     "Element, an verschweißten Berührungsstellen 90 (Anhang B, Tab. B.1, Detail 7)",
                     "Strukturspannung", NAHT_STRUKTUR)


def vorschlaege(model) -> list:
    """Alle Vorschlaege des Modells (ohne die Naehte - die stehen im Modell selbst)."""
    out = []
    for mem in model.members.values():
        v = vorschlag_stab(model, mem)
        if v is not None:
            out.append(v)
    for k in (getattr(model, "koerper", {}) or {}).values():
        out.append(vorschlag_koerper(model, k))
    return out


def anwenden(model, log: Optional[list] = None, nur_leere: bool = True) -> dict:
    """Vorschlaege in Staebe und Koerper schreiben.

    Naehte gehen vor (ihr Kerbfall ist ein Befund). Mit ``nur_leere`` bleibt
    ein eingegebener, nicht als Vorschlag markierter Wert stehen; ein
    frueherer Vorschlag wird erneuert. Rueckgabe: Zaehlung je Quelle.
    """
    n = {"naht": 0, "zugstab": 0, "gewalzt": 0, "koerper": 0, "behalten": 0}
    naht: dict = {}
    if getattr(model, "schweissnaehte", None):
        from ..schweissnaehte import kerbfaelle_je_stab
        naht = kerbfaelle_je_stab(model)
        for name, kf in naht.items():
            mem = model.members[name]
            mem.detail_category = float(kf["dsC"])
            mem.detail_category_shear = float(kf["dtC"])
            mem.kerbfall_vorschlag = False
            n["naht"] += 1
    behalten: list = []
    for v in vorschlaege(model):
        if v.art == "stab":
            if v.name in naht:
                continue
            mem = model.members[v.name]
            if nur_leere and mem.detail_category is not None and not mem.kerbfall_vorschlag:
                behalten.append(v.name)
                continue
            mem.detail_category = v.kerbfall
            mem.kerbfall_vorschlag = True
            n["zugstab" if v.kerbfall == ZUGSTAB else "gewalzt"] += 1
        else:
            k = model.koerper[v.name]
            if nur_leere and float(k.kerbfall or 0.0) > 0 and not k.kerbfall_vorschlag:
                behalten.append(v.name)
                continue
            k.kerbfall = v.kerbfall
            k.kerbfall_naht = v.kerbfall_naht
            k.kerbfall_konzept = v.konzept
            k.kerbfall_vorschlag = True
            n["koerper"] += 1
    n["behalten"] = len(behalten)
    if log is not None:
        teile = []
        if n["zugstab"]:
            teile.append(f"{n['zugstab']} Zugstäbe: Kerbfall 50 N/mm² (Tab. 8.1, Kerbfall 14: "
                         "Stange mit Gewinde unter Zug)")
        if n["gewalzt"]:
            teile.append(f"{n['gewalzt']} Stäbe mit gewalztem Querschnitt: Kerbfall 160 N/mm² "
                         "(Tab. 8.1, Kerbfall 1: Grundwerkstoff)")
        if n["koerper"]:
            teile.append(f"{n['koerper']} Volumen: Kerbfall 160 N/mm² (Grundwerkstoff, "
                         "Strukturspannung im Element), an verschweißten Berührungsstellen mit "
                         "anderen Volumen - gemeinsame Knoten ohne Kontaktbedingung - 90 N/mm² "
                         "(Anhang B, Tab. B.1, Detail 7: Kreuzstoß mit tragenden Kehlnähten)")
        if teile:
            log.append("Kerbfälle vorgeschlagen (EN 1993-1-9): " + "; ".join(teile)
                       + ". Vorschläge - in der Stab- bzw. Volumenmaske zu prüfen; Anschlüsse, "
                         "Steifen und Nähte mindern den Kerbfall (Nachweise → Schweißnähte).")
        if n["naht"]:
            log.append(f"  {n['naht']} Stäbe tragen den Kerbfall ihrer Schweißnähte.")
        if behalten:
            log.append(f"  {len(behalten)} behalten den eingegebenen Kerbfall: "
                       + ", ".join(behalten[:8]) + (", …" if len(behalten) > 8 else ""))
    return n
