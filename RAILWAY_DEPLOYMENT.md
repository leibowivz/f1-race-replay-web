# Railway 部署指南

## 优化配置

### 1. 自动休眠（省钱）
- **配置**: `railway.json` 中 `sleepAfterInactivity: "5m"`
- **效果**: 5 分钟无访问自动休眠，不计费
- **唤醒**: 访问时自动唤醒（15-30 秒）

### 2. Volume 持久化缓存（推荐）
**为什么需要 Volume：**
- Railway 容器重启会清空 `/tmp`
- 比赛数据需要重新下载（每场 200-500MB）
- Volume 可以持久化缓存，第二次访问秒开

**配置步骤：**
1. Railway Dashboard → Service → Variables
2. 添加 Volume：
   - Mount Path: `/app/cache`
   - Size: 2-5 GB
3. 添加环境变量：
   ```
   CACHE_DIR=/app/cache
   ```

### 3. 环境变量

必需：
```env
PORT=5000  # Railway 会自动设置
```

可选：
```env
CACHE_DIR=/app/cache  # 使用 Volume 时设置
RAILWAY_ENVIRONMENT=production  # Railway 自动设置
```

## 成本估算

### 偶尔访问（月使用 30 小时）
- RAM: 512MB → $0.21
- CPU: 0.3 vCPU → $0.17
- 网络: 2GB → $0.10
- **总计: $0.48**
- **实际账单: $5**（在额度内）

### 中等使用（月使用 100 小时）
- RAM: 512MB → $0.70
- CPU: 0.4 vCPU → $0.60
- 网络: 4GB → $0.20
- **总计: $1.50**
- **实际账单: $5**（在额度内）

## 部署步骤

### 方案 A: Railway CLI（推荐）
```bash
cd f1-race-replay-web

# 1. 确认登录
railway whoami

# 2. 链接项目
railway link

# 3. 创建服务（如果还没有）
railway service

# 4. 添加 Volume（可选但推荐）
# 在 Railway Dashboard 手动添加，或：
railway volume create --size 2

# 5. 部署
railway up

# 6. 查看日志
railway logs
```

### 方案 B: GitHub 自动部署
1. 推送代码到 GitHub
2. Railway Dashboard → New Project → From GitHub
3. 选择 `leibowivz/f1-race-replay-web`
4. 添加 Volume（可选）
5. 自动部署

## 优化建议

### 1. 限制资源使用
```bash
# Railway Dashboard → Service → Settings
Memory: 512 MB
CPU: 0.5 vCPU
```

### 2. 预处理热门比赛（高级）
```bash
# 本地处理好数据
python preload_races.py

# 上传到 Volume（需要用 railway volume 命令或 API）
```

### 3. 监控成本
- Railway Dashboard → Usage
- 设置预算告警
- 查看实时资源消耗

## 验证部署

1. Railway 会提供一个 URL：`https://xxx.railway.app`
2. 访问 URL 测试：
   - 首次访问可能需要 15-30 秒唤醒
   - 选择比赛，首次加载 30-60 秒（下载数据）
   - 后续访问应该很快（缓存命中）

## 故障排查

### 服务无法启动
```bash
railway logs
# 检查错误信息
```

### 缓存不工作
1. 检查 Volume 是否挂载：`railway service`
2. 检查 CACHE_DIR 环境变量
3. 查看日志中的 "Cache directory" 输出

### 成本过高
1. 确认自动休眠已启用
2. 检查是否有意外流量
3. 限制资源使用（Memory/CPU）

## 对比本地部署

| 特性 | 本地 + Cloudflare | Railway 休眠 |
|-----|------------------|-------------|
| 成本 | 免费 | $5/月 |
| 可用性 | Mac mini 必须开机 | 随时可用 |
| 缓存 | 持久化 | Volume 持久化 |
| 冷启动 | 无 | 15-30 秒 |
| 维护 | 手动 | 自动 |
| 域名 | Cloudflare 临时 | Railway 永久 |

**推荐：**
- 只有你用 → 本地部署
- 有朋友偶尔访问 → Railway 休眠
- 经常使用 → Railway + Volume
