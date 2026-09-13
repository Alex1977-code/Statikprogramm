# MUMPS für Windows bauen und an Statik3D anbinden

Anweisung für eine eigene Sitzung (Claude Code oder von Hand); Pfade sind
relativ zum Klon von Statikprogramm. Ziel: ein
`mumps`-Python-Paket unter Windows, das `from mumps import DMumpsContext`
liefert, damit Statik3D den Gleichungslöser **MUMPS** in der Auswahl
*Berechnung → Einstellungen → Gleichungslöser* nutzen kann.

Stand 13.09.2026. Lizenz von MUMPS: CeCILL-C (LGPL-artig) – darf mit der
exe ausgeliefert werden. Alles, was hier „prüfen“ heißt, ist beim
Schreiben nicht auf einem Windows-Rechner nachvollzogen worden; die
Sitzung soll es messen, nicht raten.

## Ergebnis der Umsetzung (13.09.2026)

Umgesetzt ist **Weg B + C**: MUMPS 5.8.2 aus dem unveränderten Quelltext
mit MSYS2 gfortran 16.2 gebaut (OpenMP, `-DBLR_MT`, OpenBLAS 0.3.34 in der
OpenMP-Fassung, METIS 5.1.0 statisch eingebunden, PORD) und über einen
eigenen ctypes-Wrapper angebunden — kein PyMUMPS, kein MPI, kein Cython.
Das Rad `packaging/mumps-5.8.2-py3-none-win_amd64.whl` (Paket `mumps`,
Modul `mumps`, `from mumps import DMumpsContext`) enthält:

| Datei | Inhalt |
|---|---|
| `mumps/__init__.py` | `DMumpsContext` (Schnittstelle wie PyMUMPS), `threads()`, `set_threads()`, `beschreibung()`; die C-Struktur `DMUMPS_STRUC_C` Feld für Feld aus `dmumps_c.h` 5.8.2, geprüft an der Versionsnummer, die MUMPS in die Struktur schreibt |
| `mumps/_lib/libdmumps_seq.dll` | MUMPS (3,6 MB) samt `libopenblas.dll`, `libgomp-1.dll`, `libgfortran-5.dll`, `libquadmath-0.dll`, `libwinpthread-1.dll`, `libgcc_s_seh-1.dll` aus MSYS2 |
| `mumps/LIZENZ/` | CeCILL-C (en/fr), MUMPS-Lizenzhinweis, `HERKUNFT.txt` (was weitergegeben wird, Quelle mit SHA-256, Zitierbitte), `Makefile.inc.statik3d`, Lizenzen der Drittanbieter (OpenBLAS, METIS, GCC-Laufzeit, winpthreads, PORD) |

Bauverzeichnis: `C:/Users/alexanderm/Desktop/Statik3D_Mumps_win` (MSYS2
entpackt unter `msys2/`, Quelltext unter `bau/MUMPS_5.8.2`, Paketquelle
unter `paket/`, Varianten unter `varianten/`).

**Weg A** (conda-forge) wurde zuerst probiert und verworfen: `mumps-seq`
5.8.2 gibt es für win-64 (flang-Bau, mit drei Patches), aber ohne OpenMP
in MUMPS — am Würfel 3,4 s, mit keiner Threadzahl schneller — und
`pymumps` verlangt `mpi4py`/MS-MPI. Die OpenBLAS-Variante von conda-forge
bringt `libomp.dll` (LLVM) mit, das neben `libiomp5md.dll` der MKL
(PARDISO) mit „OMP: Error #15“ abbräche; die MKL-Variante der
BLAS-Forwarder (`mkl_rt.3.dll`) lief, blieb aber einkernig. Diese DLLs
liegen als Rückfall unter `varianten/conda-mkl`; der Wrapper lädt sie, wenn
`libdmumps_seq.dll` fehlt.

**Was beim eigenen Bau gemessen wurde** (Würfel 22³ Hex8, 34.914 FHG,
2,59 Mio. Einträge, Ryzen 9 5950X, 16 Kerne / 32 Threads, Faktorisierung):

| Löser | Threads | Zeit | Anmerkung |
|---|---|---|---|
| SuperLU | 1 | 8,25 s | |
| MKL PARDISO | 31 (MKL nimmt 16) | 0,45 s | |
| MUMPS conda-forge (QAMD, ohne OpenMP) | 2…16 | 3,4 s | 7,6·10¹⁰ Flop, 427 MB |
| MUMPS eigener Bau, SYM=2, mit `-DGEMMT_AVAILABLE` | 1 / 4 / 16 / 31 | 1,63 / 2,0 / 4,9 / 10,2 s | `dgemmt` aus OpenBLAS skaliert rückwärts |
| MUMPS eigener Bau, SYM=2, ohne GEMMT | 1 / 4 / 8 / 16 / 31 | 1,26 / 0,97 / 0,86–1,09 / 1,58 / 3,34 s | 2,5·10¹⁰ Flop, 249 MB (METIS) |
| MUMPS eigener Bau, SYM=0, ohne GEMMT | 1 / 4 / 8 / 16 / 31 | 1,38 / 0,91 / 0,64–0,73 / 0,80 / 1,29 s | 4,8·10¹⁰ Flop, 534 MB |

Größeres Modell, Würfel 40³ Hex8 mit 201.720 FHG (Faktorisierung, Threads
nur über OpenMP gesetzt):

| Löser | Threads | Zeit | Anmerkung |
|---|---|---|---|
| MUMPS SYM=2 | 1 / 8 / 16 | 22,1 / 8,1 / 9,8 s | 8,0·10¹¹ Flop, 2,6–3,3 GB Faktoren |
| MUMPS SYM=0 | 16 | 11,6 s | 1,6·10¹² Flop, 5,7 GB |

Folgerungen, die im Code stehen: kein `-DGEMMT_AVAILABLE`; Threads
höchstens acht und nie mehr als physische Kerne
(`mumps.threads_vorgabe()`, `MUMPS_NUM_THREADS` übersteuert); symmetrische
Matrizen als unteres Dreieck.
libgomp liest `OMP_NUM_THREADS` über `msvcrt.dll`, das Pythons
`os.environ` nicht sieht — der Wrapper setzt die Zahl darum nach dem
Laden mit `omp_set_num_threads`. **Nie `openblas_set_num_threads()`
rufen:** danach ignoriert OpenBLAS 0.3.34 `omp_in_parallel()` und öffnet
aus MUMPS' Baumthreads heraus verschachtelte Regionen — der Prozess blieb
mit 8 Threads bei SYM=0 in `exec_blas` stehen (1 959 CPU-Sekunden,
gdb-Rückverfolgung `deadlock_gdb.txt`). Auch OpenBLAS auf einen Thread zu
nageln taugt nicht: dann skaliert MUMPS bei 3D-Modellen gar nicht (1,26 s
bei 1, 1,2–1,4 s bei 8 Threads), weil die großen Fronten oben im Baum die
BLAS brauchen. PARDISO (libiomp5md) und MUMPS (libgomp) laufen im selben
Prozess in beiden Reihenfolgen (`test_koexistenz.py` im Bauverzeichnis).

**Lizenz (CeCILL-C):** MUMPS wird unverändert als Objektcode weitergegeben
(Art. 5.3.1): Lizenztext, Haftungsausschluss (Art. 8/9) und Zugang zum
Quelltext (URL + SHA-256, Kopie im Bauverzeichnis) liegen in
`mumps/LIZENZ` bei; die exe ist „Derivative Software“ (Art. 5.3.3) und
darf unter eigener Lizenz stehen, muss aber die Urheberhinweise
unverändert wiedergeben und aus der Oberfläche heraus nennen (Art. 6.4) —
das tun das Info-Fenster, der Hinweis in der Löserauswahl und das
Benutzerhandbuch. Der Wrapper ist eigener Quelltext, kein Teil von MUMPS.

**Neu bauen** (z. B. neue MUMPS-Version): MSYS2 MINGW64 mit
`mingw-w64-x86_64-gcc-fortran openblas metis make`, Quelltext auspacken,
`Makefile.inc.statik3d` als `Makefile.inc` hineinlegen, `make -j8 d`,
`make dexamples` und `dsimpletest` (Lösung 1 2 3 4 5), dann

```bash
gfortran -shared -o libdmumps_seq.dll -Wl,--whole-archive \
    lib/libdmumps.a lib/libmumps_common.a lib/libpord.a libseq/libmpiseq.a \
    -Wl,--no-whole-archive /mingw64/lib/libmetis.a -lopenblas -fopenmp \
    -Wl,--out-implib,libdmumps_seq.dll.a
```

DLL und die sechs Laufzeit-DLLs nach `paket/mumps/_lib/`, `dmumps_c.h`
mit der Struktur prüfen, `pip wheel paket --no-deps -w dist`, Rad nach
`packaging/`.

**Abnahme (13.09.2026):** `tests.test_loeser` 31/31 (MUMPS trifft
N·L/(E·A), Threads von der Laufzeit, SYM=2 und SYM=0 richtig, Speicher
zurück, 25 Faktorisierungen ohne Wachstum); `run_gui.py --selbsttest` OK;
`pyinstaller packaging/Statik3D.spec` lokal gebaut (434 MB statt 371 MB,
die sieben DLLs kommen als `datas` nach `mumps/_lib`) und
`Statik3D.exe --selbsttest` mit Exit-Code 0: „Loeser in der exe: pardiso,
mumps, pyamg, superlu“, „MUMPS 5.8.2 (gfortran/OpenMP, OpenBLAS, METIS),
8 Threads“, Rahmenbeispiel mit mumps Abweichung 1,6·10⁻¹³. Die
Abschnitte unten sind die ursprüngliche Anweisung.

## 0. Was Statik3D erwartet

Datei `statik3d/solver.py`, Methode `LinearSolver._mumps`:

```python
from mumps import DMumpsContext
ctx = DMumpsContext(sym=0, par=1)
ctx.set_silent()
ctx.set_shape(n)
ctx.set_centralized_assembled(row_1basiert, col_1basiert, werte)   # COO, 1-basiert
ctx.run(job=4)          # Analyse + Faktorisierung
ctx.set_rhs(x)          # x wird in place ueberschrieben
ctx.run(job=3)          # Loesen
```

Das ist die Schnittstelle von **PyMUMPS** (Paket `pymumps`, Modulname
`mumps`). Wer stattdessen einen eigenen Wrapper baut, muss genau diese
Aufrufe anbieten. Die Steifigkeitsmatrix ist symmetrisch positiv definit
(mit Kontakt/Federn: symmetrisch); `sym=2` (allgemein symmetrisch) halbiert
Speicher und Zeit – dann darf nur das untere Dreieck übergeben werden. Für
den ersten Lauf reicht `sym=0`.

Ein Testmodell liegt in Statik3D bereit: `python -m tests.test_loeser`
prüft jeden vorhandenen Löser gegen die geschlossene Lösung N·L/(E·A)
(Backend `mumps` steht schon in der Reihe; fehlt das Paket, wird er
übersprungen und das steht im Protokoll).

## 1. Weg A (zuerst versuchen): fertige Pakete über conda-forge

conda-forge baut MUMPS für win-64 (`mumps-seq`, `mumps-mpi`; prüfen, ob
`pymumps` ebenfalls für win-64 vorliegt – für Linux/macOS ja).

```bat
:: Miniforge installieren (https://github.com/conda-forge/miniforge), dann:
conda create -n mumps python=3.11
conda activate mumps
conda install -c conda-forge mumps-seq pymumps
python -c "from mumps import DMumpsContext; print('ok')"
```

Gelingt der Import, Abschnitt 4 (Prüfen) und 5 (Übernahme) ausführen.
Gibt es `pymumps` nicht für win-64, bleiben die MUMPS-DLLs aus
`mumps-seq` nützlich: dann Weg C (eigener Wrapper) gegen diese DLLs.

## 2. Weg B: MUMPS aus dem Quelltext mit MSYS2 / gfortran

### 2.1 Werkzeuge

1. MSYS2 installieren (https://www.msys2.org), dann im Fenster
   „MSYS2 MINGW64“:
   ```bash
   pacman -Syu
   pacman -S --needed mingw-w64-x86_64-gcc mingw-w64-x86_64-gcc-fortran \
       mingw-w64-x86_64-openblas mingw-w64-x86_64-metis \
       mingw-w64-x86_64-scotch make tar wget
   ```
   (`metis`/`scotch` sind optional: bessere Umordnung, weniger Fill-in.
   Ohne sie nimmt MUMPS sein eigenes PORD.)
2. MUMPS-Quelltext holen: https://mumps-solver.org (Formular, Version
   5.7.x als `MUMPS_5.7.3.tar.gz`; prüfen, welche Version aktuell ist).
   ```bash
   cd <Bauverzeichnis ausserhalb des Klons>
   tar xzf MUMPS_5.7.3.tar.gz && cd MUMPS_5.7.3
   ```

### 2.2 Makefile.inc (sequentiell, gfortran, OpenBLAS)

Vorlage: `Make.inc/Makefile.inc.generic.SEQ`. Als `Makefile.inc` im
Quelltextordner anlegen – die entscheidenden Zeilen:

```make
# ---- Umordnung: PORD (liegt bei) + METIS aus MSYS2 --------------------
LPORDDIR = $(topdir)/PORD/lib/
IPORD    = -I$(topdir)/PORD/include/
LPORD    = -L$(LPORDDIR) -lpord
LMETISDIR = /mingw64/lib
IMETIS    = -I/mingw64/include
LMETIS    = -L$(LMETISDIR) -lmetis
ORDERINGSF = -Dmetis -Dpord
ORDERINGSC = $(ORDERINGSF)
LORDERINGS = $(LMETIS) $(LPORD)
IORDERINGSF = $(IMETIS)
IORDERINGSC = $(IMETIS) $(IPORD)

# ---- Compiler ------------------------------------------------------------
PLAT    =
LIBEXT  = .a
LIBEXT_SHARED = .dll
SONAME  = -soname
FPIC_OPT = 
OUTC    = -o
OUTF    = -o
RM      = /bin/rm -f
CC      = gcc
FC      = gfortran
FL      = gfortran
AR      = ar vr 
RANLIB  = ranlib
LAPACK  = -lopenblas
SCALAP  =
INCPAR  =
LIBPAR  = $(SCALAP) $(LAPACK)
INCSEQ  = -I$(topdir)/libseq
LIBSEQ  = $(LAPACK) -L$(topdir)/libseq -lmpiseq
LIBBLAS = -lopenblas
LIBOTHERS = -lpthread
CDEFS   = -DAdd_
OPTF    = -O2 -fallow-argument-mismatch -DBLR_MT -fopenmp
OPTL    = -O2 -fopenmp
OPTC    = -O2 -fopenmp
INCS = $(INCSEQ)
LIBS = $(LIBSEQ)
LIBSEQNEEDED = libseqneeded
```

`-fallow-argument-mismatch` braucht gfortran ≥ 10 für den alten
MUMPS-Fortran. `-fopenmp` und `-DBLR_MT` geben die Mehrkern-Fassung
(OpenMP in MUMPS und in OpenBLAS): das ist der Grund, MUMPS überhaupt zu
bauen – im Test **messen**, dass mit `OMP_NUM_THREADS=31` mehrere Kerne
laufen.

### 2.3 Bauen

```bash
make clean
make d            # doppelte Genauigkeit: libdmumps, libmumps_common, libpord, libmpiseq
ls lib/ libseq/   # erwartet: libdmumps.a libmumps_common.a libpord.a  und  libseq/libmpiseq.a
make dexamples    # Beispiel: examples/dsimpletest < input_simpletest_real
```

Geht `make dexamples` durch und druckt `dsimpletest` die Lösung
(1 2 3 4 5), ist die Bibliothek in Ordnung.

Für eine DLL (Python braucht eine gemeinsam nutzbare Bibliothek):

```bash
gfortran -shared -o libdmumps_seq.dll -Wl,--whole-archive \
    lib/libdmumps.a lib/libmumps_common.a lib/libpord.a libseq/libmpiseq.a \
    -Wl,--no-whole-archive -lmetis -lopenblas -fopenmp -Wl,--out-implib,libdmumps_seq.dll.a
```

Die DLL hängt an `libopenblas.dll`, `libgfortran-5.dll`, `libgomp-1.dll`,
`libquadmath-0.dll`, `libwinpthread-1.dll`, `libgcc_s_seh-1.dll` aus
`/mingw64/bin` – alle sechs neben die DLL legen (später neben die exe).

### 2.4 PyMUMPS gegen die eigene Bibliothek bauen

PyMUMPS (https://github.com/PyMumps/pymumps) ist ein Cython-Wrapper und
verlangt `mpi4py`. Unter Windows gibt es `mpi4py` als Rad gegen
**Microsoft MPI** (msmpi): MS-MPI Runtime + SDK installieren
(https://learn.microsoft.com/message-passing-interface/microsoft-mpi),
dann `pip install mpi4py`. Mit dem sequentiellen MUMPS (libmpiseq) wird der
MPI-Communicator nur formal durchgereicht.

```bash
pip install cython mpi4py
git clone https://github.com/PyMumps/pymumps
cd pymumps
# setup.py: Bibliotheks- und Include-Pfade auf den Bau zeigen lassen
#   include_dirs: <MUMPS>/include, <MUMPS>/libseq
#   library_dirs: <MUMPS>/lib, <MUMPS>/libseq, /mingw64/lib
#   libraries:    dmumps mumps_common pord mpiseq metis openblas gfortran gomp
pip install .
python -c "from mumps import DMumpsContext; print('ok')"
```

Scheitert der Cython-Bau am MSVC/MinGW-Mischmasch (Python für Windows ist
mit MSVC gebaut, die DLL mit MinGW – für reine C-Schnittstellen geht das,
prüfen), dann Weg C.

## 3. Weg C: schlanker eigener Wrapper über ctypes

Statt PyMUMPS ein Modul `mumps/__init__.py` mit einer Klasse
`DMumpsContext`, die über `ctypes` die C-Schnittstelle `dmumps_c` der DLL
aufruft. Die Struktur `DMUMPS_STRUC_C` steht in `include/dmumps_c.h` –
ihre Feldfolge ist versionsabhängig und muss aus **dieser** Header-Datei
übernommen werden (Felder: `sym, par, job, comm_fortran, icntl[60], cntl[15],
n, nnz, irn, jcn, a, ..., rhs, ...`). Nötige Aufrufe: `job=-1` (Init),
`job=4`, `job=3`, `job=-2` (Ende). `icntl[0..3]` = -1 für „stumm“
(entspricht `set_silent`). Der Wrapper ist etwa 150 Zeilen; die Sitzung
soll ihn gegen `dsimpletest` prüfen.

## 4. Prüfen (nicht raten)

```bash
cd <Klon von Statikprogramm>
.venv/Scripts/python.exe -c "from mumps import DMumpsContext; print('Import ok')"
.venv/Scripts/python.exe -m tests.test_loeser        # Zeile "MUMPS trifft N·L/(E·A)" muss OK sein
```

Dazu eine Messung am Würfel (34 914 FHG) wie im Handbuch: Zeit und
Threads für `superlu`, `pardiso`, `mumps` je einmal – Werte ins Protokoll
der Sitzung. Erwartung: MUMPS mehrkernig deutlich unter SuperLU (12,25 s),
in der Nähe von PARDISO (1,38 s mit vier Threads).

## 5. Übernahme in Statik3D

1. `sym=2` einführen, wenn der Lauf mit `sym=0` steht (nur unteres Dreieck
   übergeben, Messung Speicher/Zeit vorher/nachher).
2. `packaging/Statik3D.spec`: die MUMPS-DLL und ihre sechs MinGW-DLLs als
   `binaries` aufnehmen, `mumps` in `hiddenimports`; `requirements.txt`:
   Herkunft des Pakets (Rad im Ordner `packaging/` ablegen, z. B.
   `pymumps-…-win_amd64.whl`, und im Bau installieren).
3. `run_gui.py --selbsttest`: `mumps` in die Reihe der geprüften Löser
   (`for key in ("pyamg", "superlu", "mumps")`), damit ein Bau ohne MUMPS
   rot wird.
4. Handbuch Kap. 9 (Tabelle der Lizenzen): MUMPS „in der exe: ja“, CeCILL-C
   mit Hinweis auf die Lizenzdatei, die neben die exe gehört.
5. `tests/test_loeser.py` bleibt der Nachweis; ein Lauf ohne
   Übersprungen-Zeile für `mumps` im Protokoll.

## 6. Abnahme

- `from mumps import DMumpsContext` in der `.venv` von Statik3D läuft.
- `tests.test_loeser`: MUMPS trifft N·L/(E·A) (Abweichung < 1e-9).
- Messung: Threads > 1 (Task-Manager oder `OMP_NUM_THREADS` variieren) und
  Zeit am Würfel gegenüber SuperLU.
- exe-Bau mit `--selbsttest` grün, MUMPS in „Löser in der exe“.
