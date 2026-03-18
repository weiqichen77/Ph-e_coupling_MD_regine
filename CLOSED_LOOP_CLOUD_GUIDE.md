# Closed-Loop e-ph Coupling: Change Classification and Cloud Operation Guide

## 1) Current Closure Status

This repository now has an executable closed loop for the target method:

1. EPW-side N/U friction tensor extraction from source patch
2. QE/EPW output packing into aligned supervised data
3. DeepMD model training and freeze (PES + N/U channels)
4. LAMMPS run with custom e-ph fix and model inference
5. Trajectory output for structural evolution under coupling

Practical note:

- Two runnable training paths are available:
  - Compatibility path: PyTorch/property fallback
  - Strict path: DeepMD 2.2 + polar atomic tensor labels (recommended for strict atomic 3x3 channel supervision)

## 2) Modification Classification

### A. LAMMPS e-ph coupling core

1. [fix_ttm_hydro_3d.cpp](fix_ttm_hydro_3d.cpp)
2. [fix_ttm_hydro_3d.h](fix_ttm_hydro_3d.h)
3. [ttm_hydro_3d_plugin.cpp](ttm_hydro_3d_plugin.cpp)
4. [ttm_hydro_3d_plugin.so](ttm_hydro_3d_plugin.so)

What was added/confirmed:

1. 3D hydro fix entry and runtime registration
2. N/U dual-model loading and inference in fix
3. Explicit N reaction source term contribution in electron momentum update
4. Coarse-grained coupling terms and per-step force/energy integration path

### B. QE/EPW source patch for N/U tensors

1. [external/q-e/EPW/src/epw_nu_export.f90](external/q-e/EPW/src/epw_nu_export.f90)
2. [external/q-e/EPW/src/selfen.f90](external/q-e/EPW/src/selfen.f90)
3. [external/q-e/EPW/src/use_wannier.f90](external/q-e/EPW/src/use_wannier.f90)
4. [external/q-e/EPW/src/Makefile](external/q-e/EPW/src/Makefile)

What was added/confirmed:

1. N/U classification and export module wiring
2. Atomic/channel-resolved friction tensor accumulation path
3. Projector-based data passing path into self-energy routine
4. Makefile object inclusion and successful EPW build linkage

### C. Data pipeline and packaging scripts

1. [tools/qe_epw_pack.py](tools/qe_epw_pack.py)
2. [tools/npz_to_deepmd.py](tools/npz_to_deepmd.py)
3. [tools/run_real_epw_minimal.sh](tools/run_real_epw_minimal.sh)

What was added/confirmed:

1. Parse QE energy/forces + EPW friction tensor text
2. Build aligned NPZ with lambda/sigma labels
3. Convert to DeepMD dataset layout and template inputs
4. Real-input minimal automation script to generate non-zero friction tensors

### D. End-to-end orchestration and demos

1. [tools/run_e2e_real_training_demo.py](tools/run_e2e_real_training_demo.py)
2. [tools/run_e2e_strict_polar_demo.py](tools/run_e2e_strict_polar_demo.py)
3. [tools/run_step2_deepmd_smoke_demo.py](tools/run_step2_deepmd_smoke_demo.py)
4. [tools/demo_graphene_defect_chain.py](tools/demo_graphene_defect_chain.py)

What was added/confirmed:

1. One-command convert-train-freeze-run orchestration
2. Trajectory dump and report generation
3. Strict atomic tensor supervision path via polar head

### E. Main generated verification outputs

Compatibility/real path:

1. [tmp_e2e_real_demo/e2e_report.json](tmp_e2e_real_demo/e2e_report.json)
2. [tmp_e2e_real_demo/traj_eph_demo.lammpstrj](tmp_e2e_real_demo/traj_eph_demo.lammpstrj)
3. [tmp_e2e_real_demo/train_pes/graph_pes.pth](tmp_e2e_real_demo/train_pes/graph_pes.pth)
4. [tmp_e2e_real_demo/train_tensor_n/graph_n.pth](tmp_e2e_real_demo/train_tensor_n/graph_n.pth)
5. [tmp_e2e_real_demo/train_tensor_u/graph_u.pth](tmp_e2e_real_demo/train_tensor_u/graph_u.pth)

Strict path:

1. [tmp_e2e_strict_polar/strict_report.json](tmp_e2e_strict_polar/strict_report.json)
2. [tmp_e2e_strict_polar/traj_strict_polar.lammpstrj](tmp_e2e_strict_polar/traj_strict_polar.lammpstrj)
3. [tmp_e2e_strict_polar/train_n/graph_n_strict.pb](tmp_e2e_strict_polar/train_n/graph_n_strict.pb)
4. [tmp_e2e_strict_polar/train_u/graph_u_strict.pb](tmp_e2e_strict_polar/train_u/graph_u_strict.pb)

## 3) Recommended Cloud Deployment Workflow

## 3.1 Build-time dependencies

Suggested components:

1. QE/EPW source toolchain (Fortran/MPI/BLAS/LAPACK/FFTW)
2. LAMMPS with USER-DEEPMD support
3. DeepMD runtime for pair_style and custom fix inference
4. Python runtime for orchestration scripts

## 3.2 Source build steps

### Step A: Build QE/EPW from patched source

Run in [external/q-e](external/q-e):

```bash
make -j4 pw ph epw
```

Verify binaries:

```bash
ls -l external/q-e/bin/pw.x external/q-e/bin/ph.x external/q-e/EPW/bin/epw.x
```

### Step B: Build custom LAMMPS plugin

Run in repo root:

```bash
g++ -std=c++17 -O2 -fPIC -shared \
  ttm_hydro_3d_plugin.cpp fix_ttm_hydro_3d.cpp \
  -Ithird_party/lammps-src/src \
  -Ithird_party/deepmd-kit/source/api_cc/include \
  -Ithird_party/deepmd-kit/source/api_c/include \
  -L"$DEEP_LIB" -ldeepmd_cc \
  -Wl,-rpath,"$DEEP_LIB:/home/codespace/.python/current/lib" \
  -o ttm_hydro_3d_plugin.so
```

## 3.3 Data generation and conversion

### Step A: Generate real EPW tensors

```bash
tools/run_real_epw_minimal.sh
```

Main output:

1. [tmp_real_epw_minimal/epw_friction_tensors.dat](tmp_real_epw_minimal/epw_friction_tensors.dat)
2. [tmp_real_epw_minimal/dataset_sample.npz](tmp_real_epw_minimal/dataset_sample.npz)

### Step B: Strict model training + LAMMPS execution

```bash
/home/codespace/.python/current/bin/python tools/run_e2e_strict_polar_demo.py --n-steps 80 --u-steps 80 --md-steps 100
```

Main outputs:

1. [tmp_e2e_strict_polar/train_n/graph_n_strict.pb](tmp_e2e_strict_polar/train_n/graph_n_strict.pb)
2. [tmp_e2e_strict_polar/train_u/graph_u_strict.pb](tmp_e2e_strict_polar/train_u/graph_u_strict.pb)
3. [tmp_e2e_strict_polar/traj_strict_polar.lammpstrj](tmp_e2e_strict_polar/traj_strict_polar.lammpstrj)

## 4) Cloud API Interface Suggestion

For remote execution and orchestration, use step-based API endpoints:

1. POST /build/qe-epw
2. POST /build/lammps-plugin
3. POST /run/epw-real-minimal
4. POST /run/dataset-pack
5. POST /run/train-strict-models
6. POST /run/lammps-demo
7. GET /status/{job_id}
8. GET /artifacts/{job_id}

Suggested artifact contract:

1. graph_pes path
2. graph_n path
3. graph_u path
4. lammps input path
5. trajectory path
6. run log path

## 5) Operational Checklists

### 5.1 Functional checklist

1. LAMMPS input includes custom fix call ttm/hydro/3d
2. pair_style deepmd loads PES graph
3. fix arguments include N and U graph files
4. thermo output changes over MD steps
5. trajectory contains expected number of frames

### 5.2 Scientific sanity checklist

1. EPW friction tensors are not all zeros for selected run setup
2. N/U channels are both non-empty in exported labels
3. model compatibility with runtime backend is validated before production run
4. strict path report confirms atomic tensor label mode

## 6) Known Constraints and Mitigations

1. DeepMD schema mismatch for fitting_net.type=tensor in current default environment
   - Mitigation: strict route uses polar + atomic_polarizability in DeepMD 2.2
2. Runtime emits missing libcudart warnings on CPU-only nodes
   - Mitigation: CPU execution remains functional; can silence by matching runtime build to node profile
3. Tiny demo datasets are for closure validation, not final production fidelity
   - Mitigation: scale training data and k/q meshes for production

## 7) Fast Start for a New Cloud Node

1. Clone repository and sync patched [external/q-e](external/q-e)
2. Build QE/EPW and plugin
3. Run [tools/run_real_epw_minimal.sh](tools/run_real_epw_minimal.sh)
4. Run [tools/run_e2e_strict_polar_demo.py](tools/run_e2e_strict_polar_demo.py)
5. Collect report and trajectory:
   - [tmp_e2e_strict_polar/strict_report.json](tmp_e2e_strict_polar/strict_report.json)
   - [tmp_e2e_strict_polar/traj_strict_polar.lammpstrj](tmp_e2e_strict_polar/traj_strict_polar.lammpstrj)
