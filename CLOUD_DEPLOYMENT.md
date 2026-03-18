# 云端部署指南

## 概述

本指南说明如何在云端环境（AWS、Azure、GCP 等）部署和运行 e-ph 耦合 MD 管道。

## 云部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                    云端虚拟机 (VM)                           │
├──────────────┬──────────────┬──────────────┬────────────────┤
│   QE/EPW     │   DeepMD     │   LAMMPS     │   Python API   │
│   编译环境   │   训练环境   │   模拟引擎   │   (可选)       │
└──────────────┴──────────────┴──────────────┴────────────────┘
       ↓               ↓               ↓
   摩擦张量  →  机器学习模型  →  MD 轨迹
```

---

## 第一部分：云环境准备

### 1.1 虚拟机配置推荐

| 云服务商 | 推荐虚拟机类型 | CPU | 内存 | 存储 | 预估成本/小时 |
|---------|--------------|-----|------|------|--------------|
| AWS | c6i.2xlarge | 8 核 | 16GB | 100GB+ | ~$0.35 |
| Azure | Standard_D8s_v3 | 8 核 | 32GB | 128GB+ | ~$0.40 |
| GCP | n1-standard-8 | 8 核 | 30GB | 100GB+ | ~$0.30 |

**最小配置要求**：
- CPU：4 核+
- 内存：8GB+
- 磁盘：50GB+（训练数据较大时需要更多）
- 操作系统：Ubuntu 20.04 LTS

### 1.2 选择合适的实例

**开发/测试**：使用计算优化实例（demo 用，快速迭代）

**生产运行**：使用通用实例或计算优化实例（取决于数据规模）

---

## 第二部分：一键部署脚本

### 2.1 创建初始化脚本

创建文件 `cloud_bootstrap.sh`：

```bash
#!/bin/bash

# 云端初始化脚本
# 在 Ubuntu 20.04 LTS 虚拟机上运行

set -e

echo "=========================================="
echo "Cloud Bootstrap: Ph-e_coupling_MD"
echo "=========================================="

# 系统更新
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# 安装基础工具
echo "Installing build tools..."
sudo apt-get install -y \
    build-essential \
    gfortran \
    cmake \
    git \
    curl \
    wget \
    openmpi-bin \
    libopenmpi-dev \
    libfftw3-dev \
    liblapack-dev \
    libblas-dev \
    python3-pip \
    python3-venv

# 安装 GPU 支持（如果需要，可选）
# sudo apt-get install -y nvidia-driver-525 nvidia-cuda-toolkit

# 克隆仓库
echo "Cloning repository..."
git clone https://github.com/weiqichen77/Ph-e_coupling_MD_regine.git
cd Ph-e_coupling_MD_regine

# 创建虚拟环境
echo "Creating Python virtual environments..."
python3 -m venv .venv
python3 -m venv .venv_deepmd22

# 安装 Python 依赖（使用兼容路径）
echo "Installing Python packages..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# 安装 DeepMD 2.2.11（用于严格模式）
echo "Installing DeepMD 2.2.11 in isolated environment..."
source .venv_deepmd22/bin/activate
pip install --upgrade pip
pip install tensorflow==2.16.1 deepmd-kit==2.2.11
deactivate

# 编译 LAMMPS
if [ -d "external/lammps" ]; then
    echo "Building LAMMPS..."
    bash scripts/build_lammps_with_plugin.sh
fi

# 编译 QE/EPW（可选，耗时较长）
# echo "Building QE/EPW..."
# bash scripts/build_qe_epw.sh

echo ""
echo "=========================================="
echo "Bootstrap completed successfully!"
echo "=========================================="
echo ""
echo "You can now run:"
echo "  cd Ph-e_coupling_MD_regine"
echo "  source .venv_deepmd22/bin/activate"
echo "  python tools/run_e2e_strict_polar_demo.py"
echo ""
```

### 2.2 执行初始化脚本

```bash
# 在云端 VM 上
chmod +x cloud_bootstrap.sh
./cloud_bootstrap.sh

# 或者一行命令
curl -O https://raw.githubusercontent.com/weiqichen77/Ph-e_coupling_MD_regine/main/cloud_bootstrap.sh && \
chmod +x cloud_bootstrap.sh && \
./cloud_bootstrap.sh
```

---

## 第三部分：数据管理

### 3.1 上传数据到云端

#### 方法 1：使用 `scp`（SSH）
```bash
# 从本地上传数据
scp -r ./qe_epw_demo_system/ ubuntu@your-vm-ip:/home/ubuntu/Ph-e_coupling_MD_regine/

# 下载结果
scp -r ubuntu@your-vm-ip:/home/ubuntu/Ph-e_coupling_MD_regine/tmp_e2e_strict_polar ./results/
```

#### 方法 2：使用对象存储（AWS S3、Azure Blob Storage 等）

**上传到 S3**：
```bash
# 本地
aws s3 cp qe_epw_demo_system/ s3://my-bucket/eph-data/ --recursive

# 云端 VM
aws s3 cp s3://my-bucket/eph-data/ ./qe_epw_demo_system/ --recursive
```

#### 方法 3：使用 GitHub 仓库
```bash
# 创建 data 分支存储数据
git checkout --orphan data
git add qe_epw_demo_system/
git commit -m "Add EPW demo data"
git push origin data

# 云端克隆
git clone -b data --depth 1 https://github.com/weiqichen77/Ph-e_coupling_MD_regine.git data
```

### 3.2 组织云端目录结构

```
/home/ubuntu/
├── Ph-e_coupling_MD_regine/        # 代码库
│   ├── tools/
│   ├── external/
│   └── ...
├── data/                            # 输入数据
│   └── qe_epw_demo_system/
├── models/                          # 训练好的模型
│   └── trained_models/
└── results/                         # 输出结果
    ├── trajectories/
    └── reports/
```

---

## 第四部分：运行管道

### 4.1 单步运行

```bash
# 连接到 VM
ssh ubuntu@your-vm-ip

# 进入项目目录
cd Ph-e_coupling_MD_regine

# 激活环境
source .venv_deepmd22/bin/activate

# 运行完整演示
python tools/run_e2e_strict_polar_demo.py
```

### 4.2 后台运行与日志

```bash
# 使用 nohup 在后台运行（即使断开 SSH 也继续）
nohup python tools/run_e2e_strict_polar_demo.py > run.log 2>&1 &

# 监控进程
ps aux | grep python

# 查看日志（实时）
tail -f run.log

# 或使用 screen/tmux（推荐）
screen -S eph_run
python tools/run_e2e_strict_polar_demo.py
# 按 Ctrl+A 再按 D 退出屏幕

# 重新连接 screen 会话
screen -r eph_run
```

### 4.3 定时任务运行

使用 `cron` 定期运行：

```bash
# 编辑 crontab
crontab -e

# 添加条目（每周日晚上 8 点运行）
0 20 * * 0 cd /home/ubuntu/Ph-e_coupling_MD_regine && \
            source .venv_deepmd22/bin/activate && \
            python tools/run_e2e_strict_polar_demo.py >> /home/ubuntu/runs.log 2>&1
```

---

## 第五部分：可选的 REST API 服务

### 5.1 使用 Flask 创建微服务

创建 `app.py`：

```python
from flask import Flask, request, jsonify
import subprocess
import os
from datetime import datetime
import json

app = Flask(__name__)

PROJECT_ROOT = "/home/ubuntu/Ph-e_coupling_MD_regine"
ENV = f"{PROJECT_ROOT}/.venv_deepmd22/bin/activate"

@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/run-demo', methods=['POST'])
def run_demo():
    """启动 e-ph 管道演示"""
    try:
        cmd = f"""
        source {ENV}
        cd {PROJECT_ROOT}
        python tools/run_e2e_strict_polar_demo.py
        """
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        return jsonify({
            "status": "completed" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "stdout": result.stdout[-1000:],  # 最后 1000 字符
            "stderr": result.stderr[-1000:]
        })
    
    except subprocess.TimeoutExpired:
        return jsonify({"status": "timeout", "error": "Execution took too long"}), 408
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/get-results', methods=['GET'])
def get_results():
    """获取最新结果"""
    try:
        report_path = f"{PROJECT_ROOT}/tmp_e2e_strict_polar/strict_report.json"
        if os.path.exists(report_path):
            with open(report_path, 'r') as f:
                report = json.load(f)
            return jsonify(report)
        else:
            return jsonify({"error": "No results found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
```

### 5.2 启动 API 服务

```bash
# 安装 Flask
source .venv_deepmd22/bin/activate
pip install flask

# 启动服务
python app.py

# 或使用生产级服务器
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 5.3 测试 API

```bash
# 健康检查
curl http://your-vm-ip:5000/health

# 运行演示
curl -X POST http://your-vm-ip:5000/run-demo

# 获取结果
curl http://your-vm-ip:5000/get-results
```

---

## 第六部分：性能优化

### 6.1 多进程并行

```bash
# 同时运行多组参数
for i in {1..4}; do
    nohup python tools/run_e2e_strict_polar_demo.py \
        --run-id run_$i > run_$i.log 2>&1 &
done

# 监控所有进程
watch -n 5 'ps aux | grep python'
```

### 6.2 GPU 加速

```bash
# 检查 GPU
nvidia-smi

# 在 DeepMD 中启用 GPU
# 修改 input JSON：
# "training": {
#    "device": "gpu:0"  # 或 "gpu:1" 等
# }

# 在 LAMMPS 中启用 GPU
# 重新编译时添加 PKG_GPU=ON
```

### 6.3 分布式计算

使用 MPI 实现分布式：

```bash
# LAMMPS with MPI
mpirun -np 4 lammps -in in.strict_polar_demo

# EPW with MPI
mpirun -np 8 epw.x -in epw.in
```

---

## 第七部分：监控与告警

### 7.1 系统监控

```bash
# 实时监控
top
htop

# 磁盘使用
du -sh ~/Ph-e_coupling_MD_regine/*

# 网络监控
iftop
```

### 7.2 日志收集

```bash
# 创建日志目录
mkdir -p ~/logs

# 运行管道并保存所有输出
python tools/run_e2e_strict_polar_demo.py \
    2>&1 | tee ~/logs/run_$(date +%Y%m%d_%H%M%S).log
```

### 7.3 性能报告

创建 `performance_report.sh`：

```bash
#!/bin/bash

echo "=== Performance Report ===" >> perf.log
echo "Date: $(date)" >> perf.log
echo "CPU usage: $(top -bn1 | grep load)" >> perf.log
echo "Memory: $(free -h)" >> perf.log
echo "Disk: $(df -h /)" >> perf.log
echo "" >> perf.log
```

---

## 第八部分：成本优化

### 8.1 使用 Spot 实例（按需实例成本的 70-90% 折扣）

**AWS**：
```bash
aws ec2 run-instances \
    --instance-type c5.2xlarge \
    --instance-market-options "MarketType=spot" \
    --image-id ami-0c55b159cbfafe1f0 \
    --count 1
```

### 8.2 自动关闭不用的实例

```bash
# 设置 30 分钟不活动后自动关闭
sudo shutdown -P +30
```

### 8.3 定期清理临时文件

```bash
# 删除旧的临时目录
find ~/Ph-e_coupling_MD_regine/tmp_* -mtime +7 -exec rm -rf {} \;

# 压缩结果
tar -czf results_backup.tar.gz tmp_e2e_strict_polar/
```

---

## 第九部分：故障排除

### 常见问题

| 问题 | 解决方案 |
|-----|--------|
| SSH 连接超时 | 检查安全组/防火墙规则；增加 SSH 超时：`ssh -o ConnectTimeout=60 ...` |
| 内存不足 | 增加虚拟机内存或使用更小的数据集 |
| 磁盘满 | 清理临时文件；使用对象存储存放大文件 |
| GPU 不被识别 | 检查 CUDA 驱动版本；重新编译 DeepMD/LAMMPS |
| API 超时 | 增加 Gunicorn 工作进程；实现异步任务队列（Celery） |

---

## 第十部分：生产部署检查清单

在部署到生产环境前，完成以下检查：

- [ ] 虚拟机资源充足（CPU、内存、磁盘）
- [ ] 网络连接正常（测试数据上传/下载）
- [ ] Python 环境配置完整（所有依赖已装）
- [ ] LAMMPS 编译成功（能运行 `-version`）
- [ ] QE/EPW 可用（可选，如需数据生成）
- [ ] 测试运行成功（demo 完全执行）
- [ ] 日志收集配置好
- [ ] 备份策略已制定
- [ ] 成本监控已启用
- [ ] 安全组/防火墙配置完成

---

## 附录：快速参考命令

```bash
# 首次部署
curl -O https://raw.githubusercontent.com/.../cloud_bootstrap.sh
bash cloud_bootstrap.sh

# 日常运行
cd ~/Ph-e_coupling_MD_regine
source .venv_deepmd22/bin/activate
python tools/run_e2e_strict_polar_demo.py

# 查看结果
cat tmp_e2e_strict_polar/strict_report.json

# 下载结果
scp -r ubuntu@your-vm:~/Ph-e_coupling_MD_regine/tmp_e2e_strict_polar ./

# 关闭实例
# AWS: aws ec2 stop-instances --instance-ids i-xxxxx
# Azure: az vm deallocate --resource-group myRG --name myVM
# GCP: gcloud compute instances stop instance-name
```

---

**最后更新**：2026-03-18  
**文档版本**：v1.0.0
