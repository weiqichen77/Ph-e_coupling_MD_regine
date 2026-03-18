# EPW Patch Guide (N/U Friction Split)

This repository does not vendor QE/EPW sources. Apply the patch in your local EPW source tree.

## Objective

Split electron-phonon scattering accumulation into:
- N channel: k+q remains in first Brillouin zone (G = 0)
- U channel: k+q folds back (G != 0)

and export per-atom friction tensors:
- Lambda_N (3x3)
- Lambda_U (3x3)

## Suggested patch location

Prefer patching in the electron self-energy path that is already called in normal EPW runs:

- `EPW/src/use_wannier.f90`
  - calls `selfen_elec_q(iqq, iq, totq, first_cycle)` when `elecselfen` or `specfun_el` is enabled.
- `EPW/src/selfen.f90`
  - contains `selfen_elec_q` and the `(ik, ibnd, jbnd, imode)` accumulation loops where `g2` and weights are formed.

For `k+q` classification, follow existing EPW mapping logic:

- `EPW/src/utilities/kfold.f90`
  - `backtoBZ` and `ktokpmq` show the canonical first-BZ folding and commensurability checks.
- `EPW/src/utilities/bzgrid.f90`
  - `kpmq_map` is the standard index mapping utility for `k +/- q` on fine mesh.

A concrete interface-aligned Fortran draft snippet is provided in `tools/epw_patch_snippet.f90`.

## Minimal algorithm

1. At each `(k, q, nu)` contribution where `|g|^2` is available, determine whether `k+q` exits first BZ before reduction.
2. If no folding (`G = 0`), accumulate contribution into `A` (normal).
3. If folding (`G != 0`), accumulate into `B` (umklapp).
4. After loop completion, map A/B to per-atom tensors `Lambda_N/Lambda_U` in Cartesian basis.
5. Write text output with one line per atom:

```text
# atom_id  LambdaN(9 row-major)  LambdaU(9 row-major)
1  N11 N12 ... N33  U11 U12 ... U33
...
```

Expected file name in downstream scripts: `epw_friction_tensors.dat`.

The draft snippet follows this exact file contract.

## Interface notes from QE/EPW source

- Use the same variable space as `selfen_elec_q` (`xkf`, `xqf`, `wkf`, `wqf`, `etf`, `epf17`) to avoid extra remapping.
- Keep the branch-local definition of contribution weight (`g2 * thermal/occupancy factor * broadening`) unchanged; only split into N/U channels.
- Classification should use mesh-aware folding (same idea as `backtoBZ`) instead of plain floating-point threshold on raw `k+q`.
- The export routine should be side-effect free and called once after local accumulation and reduction.

## Integration with this repo

Use:

```bash
python tools/qe_epw_pack.py \
  --pw-out /path/to/pw.out \
  --epw-tensor /path/to/epw_friction_tensors.dat \
  --out dataset_sample.npz \
  --summary dataset_sample.json
```

This creates an aligned dataset sample with energy, force, Lambda_N/U and Sigma_N/U.
