# 项目状态

更新时间：2026-10-20。此文件记录当前状态；历史实现变化见 Git 历史。

## 当前产品

- 面向服务器部署的 TikTok 商品图文 Web 应用，React/TypeScript/Vite + FastAPI/SQLAlchemy。生产 PostgreSQL/Docker Compose，本机 SQLite 仅用于开发测试。
- 商品资料与参考图片持久化，项目保存商品快照；管理员认证、文件鉴权、密钥加密、写请求 Origin 校验。
- 独立 Worker 持久化逐图任务，并发控制、失败重试、版本恢复、ZIP 导出。中断任务不自动重新收费生成。
- 当前采用 native_text_v1：分析模型输出逐张完整自然语言设计简报，含准确标题/正文，生图端原样执行，模型直接画文字。保留模型实际尺寸，不强制裁切、不后期叠字。
- 修改文案先保存草稿，再分析修订并生成新版本；旧文件和版本不覆盖。旧项目下次生成自动升级提示词，历史版本恢复直接使用已有文件，不依赖旧排版器。
- 11国市场与默认语言联动，15种语言选项，高对比度界面。
- Windows 使用根目录 BAT/VBS + scripts/launcher.py 管理隐藏启动、停止和构建；生产部署见 README.md。

## Agent Skill（独立分享）

- skills/tiktok-carousel-generator 为唯一分享源目录，只有4份文件：SKILL.md、README.md、references/design-guide.md、templates/plan.example.json。
- 分析/策划由 Agent 自身模型完成，生图调用宿主已有工具，无额外Key配置、Python依赖、数据库或Web服务。保留参考图、准确文字、单图版本和归档规范。
- 已同步到本机 .agents 与 magpie 技能库；.dsh 技能路径链接到 magpie 库。
- 可直接转发的分享包：exports/tiktok-carousel-generator-agent-native.zip。exports只存本机交付物，不进入Git和Docker构建上下文。

## 本次目录清理

- 删除 artifacts 临时验收目录：浏览器截图/脚本、专用 Playwright 依赖、网络探测脚本、模拟商品数据库及CLI试运行输出，约22.7MB。唯一需保留的Skill ZIP迁移到exports。
- 删除 scripts/generate_carousel.py：已被原生Skill取代，且依赖不存在的同目录providers模块，无法独立运行。
- 删除 backend/app/rendering.py 及仅针对旧叠字器的6个测试用例；生产链路无调用。Docker移除只供叠字器使用的CJK字体安装步骤，保留应用用户与数据目录权限。Pillow仍由现有生产链路使用，依赖保留。
- 删除 backend/tests/mock_model_server.py：旧人工验收夹具，无仓库调用，不符合当前策划/修订协议；现有HTTP Mock测试保留。
- 清除Python/pytest缓存与TypeScript增量构建缓存。保留.venv、frontend/node_modules及frontend/dist，它们供当前开发和本机启动使用。
- 未修改 data 业务资料、logs 运行日志与配置，不重置账号、不处理历史商品资产。
- .gitignore补充exports及npm回退生成的package-lock忽略规则；部署脚本、迁移、锁文件、业务代码和有效测试保留。

## 验证与运行状态

- 清理前84项测试；移除旧叠字器6项专属测试后，78项现行业务/模型回归测试全部通过。前端类型检查与生产构建通过；Python源码语法和4文件Skill ZIP校验通过。
- 本次核查本机 http://127.0.0.1:8000 未运行服务；不额外启动或重启用户日常服务。
- 测试使用隔离目录与模拟接口，不使用实际商品数据和付费生图。
- Skill零配置流程与4文件分享包已静态校验；不代表真实商品文字准确率和模型还原效果已通过验收。

## 限制与后续

- Docker/Linux/PostgreSQL尚未真实启动验收，部署前按README验证；Web模型接口需要各自配置，和零配置Skill分别使用。
- Web仅支持同步OpenAI images接口，尚不支持异步服务商任务轮询；Skill按宿主现有工具处理异步结果。
- 参考图还原和图中文字质量取决于模型，发布前需实际检查；纯背景模式不自动合成真实商品。
- 单管理员，无TikTok自动发布、多账号或团队权限。业务旧图片暂不自动垃圾回收，需备份数据库、图片与SECRET_KEY。
