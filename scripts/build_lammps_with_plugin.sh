#!/bin/bash

# 构建 LAMMPS 和 ttm/hydro/3d 插件的脚本
# 使用：bash scripts/build_lammps_with_plugin.sh

set -e  # 任何错误都退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "Building LAMMPS with ttm/hydro/3d plugin"
echo "=========================================="
echo "Project root: $PROJECT_ROOT"
echo ""

# 检查依赖
echo "[1/5] Checking dependencies..."
command -v cmake &> /dev/null || { echo "CMake not found. Install with: sudo apt-get install cmake"; exit 1; }
command -v g++ &> /dev/null || { echo "G++ not found. Install with: sudo apt-get install build-essential"; exit 1; }
command -v gfortran &> /dev/null || { echo "Gfortran not found. Install with: sudo apt-get install gfortran"; exit 1; }
echo "   ✓ All dependencies available"
echo ""

# 下载 LAMMPS（如果需要）
echo "[2/5] Checking LAMMPS source..."
LAMMPS_DIR="$PROJECT_ROOT/external/lammps"
if [ ! -d "$LAMMPS_DIR" ]; then
    echo "   LAMMPS not found. Cloning..."
    mkdir -p "$PROJECT_ROOT/external"
    cd "$PROJECT_ROOT/external"
    git clone https://github.com/lammps/lammps.git
    cd lammps
    git checkout "22 Jul 2025" 2>/dev/null || echo "   Note: Using latest main branch"
    cd "$PROJECT_ROOT"
else
    echo "   ✓ LAMMPS source found at $LAMMPS_DIR"
fi
echo ""

# 复制自定义 fix 文件
echo "[3/5] Copying custom fix files..."
cp -v "$PROJECT_ROOT/fix_ttm_hydro_3d.cpp" "$LAMMPS_DIR/src/fix_ttm_hydro_3d.cpp"
cp -v "$PROJECT_ROOT/fix_ttm_hydro_3d.h" "$LAMMPS_DIR/src/fix_ttm_hydro_3d.h"
cp -v "$PROJECT_ROOT/ttm_hydro_3d_plugin.cpp" "$LAMMPS_DIR/src/ttm_hydro_3d_plugin.cpp"
echo "   ✓ Custom fix files copied"
echo ""

# 编译 LAMMPS
echo "[4/5] Building LAMMPS (this may take 10-15 minutes)..."
mkdir -p "$LAMMPS_DIR/build"
cd "$LAMMPS_DIR/build"

# 使用 cmake 配置
cmake -D CMAKE_BUILD_TYPE=Release \
       -D LAMMPS_SIZES=BIGBIG \
       -D PKG_USER_DEEPMD=ON \
       -D PKG_USER_COLVARS=ON \
       -D BUILD_SHARED_LIBS=yes \
       -D CMAKE_INSTALL_PREFIX="$LAMMPS_DIR/install" \
       ../cmake

# 编译
NUM_CORES=$(nproc)
echo "   Building with $NUM_CORES cores..."
make -j$NUM_CORES

echo "   ✓ LAMMPS build completed"
echo ""

# 编译插件
echo "[5/5] Building plugin..."
PLUGIN_BUILD_DIR="$LAMMPS_DIR/src/plugin_build"
mkdir -p "$PLUGIN_BUILD_DIR"
cd "$PLUGIN_BUILD_DIR"

# 获取 LAMMPS 库路径
LAMMPS_LIB="$LAMMPS_DIR/build/liblammps.so"

if [ ! -f "$LAMMPS_LIB" ]; then
    echo "WARNING: LAMMPS library not found at $LAMMPS_LIB"
    echo "         Building without linking to LAMMPS library"
    LINK_OPTS=""
else
    LINK_OPTS="-L$(dirname $LAMMPS_LIB) -llammps"
fi

# 编译插件
g++ -fPIC -shared \
    -o ttm_hydro_3d_plugin.so \
    "$LAMMPS_DIR/src/ttm_hydro_3d_plugin.cpp" \
    $LINK_OPTS \
    -I"$LAMMPS_DIR/src" \
    -Wl,-rpath,$(dirname $LAMMPS_LIB)

# 复制到项目根目录
cp ttm_hydro_3d_plugin.so "$PROJECT_ROOT/"

# 验证插件
if [ -f "$PROJECT_ROOT/ttm_hydro_3d_plugin.so" ]; then
    echo "   ✓ Plugin built successfully: ttm_hydro_3d_plugin.so"
    ls -lh "$PROJECT_ROOT/ttm_hydro_3d_plugin.so"
else
    echo "   ✗ Plugin build failed!"
    exit 1
fi

echo ""
echo "=========================================="
echo "BUILD COMPLETED SUCCESSFULLY!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Add LAMMPS to PATH:"
echo "   export PATH=$LAMMPS_DIR/build:\$PATH"
echo ""
echo "2. Test LAMMPS installation:"
echo "   lammps -version"
echo ""
echo "3. Run demo (after Python setup):"
echo "   cd $PROJECT_ROOT"
echo "   source .venv/bin/activate"
echo "   python tools/run_e2e_strict_polar_demo.py"
echo ""
