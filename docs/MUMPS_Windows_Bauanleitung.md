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
