# 编译教程与使用说明

## 目录
1. [项目概述](#项目概述)
2. [系统要求](#系统要求)
3. [快速开始](#快速开始)
4. [详细编译步骤](#详细编译步骤)
5. [使用说明](#使用说明)
6. [常见问题](#常见问题)
7. [GitHub上传与部署](#github上传与部署)

---

## 项目概述

本项目实现了电子-声子（e-ph）耦合分子动力学模拟的完整管道：
- **数据源**：Quantum ESPRESSO + EPW 导出的摩擦张量（N, U）
- **模型训练**：使用 DeepMD 训练三个模型：势能面（PES）和两个摩擦张量（N, U）
- **MD 模拟**：LAMMPS + 自定义 3D 电子流体动力学 fix + DeepMD 推理
- **输出**：分子动力学轨迹文件 (lammpstrj)

**核心组件**：
- LAMMPS 自定义 fix：`fix_ttm_hydro_3d`
- QE/EPW 补丁：导出摩擦张量
- Python 管道脚本：数据转换和模型训练编排

---

## 系统要求

### 最小配置
- **OS**：Linux (Ubuntu 20.04+, CentOS 7+)
- **Python**：3.9 或更高版本
- **编译器**：GCC 9.0+（用于编译 LAMMPS 和 QE）
- **磁盘**：最少 20GB（包含编译输出和数据）

### 推荐配置
- **CPU**：4 核或以上
- **内存**：8GB 或以上
- **GPU**（可选）：NVIDIA GPU + CUDA 11.8+（加速 DeepMD 训练）

### 所需软件
| 软件 | 版本 | 用途 |
|-----|-----|------|
| LAMMPS | 22 Jul 2025+ | 分子动力学模拟 |
| Quantum ESPRESSO | 7.1+ | 量子计算 |
| EPW | 5.8.0+ | 电子-声子耦合 |
| DeepMD-kit | 2.2.11 或 3.1.2 | 机器学习势能 |
| Python | 3.9+ | 脚本编排 |
| pip/conda | 最新版本 | 包管理 |

---

## 快速开始

### 1. 克隆仓库
```bash
git clone https://github.com/weiqichen77/Ph-e_coupling_MD_regine.git
cd Ph-e_coupling_MD_regine
```

### 2. 环境配置
```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装 Python 依赖
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 编译 LAMMPS 和插件（约 15 分钟）
```bash
# 请参考下面的"详细编译步骤"章节
bash scripts/build_lammps_with_plugin.sh
```

### 4. 编译 QE/EPW（约 30-60 分钟）
```bash
# 请参考下面的"详细编译步骤"章节
bash scripts/build_qe_epw.sh
```

### 5. 运行完整演示
```bash
# 使用严格原子张量训练路径（推荐）
python tools/run_e2e_strict_polar_demo.py

# 或者使用兼容路径（用于较旧的 DeepMD）
python tools/run_e2e_real_training_demo.py
```

---

## 详细编译步骤

### 步骤 A：环境准备

```bash
# 1. 更新系统包
sudo apt-get update
sudo apt-get install -y git build-essential gfortran cmake wget curl

# 2. 安装依赖库
sudo apt-get install -y fftw3-dev liblapack-dev libblas-dev \
    libopenmpi-dev openmpi-bin

# 3. 验证编译器版本
gcc --version        # 应为 9.0+
gfortran --version   # 应为 9.0+
```

### 步骤 B：编译 LAMMPS 和插件

#### B1. 下载 LAMMPS（如果还未下载）
```bash
cd external/
git clone https://github.com/lammps/lammps.git
cd lammps
git checkout "22 Jul 2025"  # 特定版本
cd ../..
```

#### B2. 复制自定义 fix 代码到 LAMMPS
```bash
# 复制自定义 fix 文件
cp fix_ttm_hydro_3d.cpp external/lammps/src/fix_ttm_hydro_3d.cpp
cp fix_ttm_hydro_3d.h external/lammps/src/fix_ttm_hydro_3d.h

# 复制插件源代码
cp ttm_hydro_3d_plugin.cpp external/lammps/src/ttm_hydro_3d_plugin.cpp
```

#### B3. 编译 LAMMPS 核心
```bash
cd external/lammps
mkdir -p build
cd build

# 配置编译（启用必要的包）
cmake -D CMAKE_BUILD_TYPE=Release \
      -D LAMMPS_SIZES=BIGBIG \
      -D PKG_USER_DEEPMD=ON \
      -D PKG_USER_COLVARS=ON \
      -D BUILD_SHARED_LIBS=yes \
      ../cmake

# 编译
make -j4  # 使用 4 个核心，可根据 CPU 调整

# 安装
make install  # 可能需要 sudo
```

#### B4. 编译插件
```bash
cd ../src

# 创建插件编译目录
mkdir -p plugin_build
cd plugin_build

# 编译插件代码为共享库
g++ -fPIC -shared \
   -o ttm_hydro_3d_plugin.so \
   ../ttm_hydro_3d_plugin.cpp \
   -Wl,-rpath,$(LAMMPS_LIB_PATH) \
   -L$(LAMMPS_LIB_PATH) \
   -llammps

# 复制到项目根目录供使用
cp ttm_hydro_3d_plugin.so ../../../
```

### 步骤 C：编译 Quantum ESPRESSO 和 EPW

#### C1. 下载 QE（如果还未下载）
```bash
cd external/
wget https://github.com/QEF/q-e/releases/download/qe-7.1/q-e-qe-7.1.tar.gz
tar xzf q-e-qe-7.1.tar.gz
cd q-e-qe-7.1
```

#### C2. 应用 EPW 补丁
```bash
# 依次应用 4 个补丁文件
cd EPW/src

# 备份原文件
cp Makefile Makefile.orig
cp selfen.f90 selfen.f90.orig
cp use_wannier.f90 use_wannier.f90.orig

# 应用补丁（根据仓库中的 PATCH_GUIDE 进行）
patch < ../../../external/q-e/EPW/src/epw_nu_export.patch
patch Makefile < ../../../external/q-e/EPW/src/Makefile.patch
patch selfen.f90 < ../../../external/q-e/EPW/src/selfen.patch
```

#### C3. 编译 QE
```bash
cd ../../..  # 回到 q-e-qe-7.1 目录

./configure --prefix=$(pwd)/install
make -j4
make install
```

#### C4. 编译 EPW
```bash
cd EPW/src
make -j4
```

### 步骤 D：设置 Python 环境

#### D1. 创建两个虚拟环境（推荐）

**环境 1：兼容性环境（使用 PyTorch）**
```bash
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install torch deepmd-kit==3.1.2 numpy scipy scikit-learn matplotlib pandas
pip install lammps  # 可选：从 pip 安装 LAMMPS Python 绑定
```

**环境 2：严格模式环境（使用 TensorFlow）**
```bash
python3 -m venv .venv_deepmd22
source .venv_deepmd22/bin/activate

pip install --upgrade pip
pip install tensorflow==2.16.1 deepmd-kit==2.2.11 numpy scipy scikit-learn
```

#### D2. 创建 requirements.txt 文件
```bash
cat > requirements.txt << 'EOF'
# 核心依赖
numpy>=1.21.0
scipy>=1.7.0
scikit-learn>=0.24.0
matplotlib>=3.3.0
pandas>=1.2.0

# DeepMD 和深度学习框架
# 选择其中之一：
# 兼容性（PyTorch）：
# torch>=1.10.0
# deepmd-kit==3.1.2

# 严格模式（TensorFlow）：
# tensorflow>=2.10.0
# deepmd-kit==2.2.11

# 其他工具
ase>=3.22.0  # Atomic Simulation Environment
h5py>=3.0.0
pyyaml>=5.4.0
EOF
```

---

## 使用说明

### 1. 数据准备

#### 1.1 从 QE/EPW 导出摩擦张量
```bash
# 运行 Quantum ESPRESSO 计算（包含 EPW）
cd qe_epw_demo_system/  # 或您自己的数据目录
$QE_PATH/bin/pw.x -in scf.in > scf.out
$QE_PATH/bin/ph.x -in ph.in > ph.out
$EPW_PATH/bin/epw.x -in epw.in > epw.out

# 输出文件应包含：
# - prefix_epw/prefix.npy（包含 N 和 U 张量）
```

#### 1.2 转换数据为 DeepMD 格式
```bash
python tools/npz_to_deepmd.py \
    --epw-dir qe_epw_demo_system/ \
    --output dataset_converted/ \
    --training-ratio 0.8
```

### 2. 模型训练

#### 2.1 严格原子张量模式（推荐）
```bash
# 激活 DeepMD 2.2.11 环境
source .venv_deepmd22/bin/activate

# 运行完整演示管道
python tools/run_e2e_strict_polar_demo.py

# 输出：
# - tmp_e2e_strict_polar/graph_pies.pb（势能面）
# - tmp_e2e_strict_polar/graph_n_strict.pb（N 张量）
# - tmp_e2e_strict_polar/graph_u_strict.pb（U 张量）
# - tmp_e2e_strict_polar/strict_report.json（训练报告）
```

#### 2.2 兼容性模式（备选）
```bash
# 激活默认环境
source .venv/bin/activate

python tools/run_e2e_real_training_demo.py

# 输出：
# - tmp_e2e_real_demo/graph_pes.pth
# - tmp_e2e_real_demo/graph_n.pth
# - tmp_e2e_real_demo/graph_u.pth
# - tmp_e2e_real_demo/e2e_report.json
```

### 3. LAMMPS 分子动力学模拟

#### 3.1 准备 LAMMPS 输入文件
```bash
# 使用已提供的输入文件模板
cp in.strict_polar_demo in.my_simulation

# 编辑输入参数（可选）
nano in.my_simulation
```

#### 3.2 运行 LAMMPS
```bash
# 使用编译好的 LAMMPS（假设在 PATH 中）
lammps -in in.my_simulation -l log.lammps

# 或使用完整路径
./external/lammps/build/lammps -in in.my_simulation

# 注意：需要加载插件（LAMMPS 输入文件中应包含）：
# plugin load ./ttm_hydro_3d_plugin.so
```

#### 3.3 分析轨迹
```bash
# 使用 ASE 或 OVITO 分析轨迹
python tools/analyze_trajectory.py \
    --traj traj_strict_polar.lammpstrj \
    --output analysis_results.pdf
```

### 4. 参数调整指南

#### 4.1 训练参数（在 input JSON 中）
```json
{
  "training": {
    "numb_steps": 100000,    // 增加用于更长训练
    "batch_size": 1,         // 小数据集时可用
    "learning_rate": 0.001
  },
  "model": {
    "type_map": ["H", "C"],  // 根据您的系统调整
    "descriptor": {
      "type": "se_agg",
      "rcut": 6.0,
      "rcut_smooth": 5.8
    }
  }
}
```

#### 4.2 LAMMPS 参数（在输入文件中）
```
# 温度控制
fix 1 all nvt temp 300.0 300.0 100.0

# 时间步长（fs）
timestep 0.0005

# 输出间隔
dump 1 all atom 10 traj.lammpstrj
thermo 10
```

---

## 常见问题

### Q1: LAMMPS 编译时找不到 DeepMD 库
**解决方案**：
```bash
# 指定 DeepMD 路径
cmake -D CMAKE_BUILD_TYPE=Release \
      -D DEEPMD_INCLUDE_DIR=/path/to/deepmd/include \
      -D DEEPMD_LIB_DIR=/path/to/deepmd/lib \
      ../cmake
```

### Q2: DeepMD 报错 "fitting_net.type=tensor not supported"
**解决方案**：
- 这是 DeepMD 3.1.2 PyTorch 的已知问题
- 使用 `run_e2e_strict_polar_demo.py`（使用 DeepMD 2.2.11 TensorFlow）
- 或使用 `run_e2e_real_training_demo.py`（自动回退到 property 模式）

### Q3: 程序提示找不到 EPW 导出的数据
**解决方案**：
```bash
# 确认 EPW 正确输出了摩擦张量
ls -la qe_epw_demo_system/*.npy

# 检查数据格式是否正确
python tools/check_epw_data.py qe_epw_demo_system/
```

### Q4: LAMMPS 模拟崩溃或速度很慢
**解决方案**：
- 检查模型文件路径是否正确
- 验证 fix 参数是否与模型一致
- 尝试减少 MD 步数进行测试
- 检查 LAMMPS 日志：`less log.lammps`

### Q5: GPU 加速不生效
**解决方案**：
- 确认安装了支持 CUDA 的 PyTorch / TensorFlow
- 在 Python 中验证：`python -c "import torch; print(torch.cuda.is_available())"`
- LAMMPS 也需要使用 GPU 支持重新编译：
  ```bash
  cmake -D CMAKE_BUILD_TYPE=Release \
        -D PKG_GPU=ON \
        -D GPU_ARCH=sm_70 \  # 根据您的 GPU 调整
        ../cmake
  ```

---

## GitHub 上传与部署

### 步骤 1: 初始配置（仅首次）
```bash
# 配置 git 用户信息
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# 如果使用 SSH（推荐）
ssh-keygen -t ed25519 -C "your.email@example.com"
# 将公钥添加到 GitHub 账户设置
```

### 步骤 2: 添加文件到版本控制
```bash
# 进入项目目录
cd Ph-e_coupling_MD_regine

# 查看状态
git status

# 添加所有跟踪文件
git add README.md
git add CLOSED_LOOP_CLOUD_GUIDE.md
git add EPW_PATCH_GUIDE.md
git add COMPILATION_AND_USAGE_GUIDE.md
git add fix_ttm_hydro_3d.cpp
git add fix_ttm_hydro_3d.h
git add ttm_hydro_3d_plugin.cpp
git add tools/
git add external/q-e/EPW/src/  # 补丁文件
git add .gitignore

# 查看即将提交的文件
git status
```

### 步骤 3: 提交更改
```bash
git commit -m "feat: Add complete e-ph coupling MD pipeline with LAMMPS fix and DeepMD training

- Implement ttm/hydro/3d fix for electron-phonon coupling
- Add QE/EPW friction tensor export patches
- Create end-to-end training pipeline with strict polar mode
- Add comprehensive compilation and usage documentation
- Support both PyTorch (v3.1.2) and TensorFlow (v2.2.11) backends"
```

### 步骤 4: 遇到冲突时的推送
```bash
# 拉取最新更改
git pull origin main

# 如果有冲突，手动编辑并解决
git add <resolved-files>
git commit -m "Merge main branch"

# 推送到远程
git push origin main
```

### 步骤 5: 发布编译库（可选）

#### 方法 A: 使用 GitHub Release（推荐）
```bash
# 标记版本
git tag -a v1.0.0 -m "Release v1.0.0 - Complete e-ph coupling pipeline"

# 推送标签
git push origin v1.0.0

# 然后在 GitHub 网站上：
# 1. 导航到 Releases
# 2. 点击 "Create a release"
# 3. 选择 v1.0.0 标签
# 4. 上传编译好的库：
#    - ttm_hydro_3d_plugin.so
#    - 其他二进制文件（如果有）
```

#### 方法 B: 使用 GitHub Actions 自动编译（高级）
```bash
# 创建 .github/workflows/build.yml
mkdir -p .github/workflows
cat > .github/workflows/build.yml << 'EOF'
name: Build and Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build LAMMPS plugin
        run: |
          bash scripts/build_lammps_with_plugin.sh
      - name: Upload Release Asset
        uses: softprops/action-gh-release@v1
        with:
          files: ttm_hydro_3d_plugin.so
EOF

# 推送才会触发自动编译
git push origin main
```

### 步骤 6: 验证上传
```bash
# 在浏览器中打开您的仓库：
# https://github.com/YOUR_USERNAME/Ph-e_coupling_MD_regine

# 检查：
# ✓ 所有源文件已上传
# ✓ README.md 和指南文档可见
# ✓ .gitignore 排除了临时文件
# ✓ 版本标签已发布
```

---

## 云部署快速指南

详见 [CLOSED_LOOP_CLOUD_GUIDE.md](CLOSED_LOOP_CLOUD_GUIDE.md)，包括：
- 完整的云环境设置
- 微服务 API 设计建议
- 生产环境检查清单

---

## 支持与反馈

如有问题，请提交 Issue 或联系维护者：
- GitHub Issues: https://github.com/weiqichen77/Ph-e_coupling_MD_regine/issues
- 邮件：[维护者邮箱]

---

*最后更新：2026-03-18*
*版本：v1.0.0*
