# 会议录音转文字 · 引导与降级指南

本模板供「本技能」在用户上传会议录音、但环境无可用转写能力时，输出标准化的引导话术与安装指引。核心理念：**宁可不干活，也要给可落地的下一步**——绝不只回"我做不到"，也绝不伪造/猜测转写内容。

## 一、四级降级引导（标准提示话术）

> 检测到音频文件，但当前环境没有可用的转写能力（未启用腾讯会议、未安装语音转文字技能、本机也未配置 ASR）。你可以任选一种方式继续：
> ① 最省事：用任意工具转成文字稿发我，我直接整理纪要；
> ② 开会用腾讯会议 → 去连接器页信任「腾讯会议」即可自动转写；
> ③ 想长期自动化 → 接入宿主的语音转文字能力后告诉我；
> ④ 数据要留本地 → 本机自托管 faster-whisper（我可给安装指引）。
> 选哪个？或直接把转写好的文字粘贴给我也行。

## 二、档位 1：粘贴文字稿（零门槛，推荐偶尔用）

用户用任意工具（腾讯会议导出、飞书妙记、剪映字幕、手机自带转写等）把音频转成文字，直接发来。本技能走 §1 纪要提取。

## 三、档位 2：信任腾讯会议 tmeet 连接器

适用：经常用腾讯会议开会。
- 让用户去 宿主 连接器页，找到「腾讯会议」点"信任"启用。
- 启用后云录制自带转写，本技能可直接拉取转写稿。
- 注意：tmeet 当前默认 disconnected，需用户手动授权。

## 四、档位 3：接入语音转文字能力

适用：想长期自动化、不愿手动转写。
- 接入宿主提供的「语音转文字 / 语音转写」能力。
- 装好后告诉本技能，后续音频直接分流调用它转写，再走 §1。

## 五、档位 4：本机自托管 faster-whisper（数据留本地，实测指引）

适用：数据敏感、不想出本机；或录音量大。

**本机实测环境（验证）**：
- 显卡 Intel Arc A770 16GB，但 faster-whisper 实际走 **CPU(int8)** 推理，非 XPU 加速。
- 模型 `small`：转写 14 分半音频约 **6–7 分钟**。
- 输出默认**繁体中文**，需 OpenCC `t2s` 转简体：`pip install opencc-python-reimplemented`（纯 Python 无原生依赖）。

**安装（国内镜像，避免官方源超时）**：
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple faster-whisper opencc-python-reimplemented
```

**调用（示例）**：
```python
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, _ = model.transcribe("会议录音.wav", language="zh", beam_size=5)
text = "\n".join(s.text for s in segments)
# 繁→简
from opencc import OpenCC
text = OpenCC("t2s").convert(text)
```

**提醒**：
- 少量录音够用；量大建议用档位 2/3（更快、带说话人分离）。
- 远场麦克风、重叠说话、电话窄带音(8kHz) 准确率会明显下降，转写后请人工核对关键数字与人名。

## 六、转写后纪要整理

无论哪档拿到文字稿，统一走 SKILL.md 分流表「会议纪要（任意来源）」→ dispatch.md §1，产出结构化纪要 + 行动项。转写稿标注 `[转写待核对]`，关键数字/人名提示用户核对。
