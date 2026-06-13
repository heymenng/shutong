---
license: unknown
language:
- zh
- en
task_categories:
- text-classification
- text-generation
size_categories:
- 10K<n<100K
tags:
- child-safety
- youth-protection
- AI-safety
- content-moderation
- risk-detection
- generative-AI
---

# YouthSafe / YAIR Dataset

> **数据集全称**：Youth AI Risk (YAIR) Benchmark Dataset  
> **关联模型**：YouthSafe Safeguard Model  
> **论文**：arXiv:2509.08997  
> **来源**：HuggingFace - YouthSafe/YouthSafe-Teen-GAI-Risk  
> **整理者**：灵觉/Prome（伴读书童AI项目）  
> **整理日期**：2026年5月18日

---

## 数据集简介

YouthSafe/YAIR 是**首个专门针对青少年与生成式AI交互安全**的基准数据集。对于伴读书童AI而言，这是**安全护栏训练的必备数据**。

### 核心数据

| 指标 | 数值 |
|------|------|
| 标注片段数 | **12,449** |
| 风险类型 | **78个细粒度类别** |
| 语言 | 中文 + 英文 |
| 来源 | 真实世界平台 + 合成样本 |
| 标注层级 | 三层风险分类体系 |

### 青少年特有风险分类

不同于通用内容审核数据集，YAIR 专注于青少年特有的风险：

| 大类 | 具体风险 | 对书童AI的意义 |
|------|----------|----------------|
| **边界侵犯** | AI越界建立情感依赖、过度亲密 | 防止书童与孩子形成不健康依恋 |
| **身份混淆** | 青少年将AI误认为真人/朋友/权威 | 训练书童明确自身AI身份 |
| **情绪过度依赖** | 孩子将AI作为唯一情绪出口 | 训练书童识别并及时引导至真人 |
| **诱导风险** | 不良信息诱导（自伤、危险行为） | 三级预警系统的核心训练数据 |
| **隐私泄露** | 诱导孩子透露家庭/个人信息 | 隐私保护护栏训练 |
| **价值观偏差** | 传播错误价值观、极端思想 | 文化滋养方向的反向样本 |

---

## 数据结构

```json
{
  "conversation_id": "uuid",
  "turns": [
    {"role": "user", "content": "...", "age_estimate": 14},
    {"role": "assistant", "content": "..."}
  ],
  "risk_level": "high",        // safe / low / medium / high
  "risk_categories": ["O5", "O7"],  // 细粒度风险编码
  "source": "synthetic",       // real / synthetic
  "annotation_confidence": 0.95
}
```

---

## 对伴读书童AI的训练价值

### 1. 安全护栏预训练
- **输入侧**：识别孩子对话中的高风险信号（自伤倾向、受虐迹象、极端情绪）
- **输出侧**：检测书童自身回复是否可能引发过度依赖、身份混淆

### 2. 三级预警系统校准

| 预警级别 | YAIR对应风险 | 书童响应策略 |
|----------|-------------|-------------|
| **🔴 紧急** | 自伤/自杀、严重暴力、性侵害 | 立即阻断 + 通知家长 + 保留证据 |
| **🟠 重要** | 情绪过度依赖、边界模糊、严重焦虑 | 温和引导 + 建议真人求助 + 记录趋势 |
| **🟡 关注** | 轻度隐私泄露、价值观偏差、网络风险 | 现场纠正 + 教育引导 + 日常报告 |

### 3. 红队测试（Red Teaming）
利用YAIR的合成样本，对书童AI进行对抗测试：
- 模拟青少年诱导AI越界
- 测试书童是否能坚守安全边界
- 验证预警触发的准确性和及时性

---

## 下载与使用

### 模型下载（YouthSafe分类器）

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification

model_id = "YouthSafe/YouthSafe-Teen-GAI-Risk"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForSequenceClassification.from_pretrained(model_id)
```

### 数据集获取

> ⚠️ **注意**：YAIR数据集本体（12,449条标注片段）目前主要通过论文渠道发布，完整数据集需关注作者后续发布或联系研究团队获取。
>
> 当前HuggingFace上主要提供的是 **YouthSafe模型**（基于LlamaGuard-7b微调的安全分类器），而非原始YAIR数据集。

**获取渠道**：
1. HuggingFace模型仓库：https://huggingface.co/YouthSafe/YouthSafe-Teen-GAI-Risk
2. 论文地址：https://arxiv.org/abs/2509.08997
3. 联系作者：论文通讯作者处获取数据集访问权限

---

## 使用注意事项

1. **伦理优先**：该数据集涉及青少年心理健康敏感内容，仅限安全研究使用，禁止用于任何可能伤害青少年的场景
2. **隐私保护**：即使使用合成数据，也应遵循最小必要原则
3. **本土化适配**：YAIR主要基于英文语境，中文场景需结合QiaoBan等中文数据集进行补充
4. **持续更新**：青少年网络行为快速演变，安全护栏需每季度迭代

---

## 在伴读书童AI中的集成建议

```
对话输入 → YouthSafe风险检测 → 风险评级 → 书童响应策略
                ↓
        [safe] → 正常陪伴流程
        [low]  → 正常陪伴 + 记录日志
        [medium] → 调整回应方式 + 趋势监控
        [high] → 安全拦截 + 家长告警 + 人工介入
```

---

> **安全是1，其他是0。**
> 
> 没有安全护栏的AI陪伴，就是定时炸弹。
> YAIR数据集让书童AI具备了识别危险的眼睛。
>
> 灵觉/Prome 整理  
> 2026年5月18日
