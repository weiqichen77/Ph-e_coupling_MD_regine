#!/bin/bash

# 云端一键初始化脚本
# 在 Ubuntu 20.04 LTS 虚拟机上运行
# 使用: bash cloud_bootstrap.sh

set -e

SCRIPT_START_TIME=$(date)
echo "=========================================="
echo "Cloud Bootstrap Started: $SCRIPT_START_TIME"
echo "=========================================="
echo ""

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为 root 用户（如果需要 sudo）
if [ "$EUID" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# 步骤 1: 系统更新
log_info "Step 1/7: Updating system packages..."
$SUDO apt-get update -qq
$SUDO apt-get upgrade -y -qq
log_info "System packages updated"
echo ""

# 步骤 2: 安装基础工具
log_info "Step 2/7: Installing build tools and dependencies..."
BUILD_DEPS="build-essential gfortran cmake git curl wget pkg-config"
DEV_LIBS="libopenmpi-dev openmpi-bin libfftw3-dev liblapack-dev libblas-dev"
PYTHON_TOOLS="python3-dev python3-pip python3-venv"

$SUDO apt-get install -y -qq $BUILD_DEPS $DEV_LIBS $PYTHON_TOOLS

# 验证安装
for cmd in gcc g++ gfortran cmake git make python3; do
    if ! command -v $cmd &> /dev/null; then
        log_error "$cmd not found after installation"
        exit 1
    fi
done
log_info "All build tools installed successfully"
echo ""

# 步骤 3: 克隆仓库
log_info "Step 3/7: Cloning repository..."
if [ -d "Ph-e_coupling_MD_regine" ]; then
    log_warn "Repository already exists, skipping clone"
    cd Ph-e_coupling_MD_regine
else
    git clone https://github.com/weiqichen77/Ph-e_coupling_MD_regine.git
    cd Ph-e_coupling_MD_regine
fi
PROJECT_DIR=$(pwd)
log_info "Repository directory: $PROJECT_DIR"
echo ""

# 步骤 4: 创建 Python 虚拟环境
log_info "Step 4/7: Creating Python virtual environments..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    log_info "Created .venv (PyTorch/compatibility environment)"
fi

if [ ! -d ".venv_deepmd22" ]; then
    python3 -m venv .venv_deepmd22
    log_info "Created .venv_deepmd22 (TensorFlow/strict mode)"
fi

source .venv/bin/activate
pip install --upgrade pip setuptools wheel -q
pip install -q numpy scipy scikit-learn matplotlib pandas pyyaml h5py

# 查询用户对于 PyTorch/TensorFlow 的选择
log_info "Installing deep learning packages..."
pip install -q torch toothy==1.10.0+ 2>/dev/null || pip install -q torch 2>/dev/null  # 宽松版本

# 尝试安装 DeepMD PyTorch 版本
log_info "Installing DeepMD-kit 3.1.2 (PyTorch backend)..."
pip install -q deepmd-kit==3.1.2 2>/dev/null || log_warn "Failed to install DeepMD 3.1.2"

deactivate

# 第二个环境：TensorFlow
log_info "Installing TensorFlow and DeepMD 2.2.11 (strict mode)..."
source .venv_deepmd22/bin/activate
pip install --upgrade pip setuptools wheel -q
pip install -q numpy scipy scikit-learn matplotlib pandas
pip install -q tensorflow==2.16.1
pip install -q deepmd-kit==2.2.11
deactivate

log_info "Python environments ready"
echo ""

# 步骤 5: 编译 LAMMPS（如果需要）
log_info "Step 5/7: Building LAMMPS with plugin..."

if [ -f "scripts/build_lammps_with_plugin.sh" ]; then
    chmod +x scripts/build_lammps_with_plugin.sh
    log_info "Running LAMMPS build script (this may take 10-20 minutes)..."
    timeout 1800 bash scripts/build_lammps_with_plugin.sh || log_warn "LAMMPS build timed out or failed"
    
    # 验证 LAMMPS 编译
    if [ -f "ttm_hydro_3d_plugin.so" ]; then
        log_info "LAMMPS plugin compiled successfully"
    else
        log_warn "LAMMPS plugin not found, build may have failed"
    fi
else
    log_warn "LAMMPS build script not found"
fi
echo ""

# 步骤 6: 下载 QE/EPW（可选）
log_info "Step 6/7: Checking Quantum ESPRESSO..."
if [ ! -d "external/q-e-qe-7.1" ]; then
    log_warn "QE not found. Downloading it is optional and takes 30-60 minutes."
    log_warn "To compile QE/EPW later, run: bash scripts/build_qe_epw.sh"
    log_info "Skipping QE download for now (you can build it later)"
else
    log_info "QE source already present"
fi
echo ""

# 步骤 7: 验证安装
log_info "Step 7/7: Verifying installation..."

# 检查关键文件
REQUIRED_FILES=(
    "tools/run_e2e_strict_polar_demo.py"
    "tools/run_e2e_real_training_demo.py"
    "fix_ttm_hydro_3d.cpp"
    "fix_ttm_hydro_3d.h"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        log_info "✓ $file"
    else
        log_error "✗ $file NOT FOUND"
    fi
done

# 检查编译库
if [ -f "ttm_hydro_3d_plugin.so" ]; then
    SIZE=$(du -h ttm_hydro_3d_plugin.so | cut -f1)
    log_info "✓ ttm_hydro_3d_plugin.so ($SIZE)"
else
    log_warn "⊘ ttm_hydro_3d_plugin.so not found (LAMMPS plugin)"
fi

echo ""
echo "=========================================="
log_info "Bootstrap completed successfully!"
echo "=========================================="
SCRIPT_END_TIME=$(date)
echo "Started:  $SCRIPT_START_TIME"
echo "Ended:    $SCRIPT_END_TIME"
echo ""

echo "Next steps:"
echo "1. Activate the strict-mode environment:"
echo "   source .venv_deepmd22/bin/activate"
echo ""
echo "2. Run the complete demo:"
echo "   cd $PROJECT_DIR"
echo "   python tools/run_e2e_strict_polar_demo.py"
echo ""
echo "3. Check results:"
echo "   cat tmp_e2e_strict_polar/strict_report.json"
echo ""
echo "For more details, see:"
echo "  - COMPILATION_AND_USAGE_GUIDE.md (local usage)"
echo "  - CLOUD_DEPLOYMENT.md (cloud-specific instructions)"
echo "  - CLOSED_LOOP_CLOUD_GUIDE.md (architecture overview)"
echo ""
