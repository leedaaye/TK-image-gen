# TK 图文工作台

面向服务器部署的 TikTok 带货图文 Web 应用。Windows 提供开发测试启动器；正式部署使用 Linux + Docker Compose。默认单管理员账号，所有商品资料和图片保存在自己的服务器，调用模型时会将选定商品资料及参考图片发送给配置的服务商。

## 已实现

- 商品库：描述、SKU、价格/币种、卖点、约束、多角度参考图片、角色标注、归档。
- 生成项目：商品快照、目标市场/语言、4–10张、统一风格、策划确认或自动生成。
- OpenAI 兼容接口：分析模型和生图模型分开配置；密钥服务端加密保存，读取接口不返回明文。
- 后台任务：独立 Worker、持久化队列、并发控制、逐图失败重试、服务重启中断识别。
- 内容编辑：修改策划、标题和正文；本地叠字，不额外调用生图模型。
- 版本管理：单图修改要求、独立重生成、选择历史版本。
- 导出：单张保存、勾选下载/整套 ZIP、可附无字底图、发布文案和策划 JSON。
- 管理员登录、文件鉴权、Windows 隐藏启动和服务器部署文件。

## Windows 本机测试

准备 Python 3.11+（推荐3.12）和 Node.js 22 LTS，安装时启用 PATH。首次初始化需要网络安装依赖。

1. 首次双击 `setup.bat`。它创建 `.venv`、安装依赖、构建前端、迁移数据库、启动 API 和 Worker、打开浏览器。首次可能需要数分钟，不会常驻 CMD 窗口。过程与错误查看 `logs/launcher.log`。
2. 后续双击 `start.bat`，默认地址 `http://127.0.0.1:8000`。直接双击 `start.vbs` 可以避免 BAT 的瞬间黑窗。
3. 首次访问设置管理员密码（至少10字符）。若 `.env` 已配置 `ADMIN_PASSWORD`，直接使用该密码登录，网页不会再次要求初始化。
4. 模型设置中保存分析/生图的 Base URL、模型名和 Key，再进入商品库录入商品并上传参考图。
5. 修改源代码后，先双击 `stop.bat`，再双击 `rebuild.bat` 重新构建并启动。后端变更也需要重启。
6. 停止使用时双击 `stop.bat`，网页关闭不停止后台任务。

Windows 未配置 `DATABASE_URL` 时使用 `data/app.db`（SQLite 开发替代）。生产默认 PostgreSQL。需要本机使用 PostgreSQL 时，在根目录 `.env` 中设置 `DATABASE_URL=postgresql+psycopg://用户:密码@地址:5432/数据库`。请保持 API 和 Worker 的环境配置一致。

启动器读取根 `.env`。如果系统 Node/npm 不可用，可以配置 `TK_NODE`（node.exe绝对路径）与 `TK_PNPM`（pnpm.mjs绝对路径）。启动器不安装系统级工具。

### 显示日志调试

在两个终端分别执行：

```powershell
# 终端1（项目根目录）
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload

# 终端2
Set-Location backend
..\.venv\Scripts\python.exe -m app.worker
```

这些手动命令使用终端的环境变量，不会自动读取根 `.env`；需自行设置 DATABASE_URL/DATA_DIR/SECRET_KEY，或使用启动器。前端热更新可在 frontend 中执行 `npm run dev`，默认 Vite 页面代理 `/api` 到 8000。

## 模型接口约定

Base URL 填 API 根地址，通常以 `/v1` 结束，示例 `https://api.openai.com/v1`。

- 分析：`POST /chat/completions`，需要图像输入（存在参考图时）与 `response_format: {type: "json_object"}`。普通纯文本连通测试不能证明视觉能力，需要用实际商品验证。
- 参考图生图：`POST /images/edits`，multipart 的 `image[]` 字段，支持多张商品参考图。不会静默退回无参考生成。
- 纯背景：`POST /images/generations`，不发送商品参考图，只生成场景底图；此模式不会自动抠图合成商品，不建议直接当商品成片发布。
- 返回支持 `data[0].b64_json` 或 `data[0].url`。不支持异步任务 ID 轮询式服务商，接入该类服务需新增适配器。
- extra 为 JSON 对象，可填写供应商支持的 `size`、`quality` 等参数；不能覆盖模型、提示词、认证和参考图等核心字段。
- 生图连接测试会真实请求模型并可能产生费用。工具不提供虚构的费用估算。

参考图仅使用主参考与细节参考（最多6张）；场景参考保存在商品库，不作为商品外观输入。修改商品不会改变历史项目的商品快照。API Key 更新为空表示保留，勾选清除才删除。

参考图生成依赖模型还原能力，发布前需要人工检查商品形状、Logo、颜色和细节。当前导出统一1080×1440（3:4），固定基础排版。高要求包装/数码产品建议后续加入真实商品抠图合成。阿拉伯文、复杂字形和罕见文字需另配合适字体并验证排版。

## Linux 服务器部署

准备 Docker Engine 与 Compose v2。

```bash
cp .env.example .env
# 编辑 .env 中数据库密码、SECRET_KEY、ADMIN_PASSWORD
# SECRET_KEY 至少32字符，可用 openssl rand -hex 32 生成
# 数据库密码使用随机字母数字，避免连接URL转义问题
docker compose up -d --build
```

- Compose 自动等待 PostgreSQL 健康、执行 Alembic 迁移，再启动 Web 和 Worker。
- 默认监听服务器 `127.0.0.1:8000`，适合通过 Nginx/Caddy 反向代理。通过域名 HTTPS 访问时设置 `COOKIE_SECURE=true`，代理保留 Host 并转发 `/api` 与其他页面请求，上传大小限制建议不小于 180MB。
- 临时局域网 HTTP 测试可设 `BIND_ADDRESS=0.0.0.0`、`COOKIE_SECURE=false`。
- `ADMIN_PASSWORD` 仅数据库首次初始化时生效，修改环境变量不重置已有密码。
- 单 Worker 进程内部按分析/生图配置分别控制并发；不要扩容 Worker 副本。跨进程锁通过共享 data 卷防止意外重复运行。
- 中断的 running 任务标记失败，等待人工确认后重试；目前不支持查询供应商端已完成但未返回的任务。Compose为模型请求提供11分钟停止宽限，更新时可能需要等待在途任务完成。
- 默认不信任客户端转发IP头；经反向代理访问时登录限流可能按代理来源共享，避免伪造IP绕过。
- `docker compose logs -f web worker` 查看日志；`docker compose ps` 检查状态。

### 更新和备份

```bash
docker compose build
docker compose stop web worker
docker compose run --rm migrate
docker compose up -d
```

更新前备份 PostgreSQL 与 `content` 卷。商品图片、版本、数据库、SECRET_KEY 必须一起保留；丢失 SECRET_KEY 将无法解密模型 Key。Windows 默认生成的 `data/.secret` 也要随 data 目录备份。历史引用图片不会因商品移除图片立即物理删除，当前不提供自动垃圾清理。

## 自动检查

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m compileall -q app ..\scripts
Set-Location ..\frontend
npm run build
```

测试使用隔离临时目录和模拟模型，不触碰实际商品数据、不调用付费接口。真实服务商连通、生图还原效果与服务器部署需要在配置相应环境后实测。
