English | <a href="README.zh-CN.md">简体中文</a>

<p align="center"><img src="frontend/public/laya-server-logo-black.png" alt="LAYA SERVER" width="120" /></p>

<h1 align="center">LAYA SERVER</h1>

LAYA SERVER is a self-hosted API and web interface for Laya's structured decision models, compatible with the TypeSafe Jev API format. It packages the System One inference capabilities of [upstream Laya](https://github.com/NandhaKishorM/laya) as a standalone service, making them easier to deploy and use in your applications.

## Quick Start

Once the image is published, install Docker and run the following command. Replace `latest` with a version tag to pin a release.

```sh
docker run -d --name laya-server --init --restart unless-stopped \
  -p 8080:8080 \
  -v laya-data:/data \
  -e LAYA_ADMIN_USERNAME=admin \
  -e LAYA_ADMIN_PASSWORD='change-this-admin-password' \
  1panel/laya-server:latest
```

Replace the sample password with your own, then sign in at `http://YOUR_SERVER_IP:8080`. Create a key on the **API Keys** page; the full key is shown only once. `/health/ready` checks the model files. Data is stored in the `laya-data` volume.

`YOUR_SERVER_IP` is your server's IP address. To use a domain name, configure HTTPS on a reverse proxy and forward requests to port 8080 on the server.

## Call the API

```sh
curl -X POST http://YOUR_SERVER_IP:8080/v1/systemone \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"state":{"message":"I was charged twice"},"questions":{"refund":{"type":"noul","instructions":"Does the customer ask for a refund?"}}}'
```

Successful responses include `answers`, `model`, and actual token counts in `usage`. The published image includes the multilingual model; `model=auto` (the default) and `model=multilingual` are available. See **Documentation** in the console for more request examples.

## License and Feedback

This project is licensed under [Apache License 2.0](LICENSE). For issues and suggestions, visit [GitHub Issues](https://github.com/1Panel-dev/laya-server/issues).
