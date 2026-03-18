# Ph-e_coupling_MD_regine

**电子-声子耦合分子动力学（e-ph coupling MD）一体化流程**

完整的管道包含：QE/EPW 摩擦张量导出 → DeepMD 机器学习模型训练 → LAMMPS 分子动力学模拟。

## 📚 文档导航

| 文档 | 用途 | 目标用户 |
|-----|-----|---------|
| [COMPILATION_AND_USAGE_GUIDE.md](COMPILATION_AND_USAGE_GUIDE.md) | **完整编译教程与本地使用说明** | 需要从源代码编译的用户 |
| [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) | **云端部署完整指南** | 想在 AWS/Azure/GCP 云端运行的用户 |
| [CLOSED_LOOP_CLOUD_GUIDE.md](CLOSED_LOOP_CLOUD_GUIDE.md) | **架构、变更分类、技术清单** | 想了解项目结构和云端API的用户 |
| [EPW_PATCH_GUIDE.md](EPW_PATCH_GUIDE.md) | **QE/EPW 补丁详解** | 需要修改 EPW 源代码的用户 |

## 🚀 快速开始（云端推荐）

```bash
# 1. 获取初始化脚本
curl -O https://raw.githubusercontent.com/weiqichen77/Ph-e_coupling_MD_regine/main/cloud_bootstrap.sh

# 2. 在云端 Ubuntu 20.04 LTS 上一键部署（需要 5-10 分钟）
bash cloud_bootstrap.sh

# 3. 运行完整演示
cd Ph-e_coupling_MD_regine
source .venv_deepmd22/bin/activate
python tools/run_e2e_strict_polar_demo.py

# 4. 查看结果
cat tmp_e2e_strict_polar/strict_report.json
```

## 🏗️ 项目结构

```
Ph-e_coupling_MD_regine/
├── LAMMPS 自定义代码/
│   ├── fix_ttm_hydro_3d.cpp     # 3D 电子流体动力学 fix
│   ├── fix_ttm_hydro_3d.h       # Fix 头文件
│   └── ttm_hydro_3d_plugin.cpp  # 插件接口
│
├── QE/EPW 补丁/
│   ├── external/q-e/EPW/src/
│   │   ├── epw_nu_export.f90    # 摩擦张量导出模块
│   │   ├── selfen.f90           # 修改的自能例程
│   │   ├── use_wannier.f90      # Wannier 投影修改
│   │   └── Makefile             # 包含新模块
│
├── Python 数据与训练管道/
│   ├── tools/
│   │   ├── qe_epw_pack.py                      # EPW 数据打包
│   │   ├── npz_to_deepmd.py                    # 数据格式转换
│   │   ├── run_e2e_strict_polar_demo.py        # 演示：严格模式（推荐）
│   │   ├── run_e2e_real_training_demo.py       # 演示：兼容模式（备选）
│   │   └── run_step2_deepmd_smoke_demo.py      # 单个模型训练测试
│
├── 编译脚本/
│   ├── scripts/build_lammps_with_plugin.sh     # LAMMPS 编译
│   └── scripts/build_qe_epw.sh                 # QE/EPW 编译
│
├── 文档与指南/
│   ├── COMPILATION_AND_USAGE_GUIDE.md          # 详细编译教程 ⭐ 从这里开始
│   ├── CLOUD_DEPLOYMENT.md                     # 云端部署 ⭐ 推荐用于云端
│   ├── CLOSED_LOOP_CLOUD_GUIDE.md              # 架构与清单
│   ├── EPW_PATCH_GUIDE.md                      # EPW 修改详解
│   └── cloud_bootstrap.sh                      # 一键云端初始化
│
└── 演示数据（自动生成）/
    ├── tmp_e2e_strict_polar/                   # 严格模式运行结果
    └── tmp_e2e_real_demo/                      # 兼容模式运行结果
```

## 📖 详细教程

### 🔵 新用户/云端用户

1. **开始**：查看 [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) 的"快速开始"部分
2. **部署**：运行 `cloud_bootstrap.sh` 一键初始化
3. **运行**：执行 `python tools/run_e2e_strict_polar_demo.py`
4. **结果**：查看生成的 JSON 报告和轨迹文件

### 🟠 需要本地编译的用户

1. **详细教程**：[COMPILATION_AND_USAGE_GUIDE.md](COMPILATION_AND_USAGE_GUIDE.md)
   - 系统要求检查清单
   - 分步编译 LAMMPS、QE/EPW
   - Python 环境配置
   - 参数调整指南

2. **编译 LAMMPS**：  
   ```bash
   bash scripts/build_lammps_with_plugin.sh
   ```

3. **编译 QE/EPW**（可选）：  
   ```bash
   bash scripts/build_qe_epw.sh
   ```

### 🟢 需要修改 EPW 源代码的用户

查看 [EPW_PATCH_GUIDE.md](EPW_PATCH_GUIDE.md)，包含：
- 补丁文件详解
- 手工应用补丁步骤
- 编译与测试方法

## 🎯 核心功能演示

### 严格原子张量模式（推荐）✅

```bash
source .venv_deepmd22/bin/activate
python tools/run_e2e_strict_polar_demo.py
```

**特点**：
- 使用 DeepMD 2.2.11 + TensorFlow
- 严格的原子级 3×3 张量监督
- 输出 TensorFlow 冻结图 (`.pb`)
- **推荐用于生产和发表论文**

**输出**：
- `tmp_e2e_strict_polar/graph_n_strict.pb` - N 张量模型
- `tmp_e2e_strict_polar/graph_u_strict.pb` - U 张量模型  
- `tmp_e2e_strict_polar/traj_strict_polar.lammpstrj` - 100 步 MD 轨迹
- `tmp_e2e_strict_polar/strict_report.json` - 训练报告

### 兼容模式（备选）

```bash
source .venv/bin/activate
python tools/run_e2e_real_training_demo.py
```

**特点**：
- 使用 DeepMD 3.1.2 + PyTorch
- 自动回退到全局张量属性头
- 输出 PyTorch 模型 (`.pth`)
- **用于快速样型或不同硬件**

## 🧪 运行 LAMMPS 模拟

### 快速测试
```bash
lammps -in in.strict_polar_demo
```

### 生产配置
编辑 `in.ttm_hydro_production`，设置：
- `data_file`: LAMMPS 数据文件路径
- `graph_N`, `graph_U`: DeepMD 冻结模型路径
- `nx`, `ny`, `nz`: CFD 网格尺寸
- 其他物理参数（温度、电场等）

## 🌐 部署与运行

### 本地运行
```bash
# 环境配置
python3 -m venv .venv_deepmd22
source .venv_deepmd22/bin/activate
pip install -r requirements.txt

# 运行演示
python tools/run_e2e_strict_polar_demo.py
```

### 云端运行（推荐）
```bash
# 在云端 Ubuntu 20.04 LTS VM 上
bash cloud_bootstrap.sh

# 运行演示
source .venv_deepmd22/bin/activate
python tools/run_e2e_strict_polar_demo.py
```

### Docker 运行（即将提供）
```bash
docker build -t eph-coupling .
docker run -it eph-coupling python tools/run_e2e_strict_polar_demo.py
```

## ⚠️ 已知限制与解决方案

| 限制 | 原因 | 解决方案 |
|-----|------|--------|
| DeepMD 3.1.2 PyTorch 不支持 `fitting_net.type=tensor` | 版本限制 | 使用兼容模式或切换到 DeepMD 2.2.11 |
| 演示数据仅 2 原子 | 轻量级示例 | 提供自己的 EPW 导出数据 |
| LAMMPS 编译需要 DeepMD 库 | 依赖关系 | 见编译教程中的"DEEPMD_LIB_PATH"设置 |

**所有限制都已在严格模式（DeepMD 2.2.11）中解决** ✅

## 🔧 系统要求

### 最小配置
- **OS**：Linux (Ubuntu 20.04+)
- **CPU**：4 核+
- **内存**：8GB+
- **磁盘**：50GB+ (包含编译输出)

### 编译要求
- GCC 9.0+
- gfortran 9.0+
- CMake 3.10+
- OpenMPI（可选，MPI 加速）

### 可选加速
- NVIDIA GPU + CUDA 11.8+（用于 DeepMD 训练加速）

## 📊 性能指标

| 指标 | 值 | 备注 |
|-----|-----|------|
| 演示数据集 | 2 原子 | 轻量样例 |
| 训练步数 | 5000 | 演示用；生产通常 100K+ |
| MD 步数 | 100 | 演示用；通常需要更多 |
| 单步计算时间 | ~0.5 ms | CPU 上，单精度 |
| LAMMPS 编译时间 | ~10-15 分钟 | 4 核 CPU |
| DeepMD 训练时间 | ~2-5 分钟 | 演示数据，CPU 上 |

## 🤝 贡献与反馈

欢迎提交 Issue 和 Pull Request：
- GitHub 首页：https://github.com/weiqichen77/Ph-e_coupling_MD_regine
- 问题报告：https://github.com/weiqichen77/Ph-e_coupling_MD_regine/issues

## 📝 引用

如果在研究中使用本项目，请引用：

```bibtex
@software{eph_coupling_2026,
  author = {Your Name},
  title = {Ph-e coupling MD: End-to-end MD simulation with machine-learned friction tensors},
  year = {2026},
  url = {https://github.com/weiqichen77/Ph-e_coupling_MD_regine}
}
```

## 📄 许可证

[选择合适的许可证，例如 MIT, Apache 2.0 等]

---

## 🔗 额外信息

- **项目主页**：[GitHub](https://github.com/weiqichen77/Ph-e_coupling_MD_regine)
- **演示数据**：见 `tmp_e2e_strict_polar/` 和 `tmp_e2e_real_demo/`
- **物理参考**：见各源代码文件顶部的文献

---

*版本*：v1.0.0 (2026-03-18)  
*主要功能*：完整的 e-ph 耦合 MD 管道 + LAMMPS 自定义 fix + 两种训练路径

---

## Run the custom TTM hydro fix

### Quick smoke test

```bash
lmp -in in.ttm_hydro_smoke
```

### Production template

Use `in.ttm_hydro_production` and set these fields before running:

- `data_file`: path to your LAMMPS data file
- `graph_N`: frozen DeepTensor model for Normal channel
- `graph_U`: frozen DeepTensor model for Umklapp channel
- `nx`, `ny`, `nz`, `eta`, `te0`: CFD/fix control parameters
- `mu`, `ne`, `me`: electron fluid transport and inertia terms
- `zstar`, `Ex Ey Ez`: electric driving terms for ionic/electronic coupling
- `Fx Fy Fz`: external pump/source term
- `pcoeff`, `kappae`, `gammaT`, `Tenv`: pressure closure and thermal equation controls

Run:

```bash
lmp -in in.ttm_hydro_production
```

## QE/EPW dataset packing

After you export EPW per-atom friction tensors (`epw_friction_tensors.dat`) and get `pw.out`:

```bash
python tools/qe_epw_pack.py \
	--pw-out /path/to/pw.out \
	--epw-tensor /path/to/epw_friction_tensors.dat \
	--out dataset_sample.npz \
	--summary dataset_sample.json
```

EPW patching guidance is documented in `EPW_PATCH_GUIDE.md`.

## NPZ to DeepMD conversion

Convert packed QE/EPW sample to DeepMD dataset layout (`raw` + `set.000`) and emit templates for
PES and tensor training:

```bash
python tools/npz_to_deepmd.py \
	--npz dataset_sample.npz \
	--outdir qe_epw_system \
	--coord-npy /path/to/coord.npy \
	--box-npy /path/to/box.npy \
	--types-npy /path/to/types.npy
```

Generated in `qe_epw_system/`:
- raw files: `coord.raw`, `box.raw`, `energy.raw`, `force.raw`, `tensor_N.raw`, `tensor_U.raw`
- npy files: `set.000/*.npy`
- templates: `input_pes.json`, `input_tensor_N.json`, `input_tensor_U.json`

For EPW source patching, see `tools/epw_patch_snippet.f90`.