#include "lammpsplugin.h"

#include "version.h"

#include "fix_ttm_hydro_3d.h"

using namespace LAMMPS_NS;

static Fix *ttmhydro3dcreator(LAMMPS *lmp, int argc, char **argv) {
  return new FixTTMHydro3D(lmp, argc, argv);
}

extern "C" void lammpsplugin_init(void *lmp, void *handle, void *regfunc) {
  lammpsplugin_t plugin;
  lammpsplugin_regfunc register_plugin = (lammpsplugin_regfunc)regfunc;

  plugin.version = LAMMPS_VERSION;
  plugin.style = "fix";
  plugin.name = "ttm/hydro/2d";
  plugin.info = "3D electron hydrodynamics + DeepTensor friction fix (2d alias kept)";
  plugin.author = "GitHub Copilot";
  plugin.creator.v2 = (lammpsplugin_factory2 *)&ttmhydro3dcreator;
  plugin.handle = handle;
  (*register_plugin)(&plugin, lmp);

  plugin.name = "ttm/hydro/3d";
  (*register_plugin)(&plugin, lmp);
}
