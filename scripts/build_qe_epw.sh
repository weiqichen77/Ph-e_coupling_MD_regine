#!/bin/bash

# 构建 Quantum ESPRESSO 和 EPW 的脚本
# 使用：bash scripts/build_qe_epw.sh

set -e  # 任何错误都退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "Building Quantum ESPRESSO and EPW"
echo "=========================================="
echo "Project root: $PROJECT_ROOT"
echo ""

# 检查依赖
echo "[1/4] Checking dependencies..."
command -v gfortran &> /dev/null || { echo "Gfortran not found. Install with: sudo apt-get install gfortran"; exit 1; }
command -v make &> /dev/null || { echo "Make not found. Install with: sudo apt-get install build-essential"; exit 1; }
echo "   ✓ Build tools available"
echo ""

# 下载 QE（如果需要）
echo "[2/4] Checking Quantum ESPRESSO source..."
QE_DIR="$PROJECT_ROOT/external/q-e-qe-7.1"
if [ ! -d "$QE_DIR" ]; then
    echo "   QE not found. Downloading..."
    mkdir -p "$PROJECT_ROOT/external"
    cd "$PROJECT_ROOT/external"
    
    # 检查是否已下载但未解压
    if [ ! -f "q-e-qe-7.1.tar.gz" ]; then
        wget https://github.com/QEF/q-e/releases/download/qe-7.1/q-e-qe-7.1.tar.gz
    fi
    
    tar xzf q-e-qe-7.1.tar.gz
    cd "$PROJECT_ROOT"
else
    echo "   ✓ QE source found at $QE_DIR"
fi
echo ""

# 应用补丁
echo "[3/4] Applying EPW patches..."
EPW_SRC_DIR="$QE_DIR/EPW/src"

if [ ! -d "$EPW_SRC_DIR" ]; then
    echo "   ERROR: EPW source directory not found!"
    exit 1
fi

# 备份原文件
if [ ! -f "$EPW_SRC_DIR/Makefile.orig" ]; then
    cp "$EPW_SRC_DIR/Makefile" "$EPW_SRC_DIR/Makefile.orig"
fi
if [ ! -f "$EPW_SRC_DIR/selfen.f90.orig" ]; then
    cp "$EPW_SRC_DIR/selfen.f90" "$EPW_SRC_DIR/selfen.f90.orig"
fi
if [ ! -f "$EPW_SRC_DIR/use_wannier.f90.orig" ]; then
    cp "$EPW_SRC_DIR/use_wannier.f90" "$EPW_SRC_DIR/use_wannier.f90.orig"
fi

# 应用补丁（如果存在）
PATCH_DIR="$PROJECT_ROOT/external/q-e/EPW/src"
if [ -f "$PATCH_DIR/Makefile.patch" ]; then
    echo "   Applying Makefile patch..."
    cd "$EPW_SRC_DIR"
    patch < "$PATCH_DIR/Makefile.patch" || echo "   Warning: Makefile patch may have conflicts"
    cd "$PROJECT_ROOT"
fi

if [ -f "$PATCH_DIR/selfen.patch" ]; then
    echo "   Applying selfen.f90 patch..."
    cd "$EPW_SRC_DIR"
    patch < "$PATCH_DIR/selfen.patch" || echo "   Warning: selfen.f90 patch may have conflicts"
    cd "$PROJECT_ROOT"
fi

if [ -f "$PATCH_DIR/use_wannier.patch" ]; then
    echo "   Applying use_wannier.f90 patch..."
    cd "$EPW_SRC_DIR"
    patch < "$PATCH_DIR/use_wannier.patch" || echo "   Warning: use_wannier.f90 patch may have conflicts"
    cd "$PROJECT_ROOT"
fi

# 复制 EPW 导出模块（如果存在）
if [ -f "$PATCH_DIR/epw_nu_export.f90" ]; then
    echo "   Copying epw_nu_export.f90..."
    cp "$PATCH_DIR/epw_nu_export.f90" "$EPW_SRC_DIR/"
fi

echo "   ✓ Patches applied"
echo ""

# 编译 QE
echo "[4/4] Building Quantum ESPRESSO (this may take 30-60 minutes)..."
cd "$QE_DIR"

# 配置
echo "   Configuring..."
./configure --prefix="$QE_DIR/install" \
            --enable-openmp \
            --enable-mpi

# 编译
NUM_CORES=$(nproc)
echo "   Building with $NUM_CORES cores (this takes time)..."
make -j$NUM_CORES pw 2>&1 | head -20  # 只显示前 20 行以避免过度输出
echo "   ..."

# 等待编译完成
make pw > /dev/null 2>&1 || { echo "   ERROR: QE build failed"; exit 1; }

# 编译 EPW
echo "   Building EPW..."
cd EPW
make -j$NUM_CORES > /dev/null 2>&1 || { echo "   ERROR: EPW build failed"; exit 1; }

echo "   ✓ Quantum ESPRESSO and EPW built successfully"
echo ""

echo "=========================================="
echo "BUILD COMPLETED SUCCESSFULLY!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Add QE to PATH:"
echo "   export PATH=$QE_DIR/bin:\$PATH"
echo ""
echo "2. Test QE installation:"
echo "   pw.x -version"
echo ""
echo "2. Test EPW installation:"
echo "   epw.x -version"
echo ""
echo "3. Prepare your EPW input files in:"
echo "   $PROJECT_ROOT/qe_epw_demo_system/"
echo ""
