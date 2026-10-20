# 项目状态

更新时间：2026-10-20，第一版可运行实现已完成。

## 当前实现
- React/TypeScript/Vite 中文响应式工作台：登录/初始化、总览、商品库、生成项目、任务中心、模型配置。
- FastAPI + SQLAlchemy，Alembic 初始迁移；正式 PostgreSQL，本机缺少 Docker 使用 SQLite 开发替代。
- 商品资料和参考图持久化；项目保存商品快照。
- OpenAI chat/completions 视觉策划、images/edits 多参考图、images/generations 纯背景模式。extra、Key、超时、并发分别配置。
- API Key Fernet 加密、管理员 scrypt 密码、HttpOnly session、文件鉴权、路径校验和写请求 Origin 检查。
- 独立 Worker，持久化逐图队列、并发、失败重试、中断识别；非幂等付费请求不盲目自动重试。
- 4–10 张完整策划、人工确认或自动出图、单图修改、历史版本选择、文案本地重排和 ZIP 导出。
- 当前采用native_text_v1：分析模型输出独立完整含文字生图设计简报，生图直接绘制目标语言文案；保存模型实际尺寸，不裁切不后期叠字。旧Pillow渲染模块仅保留历史兼容代码，不在当前生成链路调用。
- Windows BAT/VBS隐藏启动、停止整个Python进程树、重复启动保护、日志及重建入口。
- Dockerfile + Compose（PostgreSQL、迁移、Web、Worker、卷、健康检查、11分钟停止宽限）。

## 当前运行
- Windows启动器已启动干净业务实例：http://127.0.0.1:8000 。data/ 内商品、项目、任务均为空；管理员初始化状态已设置，保留现状，不重置密码。
- 当前 API/Worker 由 scripts/launcher.py 管理，logs/processes.json保存PID；使用stop.bat停止，start.bat或start.vbs启动。
- artifacts/smoke-data 是独立浏览器验收数据，不用于日常业务；模拟模型端点及临时后台测试服务均已停止。
- 当前未配置正式模型API Key。

## 验证结果
- Python pytest：41 passed；覆盖认证、CSRF、密钥加密、商品/图片、快照、策划到生成、并发防重复、版本、导出、中断、重试、无效请求、路径穿越、迁移和模型适配/排版。
- 前端 tsc -b 与 Vite生产构建通过。
- Chrome Playwright：录入配置/商品/参考图、策划确认、四图生成、改文字、单图重生、历史版本恢复、批量含底图下载，零pageerror；390px移动布局无横向溢出。
- 实际Windows VBS启动就绪，完整进程树停止和端口释放验证通过。
- 独立审查发现的路径穿越、代理限流绕过、旧任务重试、无效PATCH、启动器旧Worker遗留等问题已修。
- 唯一测试警告是上游Starlette对httpx TestClient的弃用提示，不影响当前测试。

## 未实测与明确限制
- 当前机器无Docker，未在真实Linux容器/PostgreSQL上启动；Compose仅静态解析。部署时执行README步骤并验证。
- 所有模型测试使用离线Mock或本机模拟服务；未调用真实付费模型。需接入用户服务商做真实参考图兼容性和商品还原验收。
- 生图仅同步OpenAI images接口，不支持返回task_id的异步服务商，后续按实际供应商加适配。
- 纯背景仅生成场景，不自动合成真实商品；暂未做自动抠图、S3存储实现或自由画布排版。
- 默认单管理员，不含团队权限、TikTok自动发布、批量跨商品创建和价格覆盖等后续能力。
- 历史商品参考图和旧渲染文件保留，暂未提供垃圾清理；需要定期备份数据库、图片和SECRET_KEY。

## 本次增量：目标市场与语言联动
- 新建图文项目的目标市场由 datalist 改为原生 select，明确展示 US/UK/AU/CA/MY/ID/TH/PH/VN/SG/JP 共11个国家。
- 国家切换时自动填入对应语言，包括美/英/澳/加拿大英语、马来语、印尼语、泰语、菲律宾语、越南语、新加坡英语和日语；仍可手动修改内容语言，再切国家时重置为新国家默认语言。
- 市场按中文国家名、语言按明确地区/语言描述提交，沿用现有后端协议，无需数据库迁移。
- 验证：tsc/Vite构建通过；真实Chrome逐项验证11国联动、初始默认、手动覆盖、再次切国和请求负载，零页面错误；浏览器验收拦截API请求，未更改实际商品数据或调用模型。
- 前端构建已更新，本机8000页面刷新即可加载。

## 本次修复：生图网络、语言下拉和配色
- 已复现真实生图失败根因：本机NO_PROXY包含IPv6 [::1]，HTTPX在初始化环境代理路由时抛出InvalidURL: Invalid port ':1]'，尚未向生图接口提交请求。
- 统一模型请求与图片下载的网络选项：按目标地址显式选择环境代理，遵循NO_PROXY，回环地址直连；不修改进程环境，不关闭外网代理；无效代理返回脱敏中文提示。
- 内容语言改为真正的select（15选项），保留11国默认联动和手动改选。
- 重设高对比度浅色配色：海军蓝正文、灰蓝画布、白卡、皇家蓝主色、深绿/红/琥珀状态；辅助文字加深，最小12px，禁用状态不再整体降低透明度。
- 验证：47项pytest通过；tsc/Vite构建通过；实际生图服务只读GET /models返回200，无收费生图请求；Chrome验证11国/15语言、改选和提交字段、移动端无横向溢出，抽查表单文字最低6.31:1。
- API和Worker在无排队/运行任务时通过启动器重启，已加载修复；旧失败任务没有自动重试，用户可点击生成未完成图片。

## 本次优化：精简页面顶部与右上角标记
- 移除各页面顶部重复的大标题横幅（.page-title，包括 TK STUDIO / WORKSPACE 及说明段落），为商品卡片、图文列表和详情页释放出 140px+ 的垂直可视高度。
- 移除顶部导航栏右上角的环境标记标签（.environment，即 `• SQLite 开发环境` 标签），保持顶栏清爽。
- 增强 Studio 中 project.tags 缺省时的安全兜底，避免历史或测试记录标签为空时触发渲染异常。
- 验证：前端 `tsc -b` 及生产构建通过；真实 Chrome 自动化测试确认所有页面大标题与右上角标记已彻底移除，零控制台报错；后端 47 项集成测试持续全部通过。

## 本次重构：AI完整设计简报与原生图中文字
- 替换旧“Worker拼接原始商品字典+无字底图+Pillow叠字”流程。分析模型按整套销售叙事输出共享视觉方向及每图准确title/body与完整自然语言prompt，生图端原样执行prompt。
- prompt包含逐字目标语言文案、字体层级/对比/移动安全区、商品与场景布局、真实卖点，明确不得复制原始资料dump或伪造参数。真实包装Logo可保留。
- 首次生成直接使用策划；单图重生（含空说明）、草稿变更、旧项目或模式变化先由分析模型结合参考图修订完整prompt，保留指定文案。最终prompt在生图前持久化；失败重试上下文一致时复用，避免重复分析。
- 不再后期叠字/裁切，保留模型成品原尺寸PNG及JPEG。Version保存实际prompt、title/body、native_text、style等，恢复直接用历史文件及记录文案。
- 前端“改文字”改为免费保存草稿→AI生成新版（分析+生图费用），显示待重新生成，查看每版本实际prompt，导出模型原图不再宣称无字底图。
- 老图保留，旧无字/叠字提示词下一次生成自动升级，不需删除商品或项目。JSON文档扩展，无数据库表结构迁移。
- 验证：84项pytest通过（新增准确prompt直传、像素无叠字/裁切、旧项目升级、重试复用、空说明修订、风格变化版本恢复等）；tsc/Vite构建通过；Chrome模拟API验证草稿/付费生成两步、版本prompt可见、旧图保持，零脚本错误。
- 本次未调用真实付费模型；正式文字拼写与商品还原效果需用户在新流程中验收。

## 本次扩展：抽象为 Agent Skill 与独立 CLI 自动化生成管道
- 抽象并落地系统级 Skill：`tiktok-carousel-generator`，已注册至 `.agents/skills` 与 `magpie/library/skills`。
- 新增独立命令行自动化脚本：`scripts/generate_carousel.py`，支持无 UI 模式下由 Agent 自动化驱动完整链路（分析策划 -> 原生文字提示词 -> 并发生图 -> 文件与文案归档）。
- 支持 `--plan-only` 预审策划与 `--refine-slide` 单图微调，自动复用本地模型配置，提供标准 JSON stdout 输出供 Agent 结构化读取。
- 增强 providers 的 JSON 容错保护：自动识别并剥离模型偶然返回的 markdown 代码块包裹（```json ... ```）。
- 验证：84 项 pytest 持续全绿；真实调用本地 analysis 模型实测 `--plan-only` 策划输出与 `--refine-slide` 单图 Prompt 微调均顺利成功。

## 本次优化：Skill 自包含便携化与跨平台打包支持
- 将 `tiktok-carousel-generator` 彻底重构为独立便携包：包含 `SKILL.md`、`generate_carousel.py`、`providers.py`、`requirements.txt`、`.env.example` 和 `README.md`。
- 消除任何对特定项目路径或外部数据库的硬依赖：同事获取该文件夹后，仅需安装 `requirements.txt` 并配置 `.env` 即可由 Agent 或命令行独立运行。在当前机器上仍能无缝复用本地既有配置。
- 增强 Windows 控制台编码保护：自动重定向 stdout/stderr 为 UTF-8，彻底解决多语言（日/泰/越语等）在 Windows GBK 控制台下的编码崩溃问题。
- 代码库归档：在项目根目录同步维护 `skills/tiktok-carousel-generator`，方便用户直接打包压缩或推送到 GitHub 供团队下载使用；同时已同步注册至 `~/.agents/skills` 与 `~/.config/magpie/library/skills`。
- 验证：84 项 pytest 持续全绿；实测从全局 Skill 目录直接运行便携版脚本（日本市场策划）成功输出地道日语原生文字设计简报，JSON 结构完整，无控制台编码异常。

## 当前 Skill：Agent 原生零配置版（取代上述 API/CLI 分享方式）
- 用户要求直接复用 Agent 自身模型分析/策划，调用会话已有生图工具，不再单独配置Key/模型或安装运行环境。
- 分享目录 skills/tiktok-carousel-generator 仅4文件：SKILL.md、README.md、references/design-guide.md、templates/plan.example.json。旧generate_carousel.py、providers.py、requirements.txt、.env.example已从分享目录及本机安装副本移除。
- 新规范包含11国默认语言、逐页完整含文字提示词、参考图传递、现有工具能力映射、异步任务收取、单图版本留存和交付归档。仅策划时不调用生图，缺少工具时如实交付已完成策划，不索取Key或读取宿主密钥。
- Web项目及scripts目录中的旧CLI不作为Skill前提；本次未修改Web业务代码。
- 已同步.agents安装目录和magpie库；.dsh技能路径为magpie库符号链接，当前宿主已识别新描述。
- 校验通过：4文件清单、相对引用、11国映射、JSON模板、3个可见安装路径字节一致；ZIP白名单仅4文件，无密钥或配置。独立审查纸面推演六图生成/单图重生/仅策划流程通过，未调用收费生图。
- 分享包 artifacts/tiktok-carousel-generator-agent-native.zip 已生成；源目录随Git推送，临时ZIP由本机会话交付。
- 现有后端84项测试通过，前端类型检查和构建通过；本次未作实际商品出图效果验收。

## 下一步
1. 用户在模型设置输入实际服务商地址/模型/Key，用真实商品完成质量验收。
2. 基于品类加入真实商品抠图合成与更多版式/输出比例。
3. 服务器就绪后验证Docker/PostgreSQL、HTTPS反代和持久化备份恢复。
