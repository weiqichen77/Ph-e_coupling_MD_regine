#!/usr/bin/env python3
"""Strict N/U tensor-like training via DeepMD polar head (atomic labels).

Why this script:
- In available DeepMD schemas, fitting_net.type=tensor is not a valid model type.
- The strict atomic 3x3 route is fitting_net.type=polar + loss.type=tensor
  with atomic_polarizability.npy labels.

Pipeline:
1) Build DeepMD dataset from real EPW npz
2) Prepare strict N/U datasets with atomic_polarizability labels (9*nat per frame)
3) Train/freeze N and U models with DeepMD 2.2 (TF backend, .pb output)
4) Run LAMMPS demo using PES model + strict N/U pb models
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np


def run(cmd: list[str], cwd: Path) -> None:
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def save_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def harmonize_set000(dataset_dir: Path) -> None:
    set_dir = dataset_dir / "set.000"
    if not set_dir.exists():
        return

    for name in ["coord.npy", "force.npy", "sigma_n.npy", "sigma_u.npy", "lambda_n.npy", "lambda_u.npy"]:
        p = set_dir / name
        if p.exists():
            arr = np.load(p)
            if arr.ndim == 3:
                np.save(p, arr.reshape(arr.shape[0], -1))

    # Keep explicit tensor_N/U labels for convenience.
    if (set_dir / "sigma_n.npy").exists():
        np.save(set_dir / "tensor_N.npy", np.load(set_dir / "sigma_n.npy"))
    elif (set_dir / "lambda_n.npy").exists():
        np.save(set_dir / "tensor_N.npy", np.load(set_dir / "lambda_n.npy"))

    if (set_dir / "sigma_u.npy").exists():
        np.save(set_dir / "tensor_U.npy", np.load(set_dir / "sigma_u.npy"))
    elif (set_dir / "lambda_u.npy").exists():
        np.save(set_dir / "tensor_U.npy", np.load(set_dir / "lambda_u.npy"))


def make_strict_dataset(src_dataset: Path, dst_dataset: Path, tensor_file: str) -> None:
    if dst_dataset.exists():
        shutil.rmtree(dst_dataset)
    shutil.copytree(src_dataset, dst_dataset)

    set_dir = dst_dataset / "set.000"
    src = set_dir / tensor_file
    if not src.exists():
        raise FileNotFoundError(f"Missing strict tensor source: {src}")

    arr = np.load(src)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D array in {src}, got {arr.shape}")
    np.save(set_dir / "atomic_polarizability.npy", arr)


def build_polar_input(dataset_dir: Path, out_json: Path, steps: int, ckpt: str, disp: str) -> None:
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
                "type": "polar",
                "neuron": [120, 120, 120],
                "resnet_dt": True,
                "fit_diag": False,
                "sel_type": [0],
            },
        },
        "learning_rate": {
            "type": "exp",
            "start_lr": 1.0e-3,
            "stop_lr": 1.0e-8,
            "decay_steps": 5000,
        },
        "loss": {
            "type": "tensor",
            "pref": 0.0,
            "pref_atomic": 1.0,
        },
        "training": {
            "training_data": {
                "systems": [str(dataset_dir.resolve())],
                "batch_size": 1,
                "auto_prob": "prob_uniform",
            },
            "validation_data": {
                "systems": [str(dataset_dir.resolve())],
                "batch_size": 1,
                "auto_prob": "prob_uniform",
                "numb_btch": 1,
            },
            "numb_steps": int(steps),
            "disp_file": disp,
            "disp_freq": max(1, steps // 10),
            "save_freq": max(1, steps),
            "save_ckpt": ckpt,
            "seed": 20260317,
        },
    }
    save_json(out_json, cfg)


def write_lammps_data(data_file: Path, coord: np.ndarray, types: np.ndarray) -> None:
    nat = coord.shape[0]
    lo = coord.min(axis=0) - 2.0
    hi = coord.max(axis=0) + 2.0

    lines: list[str] = []
    lines.append("LAMMPS data file generated from strict polar pipeline")
    lines.append("")
    lines.append(f"{nat} atoms")
    lines.append(f"{int(types.max()) + 1} atom types")
    lines.append("")
    lines.append(f"{lo[0]:.10f} {hi[0]:.10f} xlo xhi")
    lines.append(f"{lo[1]:.10f} {hi[1]:.10f} ylo yhi")
    lines.append(f"{lo[2]:.10f} {hi[2]:.10f} zlo zhi")
    lines.append("")
    lines.append("Masses")
    lines.append("")
    for t in range(int(types.max()) + 1):
        lines.append(f"{t + 1} 12.01")
    lines.append("")
    lines.append("Atoms")
    lines.append("")
    for i, r in enumerate(coord, start=1):
        lines.append(f"{i} {int(types[i - 1]) + 1} {r[0]:.10f} {r[1]:.10f} {r[2]:.10f}")

    data_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_lammps_input(
    in_file: Path,
    data_file: Path,
    plugin_so: Path,
    pes_graph: Path,
    graph_n: Path,
    graph_u: Path,
    md_steps: int,
) -> None:
    txt = f"""units metal
atom_style atomic
boundary p p p

read_data {data_file}

velocity all create 300.0 12345 mom yes rot no dist gaussian

pair_style deepmd {pes_graph}
pair_coeff * *

neighbor 1.0 bin
neigh_modify every 1 delay 0 check yes

plugin load {plugin_so}
fix int all nve
fix eh all ttm/hydro/3d {graph_n} {graph_u} 8 8 8 0.01 300.0 13579

timestep 0.001
thermo 10
dump trj all custom 1 traj_strict_polar.lammpstrj id type x y z vx vy vz fx fy fz
run {md_steps}
"""
    in_file.write_text(txt, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Strict N/U training + LAMMPS demo")
    p.add_argument("--repo", type=Path, default=Path("/workspaces/Ph-e_coupling_MD_regine"))
    p.add_argument("--source", type=Path, default=Path("/workspaces/Ph-e_coupling_MD_regine/tmp_real_epw_minimal"))
    p.add_argument("--work", type=Path, default=Path("/workspaces/Ph-e_coupling_MD_regine/tmp_e2e_strict_polar"))
    p.add_argument("--dp-bin", type=Path, default=Path("/workspaces/Ph-e_coupling_MD_regine/.venv_deepmd22/bin/dp"))
    p.add_argument("--n-steps", type=int, default=80)
    p.add_argument("--u-steps", type=int, default=80)
    p.add_argument("--md-steps", type=int, default=100)
    p.add_argument("--pes-graph", type=Path, default=Path("/workspaces/Ph-e_coupling_MD_regine/tmp_e2e_real_demo/train_pes/graph_pes.pth"))
    args = p.parse_args()

    repo = args.repo.resolve()
    source = args.source.resolve()
    work = args.work.resolve()
    dp_bin = args.dp_bin.resolve()

    if not dp_bin.exists():
        raise FileNotFoundError(f"Missing dp binary: {dp_bin}")

    for needed in [source / "dataset_sample.npz", source / "coord.npy", source / "types.npy", source / "box.npy"]:
        if not needed.exists():
            raise FileNotFoundError(f"Missing input file: {needed}")

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    dataset_dir = work / "qe_epw_system"
    run(
        [
            sys.executable,
            str(repo / "tools/npz_to_deepmd.py"),
            "--npz",
            str(source / "dataset_sample.npz"),
            "--outdir",
            str(dataset_dir),
            "--box-npy",
            str(source / "box.npy"),
            "--types-npy",
            str(source / "types.npy"),
        ],
        cwd=repo,
    )
    harmonize_set000(dataset_dir)

    ds_n = work / "system_strict_n"
    ds_u = work / "system_strict_u"
    make_strict_dataset(dataset_dir, ds_n, "tensor_N.npy")
    make_strict_dataset(dataset_dir, ds_u, "tensor_U.npy")

    train_n = work / "train_n"
    train_u = work / "train_u"
    train_n.mkdir(parents=True, exist_ok=True)
    train_u.mkdir(parents=True, exist_ok=True)

    n_input = train_n / "input_n_strict.json"
    u_input = train_u / "input_u_strict.json"
    build_polar_input(ds_n, n_input, args.n_steps, "model_n_strict.ckpt", "lcurve_n_strict.out")
    build_polar_input(ds_u, u_input, args.u_steps, "model_u_strict.ckpt", "lcurve_u_strict.out")

    run([str(dp_bin), "train", str(n_input)], cwd=train_n)
    run([str(dp_bin), "freeze", "-c", str(train_n), "-o", str(train_n / "graph_n_strict.pb")], cwd=train_n)
    run([str(dp_bin), "train", str(u_input)], cwd=train_u)
    run([str(dp_bin), "freeze", "-c", str(train_u), "-o", str(train_u / "graph_u_strict.pb")], cwd=train_u)

    graph_n = train_n / "graph_n_strict.pb"
    graph_u = train_u / "graph_u_strict.pb"
    if not graph_n.exists() or not graph_u.exists():
        raise FileNotFoundError("Strict N/U .pb models were not generated")

    pes_graph = args.pes_graph.resolve()
    if not pes_graph.exists():
        raise FileNotFoundError(f"Missing PES graph: {pes_graph}")

    coord = np.load(source / "coord.npy")
    types = np.load(source / "types.npy").reshape(-1)
    data_file = work / "data.strict"
    write_lammps_data(data_file, coord, types)

    plugin_so = repo / "ttm_hydro_3d_plugin.so"
    if not plugin_so.exists():
        raise FileNotFoundError(f"Missing plugin: {plugin_so}")

    in_file = work / "in.strict_polar_demo"
    write_lammps_input(in_file, data_file, plugin_so, pes_graph, graph_n, graph_u, args.md_steps)

    run(["lmp", "-in", str(in_file)], cwd=repo)

    src_trj = repo / "traj_strict_polar.lammpstrj"
    dst_trj = work / "traj_strict_polar.lammpstrj"
    if src_trj.exists():
        shutil.move(str(src_trj), str(dst_trj))

    report = {
        "status": "ok",
        "strict_label_mode": "polar + atomic_polarizability",
        "dp_bin": str(dp_bin),
        "graph_n": str(graph_n),
        "graph_u": str(graph_u),
        "pes_graph": str(pes_graph),
        "lammps_input": str(in_file),
        "trajectory": str(dst_trj),
    }
    (work / "strict_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
