#!/usr/bin/env python3
"""Train a tiny PES model and run LAMMPS smoke with pair_style deepmd.

Pipeline:
1) Ensure synthetic graphene datasets exist (pristine + defect)
2) Train a tiny DeepMD PES model (very short run, smoke-only)
3) Freeze model to .pth
4) Build a LAMMPS data file from pristine coordinates
5) Run LAMMPS with pair_style deepmd + ttm/hydro/3d fix
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import shutil

import numpy as np


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_synth_demo(repo: Path) -> Path:
    out_root = repo / "tmp_graphene_demo"
    report = out_root / "demo_report.json"
    if report.exists():
        return out_root
    run(["python", "tools/demo_graphene_defect_chain.py", "--out-root", "tmp_graphene_demo"], cwd=repo)
    return out_root


def write_pes_input(train_dir: Path, systems: list[str]) -> Path:
    cfg = {
        "model": {
            "type_map": ["X"],
            "descriptor": {
                "type": "se_e2_a",
                "sel": [60],
                "rcut": 6.0,
                "rcut_smth": 5.5,
                "neuron": [25, 50, 100],
                "axis_neuron": 16,
            },
            "fitting_net": {
                "type": "ener",
                "neuron": [120, 120, 120],
                "resnet_dt": True,
            },
        },
        "learning_rate": {
            "type": "exp",
            "start_lr": 1.0e-3,
            "stop_lr": 1.0e-8,
            "decay_steps": 200,
        },
        "loss": {
            "type": "ener",
            "start_pref_e": 0.02,
            "limit_pref_e": 1.0,
            "start_pref_f": 1000.0,
            "limit_pref_f": 1.0,
        },
        "training": {
            "training_data": {
                "systems": systems,
                "batch_size": 1,
                "auto_prob": "prob_uniform",
            },
            "validation_data": {
                "systems": systems,
                "batch_size": 1,
                "auto_prob": "prob_uniform",
                "numb_btch": 1,
            },
            "numb_steps": 20,
            "disp_file": "lcurve_pes_smoke.out",
            "disp_freq": 10,
            "save_freq": 20,
            "save_ckpt": "model_pes_smoke.ckpt",
            "seed": 20260317,
        },
    }
    path = train_dir / "input_pes_smoke.json"
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return path


def build_set_system(src_system: Path, dst_system: Path) -> None:
    dst_set = dst_system / "set.000"
    dst_set.mkdir(parents=True, exist_ok=True)

    type_raw = np.loadtxt(src_system / "type.raw", dtype=int).reshape(-1)
    nat = type_raw.shape[0]

    coord_raw = np.loadtxt(src_system / "coord.raw", dtype=float).reshape(-1)
    force_raw = np.loadtxt(src_system / "force.raw", dtype=float).reshape(-1)
    box_raw = np.loadtxt(src_system / "box.raw", dtype=float).reshape(-1)
    energy_raw = np.loadtxt(src_system / "energy.raw", dtype=float).reshape(-1)

    np.save(dst_set / "coord.npy", coord_raw.reshape(1, nat * 3))
    np.save(dst_set / "force.npy", force_raw.reshape(1, nat * 3))
    np.save(dst_set / "box.npy", box_raw.reshape(1, 9))
    np.save(dst_set / "energy.npy", energy_raw.reshape(1))

    shutil.copy2(src_system / "type.raw", dst_system / "type.raw")


def write_lammps_data(data_file: Path, coord: np.ndarray, box9: np.ndarray) -> None:
    nat = coord.shape[0]
    lx, ly, lz = float(box9[0]), float(box9[4]), float(box9[8])
    lines = []
    lines.append("LAMMPS data file for deepmd smoke")
    lines.append("")
    lines.append(f"{nat} atoms")
    lines.append("1 atom types")
    lines.append("")
    lines.append(f"0.0 {lx:.10f} xlo xhi")
    lines.append(f"0.0 {ly:.10f} ylo yhi")
    lines.append(f"0.0 {lz:.10f} zlo zhi")
    lines.append("")
    lines.append("Masses")
    lines.append("")
    lines.append("1 12.01")
    lines.append("")
    lines.append("Atoms")
    lines.append("")
    for i, r in enumerate(coord, start=1):
        lines.append(f"{i} 1 {r[0]:.10f} {r[1]:.10f} {r[2]:.10f}")
    data_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_lammps_input(path: Path, data_file: Path, graph_pes: Path, fix_style: str) -> None:
    if fix_style == "ttm/hydro/3d":
        fix_args = "8 8 8 0.01 300.0 13579"
    else:
        fix_args = "8 8 0.01 300.0 13579"

    txt = f"""units metal
atom_style atomic
boundary p p p

read_data {data_file}

mass 1 12.01
velocity all create 300.0 12345 mom yes rot no dist gaussian

pair_style deepmd {graph_pes}
pair_coeff * *

neighbor 1.0 bin
neigh_modify every 1 delay 0 check yes

plugin load ./ttm_hydro_3d_plugin.so
fix int all nve
fix eh all {fix_style} graph_prop_gt.pth graph_prop_gt.pth {fix_args}

timestep 0.001
thermo 1
run 1
"""
    path.write_text(txt, encoding="utf-8")


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    out_root = ensure_synth_demo(repo)

    train_dir = out_root / "pes_train"
    train_dir.mkdir(parents=True, exist_ok=True)

    pristine_src = out_root / "graphene_pristine" / "qe_epw_system"
    defect_src = out_root / "graphene_defect" / "qe_epw_system"
    pristine_set = train_dir / "graphene_pristine_set"
    defect_set = train_dir / "graphene_defect_set"
    build_set_system(pristine_src, pristine_set)
    build_set_system(defect_src, defect_set)

    systems = [str(pristine_set.resolve()), str(defect_set.resolve())]
    input_json = write_pes_input(train_dir, systems)

    run(["dp", "--pt", "train", str(input_json)], cwd=train_dir)
    run(["dp", "--pt", "freeze", "-c", str(train_dir), "-o", "graph_pes_smoke.pth"], cwd=train_dir)

    coord = np.load(out_root / "graphene_pristine" / "coord.npy")
    box = np.load(out_root / "graphene_pristine" / "box.npy")

    data_file = out_root / "graphene_pristine" / "data.graphene_pristine"
    write_lammps_data(data_file, coord, box)

    in_file = out_root / "in.ttm_hydro_smoke_deepmd"
    graph_pes = (train_dir / "graph_pes_smoke.pth").resolve()
    write_lammps_input(in_file, data_file.resolve(), graph_pes, "ttm/hydro/3d")

    used_fix_style = "ttm/hydro/3d"
    try:
        run(["lmp", "-in", str(in_file.resolve())], cwd=repo)
    except subprocess.CalledProcessError:
        # Compatibility path for stale plugin binaries that only expose 2d style name.
        used_fix_style = "ttm/hydro/2d"
        write_lammps_input(in_file, data_file.resolve(), graph_pes, used_fix_style)
        run(["lmp", "-in", str(in_file.resolve())], cwd=repo)

    report = {
        "status": "ok",
        "train_input": str(input_json),
        "frozen_pes": str(graph_pes),
        "lammps_input": str(in_file),
        "data_file": str(data_file),
        "used_fix_style": used_fix_style,
    }
    (out_root / "step2_deepmd_smoke_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
