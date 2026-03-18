#ifdef FIX_CLASS
// clang-format off
FixStyle(ttm/hydro/2d,FixTTMHydro3D)
FixStyle(ttm/hydro/3d,FixTTMHydro3D)
// clang-format on
#else

#ifndef LMP_FIX_TTM_HYDRO_3D_H
#define LMP_FIX_TTM_HYDRO_3D_H

#include "fix.h"
#include "DeepTensor.h"

namespace LAMMPS_NS {

class RanMars;

class FixTTMHydro3D : public Fix {
 public:
  struct CFDCell {
    double u_e[3];        // Electron fluid velocity in this voxel
    double T_e;           // Electron temperature in this voxel
    double gamma_u;       // Coarse-grained Umklapp drag scalar
    double gamma_u_mat[9]; // Optional full 3x3 coarse-grained drag tensor
    double heat_src;      // Coarse-grained electron heat source term
    int count;            // Number of local atoms mapped to this voxel
  };

  FixTTMHydro3D(class LAMMPS *, int, char **);
  ~FixTTMHydro3D() override;

  int setmask() override;
  void init() override;
  void post_force(int vflag) override;

 private:
  // DeepTensor models for Normal and Umklapp channels
  deepmd::DeepTensor *dp_model_N;
  deepmd::DeepTensor *dp_model_U;

  // Random generator for Langevin noise (initialized in implementation)
  RanMars *random;

  // 3D CFD grid metadata
  int nx;
  int ny;
  int nz;
  int nxyz;
  double xlo;
  double xhi;
  double ylo;
  double yhi;
  double zlo;
  double zhi;
  double dx;
  double dy;
  double dz;

  // Time-step and transport coefficients
  double dt;
  double eta;
  double mu;
  double n_e;
  double m_e;
  double zstar;
  double e_charge;
  double p_coeff;
  double kappa_e;
  double gamma_t;
  double t_env;
  double efield[3];
  double fpump[3];
  double kb;

  // Contiguous grid storage managed by LAMMPS memory API
  CFDCell *grid;

  // Scratch buffers for DeepTensor inference outputs (flattened N x 9)
  double *tensor_N;
  double *tensor_U;
  int tensor_capacity;

  // Model graph paths
  char *graph_N_file;
  char *graph_U_file;

  inline int clamp_ix(int ix) const;
  inline int clamp_iy(int iy) const;
  inline int clamp_iz(int iz) const;
  inline int cell_index(int ix, int iy, int iz) const;
  inline int coord_to_cell(double x, double y, double z) const;
};

}  // namespace LAMMPS_NS

#endif
#endif
