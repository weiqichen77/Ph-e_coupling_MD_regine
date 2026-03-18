#!/usr/bin/env python3
"""End-to-end automation: real EPW dataset -> DeepMD training -> LAMMPS trajectory.

Pipeline:
1) Convert packed QE/EPW npz to DeepMD dataset layout
2) Train/freeze one PES model and two tensor models (N/U)
3) Run LAMMPS with pair_style deepmd + ttm/hydro fix using trained models
4) Dump trajectory for demo structural evolution under e-ph coupling
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def prepare_train_input(template: Path, dataset_dir: Path, out_path: Path, steps: int, save_ckpt: str, disp_file: str) -> None:
    cfg = load_json(template)
    ds = str(dataset_dir.resolve())

    cfg["training"]["training_data"]["systems"] = [ds]
    cfg["training"]["validation_data"]["systems"] = [ds]
    cfg["training"]["numb_steps"] = int(steps)
    cfg["training"]["save_ckpt"] = save_ckpt
    cfg["training"]["disp_file"] = disp_file
    cfg["training"]["disp_freq"] = max(1, steps // 10)
    cfg["training"]["save_freq"] = max(1, steps)

    save_json(out_path, cfg)


def train_and_freeze(train_dir: Path, input_json: Path, graph_name: str) -> Path:
    run(["dp", "--pt", "train", str(input_json)], cwd=train_dir)
    out_graph = train_dir / graph_name
    run(["dp", "--pt", "freeze", "-c", str(train_dir), "-o", str(out_graph)], cwd=train_dir)
    if not out_graph.exists():
        raise FileNotFoundError(f"Missing frozen graph: {out_graph}")
    return out_graph


def build_property_input(dataset_dir: Path, out_path: Path, steps: int, save_ckpt: str, disp_file: str) -> None:
    ds = str(dataset_dir.resolve())
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
                "type": "property",
                "neuron": [120, 120, 120],
                "task_dim": 9,
                "intensive": False,
                "property_name": "global_tensor",
            },
        },
        "learning_rate": {
            "type": "exp",
            "start_lr": 1.0e-3,
            "stop_lr": 1.0e-8,
            "decay_steps": 5000,
        },
        "loss": {
            "type": "property",
            "loss_func": "mse",
            "metric": ["mse"],
        },
        "training": {
            "training_data": {
                "systems": [ds],
                "batch_size": 1,
                "auto_prob": "prob_uniform",
            },
            "validation_data": {
                "systems": [ds],
                "batch_size": 1,
                "auto_prob": "prob_uniform",
                "numb_btch": 1,
            },
            "numb_steps": int(steps),
            "disp_file": disp_file,
            "disp_freq": max(1, steps // 10),
            "save_freq": max(1, steps),
            "save_ckpt": save_ckpt,
            "seed": 20260317,
        },
    }
    save_json(out_path, cfg)


def harmonize_set000(dataset_dir: Path) -> None:
    set_dir = dataset_dir / "set.000"
    if not set_dir.exists():
        return

    def _reshape_if_3d(name: str) -> None:
        p = set_dir / name
        if not p.exists():
            return
        arr = np.load(p)
        if arr.ndim == 3:
            np.save(p, arr.reshape(arr.shape[0], -1))

    _reshape_if_3d("coord.npy")
    _reshape_if_3d("force.npy")

    # Tensor fitting expects label files matching tensor_name.
    # Prefer sigma_* (A) if available, otherwise fallback to lambda_*.
    src_n = set_dir / "sigma_n.npy"
    if not src_n.exists():
        src_n = set_dir / "lambda_n.npy"
    if src_n.exists():
        arr_n = np.load(src_n)
        if arr_n.ndim == 3:
            arr_n = arr_n.reshape(arr_n.shape[0], -1)
        np.save(set_dir / "tensor_N.npy", arr_n)

    src_u = set_dir / "sigma_u.npy"
    if not src_u.exists():
        src_u = set_dir / "lambda_u.npy"
    if src_u.exists():
        arr_u = np.load(src_u)
        if arr_u.ndim == 3:
            arr_u = arr_u.reshape(arr_u.shape[0], -1)
        np.save(set_dir / "tensor_U.npy", arr_u)


def make_property_dataset(src_dataset: Path, dst_dataset: Path, tensor_name: str) -> None:
    if dst_dataset.exists():
        shutil.rmtree(dst_dataset)
    shutil.copytree(src_dataset, dst_dataset)

    set_dir = dst_dataset / "set.000"
    tensor_file = set_dir / tensor_name
    if not tensor_file.exists():
        raise FileNotFoundError(f"Missing tensor label file: {tensor_file}")

    arr = np.load(tensor_file)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D tensor label array in {tensor_file}, got shape {arr.shape}")
    if arr.shape[1] % 9 != 0:
        raise ValueError(f"Tensor label width must be multiple of 9 in {tensor_file}, got {arr.shape[1]}")

    nat = arr.shape[1] // 9
    global_tensor = arr.reshape(arr.shape[0], nat, 9).mean(axis=1)
    np.save(set_dir / "global_tensor.npy", global_tensor)
    np.save(set_dir / "property.npy", global_tensor)


def write_lammps_data(data_file: Path, coord: np.ndarray, types: np.ndarray) -> None:
    nat = coord.shape[0]
    lo = coord.min(axis=0) - 2.0
    hi = coord.max(axis=0) + 2.0

    lines: list[str] = []
    lines.append("LAMMPS data file generated from real EPW sample")
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

    # Demo assumes carbon-only sample; map all types to same mass.
    for t in range(int(types.max()) + 1):
        lines.append(f"{t + 1} 12.01")

    lines.append("")
    lines.append("Atoms")
    lines.append("")
    for i, r in enumerate(coord, start=1):
        lammps_type = int(types[i - 1]) + 1
        lines.append(f"{i} {lammps_type} {r[0]:.10f} {r[1]:.10f} {r[2]:.10f}")

    data_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_lammps_input(
    in_file: Path,
    data_file: Path,
    plugin_so: Path,
    graph_pes: Path,
    graph_n: Path,
    graph_u: Path,
    md_steps: int,
    fix_style: str,
) -> None:
    if fix_style == "ttm/hydro/3d":
        fix_args = "8 8 8 0.01 300.0 13579"
    else:
        fix_args = "8 8 0.01 300.0 13579"

    txt = f"""units metal
atom_style atomic
boundary p p p

read_data {data_file}

velocity all create 300.0 12345 mom yes rot no dist gaussian

pair_style deepmd {graph_pes}
pair_coeff * *

neighbor 1.0 bin
neigh_modify every 1 delay 0 check yes

plugin load {plugin_so}
fix int all nve
fix eh all {fix_style} {graph_n} {graph_u} {fix_args}

timestep 0.001
thermo 10
dump trj all custom 1 traj_eph_demo.lammpstrj id type x y z vx vy vz fx fy fz
run {md_steps}
"""
    in_file.write_text(txt, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Run full real-data DeepMD+LAMMPS demo")
    p.add_argument("--repo", type=Path, default=Path("/workspaces/Ph-e_coupling_MD_regine"))
    p.add_argument("--source", type=Path, default=Path("/workspaces/Ph-e_coupling_MD_regine/tmp_real_epw_minimal"))
    p.add_argument("--work", type=Path, default=Path("/workspaces/Ph-e_coupling_MD_regine/tmp_e2e_real_demo"))
    p.add_argument("--pes-steps", type=int, default=80)
    p.add_argument("--tensor-steps", type=int, default=80)
    p.add_argument("--md-steps", type=int, default=100)
    args = p.parse_args()

    repo = args.repo.resolve()
    source = args.source.resolve()
    work = args.work.resolve()

    dataset_npz = source / "dataset_sample.npz"
    coord_npy = source / "coord.npy"
    box_npy = source / "box.npy"
    types_npy = source / "types.npy"

    for needed in [dataset_npz, coord_npy, box_npy, types_npy]:
        if not needed.exists():
            raise FileNotFoundError(f"Missing required input: {needed}")

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    dataset_dir = work / "qe_epw_system"
    run(
        [
            sys.executable,
            str(repo / "tools/npz_to_deepmd.py"),
            "--npz",
            str(dataset_npz),
            "--outdir",
            str(dataset_dir),
            "--box-npy",
            str(box_npy),
            "--types-npy",
            str(types_npy),
        ],
        cwd=repo,
    )
    harmonize_set000(dataset_dir)

    train_pes = work / "train_pes"
    train_n = work / "train_tensor_n"
    train_u = work / "train_tensor_u"
    train_pes.mkdir(parents=True, exist_ok=True)
    train_n.mkdir(parents=True, exist_ok=True)
    train_u.mkdir(parents=True, exist_ok=True)

    pes_input = train_pes / "input_pes.json"
    n_input = train_n / "input_tensor_n.json"
    u_input = train_u / "input_tensor_u.json"

    prepare_train_input(
        template=dataset_dir / "input_pes.json",
        dataset_dir=dataset_dir,
        out_path=pes_input,
        steps=args.pes_steps,
        save_ckpt="model_pes.ckpt",
        disp_file="lcurve_pes.out",
    )
    prepare_train_input(
        template=dataset_dir / "input_tensor_N.json",
        dataset_dir=dataset_dir,
        out_path=n_input,
        steps=args.tensor_steps,
        save_ckpt="model_tensor_n.ckpt",
        disp_file="lcurve_tensor_n.out",
    )
    prepare_train_input(
        template=dataset_dir / "input_tensor_U.json",
        dataset_dir=dataset_dir,
        out_path=u_input,
        steps=args.tensor_steps,
        save_ckpt="model_tensor_u.ckpt",
        disp_file="lcurve_tensor_u.out",
    )

    graph_pes = train_and_freeze(train_pes, pes_input, "graph_pes.pth")

    used_tensor_fallback = False
    try:
        graph_n = train_and_freeze(train_n, n_input, "graph_n.pth")
        graph_u = train_and_freeze(train_u, u_input, "graph_u.pth")
    except subprocess.CalledProcessError:
        used_tensor_fallback = True

        ds_n = work / "qe_epw_system_prop_n"
        ds_u = work / "qe_epw_system_prop_u"
        make_property_dataset(dataset_dir, ds_n, "tensor_N.npy")
        make_property_dataset(dataset_dir, ds_u, "tensor_U.npy")

        n_prop_input = train_n / "input_prop_n.json"
        u_prop_input = train_u / "input_prop_u.json"
        build_property_input(ds_n, n_prop_input, args.tensor_steps, "model_prop_n.ckpt", "lcurve_prop_n.out")
        build_property_input(ds_u, u_prop_input, args.tensor_steps, "model_prop_u.ckpt", "lcurve_prop_u.out")

        graph_n = train_and_freeze(train_n, n_prop_input, "graph_n.pth")
        graph_u = train_and_freeze(train_u, u_prop_input, "graph_u.pth")

    coord = np.load(coord_npy)
    types = np.load(types_npy).reshape(-1)

    data_file = work / "data.real_epw"
    write_lammps_data(data_file, coord, types)

    plugin_so = repo / "ttm_hydro_3d_plugin.so"
    if not plugin_so.exists():
        raise FileNotFoundError(f"Missing plugin: {plugin_so}")

    in_file = work / "in.e2e_real_demo"
    used_fix_style = "ttm/hydro/3d"

    write_lammps_input(
        in_file,
        data_file,
        plugin_so,
        graph_pes,
        graph_n,
        graph_u,
        args.md_steps,
        used_fix_style,
    )
    try:
        run(["lmp", "-in", str(in_file)], cwd=repo)
    except subprocess.CalledProcessError:
        used_fix_style = "ttm/hydro/2d"
        write_lammps_input(
            in_file,
            data_file,
            plugin_so,
            graph_pes,
            graph_n,
            graph_u,
            args.md_steps,
            used_fix_style,
        )
        run(["lmp", "-in", str(in_file)], cwd=repo)

    traj = repo / "traj_eph_demo.lammpstrj"
    out_traj = work / "traj_eph_demo.lammpstrj"
    if traj.exists():
        shutil.move(str(traj), str(out_traj))

    report = {
        "status": "ok",
        "dataset_dir": str(dataset_dir),
        "graph_pes": str(graph_pes),
        "graph_n": str(graph_n),
        "graph_u": str(graph_u),
        "used_tensor_fallback": used_tensor_fallback,
        "lammps_input": str(in_file),
        "lammps_data": str(data_file),
        "used_fix_style": used_fix_style,
        "trajectory": str(out_traj),
    }
    (work / "e2e_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
