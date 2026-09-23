<a href="README.md">English</a> | 简体中文

<p align="center"><img src="frontend/public/laya-server-logo-black.png" alt="LAYA SERVER" width="120" /></p>

<h1 align="center">LAYA SERVER</h1>

LAYA SERVER 是 Laya 结构化决策模型的自托管 API 与 Web 界面，兼容 TypeSafe Jev API 格式。它将[上游 Laya](https://github.com/NandhaKishorM/laya) 的 System One 推理能力封装为独立服务，方便开发者在自己的应用中部署和使用。

## 快速开始

镜像发布后，安装 Docker 并运行（如需固定版本，将 `latest` 换成对应标签）：

```sh
docker run -d --name laya-server --init --restart unless-stopped \
  -p 8080:8080 \
  -v laya-data:/data \
  -e LAYA_ADMIN_USERNAME=admin \
  -e LAYA_ADMIN_PASSWORD='change-this-admin-password' \
  1panel/laya-server:latest
```

将示例密码换成自己的密码，访问 `http://YOUR_SERVER_IP:8080` 登录，在 **API Keys** 页面创建密钥；完整密钥只显示一次。`/health/ready` 可用于检查模型文件。数据保存在 `laya-data` 卷中。

`YOUR_SERVER_IP` 是服务器 IP。若通过域名访问，可在反向代理上配置 HTTPS 并转发到服务器的 8080 端口。

## 调用 API

```sh
curl -X POST http://YOUR_SERVER_IP:8080/v1/systemone \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"state":{"message":"I was charged twice"},"questions":{"refund":{"type":"noul","instructions":"Does the customer ask for a refund?"}}}'
```

成功响应包含 `answers`、`model` 和实际的 `usage` token 计数。发布镜像内置 multilingual 模型；`model=auto`（默认）和 `model=multilingual` 均可使用。更多请求格式见控制台 **Documentation** 页面。

## 许可与反馈

本项目采用 [Apache License 2.0](LICENSE) 许可证。问题和建议请提交至 [GitHub Issues](https://github.com/1Panel-dev/laya-server/issues)。
