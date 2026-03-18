#!/usr/bin/env python3
"""Package QE pw.x outputs and EPW friction tensors into aligned training data.

Inputs
- pw.out from QE (SCF/NSCF/relax) containing total energy and atomic forces.
- EPW tensor file exported by patched EPW loop with one 3x3 tensor per atom:
  index lambda_N(9) lambda_U(9)

Outputs
- npz bundle for downstream conversion/training
- optional plain-text summary
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

RY_TO_EV = 13.605693009
RYBOHR_TO_EV_A = RY_TO_EV / 0.529177210903


def parse_pw_out(pw_out: Path) -> tuple[float, np.ndarray]:
    text = pw_out.read_text(encoding="utf-8", errors="ignore")

    # QE total energy line: !    total energy              =   -114.12345678 Ry
    energy_matches = re.findall(r"!\s+total energy\s+=\s+([\-0-9.Ee+]+)\s+Ry", text)
    if not energy_matches:
        raise ValueError(f"Cannot find total energy in {pw_out}")
    energy_ev = float(energy_matches[-1]) * RY_TO_EV

    # QE force lines: atom    1 type  1   force =   0.00000000  0.00000000  0.00123456
    force_matches = re.findall(
        r"atom\s+\d+\s+type\s+\d+\s+force\s*=\s*([\-0-9.Ee+]+)\s+([\-0-9.Ee+]+)\s+([\-0-9.Ee+]+)",
        text,
    )
    if not force_matches:
        raise ValueError(f"Cannot find atomic forces in {pw_out}")

    forces = np.array(force_matches, dtype=float) * RYBOHR_TO_EV_A
    return energy_ev, forces


def parse_epw_tensors(epw_tensor_file: Path) -> tuple[np.ndarray, np.ndarray]:
    rows = []
    for line in epw_tensor_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 19:
            raise ValueError(
                f"Expected 19 columns (id + 9 + 9), got {len(parts)} in line: {line[:120]}"
            )
        rows.append([float(x) for x in parts[1:]])

    if not rows:
        raise ValueError(f"No tensor data found in {epw_tensor_file}")

    arr = np.array(rows, dtype=float)
    tensor_n = arr[:, :9].reshape(-1, 3, 3)
    tensor_u = arr[:, 9:].reshape(-1, 3, 3)
    return tensor_n, tensor_u


def nearest_psd_sqrt(mat: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    # Symmetrize and project tiny negative eigenvalues to keep PSD for sqrt
    sym = 0.5 * (mat + mat.T)
    w, v = np.linalg.eigh(sym)
    w = np.clip(w, eps, None)
    return (v * np.sqrt(w)) @ v.T


def main() -> None:
    p = argparse.ArgumentParser(description="Pack QE + EPW outputs into one aligned sample")
    p.add_argument("--pw-out", type=Path, required=True, help="Path to QE pw.out")
    p.add_argument("--epw-tensor", type=Path, required=True, help="Path to EPW tensor text file")
    p.add_argument("--coord", type=Path, default=None, help="Optional npy coords (N,3)")
    p.add_argument("--types", type=Path, default=None, help="Optional npy atom types (N,)")
    p.add_argument("--out", type=Path, default=Path("dataset_sample.npz"), help="Output npz file")
    p.add_argument("--summary", type=Path, default=Path("dataset_sample.json"), help="Output summary json")
    args = p.parse_args()

    energy_ev, forces = parse_pw_out(args.pw_out)
    tensor_n, tensor_u = parse_epw_tensors(args.epw_tensor)

    nat = forces.shape[0]
    if tensor_n.shape[0] != nat:
        raise ValueError(
            f"Atom count mismatch: forces has {nat}, tensor file has {tensor_n.shape[0]}"
        )

    # Build Sigma factors used by stochastic force term: Lambda = Sigma Sigma^T
    sigma_n = np.stack([nearest_psd_sqrt(tensor_n[i]) for i in range(nat)], axis=0)
    sigma_u = np.stack([nearest_psd_sqrt(tensor_u[i]) for i in range(nat)], axis=0)

    payload = {
        "energy_ev": np.array([energy_ev], dtype=float),
        "force_ev_ang": forces,
        "lambda_n": tensor_n,
        "lambda_u": tensor_u,
        "sigma_n": sigma_n,
        "sigma_u": sigma_u,
    }

    if args.coord is not None:
        payload["coord"] = np.load(args.coord)
    if args.types is not None:
        payload["types"] = np.load(args.types)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.out, **payload)

    meta = {
        "pw_out": str(args.pw_out),
        "epw_tensor": str(args.epw_tensor),
        "natoms": int(nat),
        "energy_ev": float(energy_ev),
        "fields": sorted(payload.keys()),
        "note": "sigma_* are symmetric PSD square-root factors reconstructed from lambda_*",
    }
    args.summary.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Wrote {args.out} and {args.summary}")


if __name__ == "__main__":
    main()
