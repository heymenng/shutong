# 伴读书童AI - 外部数据集预处理指南

> **文档定位**：指导技术团队如何将下载的原始数据转换为训练可用的格式  
> **适用对象**：AI工程师、数据工程师  
> **版本**：v1.0  
> **日期**：2026年5月18日

---

## 数据集总览

| 数据集 | 类型 | 原始大小 | 预处理后大小 | 训练阶段 | 优先级 |
|--------|------|---------|-------------|---------|--------|
| TinyDialogues | 英语儿童对话 | ~500MB | ~400MB | Stage 1 | P0 |
| QiaoBan | 中文情感对话 | ~100MB | ~80MB | Stage 2 | P0 |
| YouthSafe | 安全分类模型 | ~1GB | ~1GB | Stage 3 | P0 |
| CCI2 | 中文通用语料 | ~501GB | ~50GB(筛选后) | Stage 1 | P1 |
| ASD Screening V3 | 医学筛查数据 | ~50MB | ~30MB | Stage 3 | P1 |

---

## 预处理流水线

```
原始数据下载 → 格式验证 → 去重清洗 → 年龄适配 → 安全过滤 → 格式标准化 → 训练集生成
```

---

## 一、TinyDialogues 预处理

### 1.1 原始格式

```json
{
  "conversation_id": "uuid",
  "turns": [
    {"speaker": "Parent", "text": "Let's go to the park!"},
    {"speaker": "Child", "text": "Yay! I want to swing."}
  ],
  "age": 5,
  "setting": "park",
  "participants": ["parent", "child"]
}
```

### 1.2 预处理步骤

**步骤1：按年龄段分离**

```python
age_map = {
    2: "infant",      # 对应孕育期+襁褓期
    5: "toddler",     # 对应幼童期
    10: "child",      # 对应蒙学期+小学期
    15: "teen",       # 对应少学期
}
```

**步骤2：转换为书童对话格式**

```json
{
  "messages": [
    {"role": "child", "content": "Let's go to the park!"},
    {"role": "shutong", "content": "Yay! I want to swing."}
  ],
  "metadata": {
    "age_group": "toddler",
    "source": "TinyDialogues",
    "language": "en",
    "topic": "play"
  }
}
```

**步骤3：中文对照生成（可选）**
- 使用翻译模型将核心对话译为中文
- 保留英文原句用于双语训练

### 1.3 质量检查点

- [ ] 对话轮数 ≥ 2
- [ ] 每轮字数 ≤ 50（儿童语言简短特征）
- [ ] 无成人敏感内容
- [ ] 年龄标签准确

---

## 二、QiaoBan 预处理

### 2.1 原始格式

```json
{
  "dialogue_id": "uuid",
  "turns": [
    {"speaker": "child", "text": "我今天考试没考好..."},
    {"speaker": "companion", "text": "没关系，一次考试不代表什么..."}
  ],
  "emotion": "sad",
  "strategy": "comfort",
  "age": 8
}
```

### 2.2 预处理步骤

**步骤1：情感标签标准化**

将QiaoBan的原始情感标签映射为书童统一标签：

| QiaoBan原始标签 | 书童标准标签 | 对应五维 |
|----------------|-------------|---------|
| sad | E-Sad | 神 |
| angry | E-Angry | 神 |
| happy | E-Happy | 神 |
| anxious | E-Anx | 神 |
| frustrated | E-Frustrated | 神 |
| confused | E-Confused | 神 |

**步骤2：策略标签映射**

| QiaoBan策略 | 书童心智标签 |
|------------|-------------|
| comfort | M-Comfort |
| encourage | M-Encourage |
| guide | M-Guide |
| listen | M-Listen |
| distract | M-Distract |

**步骤3：添加三维标签**

```json
{
  "tags": {
    "emotion": "E-Sad",
    "mind": "M-Comfort",
    "development": "D-3",
    "wuxing": "F-Shen"
  }
}
```

### 2.3 质量检查点

- [ ] 中文语境自然
- [ ] 情感标签与对话内容一致
- [ ] 无说教口吻（书童原则：共探而非教育）
- [ ] 每轮回应 ≤ 100字

---

## 三、YouthSafe 模型集成

### 3.1 非数据集，是模型

YouthSafe在HuggingFace上发布的是**安全分类模型**，不是原始YAIR数据集。

### 3.2 集成方式

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification

model_id = "YouthSafe/YouthSafe-Teen-GAI-Risk"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForSequenceClassification.from_pretrained(model_id)

def check_safety(dialogue_turns):
    text = "\n".join([f"{t['role']}: {t['content']}" for t in dialogue_turns])
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    outputs = model(**inputs)
    risk_score = outputs.logits.softmax(dim=-1)[0][1].item()
    return risk_score > 0.5  # 阈值可调
```

### 3.3 在训练流程中的位置

- **数据清洗阶段**：过滤高风险对话样本
- **在线推理阶段**：实时检测书童输出是否安全
- **红队测试阶段**：评估书童对危险输入的抵抗能力

---

## 四、CCI2 预处理

### 4.1 体积控制策略

CCI2原始数据501GB，全量下载不现实。建议策略：

**策略A：主题筛选（推荐）**

```python
keywords = [
    "儿童", "教育", "育儿", "家庭", "心理健康",
    "情感", "成长", "学校", "亲子", "健康"
]
# 仅保留包含关键词的文档
```

**策略B：质量筛选**

```python
min_length = 500      # 至少500字
max_length = 5000     # 最多5000字
min_chinese_ratio = 0.8  # 中文占比≥80%
```

**策略C：去重**

```python
# 使用SimHash或MinHash进行近似去重
threshold = 0.85  # 相似度阈值
```

### 4.2 预处理后规模

预计筛选后保留 **5-10GB**，约为原始的 **1-2%**。

---

## 五、ASD Screening V3 预处理

### 5.1 医学数据敏感性

- 所有记录必须脱敏（去除姓名、地点、具体日期）
- 仅保留症状描述、评估结果、年龄性别
- 用于训练书童的**医学知识**，而非诊断能力

### 5.2 转换格式

```json
{
  "case_id": "anonymized_001",
  "age_months": 36,
  "gender": "M",
  "symptoms": ["语言延迟", "社交回避", "重复行为"],
  "screening_score": 12,
  "risk_level": "high",
  "source": "ASD_V3"
}
```

### 5.3 使用边界

> ⚠️ **书童AI仅提供发育里程碑提醒和早期筛查建议，不做医学诊断。**

---

## 六、统一输出格式

所有预处理后的数据必须转换为统一的JSONL格式：

```json
{
  "id": "uuid",
  "conversations": [
    {"from": "child", "value": "..."},
    {"from": "shutong", "value": "..."}
  ],
  "metadata": {
    "source": "TinyDialogues|QiaoBan|...",
    "age_group": "infant|toddler|child|teen",
    "language": "zh|en|mixed",
    "tags": {
      "emotion": "E-XXX",
      "mind": "M-XXX",
      "development": "D-X",
      "wuxing": "F-XXX"
    },
    "safety_score": 0.95,
    "processed_at": "2026-05-18T12:00:00Z"
  }
}
```

---

## 七、训练数据配比

### 7.1 四阶段配比

| 训练阶段 | 数据组成 | 比例 | 批次大小 | 训练轮数 |
|---------|---------|------|---------|---------|
| **Stage 1** 预训练 | CCI2(筛选) + TinyDialogues | 6:4 | 64 | 3 |
| **Stage 2** 微调 | QiaoBan + 内部故事对话 | 5:5 | 32 | 5 |
| **Stage 3** 安全 | YouthSafe红队测试 + ASD案例 | 7:3 | 16 | 10 |
| **Stage 4** 文化 | 内部文化对话 + 节气体验 | 8:2 | 16 | 5 |

### 7.2 年龄配比

```python
age_weights = {
    "infant": 0.10,    # 0-2岁
    "toddler": 0.15,   # 2-4岁
    "child": 0.35,     # 4-10岁
    "teen": 0.40,      # 10-18岁
}
```

---

## 八、质量评估指标

| 指标 | 目标值 | 检测方法 |
|------|--------|---------|
| 数据去重率 | < 5% | SimHash |
| 年龄标签准确率 | > 95% | 人工抽检100条 |
| 安全违规率 | 0% | YouthSafe模型扫描 |
| 语言质量分 | > 4.0/5.0 | GPT-4评分 |
| 对话连贯性 | > 0.8 | 困惑度(PPL) |

---

## 九、目录结构（预处理后）

```
09-外部数据集/
├── README.md                          # 本指南
├── 下载并预处理外部数据集_v2.py       # 自动化脚本
├── dataset_usage_guide.json           # 使用指南（JSON版）
│
├── TinyDialogues/                     # 原始数据（下载后）
│   ├── train.jsonl
│   └── val.jsonl
├── TinyDialogues_processed/           # 预处理后
│   ├── infant.jsonl
│   ├── toddler.jsonl
│   ├── child.jsonl
│   ├── teen.jsonl
│   └── preprocess_report.json
│
├── QiaoBan/                           # 原始数据
├── QiaoBan_processed/                 # 预处理后
│   ├── emotional_support.jsonl
│   └── preprocess_report.json
│
├── YouthSafe/                         # 安全模型
│   ├── README.md
│   ├── adapter_config.json
│   └── adapter_model.safetensors
│
├── CCI2/                              # 原始数据（分片）
└── CCI2_processed/                    # 筛选后
    └── filtered_shard_*.jsonl
```

---

## 十、常见问题

**Q1: CCI2太大，无法全量下载怎么办？**
A: 使用`hf_hub_download`按需下载特定分片，或联系BAAI申请筛选后的子集。

**Q2: TinyDialogues是英文，如何用于中文书童？**
A: 两个用途：① 训练英语对话能力（双语书童）；② 提取对话结构，用于生成中文对照样本。

**Q3: YouthSafe模型可以商用吗？**
A: 需查看HuggingFace上的License。伴读书童AI如商用，建议联系YouthSafe作者获取授权。

**Q4: 预处理后的数据如何版本管理？**
A: 建议使用DVC(Data Version Control)或Git LFS管理大文件，元数据用Git管理。

---

> **数据是AI的食粮，质量决定书童的智商。**
>�> 宁可数据少，不可数据差。
>
> 灵觉/Prome 整理  
> 2026年5月18日
