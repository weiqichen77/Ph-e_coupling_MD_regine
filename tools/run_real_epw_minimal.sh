#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspaces/Ph-e_coupling_MD_regine"
QE_ROOT="$ROOT/external/q-e"
RUN_DIR="$ROOT/tmp_real_epw_minimal"
PYTHON_BIN="/home/codespace/.python/current/bin/python"

# Runtime tunables for stronger/non-zero friction probing.
EPW_NKF="${EPW_NKF:-6}"
EPW_NQF="${EPW_NQF:-6}"
EPW_FSTHICK="${EPW_FSTHICK:-8.0}"
EPW_DEGAUSSW="${EPW_DEGAUSSW:-0.3}"
EPW_TEMPS="${EPW_TEMPS:-1200}"

PW_BIN="$QE_ROOT/bin/pw.x"
PH_BIN="$QE_ROOT/bin/ph.x"
EPW_BIN="$QE_ROOT/EPW/bin/epw.x"

if [[ ! -x "$PW_BIN" ]]; then
  PW_BIN="$(command -v pw.x)"
fi
if [[ ! -x "$PH_BIN" ]]; then
  PH_BIN="$(command -v ph.x)"
fi

if [[ ! -x "$PW_BIN" || ! -x "$PH_BIN" ]]; then
  echo "pw.x/ph.x not found in PATH" >&2
  exit 1
fi
if [[ ! -x "$EPW_BIN" ]]; then
  echo "Patched EPW binary not found at $EPW_BIN" >&2
  exit 1
fi

rm -rf "$RUN_DIR"
mkdir -p "$RUN_DIR"
cd "$RUN_DIR"

cp "$QE_ROOT/EPW/examples/diamond/pp/C_3.98148.UPF" .
mkdir -p meshes

cat > scf.in << 'EOF'
&control
  calculation = 'scf'
  prefix = 'diam'
  pseudo_dir = './'
  outdir = './tmp'
  tprnfor = .true.
  tstress = .true.
/
&system
  ibrav = 2
  celldm(1) = 6.64245
  nat = 2
  ntyp = 1
  ecutwfc = 60
  occupations = 'smearing'
  smearing = 'mp'
  degauss = 0.02
  nbnd = 8
/
&electrons
  diagonalization = 'david'
  mixing_beta = 0.7
  conv_thr = 1.0d-10
/
ATOMIC_SPECIES
  C 12.01078 C_3.98148.UPF
ATOMIC_POSITIONS alat
  C 0.00 0.00 0.00
  C 0.25 0.25 0.25
K_POINTS automatic
  4 4 4 1 1 1
EOF

cat > nscf.in << 'EOF'
&control
  calculation = 'nscf'
  prefix = 'diam'
  pseudo_dir = './'
  outdir = './tmp'
/
&system
  ibrav = 2
  celldm(1) = 6.64245
  nat = 2
  ntyp = 1
  ecutwfc = 60
  occupations = 'smearing'
  smearing = 'mp'
  degauss = 0.02
  nbnd = 8
/
&electrons
  diagonalization = 'david'
  mixing_beta = 0.7
  conv_thr = 1.0d-10
/
ATOMIC_SPECIES
  C 12.01078 C_3.98148.UPF
ATOMIC_POSITIONS alat
  C 0.00 0.00 0.00
  C 0.25 0.25 0.25
EOF

"$PYTHON_BIN" - << 'PY'
from pathlib import Path

n = 4
wk = 1.0 / (n ** 3)
with Path("nscf.in").open("a", encoding="utf-8") as f:
    f.write("K_POINTS crystal\n")
    f.write(f"{n**3}\n")
    for i in range(n):
        for j in range(n):
            for k in range(n):
                f.write(f"  {i/n:.10f}  {j/n:.10f}  {k/n:.10f}  {wk:.10f}\n")
PY

cat > ph.in << 'EOF'
&inputph
  prefix = 'diam'
  outdir = './tmp'
  epsil = .false.
  fildyn = 'diam.dyn'
  ldisp = .true.
  fildvscf = 'dvscf'
  nq1 = 2
  nq2 = 2
  nq3 = 2
  tr2_ph = 1.0d-12
/
EOF

cat > meshes/path.dat << 'EOF'
8 crystal
 0.0 0.0 0.0 0.125
 0.0 0.0 0.5 0.125
 0.0 0.5 0.0 0.125
 0.0 0.5 0.5 0.125
 0.5 0.0 0.0 0.125
 0.5 0.0 0.5 0.125
 0.5 0.5 0.0 0.125
 0.5 0.5 0.5 0.125
EOF

cat > epw.in << 'EOF'
&inputepw
  prefix = 'diam'
  amass(1) = 12.01078
  outdir = './tmp'

  iverbosity = 0

  elph = .true.
  epbwrite = .true.
  epbread = .false.
  epwwrite = .true.
  epwread = .false.

  nbndsub = 4

  wannierize = .true.
  num_iter = 100
  iprint = 2
  dis_win_max = 30
  dis_froz_max = 12
  proj(1) = 'f=0,0,0:l=-3'

  elecselfen = .true.
  phonselfen = .false.
  a2f = .false.

  fsthick = 1.36056981
  temps = 300
  degaussw = 0.1

  dvscf_dir = './save'
  filukk = './diam.ukk'
  filqf = 'meshes/path.dat'
  nkf1 = EPW_NKF_PLACEHOLDER
  nkf2 = EPW_NKF_PLACEHOLDER
  nkf3 = EPW_NKF_PLACEHOLDER

  nqf1 = EPW_NQF_PLACEHOLDER
  nqf2 = EPW_NQF_PLACEHOLDER
  nqf3 = EPW_NQF_PLACEHOLDER

  nk1 = 4
  nk2 = 4
  nk3 = 4

  nq1 = 2
  nq2 = 2
  nq3 = 2
/
EOF

sed -i \
  -e "s/EPW_NKF_PLACEHOLDER/${EPW_NKF}/g" \
  -e "s/EPW_NQF_PLACEHOLDER/${EPW_NQF}/g" \
  -e "s/fsthick = 1.36056981/fsthick = ${EPW_FSTHICK}/" \
  -e "s/degaussw = 0.1/degaussw = ${EPW_DEGAUSSW}/" \
  -e "s/temps = 300/temps = ${EPW_TEMPS}/" \
  epw.in

echo "[1/7] Running SCF"
"$PW_BIN" < scf.in > scf.out

echo "[2/7] Running NSCF"
"$PW_BIN" < nscf.in > nscf.out

echo "[3/7] Running PH"
"$PH_BIN" < ph.in > ph.out

echo "[4/7] Collecting dvscf/dyn files into save/"
mkdir -p save
PH_WORKDIR="_ph0"
if [[ -d tmp/_ph0 ]]; then
  PH_WORKDIR="tmp/_ph0"
fi

if [[ -d "$PH_WORKDIR/diam.phsave" ]]; then
  cp -r "$PH_WORKDIR/diam.phsave" save/
fi

mapfile -t DYN_FILES < <(find . -maxdepth 1 -type f -name 'diam.dyn*' | sed 's#^./##' | grep -E '^diam\.dyn[1-9][0-9]*$' | sort -V)
if [[ ${#DYN_FILES[@]} -eq 0 ]]; then
  echo "No diam.dyn* files found" >&2
  exit 1
fi

qidx=1
for dyn in "${DYN_FILES[@]}"; do
  cp "$dyn" "save/diam.dyn_q${qidx}"
  if [[ $qidx -eq 1 && -f "$PH_WORKDIR/diam.dvscf1" ]]; then
    cp "$PH_WORKDIR/diam.dvscf1" "save/diam.dvscf_q${qidx}"
  else
    src=""
    if [[ -f "$PH_WORKDIR/diam.q_${qidx}/diam.dvscf1" ]]; then
      src="$PH_WORKDIR/diam.q_${qidx}/diam.dvscf1"
    else
      match="$(find "$PH_WORKDIR" -type f -path "*/diam.q_${qidx}*/diam.dvscf1" | head -n 1 || true)"
      if [[ -n "$match" ]]; then
        src="$match"
      fi
    fi
    if [[ -z "$src" ]]; then
      echo "Could not find dvscf file for q index ${qidx}" >&2
      exit 1
    fi
    cp "$src" "save/diam.dvscf_q${qidx}"
  fi
  qidx=$((qidx + 1))
done

echo "[5/7] Running patched EPW"
"$EPW_BIN" < epw.in > epw.out

if [[ ! -s epw_friction_tensors.dat ]]; then
  echo "epw_friction_tensors.dat was not generated" >&2
  exit 1
fi

echo "[6/7] Preparing coord/types/box arrays"
"$PYTHON_BIN" - << 'PY'
import numpy as np

# diamond primitive positions in alat coordinates with celldm(1)=6.64245 bohr
bohr_to_ang = 0.529177210903
a = 6.64245 * bohr_to_ang
coord = np.array([
    [0.0, 0.0, 0.0],
    [0.25 * a, 0.25 * a, 0.25 * a],
], dtype=float)
box = np.array([
    [
        0.0, a / 2.0, a / 2.0,
        a / 2.0, 0.0, a / 2.0,
        a / 2.0, a / 2.0, 0.0,
    ]
], dtype=float)
np.save('coord.npy', coord)
np.save('types.npy', np.array([0, 0], dtype=int))
np.save('box.npy', box)
PY

echo "[7/7] Running pack + npz->deepmd conversion"
"$PYTHON_BIN" "$ROOT/tools/qe_epw_pack.py" \
  --pw-out "$RUN_DIR/scf.out" \
  --epw-tensor "$RUN_DIR/epw_friction_tensors.dat" \
  --coord "$RUN_DIR/coord.npy" \
  --types "$RUN_DIR/types.npy" \
  --out "$RUN_DIR/dataset_sample.npz" \
  --summary "$RUN_DIR/dataset_sample.json"

"$PYTHON_BIN" "$ROOT/tools/npz_to_deepmd.py" \
  --npz "$RUN_DIR/dataset_sample.npz" \
  --outdir "$RUN_DIR/qe_epw_system" \
  --box-npy "$RUN_DIR/box.npy" \
  --types-npy "$RUN_DIR/types.npy"

echo "Completed end-to-end real-input minimal EPW chain in: $RUN_DIR"
