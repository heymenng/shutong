---
language:
- zh
task_categories:
- text-generation
dataset_info:
  features:
  - name: id
    dtype: string
  - name: content
    dtype: string
  splits:
  - name: cci2
    num_bytes: 531432249559
    num_examples: 178959936
  download_size: 349348858174
  dataset_size: 531432249559
configs:
- config_name: default
  data_files:
  - split: cci2
    path: data/cci2-*
extra_gated_prompt: "You agree to not use the dataset to conduct experiments that cause harm to human subjects."
extra_gated_fields:
  Company/Organization: text
  Country: country
---

## Data Description

To address the scarcity of high-quality safety datasets in the Chinese, we open-sourced the [CCI](https://huggingface.co/datasets/BAAI/CCI-Data) (Chinese Corpora Internet) dataset on November 29, 2023. Building on this foundation, we continue to expand the data source, adopt stricter data cleaning methods, and complete the construction of the CCI 2.0 dataset. This dataset is composed of high-quality, reliable Internet data from trusted sources. It has undergone strict data cleaning and de-duplication, with targeted detection and filtering carried out for content quality and safety. The rules for data processing include:

- Rule-based filtering: safety filtering based on keywords, spam information filtering, etc.
- Model-based filtering: filtering of low-quality content by training a classification model
- Deduplication: within and between datasets dedup

The CCI 2.0 corpus released is 501GB in size. 

## Update

- April 26, 2024, CCI 2.0 released!


## Data Format


|  Field  |  Type  |           Meaning            |
| :-----: | :----: | :--------------------------: |
|   id    | String | Document ID, globally unique |
| content | String |   Content of the document    |


## Sample

```json
{
    "id": "97934bc9f83ad6a7dcdf6fed69eeb566",
    "content": "山东出台省属高校多渠道筹资收入财政配比政策\n为进一步放大杠杆激励效应，更好带动高校增强资金筹措能力和内生发展动力，近日山东省教育厅、省财政厅印发《省属本科高校多渠道筹资收入财政配比资金管理办法》，将高校捐赠收入财政配比政策，优化升级为多渠道筹资收入财政配比政策。\n　　据悉，自2017年高校捐赠收入财政配比政策出台以来，省财政按照高校捐赠收入1：1比例，累计兑现配比资金4.82亿元，对引导高校树立多渠道筹资理念、提升高质量发展水平发挥了重要促进作用。\n　　此次调整从“一元”变“多元”，强化配比力度。扩大财政配比范围，将高校为地方经济社会发展提供科研服务、技术服务、培训服务、仪器设备共享服务及开展产学研合作等取得的收入新增纳入配比范围，激励高校提升与地方“互哺”发展能力，引导作用更强、支持力度更大。\n　　引入调节系数，体现统筹兼顾。充分考虑不同层次和类型高校办学基础条件和筹资能力差异，按照学校办学层次和专业特色，分校确定层次系数、类别系数，根据各校经调节系数折算后的筹资收入分配配比资金，加大对办学实力较弱高校的倾斜。新政策的出台，全面强化了资金支持引导力度，将进一步发挥激励引导作用，更好调动各类高校多渠道筹资积极性。"
}

```

## Download

The CCI 2.0 dataset is simultaneously open-sourced on the [BAAI DataHub](https://data.baai.ac.cn/details/BAAI-CCI2) and Huggingface. 

### BAAI DataHub

Users can click the link [CCI 2.0 Dataset](https://data.baai.ac.cn/details/BAAI-CCI2) to view the data files, and click to download.

Note that users need to register on BAAI DataHub to use the data, and filling out a survey questionnaire is required before their first download.

### Huggingface

To use the data, you can load it using the following code:

```python
from datasets import load_dataset

dataset = load_dataset("BAAI/CCI2-Data")
```

## User Agreement

Users need to comply with the usage agreement of the CCI 2.0 dataset. You can view the agreement by clicking on the following link: （[View Usage Agreement](https://data.baai.ac.cn/resources/agreement/cci_usage_aggrement.pdf)）.

## Notice

If you have any questions related to this dataset, please contact data@baai.ac.cn.