#!/usr/bin/env python3
"""Synthetic end-to-end chain demo for graphene and defected graphene.

This script builds two temporary cases:
- pristine graphene-like supercell
- defected graphene-like supercell (local geometric perturbation)

For each case it generates mock QE/EPW outputs, then runs:
  tools/qe_epw_pack.py
  tools/npz_to_deepmd.py

Outputs are written under --out-root.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np


def graphene_positions(nx: int = 5, ny: int = 10, a: float = 2.46) -> np.ndarray:
    a1 = np.array([a, 0.0, 0.0], dtype=float)
    a2 = np.array([0.5 * a, 0.5 * np.sqrt(3.0) * a, 0.0], dtype=float)
    b0 = np.array([0.0, 0.0, 0.0], dtype=float)
    b1 = np.array([0.0, a / np.sqrt(3.0), 0.0], dtype=float)

    pts = []
    for i in range(nx):
        for j in range(ny):
            o = i * a1 + j * a2
            pts.append(o + b0)
            pts.append(o + b1)

    coord = np.asarray(pts, dtype=float)
    coord[:, 0] -= coord[:, 0].min() - 2.0
    coord[:, 1] -= coord[:, 1].min() - 2.0
    coord[:, 2] = 0.0
    return coord


def make_defect(coord: np.ndarray) -> np.ndarray:
    out = coord.copy()
    # Local out-of-plane + in-plane distortion around one region as a defect proxy.
    center = np.array([out[:, 0].mean() * 0.6, out[:, 1].mean() * 0.6, 0.0])
    r = np.linalg.norm(out[:, :2] - center[:2], axis=1)
    mask = r < 3.0
    out[mask, 2] += 0.35 * np.exp(-0.25 * r[mask] ** 2)
    out[mask, 0] += 0.08 * np.sin(1.5 * out[mask, 1])
    out[mask, 1] += 0.08 * np.cos(1.5 * out[mask, 0])
    return out


def make_psd_tensor(rng: np.random.Generator) -> np.ndarray:
    m = rng.normal(size=(3, 3))
    t = m.T @ m
    return 0.5 * (t + t.T)


def write_mock_pw_out(path: Path, forces_ry_bohr: np.ndarray, total_energy_ry: float) -> None:
    lines = [
        "Program PWSCF mock run",
        f"!    total energy              =   {total_energy_ry: .10f} Ry",
        "Forces acting on atoms (Ry/Bohr)",
    ]
    for i, f in enumerate(forces_ry_bohr, start=1):
        lines.append(
            f"     atom   {i:3d} type  1   force =  {f[0]: .8f}  {f[1]: .8f}  {f[2]: .8f}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mock_epw_tensors(path: Path, natoms: int, rng: np.random.Generator) -> None:
    rows = ["# atom_id  LambdaN(9 row-major)  LambdaU(9 row-major)"]
    for i in range(1, natoms + 1):
        ln = make_psd_tensor(rng).reshape(-1)
        lu = make_psd_tensor(rng).reshape(-1)
        vals = " ".join(f"{x:.14e}" for x in np.concatenate([ln, lu]))
        rows.append(f"{i} {vals}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def run_case(repo: Path, root: Path, case_name: str, coord: np.ndarray, seed: int, e_ry: float) -> dict:
    case = root / case_name
    case.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)
    nat = coord.shape[0]
    box = np.array([coord[:, 0].max() + 4.0, 0, 0, 0, coord[:, 1].max() + 4.0, 0, 0, 0, 20.0], dtype=float)
    types = np.zeros((nat,), dtype=np.int32)
    forces_ry_bohr = rng.normal(0.0, 1.2e-3, size=(nat, 3))

    pw_out = case / "pw.out"
    epw_txt = case / "epw_friction_tensors.dat"
    coord_npy = case / "coord.npy"
    box_npy = case / "box.npy"
    types_npy = case / "types.npy"
    npz_out = case / "dataset_sample.npz"
    json_out = case / "dataset_sample.json"
    system = case / "qe_epw_system"

    write_mock_pw_out(pw_out, forces_ry_bohr, total_energy_ry=e_ry)
    write_mock_epw_tensors(epw_txt, nat, rng)
    np.save(coord_npy, coord)
    np.save(box_npy, box)
    np.save(types_npy, types)

    run(
        [
            "python",
            "tools/qe_epw_pack.py",
            "--pw-out",
            str(pw_out),
            "--epw-tensor",
            str(epw_txt),
            "--coord",
            str(coord_npy),
            "--types",
            str(types_npy),
            "--out",
            str(npz_out),
            "--summary",
            str(json_out),
        ],
        cwd=repo,
    )

    run(
        [
            "python",
            "tools/npz_to_deepmd.py",
            "--npz",
            str(npz_out),
            "--outdir",
            str(system),
            "--box-npy",
            str(box_npy),
            "--types-npy",
            str(types_npy),
        ],
        cwd=repo,
    )

    required = [
        system / "coord.raw",
        system / "box.raw",
        system / "energy.raw",
        system / "force.raw",
        system / "tensor_N.raw",
        system / "tensor_U.raw",
        system / "set.000" / "coord.npy",
        system / "set.000" / "lambda_n.npy",
        system / "set.000" / "lambda_u.npy",
        system / "input_pes.json",
        system / "input_tensor_N.json",
        system / "input_tensor_U.json",
    ]
    miss = [str(p) for p in required if not p.exists()]
    if miss:
        raise RuntimeError(f"{case_name} missing outputs:\n" + "\n".join(miss))

    return {
        "case": case_name,
        "natoms": int(nat),
        "packed_npz": str(npz_out),
        "system_dir": str(system),
        "status": "ok",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Graphene/defect synthetic chain demo")
    p.add_argument("--out-root", type=Path, default=Path("tmp_graphene_demo"), help="Output root")
    args = p.parse_args()

    repo = Path(__file__).resolve().parents[1]
    out = (repo / args.out_root).resolve()
    out.mkdir(parents=True, exist_ok=True)

    g = graphene_positions(5, 10, 2.46)
    gd = make_defect(g)

    r1 = run_case(repo, out, "graphene_pristine", g, seed=20260317, e_ry=-120.3)
    r2 = run_case(repo, out, "graphene_defect", gd, seed=20260318, e_ry=-119.8)

    report = {"out_root": str(out), "results": [r1, r2]}
    (out / "demo_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
