#!/usr/bin/env python3
"""Run a fully synthetic QE/EPW -> DeepMD pipeline smoke test.

This script does not require real ab-initio calculations. It generates temporary:
- pw.out-like file with total energy and force lines
- epw_friction_tensors.dat with per-atom Lambda_N/U tensors
- coord/box/types npy files

Then it calls:
- tools/qe_epw_pack.py
- tools/npz_to_deepmd.py

and validates expected outputs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np


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


def main() -> None:
    p = argparse.ArgumentParser(description="Synthetic QE/EPW pipeline dry run")
    p.add_argument("--out-root", type=Path, default=Path("tmp_dryrun"), help="Output root directory")
    p.add_argument("--natoms", type=int, default=8, help="Number of atoms in mock data")
    p.add_argument("--seed", type=int, default=20260317, help="Random seed")
    args = p.parse_args()

    repo = Path(__file__).resolve().parents[1]
    out_root = (repo / args.out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    nat = args.natoms

    # Build simple cubic-like coordinates and box in Angstrom.
    coord = rng.uniform(0.5, 8.0, size=(nat, 3))
    box = np.diag([10.0, 10.0, 10.0]).reshape(9)
    types = np.zeros((nat,), dtype=np.int32)

    # Forces in Ry/Bohr to match pw.out parser assumptions.
    forces_ry_bohr = rng.normal(0.0, 1.0e-3, size=(nat, 3))

    pw_out = out_root / "pw.out"
    epw_tensor = out_root / "epw_friction_tensors.dat"
    coord_npy = out_root / "coord.npy"
    box_npy = out_root / "box.npy"
    types_npy = out_root / "types.npy"
    packed_npz = out_root / "dataset_sample.npz"
    packed_json = out_root / "dataset_sample.json"
    system_dir = out_root / "qe_epw_system"

    write_mock_pw_out(pw_out, forces_ry_bohr=forces_ry_bohr, total_energy_ry=-123.456789)
    write_mock_epw_tensors(epw_tensor, natoms=nat, rng=rng)
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
            str(epw_tensor),
            "--coord",
            str(coord_npy),
            "--types",
            str(types_npy),
            "--out",
            str(packed_npz),
            "--summary",
            str(packed_json),
        ],
        cwd=repo,
    )

    run(
        [
            "python",
            "tools/npz_to_deepmd.py",
            "--npz",
            str(packed_npz),
            "--outdir",
            str(system_dir),
            "--box-npy",
            str(box_npy),
            "--types-npy",
            str(types_npy),
        ],
        cwd=repo,
    )

    required = [
        system_dir / "coord.raw",
        system_dir / "box.raw",
        system_dir / "energy.raw",
        system_dir / "force.raw",
        system_dir / "tensor_N.raw",
        system_dir / "tensor_U.raw",
        system_dir / "set.000" / "coord.npy",
        system_dir / "set.000" / "box.npy",
        system_dir / "set.000" / "energy.npy",
        system_dir / "set.000" / "force.npy",
        system_dir / "set.000" / "lambda_n.npy",
        system_dir / "set.000" / "lambda_u.npy",
        system_dir / "input_pes.json",
        system_dir / "input_tensor_N.json",
        system_dir / "input_tensor_U.json",
        system_dir / "conversion_summary.json",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError("Dry run failed; missing outputs:\n" + "\n".join(missing))

    report = {
        "out_root": str(out_root),
        "natoms": int(nat),
        "packed_npz": str(packed_npz),
        "system_dir": str(system_dir),
        "status": "ok",
    }
    (out_root / "dryrun_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
