#include "fix_ttm_hydro_3d.h"

#include <cmath>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

#include "atom.h"
#include "comm.h"
#include "domain.h"
#include "error.h"
#include "force.h"
#include "memory.h"
#include "random_mars.h"
#include "update.h"
#include "utils.h"

namespace LAMMPS_NS {

namespace {

inline void matmul_aat(const double *a, double *lambda) {
  // lambda = a * a^T, with a in row-major 3x3 layout.
  const double a00 = a[0], a01 = a[1], a02 = a[2];
  const double a10 = a[3], a11 = a[4], a12 = a[5];
  const double a20 = a[6], a21 = a[7], a22 = a[8];

  lambda[0] = a00 * a00 + a01 * a01 + a02 * a02;
  lambda[1] = a00 * a10 + a01 * a11 + a02 * a12;
  lambda[2] = a00 * a20 + a01 * a21 + a02 * a22;

  lambda[3] = lambda[1];
  lambda[4] = a10 * a10 + a11 * a11 + a12 * a12;
  lambda[5] = a10 * a20 + a11 * a21 + a12 * a22;

  lambda[6] = lambda[2];
  lambda[7] = lambda[5];
  lambda[8] = a20 * a20 + a21 * a21 + a22 * a22;
}

inline void matvec3(const double *m, const double *x, double *y) {
  y[0] = m[0] * x[0] + m[1] * x[1] + m[2] * x[2];
  y[1] = m[3] * x[0] + m[4] * x[1] + m[5] * x[2];
  y[2] = m[6] * x[0] + m[7] * x[1] + m[8] * x[2];
}

inline void matvec3_raw(const double *a, const double *x, double *y) {
  y[0] = a[0] * x[0] + a[1] * x[1] + a[2] * x[2];
  y[1] = a[3] * x[0] + a[4] * x[1] + a[5] * x[2];
  y[2] = a[6] * x[0] + a[7] * x[1] + a[8] * x[2];
}

}  // namespace

FixTTMHydro3D::FixTTMHydro3D(LAMMPS *lmp, int narg, char **arg)
    : Fix(lmp, narg, arg),
      dp_model_N(nullptr),
      dp_model_U(nullptr),
      random(nullptr),
      nx(32),
      ny(32),
      nz(32),
      nxyz(0),
      xlo(0.0),
      xhi(1.0),
      ylo(0.0),
      yhi(1.0),
      zlo(0.0),
      zhi(1.0),
      dx(1.0),
      dy(1.0),
      dz(1.0),
      dt(0.0),
      eta(0.01),
      mu(0.01),
      n_e(1.0),
      m_e(1.0),
      zstar(0.0),
      e_charge(1.0),
      p_coeff(0.0),
      kappa_e(0.05),
      gamma_t(0.02),
      t_env(300.0),
      kb(0.0),
      grid(nullptr),
      tensor_N(nullptr),
      tensor_U(nullptr),
      tensor_capacity(0),
      graph_N_file(nullptr),
      graph_U_file(nullptr) {
  if (narg < 8) {
    error->all(FLERR,
               "Illegal fix ttm/hydro/2d or ttm/hydro/3d command. Usage: fix ID group ttm/hydro/3d graph_N.pb graph_U.pb nx ny nz [eta] [Te0] [seed] [mu] [ne] [me] [zstar] [Ex Ey Ez] [Fx Fy Fz] [pcoeff] [kappae] [gammaT] [Tenv]");
  }

  graph_N_file = utils::strdup(arg[3]);
  graph_U_file = utils::strdup(arg[4]);
  nx = utils::inumeric(FLERR, arg[5], false, lmp);
  ny = utils::inumeric(FLERR, arg[6], false, lmp);
  nz = utils::inumeric(FLERR, arg[7], false, lmp);

  if (nx < 2 || ny < 2 || nz < 2)
    error->all(FLERR, "nx, ny, and nz must be >= 2 for fix ttm/hydro/3d");

  if (narg > 8) eta = utils::numeric(FLERR, arg[8], false, lmp);

  double te0 = 300.0;
  if (narg > 9) te0 = utils::numeric(FLERR, arg[9], false, lmp);

  int seed = 13579;
  if (narg > 10) seed = utils::inumeric(FLERR, arg[10], false, lmp);

  if (narg > 11) mu = utils::numeric(FLERR, arg[11], false, lmp);
  if (narg > 12) n_e = utils::numeric(FLERR, arg[12], false, lmp);
  if (narg > 13) m_e = utils::numeric(FLERR, arg[13], false, lmp);
  if (narg > 14) zstar = utils::numeric(FLERR, arg[14], false, lmp);

  if (narg > 17) {
    efield[0] = utils::numeric(FLERR, arg[15], false, lmp);
    efield[1] = utils::numeric(FLERR, arg[16], false, lmp);
    efield[2] = utils::numeric(FLERR, arg[17], false, lmp);
  } else {
    efield[0] = 0.0;
    efield[1] = 0.0;
    efield[2] = 0.0;
  }

  if (narg > 20) {
    fpump[0] = utils::numeric(FLERR, arg[18], false, lmp);
    fpump[1] = utils::numeric(FLERR, arg[19], false, lmp);
    fpump[2] = utils::numeric(FLERR, arg[20], false, lmp);
  } else {
    fpump[0] = 0.0;
    fpump[1] = 0.0;
    fpump[2] = 0.0;
  }

  if (narg > 21) p_coeff = utils::numeric(FLERR, arg[21], false, lmp);
  if (narg > 22) kappa_e = utils::numeric(FLERR, arg[22], false, lmp);
  if (narg > 23) gamma_t = utils::numeric(FLERR, arg[23], false, lmp);
  if (narg > 24) t_env = utils::numeric(FLERR, arg[24], false, lmp);

  if (n_e <= 0.0) error->all(FLERR, "n_e must be > 0 for fix ttm/hydro/3d");
  if (m_e <= 0.0) error->all(FLERR, "m_e must be > 0 for fix ttm/hydro/3d");
  if (mu < 0.0) error->all(FLERR, "mu must be >= 0 for fix ttm/hydro/3d");

  kb = force->boltz;
  dt = update->dt;

  nxyz = nx * ny * nz;
  memory->create(grid, nxyz, "ttm/hydro/3d:grid");
  for (int c = 0; c < nxyz; ++c) {
    grid[c].u_e[0] = 0.0;
    grid[c].u_e[1] = 0.0;
    grid[c].u_e[2] = 0.0;
    grid[c].T_e = te0;
    grid[c].gamma_u = 0.0;
    for (int k = 0; k < 9; ++k) grid[c].gamma_u_mat[k] = 0.0;
    grid[c].heat_src = 0.0;
    grid[c].count = 0;
  }

  random = new RanMars(lmp, seed + comm->me);

  try {
    dp_model_N = new deepmd::DeepTensor(std::string(graph_N_file), 0, std::string(""));
    dp_model_U = new deepmd::DeepTensor(std::string(graph_U_file), 0, std::string(""));
  } catch (std::exception &e) {
    std::string msg = std::string("Failed to initialize DeepTensor models: ") + e.what();
    error->all(FLERR, msg.c_str());
  }
}

FixTTMHydro3D::~FixTTMHydro3D() {
  if (graph_N_file) delete[] graph_N_file;
  if (graph_U_file) delete[] graph_U_file;

  if (dp_model_N) delete dp_model_N;
  if (dp_model_U) delete dp_model_U;

  if (random) delete random;

  if (tensor_N) memory->destroy(tensor_N);
  if (tensor_U) memory->destroy(tensor_U);
  if (grid) memory->destroy(grid);
}

int FixTTMHydro3D::setmask() {
  int mask = 0;
  mask |= FixConst::POST_FORCE;
  return mask;
}

void FixTTMHydro3D::init() {
  dt = update->dt;
  kb = force->boltz;
}

inline int FixTTMHydro3D::clamp_ix(int ix) const {
  if (ix < 0) return 0;
  if (ix >= nx) return nx - 1;
  return ix;
}

inline int FixTTMHydro3D::clamp_iy(int iy) const {
  if (iy < 0) return 0;
  if (iy >= ny) return ny - 1;
  return iy;
}

inline int FixTTMHydro3D::clamp_iz(int iz) const {
  if (iz < 0) return 0;
  if (iz >= nz) return nz - 1;
  return iz;
}

inline int FixTTMHydro3D::cell_index(int ix, int iy, int iz) const {
  return (clamp_iz(iz) * ny + clamp_iy(iy)) * nx + clamp_ix(ix);
}

inline int FixTTMHydro3D::coord_to_cell(double x, double y, double z) const {
  const double fx = (x - xlo) / dx;
  const double fy = (y - ylo) / dy;
  const double fz = (z - zlo) / dz;
  const int ix = clamp_ix(static_cast<int>(fx));
  const int iy = clamp_iy(static_cast<int>(fy));
  const int iz = clamp_iz(static_cast<int>(fz));
  return (iz * ny + iy) * nx + ix;
}

void FixTTMHydro3D::post_force(int /*vflag*/) {
  const int nlocal = atom->nlocal;
  if (nlocal <= 0) return;

  xlo = domain->boxlo[0];
  xhi = domain->boxhi[0];
  ylo = domain->boxlo[1];
  yhi = domain->boxhi[1];
  zlo = domain->boxlo[2];
  zhi = domain->boxhi[2];

  dx = (xhi - xlo) / static_cast<double>(nx);
  dy = (yhi - ylo) / static_cast<double>(ny);
  dz = (zhi - zlo) / static_cast<double>(nz);

  if (dx <= 0.0 || dy <= 0.0 || dz <= 0.0)
    error->all(FLERR, "Invalid domain size for fix ttm/hydro/3d");

  const int need = nlocal * 9;
  if (need > tensor_capacity) {
    if (tensor_N) memory->destroy(tensor_N);
    if (tensor_U) memory->destroy(tensor_U);
    memory->create(tensor_N, need, "ttm/hydro/3d:tensor_N");
    memory->create(tensor_U, need, "ttm/hydro/3d:tensor_U");
    tensor_capacity = need;
  }

  std::vector<double> coord(3 * nlocal, 0.0);
  std::vector<int> atype(nlocal, 0);
  std::vector<double> box(9, 0.0);
  std::vector<double> predN(need, 0.0);
  std::vector<double> predU(need, 0.0);

  double **x = atom->x;
  int *type = atom->type;
  for (int i = 0; i < nlocal; ++i) {
    coord[3 * i + 0] = x[i][0];
    coord[3 * i + 1] = x[i][1];
    coord[3 * i + 2] = x[i][2];
    atype[i] = type[i] - 1;
  }

  box[0] = domain->boxhi[0] - domain->boxlo[0];
  box[4] = domain->boxhi[1] - domain->boxlo[1];
  box[8] = domain->boxhi[2] - domain->boxlo[2];

  // Step A: DeepTensor inference.
  try {
    dp_model_N->compute(predN, coord, atype, box);
    dp_model_U->compute(predU, coord, atype, box);
  } catch (std::exception & /*e*/) {
    // Fallback to isotropic identity tensors to keep dynamics running in MVP mode.
    for (int i = 0; i < nlocal; ++i) {
      double *an = predN.data() + 9 * i;
      double *au = predU.data() + 9 * i;
      for (int k = 0; k < 9; ++k) {
        an[k] = 0.0;
        au[k] = 0.0;
      }
      an[0] = an[4] = an[8] = 1.0;
      au[0] = au[4] = au[8] = 1.0;
    }
  }

  std::memcpy(tensor_N, predN.data(), sizeof(double) * need);
  std::memcpy(tensor_U, predU.data(), sizeof(double) * need);

  // Reset per-step coarse-grained accumulators.
  std::vector<double> react_n(3 * nxyz, 0.0);
  for (int c = 0; c < nxyz; ++c) {
    grid[c].gamma_u = 0.0;
    for (int k = 0; k < 9; ++k) grid[c].gamma_u_mat[k] = 0.0;
    grid[c].heat_src = 0.0;
    grid[c].count = 0;
  }

  // Step B: Coarse-grain Lambda tensors and source terms to CFD voxels.
  double **v = atom->v;
  for (int i = 0; i < nlocal; ++i) {
    const int c = coord_to_cell(x[i][0], x[i][1], x[i][2]);
    const double *a_n = tensor_N + 9 * i;
    const double *a_u = tensor_U + 9 * i;

    double lambda_n[9];
    double lambda_u[9];
    matmul_aat(a_n, lambda_n);
    matmul_aat(a_u, lambda_u);

    grid[c].gamma_u += (lambda_u[0] + lambda_u[4] + lambda_u[8]);
    for (int k = 0; k < 9; ++k) grid[c].gamma_u_mat[k] += lambda_u[k];

    const double rel[3] = {
        v[i][0] - grid[c].u_e[0],
        v[i][1] - grid[c].u_e[1],
        v[i][2] - grid[c].u_e[2],
    };

    double drag_n[3], drag_u[3];
    matvec3(lambda_n, rel, drag_n);
    matvec3(lambda_u, v[i], drag_u);

    // Action-reaction source for electron momentum equation:
    // +sum_i Lambda_N * (v_i - u_e) on each CFD voxel.
    react_n[3 * c + 0] += drag_n[0];
    react_n[3 * c + 1] += drag_n[1];
    react_n[3 * c + 2] += drag_n[2];

    const double drag_work =
        drag_n[0] * rel[0] + drag_n[1] * rel[1] + drag_n[2] * rel[2] +
        drag_u[0] * v[i][0] + drag_u[1] * v[i][1] + drag_u[2] * v[i][2];
    grid[c].heat_src += drag_work;
    grid[c].count += 1;
  }

  for (int c = 0; c < nxyz; ++c) {
    if (grid[c].count > 0) {
      const double inv = 1.0 / static_cast<double>(grid[c].count);
      grid[c].gamma_u *= inv;
      for (int k = 0; k < 9; ++k) grid[c].gamma_u_mat[k] *= inv;
    }
  }

  // Step C: One explicit Euler update for electron velocity on CFD grid.
  std::vector<double> u_new(3 * nxyz, 0.0);
  const double idx2 = 1.0 / (dx * dx);
  const double idy2 = 1.0 / (dy * dy);
  const double idz2 = 1.0 / (dz * dz);

  for (int iz = 0; iz < nz; ++iz) {
    for (int iy = 0; iy < ny; ++iy) {
      for (int ix = 0; ix < nx; ++ix) {
        const int c = cell_index(ix, iy, iz);
        const int cxm = cell_index(ix - 1, iy, iz);
        const int cxp = cell_index(ix + 1, iy, iz);
        const int cym = cell_index(ix, iy - 1, iz);
        const int cyp = cell_index(ix, iy + 1, iz);
        const int czm = cell_index(ix, iy, iz - 1);
        const int czp = cell_index(ix, iy, iz + 1);

        const int cell_l = cell_index(ix - 1, iy, iz);
        const int cell_r = cell_index(ix + 1, iy, iz);
        const int cell_d = cell_index(ix, iy - 1, iz);
        const int cell_u = cell_index(ix, iy + 1, iz);
        const int cell_b = cell_index(ix, iy, iz - 1);
        const int cell_f = cell_index(ix, iy, iz + 1);

        const double gamma = grid[c].gamma_u;
        const double inv_cell_vol = 1.0 / (dx * dy * dz);

        const double dte_dx = (grid[cell_r].T_e - grid[cell_l].T_e) / (2.0 * dx);
        const double dte_dy = (grid[cell_u].T_e - grid[cell_d].T_e) / (2.0 * dy);
        const double dte_dz = (grid[cell_f].T_e - grid[cell_b].T_e) / (2.0 * dz);
        const double grad_p_x = p_coeff * dte_dx;
        const double grad_p_y = p_coeff * dte_dy;
        const double grad_p_z = p_coeff * dte_dz;

        const double dux_dx = (grid[cxp].u_e[0] - grid[cxm].u_e[0]) / (2.0 * dx);
        const double dux_dy = (grid[cyp].u_e[0] - grid[cym].u_e[0]) / (2.0 * dy);
        const double dux_dz = (grid[czp].u_e[0] - grid[czm].u_e[0]) / (2.0 * dz);
        const double duy_dx = (grid[cxp].u_e[1] - grid[cxm].u_e[1]) / (2.0 * dx);
        const double duy_dy = (grid[cyp].u_e[1] - grid[cym].u_e[1]) / (2.0 * dy);
        const double duy_dz = (grid[czp].u_e[1] - grid[czm].u_e[1]) / (2.0 * dz);
        const double duz_dx = (grid[cxp].u_e[2] - grid[cxm].u_e[2]) / (2.0 * dx);
        const double duz_dy = (grid[cyp].u_e[2] - grid[cym].u_e[2]) / (2.0 * dy);
        const double duz_dz = (grid[czp].u_e[2] - grid[czm].u_e[2]) / (2.0 * dz);

        const double adv[3] = {
            grid[c].u_e[0] * dux_dx + grid[c].u_e[1] * dux_dy + grid[c].u_e[2] * dux_dz,
            grid[c].u_e[0] * duy_dx + grid[c].u_e[1] * duy_dy + grid[c].u_e[2] * duy_dz,
            grid[c].u_e[0] * duz_dx + grid[c].u_e[1] * duz_dy + grid[c].u_e[2] * duz_dz,
        };

        const double inv_rho_e = 1.0 / (m_e * n_e);
        for (int a = 0; a < 3; ++a) {
          const double u0 = grid[c].u_e[a];
          const double lap = (grid[cxp].u_e[a] + grid[cxm].u_e[a] - 2.0 * u0) * idx2 +
                             (grid[cyp].u_e[a] + grid[cym].u_e[a] - 2.0 * u0) * idy2 +
                             (grid[czp].u_e[a] + grid[czm].u_e[a] - 2.0 * u0) * idz2;

          double pressure_term = 0.0;
          if (a == 0) pressure_term = -inv_rho_e * grad_p_x;
          if (a == 1) pressure_term = -inv_rho_e * grad_p_y;
          if (a == 2) pressure_term = -inv_rho_e * grad_p_z;

          const double drag_term = -gamma * u0;
          const double n_reaction_term = inv_rho_e * react_n[3 * c + a] * inv_cell_vol;
          const double electric_term = -(n_e * e_charge * efield[a]) * inv_rho_e;

          const double du =
              -adv[a] + mu * lap + pressure_term + n_reaction_term + drag_term + fpump[a] + electric_term;
          u_new[3 * c + a] = u0 + dt * du;
        }
      }
    }
  }

  for (int c = 0; c < nxyz; ++c) {
    grid[c].u_e[0] = u_new[3 * c + 0];
    grid[c].u_e[1] = u_new[3 * c + 1];
    grid[c].u_e[2] = u_new[3 * c + 2];

    const int ix = c % nx;
    const int iy = (c / nx) % ny;
    const int iz = c / (nx * ny);
    const int cxm = cell_index(ix - 1, iy, iz);
    const int cxp = cell_index(ix + 1, iy, iz);
    const int cym = cell_index(ix, iy - 1, iz);
    const int cyp = cell_index(ix, iy + 1, iz);
    const int czm = cell_index(ix, iy, iz - 1);
    const int czp = cell_index(ix, iy, iz + 1);
    const double lap_t = (grid[cxp].T_e + grid[cxm].T_e - 2.0 * grid[c].T_e) * idx2 +
                         (grid[cyp].T_e + grid[cym].T_e - 2.0 * grid[c].T_e) * idy2 +
                         (grid[czp].T_e + grid[czm].T_e - 2.0 * grid[c].T_e) * idz2;
    const double joule = n_e * e_charge *
                         (efield[0] * grid[c].u_e[0] + efield[1] * grid[c].u_e[1] +
                          efield[2] * grid[c].u_e[2]);
    const double dte =
        kappa_e * lap_t + 0.05 * grid[c].heat_src + 0.01 * joule - gamma_t * (grid[c].T_e - t_env);
    grid[c].T_e += dt * dte;
    if (grid[c].T_e < 1.0) grid[c].T_e = 1.0;
  }

  // Step D: Atomic feedback force update.
  double **f = atom->f;

  for (int i = 0; i < nlocal; ++i) {
    const int c = coord_to_cell(x[i][0], x[i][1], x[i][2]);

    const double *a_n = tensor_N + 9 * i;
    const double *a_u = tensor_U + 9 * i;

    double lambda_n[9], lambda_u[9];
    matmul_aat(a_n, lambda_n);
    matmul_aat(a_u, lambda_u);

    const double rel[3] = {
        v[i][0] - grid[c].u_e[0],
        v[i][1] - grid[c].u_e[1],
        v[i][2] - grid[c].u_e[2],
    };

    double f_n[3], f_u[3];
    matvec3(lambda_n, rel, f_n);
    matvec3(lambda_u, v[i], f_u);

    f_n[0] = -f_n[0];
    f_n[1] = -f_n[1];
    f_n[2] = -f_n[2];

    f_u[0] = -f_u[0];
    f_u[1] = -f_u[1];
    f_u[2] = -f_u[2];

    const double xi_n[3] = {random->gaussian(), random->gaussian(), random->gaussian()};
    const double xi_u[3] = {random->gaussian(), random->gaussian(), random->gaussian()};

    double an_xi[3], au_xi[3];
    matvec3_raw(a_n, xi_n, an_xi);
    matvec3_raw(a_u, xi_u, au_xi);

    const double te = grid[c].T_e;
    const double pref = std::sqrt(2.0 * kb * te / dt);
    const double f_rand[3] = {
        pref * (an_xi[0] + au_xi[0]),
        pref * (an_xi[1] + au_xi[1]),
        pref * (an_xi[2] + au_xi[2]),
    };

    const double f_e[3] = {
      zstar * e_charge * efield[0],
      zstar * e_charge * efield[1],
      zstar * e_charge * efield[2],
    };

    f[i][0] += f_n[0] + f_u[0] + f_rand[0] + f_e[0];
    f[i][1] += f_n[1] + f_u[1] + f_rand[1] + f_e[1];
    f[i][2] += f_n[2] + f_u[2] + f_rand[2] + f_e[2];
  }
}

}  // namespace LAMMPS_NS
