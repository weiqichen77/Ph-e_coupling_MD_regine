#!/usr/bin/env python3
"""Convert QE+EPW packed npz into DeepMD raw/set.000 layout.

Input npz (from tools/qe_epw_pack.py) can include:
- energy_ev: (nframe,) or (nframe,1)
- force_ev_ang: (nframe,natom,3) or (natom,3)
- lambda_n / lambda_u: (nframe,natom,3,3) or (natom,3,3)
- sigma_n / sigma_u: (nframe,natom,3,3) or (natom,3,3)
- coord: (nframe,natom,3) or (natom,3)
- box: (nframe,9) or (9,)
- types: (natom,)

Outputs:
- raw files for PES + tensor tasks
- set.000 npy files
- template inputs for PES and tensor tasks
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def to_frames(arr: np.ndarray, target_ndim: int) -> np.ndarray:
    arr = np.asarray(arr)
    if arr.ndim == target_ndim - 1:
        return arr[np.newaxis, ...]
    return arr


def flatten_framewise(arr: np.ndarray) -> np.ndarray:
    return arr.reshape(arr.shape[0], -1)


def write_raw(path: Path, values: np.ndarray, fmt: str = "%.16e") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(path, values, fmt=fmt)


def build_pes_input(system_dir: str) -> dict:
    return {
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
            "decay_steps": 5000,
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
                "systems": [system_dir],
                "batch_size": 1,
                "auto_prob": "prob_uniform",
            },
            "validation_data": {
                "systems": [system_dir],
                "batch_size": 1,
                "auto_prob": "prob_uniform",
                "numb_btch": 1,
            },
            "numb_steps": 20000,
            "disp_file": "lcurve_pes.out",
            "disp_freq": 100,
            "save_freq": 1000,
            "save_ckpt": "model_pes.ckpt",
            "seed": 20260317,
        },
    }


def build_tensor_input(system_dir: str, tensor_name: str) -> dict:
    return {
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
                "type": "tensor",
                "tensor_name": tensor_name,
                "neuron": [120, 120, 120],
                "resnet_dt": True,
                "fit_diag": False,
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
                "systems": [system_dir],
                "batch_size": 1,
                "auto_prob": "prob_uniform",
            },
            "validation_data": {
                "systems": [system_dir],
                "batch_size": 1,
                "auto_prob": "prob_uniform",
                "numb_btch": 1,
            },
            "numb_steps": 20000,
            "disp_file": f"lcurve_{tensor_name}.out",
            "disp_freq": 100,
            "save_freq": 1000,
            "save_ckpt": f"model_{tensor_name}.ckpt",
            "seed": 20260317,
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Convert packed npz to DeepMD dataset layout")
    p.add_argument("--npz", type=Path, required=True, help="Input npz file")
    p.add_argument("--outdir", type=Path, default=Path("qe_epw_system"), help="Output dataset root")
    p.add_argument("--coord-npy", type=Path, default=None, help="Fallback coord npy if npz has no coord")
    p.add_argument("--box-npy", type=Path, default=None, help="Fallback box npy if npz has no box")
    p.add_argument("--types-npy", type=Path, default=None, help="Fallback type npy if npz has no types")
    p.add_argument("--default-type", type=int, default=0, help="Type value if no types provided")
    args = p.parse_args()

    blob = np.load(args.npz)

    if "energy_ev" not in blob or "force_ev_ang" not in blob:
        raise ValueError("npz must contain energy_ev and force_ev_ang")

    energy = np.asarray(blob["energy_ev"], dtype=float)
    if energy.ndim == 1:
        energy = energy.reshape(-1, 1)

    force = to_frames(np.asarray(blob["force_ev_ang"], dtype=float), 3)
    nframe = force.shape[0]
    nat = force.shape[1]

    if energy.shape[0] != nframe:
        if energy.shape[0] == 1 and nframe > 1:
            energy = np.repeat(energy, nframe, axis=0)
        else:
            raise ValueError(f"Frame mismatch: energy {energy.shape[0]} vs force {nframe}")

    if "coord" in blob:
        coord = to_frames(np.asarray(blob["coord"], dtype=float), 3)
    elif args.coord_npy is not None:
        coord = to_frames(np.load(args.coord_npy), 3)
    else:
        raise ValueError("No coordinates found. Provide coord in npz or --coord-npy")

    if coord.shape[0] != nframe:
        if coord.shape[0] == 1 and nframe > 1:
            coord = np.repeat(coord, nframe, axis=0)
        else:
            raise ValueError(f"Frame mismatch: coord {coord.shape[0]} vs force {nframe}")

    if coord.shape[1] != nat:
        raise ValueError(f"Atom mismatch: coord {coord.shape[1]} vs force {nat}")

    if "box" in blob:
        box = to_frames(np.asarray(blob["box"], dtype=float), 2)
    elif args.box_npy is not None:
        box = to_frames(np.load(args.box_npy), 2)
    else:
        # Fallback orthorhombic box estimated from coordinates (with margin)
        xyz_min = coord.min(axis=1)
        xyz_max = coord.max(axis=1)
        lengths = (xyz_max - xyz_min) + 10.0
        box = np.zeros((nframe, 9), dtype=float)
        box[:, 0] = lengths[:, 0]
        box[:, 4] = lengths[:, 1]
        box[:, 8] = lengths[:, 2]

    if box.shape[0] != nframe:
        if box.shape[0] == 1 and nframe > 1:
            box = np.repeat(box, nframe, axis=0)
        else:
            raise ValueError(f"Frame mismatch: box {box.shape[0]} vs force {nframe}")

    if "types" in blob:
        types = np.asarray(blob["types"], dtype=int).reshape(-1)
    elif args.types_npy is not None:
        types = np.load(args.types_npy).astype(int).reshape(-1)
    else:
        types = np.full((nat,), args.default_type, dtype=int)

    if types.shape[0] != nat:
        raise ValueError(f"Atom mismatch: types {types.shape[0]} vs force {nat}")

    out = args.outdir
    set0 = out / "set.000"
    out.mkdir(parents=True, exist_ok=True)
    set0.mkdir(parents=True, exist_ok=True)

    # Save npy layout
    np.save(set0 / "coord.npy", coord)
    np.save(set0 / "box.npy", box)
    np.save(set0 / "energy.npy", energy.reshape(nframe))
    np.save(set0 / "force.npy", force)
    np.save(set0 / "type.npy", np.repeat(types[np.newaxis, :], nframe, axis=0))

    # Optional tensor labels
    if "sigma_n" in blob:
        sigma_n = to_frames(np.asarray(blob["sigma_n"], dtype=float), 4)
        np.save(set0 / "sigma_n.npy", sigma_n.reshape(nframe, nat, 9))
    if "sigma_u" in blob:
        sigma_u = to_frames(np.asarray(blob["sigma_u"], dtype=float), 4)
        np.save(set0 / "sigma_u.npy", sigma_u.reshape(nframe, nat, 9))
    if "lambda_n" in blob:
        lambda_n = to_frames(np.asarray(blob["lambda_n"], dtype=float), 4)
        np.save(set0 / "lambda_n.npy", lambda_n.reshape(nframe, nat, 9))
    if "lambda_u" in blob:
        lambda_u = to_frames(np.asarray(blob["lambda_u"], dtype=float), 4)
        np.save(set0 / "lambda_u.npy", lambda_u.reshape(nframe, nat, 9))

    # Save raw layout
    write_raw(out / "coord.raw", flatten_framewise(coord))
    write_raw(out / "box.raw", box)
    write_raw(out / "energy.raw", energy)
    write_raw(out / "force.raw", flatten_framewise(force))
    write_raw(out / "type.raw", types.reshape(1, -1), fmt="%d")

    if "sigma_n" in blob:
        sigma_n = to_frames(np.asarray(blob["sigma_n"], dtype=float), 4)
        write_raw(out / "tensor_N.raw", flatten_framewise(sigma_n.reshape(nframe, nat, 9)))
    elif "lambda_n" in blob:
        lambda_n = to_frames(np.asarray(blob["lambda_n"], dtype=float), 4)
        write_raw(out / "tensor_N.raw", flatten_framewise(lambda_n.reshape(nframe, nat, 9)))

    if "sigma_u" in blob:
        sigma_u = to_frames(np.asarray(blob["sigma_u"], dtype=float), 4)
        write_raw(out / "tensor_U.raw", flatten_framewise(sigma_u.reshape(nframe, nat, 9)))
    elif "lambda_u" in blob:
        lambda_u = to_frames(np.asarray(blob["lambda_u"], dtype=float), 4)
        write_raw(out / "tensor_U.raw", flatten_framewise(lambda_u.reshape(nframe, nat, 9)))

    # Emit training templates
    (out / "input_pes.json").write_text(
        json.dumps(build_pes_input(out.name), indent=2), encoding="utf-8"
    )
    (out / "input_tensor_N.json").write_text(
        json.dumps(build_tensor_input(out.name, "tensor_N"), indent=2), encoding="utf-8"
    )
    (out / "input_tensor_U.json").write_text(
        json.dumps(build_tensor_input(out.name, "tensor_U"), indent=2), encoding="utf-8"
    )

    summary = {
        "outdir": str(out),
        "nframe": int(nframe),
        "natoms": int(nat),
        "fields_in_npz": sorted(blob.files),
        "note": "input_tensor_*.json use fit_tensor; if backend compatibility issues appear, switch to your property-compatible config.",
    }
    (out / "conversion_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote DeepMD dataset at {out}")


if __name__ == "__main__":
    main()
