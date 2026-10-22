---
name: medical-imaging
description: 医学影像套件部署：用 Docker 部署 OHIF viewer、DICOMweb 集成与 TotalSegmentator/MONAI 分割 API。触发场景：自建医学影像查看或分割环境、医学影像套件部署。
author: Soulmate Agent团队成员：岸
---

# 医学影像套件部署

## 适用场景

自建医学影像查看与分割环境。包含 OHIF viewer 部署、DICOMweb 集成、TotalSegmentator、MONAI 工作流、Docker 部署。

## 步骤

```bash
# 部署完整套件
./deploy.sh

# 仅部署查看器
./deploy.sh viewer

# 仅部署分割 API
./deploy.sh segmentation
```

脚本：`scripts/imaging/deploy.sh`。

## 输入输出

- 输入：Docker 环境。
- 输出：可访问的 OHIF viewer / 分割 API 服务。
- 可对接的 DICOMweb 服务（未验证具体配置）：tbidea、orthanc、DCM4CHEE。

## 注意事项

- 要求：Docker、≥4GB RAM。
- **未验证**：`deploy.sh` 内部具体镜像、端口、DICOMweb 端点参数、TotalSegmentator/MONAI 配置未逐项展开；使用前须阅读脚本并按本机环境核对。
- 面向医学影像数据，注意患者隐私与数据合规；本功能属自建服务部署，不涉及诊断结论。

## 可复用示例

在一台已装 Docker、内存 ≥4GB 的机器上：
```bash
cp scripts/imaging/deploy.sh .
chmod +x deploy.sh
./deploy.sh viewer      # 先只起查看器验证环境
```
确认 viewer 可访问后，再执行 `./deploy.sh` 部署完整套件。
