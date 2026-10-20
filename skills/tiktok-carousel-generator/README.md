# TikTok 图文带货生成工具包 (tiktok-carousel-generator)

这是一个完全自包含、即开即用的 **TikTok 电商图文轮播（Photo Mode）全自动化生成工具包**。
支持直接作为 AI Agent 的 Skill 使用，也可以由人类在命令行中直接运行。

---

## 目录结构

```text
tiktok-carousel-generator/
├── SKILL.md                 # Agent Skill 规范与使用手册
├── generate_carousel.py     # 独立主执行脚本 (CLI)
├── providers.py             # 核心模型适配引擎 (带货叙事策划 + 原生文字绘制)
├── .env.example             # 模型配置环境变量模板
├── requirements.txt         # 核心 Python 依赖
└── README.md                # 快速入门指引
```

---

## 快速安装与配置

### 1. 安装依赖
需要 Python 3.10+ 环境：
```bash
pip install -r requirements.txt
```

### 2. 配置 API Key
复制 `.env.example` 为 `.env` 并填写：
```env
ANALYSIS_BASE_URL=https://api.openai.com/v1
ANALYSIS_API_KEY=sk-xxxxxx
ANALYSIS_MODEL=gpt-4o

IMAGE_BASE_URL=https://api.openai.com/v1
IMAGE_API_KEY=sk-xxxxxx
IMAGE_MODEL=gpt-image-1
IMAGE_MODE=reference
```
*(注：如果不想使用 `.env` 文件，也可以在运行命令时直接通过 `--analysis-key`、`--image-key` 等参数传入。)*

---

## 常用命令示例

### 1. 全套图文一键生成 (直出成套带货图片与发布文案)
```bash
python generate_carousel.py \
  --name "车载香薰" \
  --desc "120ml易拉罐车用香氛，专为热带气候调配，香气柔和持久，不晕车。" \
  --features "120ml大容量；旋转出气孔自由调节香度；6.5cm杯架尺寸；不漏液" \
  --constraints "不宣称医疗功效，不编造未提供的权威认证" \
  --images "path/to/ref1.jpg,path/to/ref2.jpg" \
  --market "MY" \
  --count 6 \
  --style "生活方式" \
  --out-dir "./my_car_scent_carousel"
```
完成后，输出目录下将包含：
- `01.jpg` ~ `06.jpg`：模型原生绘制了目标语言文案的高清带货图片。
- `01.png` ~ `06.png`：模型无损原图。
- `caption.txt`：适合直接复制发布的 TikTok 文案与热门标签。
- `plan.json`：每张图的完整 Prompt、文案与策划方案。

### 2. 先审策划再出图 (省流模式)
添加 `--plan-only` 参数，只进行 AI 视觉策划并输出文案与每张图的 Prompt，不调用生图模型扣费：
```bash
python generate_carousel.py \
  --name "车载香薰" \
  --market "MY" \
  --count 4 \
  --plan-only \
  --out-dir "./my_plan_only"
```

### 3. 单图精准微调 (Refine Slide)
如果对某一张（例如第 1 张）画面不满意，希望调整光影或背景：
```bash
python generate_carousel.py \
  --name "车载香薰" \
  --refine-slide 1 \
  --instruction "将背景换为傍晚夕阳暖光，金色余晖，保持商品主体与原有文案" \
  --plan-file "./my_plan_only/plan.json" \
  --out-dir "./my_plan_only"
```

---

## 11 国目标市场代号

指定 `--market` 时输入国家代号，系统会自动适配该国主流语言与文案表达：

| 代码 | 市场 | 默认语言 |
|:---|:---|:---|
| **MY** | 马来西亚 | 马来语（Bahasa Melayu） |
| **ID** | 印度尼西亚 | 印尼语（Bahasa Indonesia） |
| **TH** | 泰国 | 泰语（ภาษาไทย） |
| **PH** | 菲律宾 | 菲律宾语（Filipino） |
| **VN** | 越南 | 越南语（Tiếng Việt） |
| **SG** | 新加坡 | 英语（English） |
| **US** | 美国 | 美式英语（American English） |
| **UK** | 英国 | 英式英语（British English） |
| **AU** | 澳大利亚 | 澳大利亚英语（Australian English） |
| **CA** | 加拿大 | 加拿大英语（Canadian English） |
| **JP** | 日本 | 日语（日本語） |
