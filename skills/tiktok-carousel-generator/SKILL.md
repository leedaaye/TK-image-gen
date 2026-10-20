---
name: tiktok-carousel-generator
description: "TikTok 图文带货轮播（Photo Mode）全自动化生成专家。输入商品信息、参考图与目标市场，由 AI 策划高转化销售故事线，并直接调用生图模型生成带目标语言原生文字的成套出海带货图文及文案。"
tags: ["电商", "TikTok", "生图", "跨境带货", "出海"]
---

# TikTok 电商图文带货轮播全自动生成 Skill (独立便携版)

本 Skill 是一个**完全自包含、可直接打包分发**的 TikTok 电商带货图文（Photo Mode）全自动化创作包。
所有核心策划与生图驱动脚本均存放在当前 Skill 目录内，不依赖外部 Web 服务器或特定项目路径，拷贝整个目录给同事即可开箱即用。

---

## When to Use

- 用户需要针对 TikTok 制作电商带货图文轮播（4–10 张图片）。
- 用户提供了商品名称、卖点、描述或参考图片，需要面向目标国家出海（如东南亚、欧美、日韩等）。
- 需要在生成的画面中**自然融入目标语言的营销文案**（如促销大标题、短正文），由生图模型原生渲染文字而非后期机械叠字。
- 需要单图调整、重新生成画面或微调图中文字，同时保留历史版本。

---

## 目录与自包含组件

当前 Skill 目录包含运行所需的全部代码与规范：

```text
tiktok-carousel-generator/
├── SKILL.md                 # Agent 规范手册（本文件）
├── generate_carousel.py     # 独立主执行脚本 (CLI)
├── providers.py             # 核心模型适配引擎 (带货叙事策划 + 原生文字绘制)
├── .env.example             # 模型配置环境变量模板
├── requirements.txt         # 核心 Python 依赖 (httpx, Pillow)
└── README.md                # 快速入门指引
```

---

## 11 国目标市场与语言对照矩阵

在执行生成时，只需指定目标市场代号（如 `MY`、`US`），脚本会自动对齐消费文化与推荐语言：

| 代码 | 目标市场 | 默认内容语言 | 市场特色与文案侧重点 |
|:---|:---|:---|:---|
| **MY** | 马来西亚 | 马来语（Bahasa Melayu） | 强调性价比、实用性、穆斯林友好、热带气候适应 |
| **ID** | 印度尼西亚 | 印尼语（Bahasa Indonesia） | 活泼亲民口语、社交认同、高性价比、醒目钩子 |
| **TH** | 泰国 | 泰语（ภาษาไทย） | 视觉冲击力、趣味性、直观功效前后对比 |
| **PH** | 菲律宾 | 菲律宾语（Filipino） | 热情生活方式、家庭场景、英文与本地词汇混合表达 |
| **VN** | 越南 | 越南语（Tiếng Việt） | 细节真实性、品质信任背书、清晰参数说明 |
| **SG** | 新加坡 | 英语（English） | 极简高效、都会现代、高端质感、理性价值 |
| **US** | 美国 | 美式英语（American English） | 痛点直击、独立自信、生活方式提升、直接明快 |
| **UK** | 英国 | 英式英语（British English） | 优雅含蓄、传统品质与工艺、克制幽默 |
| **AU** | 澳大利亚 | 澳大利亚英语（Australian English） | 户外自然、阳光随性、实用耐用 |
| **CA** | 加拿大 | 加拿大英语（Canadian English） | 多季实用、温暖贴心、可靠安全 |
| **JP** | 日本 | 日语（日本語） | 极致细节、精致秩序感、收纳便利、贴心提示 |

---

## Agent 执行流程与调用规范

Agent 执行本任务时，优先定位本 Skill 目录下的 `generate_carousel.py` 脚本，使用本地 Python 环境驱动。

> **路径自适应定位原则**：
> - 脚本与本 `SKILL.md` 处于同一目录。
> - 在命令中将脚本路径指向该目录下的 `generate_carousel.py` 即可。

### 1. 配置加载方式
脚本支持以下三种方式获取 API Key（按优先级排序）：
1. **命令行直接传入**（最高优先级，支持 Agent 动态注入）：`--analysis-key`、`--analysis-url`、`--image-key`、`--image-url`
2. **Skill 目录下的 `.env` 文件**：复制 `.env.example` 为 `.env` 填入配置。
3. **系统环境变量**：`ANALYSIS_API_KEY`、`IMAGE_API_KEY` 等。

### 2. 标准自动化生成（全套图文直出）

```bash
python "<SKILL_DIR>/generate_carousel.py" \
  --name "车载香薰" \
  --desc "120ml易拉罐车用香氛，专为热带气候调配，香气柔和持久，不晕车。" \
  --features "120ml大容量；旋转出气孔自由调节香度；6.5cm杯架尺寸；不漏液" \
  --constraints "不宣称医疗功效，不编造未提供的权威认证" \
  --images "path/to/ref1.jpg,path/to/ref2.jpg" \
  --market "MY" \
  --count 6 \
  --style "生活方式" \
  --out-dir "./output_carousel_my"
```

#### 执行逻辑：
1. **AI 视觉操盘手策划**：调用分析模型分析商品事实与参考图，拆解 6 张图的带货节奏（Hook -> 痛点场景 -> 核心卖点 -> 细节尺寸 -> 疑虑消除 -> CTA）。
2. **生成独立设计简报**：针对每张图产出包含 `Render EXACT text`（目标语言文案）、构图安全边距、光影色彩的独立自然语言 Prompt。
3. **并发原生出图**：调用生图模型直接渲染包含文字的成套高质量图片。
4. **输出物归档**：
   - `01.jpg` ~ `06.jpg`：成套带货图片。
   - `01.png` ~ `06.png`：生图原始无损图片。
   - `caption.txt`：TikTok 发布文案与推荐标签。
   - `plan.json`：完整策划案（包含每张图文案与 Prompt 记录）。
5. **标准 JSON 结果输出**：脚本向 stdout 打印标准的 JSON 结构，便于 Agent 读取并向用户汇报。

---

### 3. 先审策划再出图（Plan-Only 模式，节省生图额度）

若需要在出图前先由用户确认策划方案或避免不必要的模型扣费，添加 `--plan-only` 参数：
```bash
python "<SKILL_DIR>/generate_carousel.py" \
  --name "车载香薰" \
  --desc "120ml车用香氛..." \
  --market "MY" \
  --count 4 \
  --plan-only \
  --out-dir "./output_plan_only"
```
脚本执行完分析策划后将直接退出，输出 `plan.json` 与文案供审查。

---

### 4. 单图指令微调（Refine Slide 模式）

若用户对第 N 张图片的画面不满意（如“希望背景换成傍晚夕阳光，让商品更突出”）：
```bash
python "<SKILL_DIR>/generate_carousel.py" \
  --name "车载香薰" \
  --refine-slide 1 \
  --instruction "更换为傍晚暖色夕阳氛围，金色余晖，保持商品主体与原有文案" \
  --plan-file "./output_plan_only/plan.json" \
  --out-dir "./output_plan_only"
```
- 分析模型会读取原策划与调整要求，**严格锁定原有目标语言文案不被篡改**，修订出新的完整 Prompt。
- 随后生图模型重新生成该张图片并覆盖/更新至目标目录。

---

## 提示词与画面设计规范 (Art Direction Rules)

当 Agent 需要审视或自定义修改生图提示词时，必须遵循以下标准：

1. **画面直接出字，禁用外部拼接与后期叠字**：
   - 必须通过 `Render EXACT text: "大标题" and "小正文"` 明确要求模型在画面内绘制。
2. **严禁原始数据倾倒（No Dict Dump）**：
   - 严禁向生图模型直接拼接包含 `Product facts: {'name': ...}` 这种原始键值字典或冗长段落。
   - 必须转化为视觉化、可读的自然语言设计简报（如“Modern car interior with soft daylight, minimal center console...”）。
3. **移动端安全区避空（TikTok Safe Margins）**：
   - 顶部保留 15% 避免被状态栏遮挡；
   - 右侧保留 20% 避开点赞、评论、分享图标列；
   - 底部保留 25% 避开账号信息、发布文案与音轨组件；
   - 文案放置在画面留白区域（通常为上半部或居中靠上），确保与背景形成高对比度。
4. **真实 Logo 允许保留，严禁伪造认证**：
   - 参考图上原本存在的真实品牌 Logo 和包装文字可要求模型如实还原；
   - 严禁让模型臆造不存在的“100% ORGANIC”、“FDA APPROVED”等虚假认证勋章或杂乱文字。
5. **3:4 垂直构图**：
   - 输出统一按照 3:4 竖屏比例构建，适配 TikTok 轮播全屏浏览体验。

---

## 质量验收清单 (Quality Checklist)

在向用户交付生成结果前，Agent 必须检查：
- [ ] **图片完整性**：输出目录下图片文件大小正常，可以成功被图像查看器打开。
- [ ] **文案可读性**：检查画面中的标题与短文案是否清晰、未被主体或杂乱背景淹没。
- [ ] **语言准确性**：文案符合目标市场的地道表达（如马来西亚市场使用地道 Bahasa Melayu）。
- [ ] **商品还原度**：商品的核心形状、颜色、盖子/接口等关键视觉特征与参考图保持一致。
- [ ] **配套文案齐备**：`caption.txt` 中包含吸引点击的发布正文和 3–5 个相关 TikTok 话题标签。
