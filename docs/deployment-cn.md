# 国内可访问部署说明

本项目是 Streamlit 服务端应用，不能用 GitHub Pages 这类静态站点部署。

## 推荐路径

1. 生产稳定访问：大陆云服务器或云托管，需完成 ICP 备案或使用平台提供的预备案子域名。
2. 快速演示：香港或新加坡区域容器服务，通常免备案，但大陆访问稳定性受跨境链路影响。

## 容器启动

镜像会读取平台注入的 `PORT`，没有注入时默认使用 `8501`。

本地推荐用 OrbStack 作为 Docker 引擎，统一走项目脚本：

```bash
./scripts/start_app.sh
./scripts/status_app.sh
./scripts/stop_app.sh
```

脚本会把本地 `.streamlit/uploaded_files/` 挂载到容器内 `/app/.streamlit/uploaded_files`，
因此刷新网页或重启容器后，已上传文件会继续保留。

手动 Docker 命令：

```bash
docker build -t retail-channel-ai-assistant .
docker run --rm -p 8501:8501 \
  -v "$PWD/.streamlit/uploaded_files:/app/.streamlit/uploaded_files" \
  retail-channel-ai-assistant
```

访问：

```text
http://127.0.0.1:8501/
```

## 云平台配置

通用配置：

- 构建方式：Dockerfile
- 启动端口：使用平台注入的 `PORT`，默认 `8501`
- 健康检查路径：`/_stcore/health`
- 持久化目录：如需保留网页上传文件，挂载 `/app/.streamlit/uploaded_files`
