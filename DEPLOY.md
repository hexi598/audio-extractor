# 视频音频提取 - 云端部署指南

把「视频音频提取」部署到云端，手机浏览器打开就能用，还可以"添加到主屏幕"像原生 App 一样使用。

---

## 方案一：Render 一键部署（推荐）

Render 有免费套餐，不需要绑定信用卡，支持 Docker 自动部署。

### 步骤

1. **把项目上传到 GitHub**
   - 在 GitHub 创建新仓库（如 `audio-extractor`）
   - 把整个项目文件夹推送上去：
     ```bash
     git init
     git add .
     git commit -m "init: audio extractor cloud version"
     git remote add origin https://github.com/你的用户名/audio-extractor.git
     git push -u origin main
     ```

2. **注册 Render**
   - 打开 [render.com](https://render.com)
   - 点击 `Sign Up`，用 GitHub 账号注册

3. **创建 Web Service**
   - 点击 `New +` → `Web Service`
   - 选择你刚上传的 GitHub 仓库
   - Render 会自动识别 `render.yaml`（Blueprint 部署）
   - 或者手动配置：
     - **Name**: `audio-extractor`（任意）
     - **Environment**: `Docker`
     - **Region**: `Singapore`（东南亚，对国内访问快）
     - **Plan**: `Free`
     - **Health Check Path**: `/api/health`

4. **等待部署完成**
   - 首次部署约 3-5 分钟（需要下载 Python 镜像 + 安装依赖）
   - 完成后你会得到一个类似 `https://audio-extractor.onrender.com` 的地址

5. **在手机上使用**
   - 用手机浏览器打开上面的地址
   - 粘贴视频链接，提取音频
   - **安装到桌面**：Chrome 菜单 → "添加到主屏幕"（这就是 PWA，可离线打开）

---

## 方案二：自行部署（VPS / Oracle Always Free）

如果你有自己的服务器或 Oracle Cloud 免费 ARM 实例（4核 24GB，永久免费）：

```bash
# 1. 安装 Docker
curl -fsSL https://get.docker.com | bash

# 2. 克隆项目
git clone https://github.com/你的用户名/audio-extractor.git
cd audio-extractor

# 3. 构建镜像
docker build -t audio-extractor .

# 4. 运行（映射到 80 端口）
docker run -d -p 80:10000 --restart unless-stopped audio-extractor

# 5. 配置 HTTPS（可选，但 PWA 需要 HTTPS）
# 使用 nginx + certbot，或者 Cloudflare Tunnel
```

---

## 环境变量参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | 10000 | 服务端口（Render 自动注入） |
| `DOWNLOAD_DIR` | `/tmp/audio-extractor-downloads` | 音频文件存储目录 |
| `FILE_MAX_AGE` | 1800 | 文件保留时间（秒），超时自动清理 |
| `MAX_CONCURRENT_TASKS` | 2 | 同时处理的最大任务数 |
| `FFMPEG_PATH` | 自动查找 | 手动指定 ffmpeg 路径 |
| `YTDLP_PATH` | 自动查找 | 手动指定 yt-dlp 路径 |

---

## 免费层限制

Render 免费层：
- **512 MB RAM**：适合提取 3-10 分钟的普通视频音频，超大视频（1小时+ FLAC）可能超内存
- **15 分钟无访问自动休眠**：休眠后首次访问需要等待约 30 秒冷启动
- **每月 750 小时**：够 24/7 运行一个月（单实例刚好全覆盖）
- **单个 Worker**：同时只能处理一个提取任务

如果不够用，可以考虑：
- **Oracle Cloud Always Free**：4核 ARM，24GB RAM，永不休眠，完全免费但需要信用卡注册
- **Koyeb**：免费层 512MB，在 Frankfurt 有节点

---

## 本地测试

在部署到云端前，可以先在本地用 Docker 测试：

```bash
# 构建
docker build -t audio-extractor .

# 运行（访问 http://localhost:5000）
docker run -p 5000:10000 audio-extractor

# 测试健康检查
curl http://localhost:5000/api/health
```

---

## 常见问题

**Q: 部署后手机打不开？**
A: 检查 Render Dashboard 的 Logs，确认服务已成功启动。确认 URL 是 `https://` 开头（不是 `http://`）。

**Q: PWA 安装失败？**
A: PWA 要求 HTTPS。Render 自动提供 HTTPS 证书，确保用 `https://` 访问。

**Q: 提取 B 站视频失败？**
A: B 站 API 可能更新了 WBI 签名机制。如果失效，需要更新 `bilibili_api.py` 中的 `MIXIN_KEY_ENC_TAB`。

**Q: 文件下载后找不到了？**
A: 文件会在 30 分钟后自动清理。下载后请及时保存到手机本地。

**Q: 能提取 YouTube 吗？**
A: 可以。yt-dlp 支持数千个网站。但如果 Render 的 IP 被 YouTube 限制，可能需要配置 Cookie 或换个平台。

**Q: 想要更多并发任务？**
A: 修改 `MAX_CONCURRENT_TASKS` 环境变量。免费层建议不要超过 2。
