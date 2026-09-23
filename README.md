# Laya Server

独立的 Laya System One HTTP 服务和单管理员控制台。后端使用 FastAPI + SQLite，前端使用 React + Vite + TypeScript 与 shadcn/ui；构建后由一个应用容器提供网页和 API。

## 上游源码

本仓库不跟踪 Laya 源码。构建前在仓库根目录检出固定的 v0.3.7 版本：

```sh
git clone https://github.com/NandhaKishorM/laya.git laya
git -C laya checkout --detach 010bacef009c855ccba814b51f7c8e1d38ab5e3f
sh scripts/check-upstream.sh
```

`laya/` 已加入 `.gitignore`，但会进入 Docker 构建上下文。Dockerfile 验证完整 SHA 和干净工作区，最终镜像只包含运行所需的上游包和许可证，不包含 `.git`。

## 管理员与配置

在 `.env` 中设置 `LAYA_ADMIN_USERNAME` 和至少 10 个字符的 `LAYA_ADMIN_PASSWORD`，服务启动时会在内存中生成 Argon2id 哈希用于登录校验。也可以不设置明文密码，改用 `.venv/bin/python scripts/hash-password.py` 生成 `LAYA_ADMIN_PASSWORD_HASH`；两者必须且只能设置一个。哈希值用单引号包住，确保 Docker Compose 按字面保留 `$`。`LAYA_PUBLIC_ORIGIN` 也必须填写；生产环境必须是 HTTPS 来源，例如 `https://console.example.com`。本地 HTTP 测试需要 `LAYA_ALLOW_INSECURE_LOCAL=1`。`.env` 已被 Git 忽略，不要提交实际密码。

```sh
cp .env.example .env
python3.12 -m venv .venv
.venv/bin/python -m pip install -e 'backend[test]'
# 编辑 .env，填写 LAYA_ADMIN_USERNAME 和 LAYA_ADMIN_PASSWORD
```

## 模型文件

模型权重不随仓库和镜像分发。`scripts/download-models.py` 将 Hugging Face 仓库固定在提交 `1c5edc17a7acd8701df6fc341c0d179f1c62c982`，把三个 checkpoint 放到持久化模型卷的 `/models/english`、`/models/multilingual`、`/models/typed-decisions`。每个目录至少要有上游模型包里的 `rl_agent_config.json`、`model.safetensors`、`tokenizer/` 和 `encoder/`。文件存在性可通过 `GET /health/ready` 检查；缺失时推理返回 `503 MODEL_UNAVAILABLE`。实际模型是否兼容仍需做推理冒烟测试。

本项目的模型推理不在应用启动时自动下载；请在启动前准备模型卷。一个应用进程只加载所需模型，默认最多驻留一个，可用 `LAYA_MAX_LOADED_MODELS` 调整；该值控制模型缓存数量，不限制同时处理的请求数。服务不设置额外的推理并发槽位；实际并发能力取决于运行时线程池、模型和机器资源。CPU 推理镜像使用 PyTorch CPU wheel；若部署 GPU，需按设备改用相应 PyTorch 基础环境并验收。

本地先安装上游运行依赖与被忽略的 Laya 检出，再下载三个固定版本模型，运行包含英文、中文显式选型、中文自动路由和 typed-decisions 的真实请求冒烟测试：

```sh
.venv/bin/python -m pip install torch==2.5.1 transformers==4.48.3 safetensors==0.5.3 huggingface-hub==0.29.3 numpy==1.26.4
.venv/bin/python -m pip install --no-deps -e ./laya
LAYA_MODEL_DIR=models .venv/bin/python scripts/download-models.py --model english
LAYA_MODEL_DIR=models .venv/bin/python scripts/download-models.py --model multilingual
LAYA_MODEL_DIR=models .venv/bin/python scripts/download-models.py --model typed-decisions
LAYA_MODEL_DIR=models .venv/bin/python scripts/smoke-real-model.py
```

模型下载与运行依赖上游的 PyTorch、Transformers、Safetensors、Hugging Face Hub 和 NumPy。

## 启动

首次启动前，先构建镜像并将固定版本模型下载到模型卷，然后启动应用：

```sh
docker compose build
docker compose run --rm app python /app/scripts/download-models.py
docker compose up -d
```

Compose 只启动一个应用服务并将 `127.0.0.1:8080` 暴露给宿主机。公网入口需由外部反向代理提供 HTTPS，并将请求转发到该端口。SQLite 数据在 `laya-data` 卷，模型在 `laya-models` 卷。构建机器需要能访问 PyPI、PyTorch CPU 包索引和 npm registry；已构建镜像启动时无需拉取源码或依赖。

如果由现有的 1Panel 反向代理提供公网 HTTPS，将域名请求转发到宿主机的 `127.0.0.1:8080`，并确保 `LAYA_PUBLIC_ORIGIN` 与实际 HTTPS 域名一致。反向代理不属于本项目的应用容器。

### 本地开发（热更新）

第一次先执行 `cp .env.example .env`，将 `.env` 中的 `LAYA_ADMIN_USERNAME` 和 `LAYA_ADMIN_PASSWORD` 填写好。若使用哈希配置，则将 `LAYA_ADMIN_PASSWORD` 留空并填写 `LAYA_ADMIN_PASSWORD_HASH='...'`（保留单引号）。`scripts/dev-backend.sh` 会把本地来源、SQLite 路径和模型路径设为开发值。确保上面的 Python/前端依赖与三个模型已经准备好。

分别打开两个终端，在仓库根目录运行：

```sh
# 终端 1：FastAPI 与 SQLite
sh scripts/dev-backend.sh
```

```sh
# 终端 2：React/Vite
cd frontend
pnpm dev
```

打开 `http://127.0.0.1:5173` 登录。Vite 将 `/internal` 和 `/v1` 代理到本地 8000 端口；生产环境仍由同一个 FastAPI 容器提供构建后的前端。若只想用一个本地进程，可先在 `frontend/` 运行 `pnpm build`，再把 `LAYA_PUBLIC_ORIGIN` 设为 `http://127.0.0.1:8000` 启动 Uvicorn 并打开 8000 端口。

控制台支持简体中文、English 和繁體中文。登录页及登录后的顶部栏均可切换语言；首次访问按浏览器语言选择，手动选择会保存在当前浏览器中。

## 调用接口

登录控制台后在 **API Keys** 页面创建密钥。完整密钥只在创建响应中显示一次。

```sh
curl -X POST https://console.example.com/v1/systemone \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"state":{"message":"I was charged twice"},"questions":{"refund":{"type":"noul","instructions":"Does the customer ask for a refund?"}}}'
```

请求中的 `state` 可为字符串、JSON 对象或数组；`questions` 是非空问题 ID 映射，支持 `noul`、`choice` 和 `score`；`model` 可选 `auto`（默认）、`english`、`multilingual` 或 `typed-decisions`。返回保留上游 `answers`、`model` 和 `usage`。错误使用 `detail.code` 和 `detail.message`。无效密钥为 401，校验失败为 422，模型不可用为 503。控制台 Playground 使用管理员会话，记录为单独用量来源。

## 数据与维护

SQLite 开启 WAL 模式；备份时应先停止应用，再复制数据库文件或使用 SQLite backup API，避免遗漏 WAL 中的数据。恢复时停止应用，替换持久化卷内的数据库，再启动。升级 Laya 时更新 `scripts/check-upstream.sh` 和 Dockerfile 中的完整 SHA，重新检出 `laya/`，运行测试并做真实模型冒烟测试。

```sh
.venv/bin/python -m pytest backend/tests -q
git ls-files laya/
```

第二条命令应无输出。

部署完成后，建议先访问 `GET /health/ready` 确认模型文件已就绪，再登录控制台通过 Playground 发起一次测试请求，检查实际推理和响应是否正常。
