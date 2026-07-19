# 书童AI 项目 · 代理操作须知

> 本文档供 OpenCode / 其他自动化代理阅读，记录本项目的部署结构、访问限制和变更铁律。

---

## 一、访问限制（重要）

### 1.1 生产服务器 SSH 访问

- **大陆主站**：`114.55.9.27`（阿里云 ECS）
- **香港节点**：`8.217.246.219`（阿里云 ECS）
- **访问方式**：本代理持有 SSH 密钥，可直接登录生产服务器。
  - 大陆主站：`ssh -i 01-配置区/.ssh/bookboy-cloud.pem bookboy@114.55.9.27`
  - 香港节点：`ssh -i 01-配置区/.ssh/bookboy-hk-key.pem bookboy@8.217.246.219`

> ⚠️ 拥有权限不等于可以随意操作。**做任何可能破坏服务的操作前，必须先确认能回滚或已取得用户授权。**

### 1.2 本地开发机有 VPN 拦截

- 本机存在 `utun7` 隧道（`198.18.0.0/15`），DNS 和 HTTP 流量会被本地 VPN/代理拦截。
- `dig`、`curl` 等本地命令测出来的路由、IP、响应头**不代表真实用户体验**。
- 验证 DNS 路由请用 DoH（Google / DNSPod / AliDNS），或让用户从目标网络实测。

---

## 二、部署结构

```
大陆主站 114.55.9.27
  └── /opt/bookboy-cloud/
      ├── cloud_server.py          # Supervisor 运行的入口文件
      ├── 06-对接区/
      │   ├── cloud_server.py      # 源码副本
      │   └── 前端页面/            # 师父控制台、家庭端等 HTML
      ├── 03-引擎区/
      └── 云端数据区/              # 运行时数据：accounts.db、subscriptions.json、家庭数据

香港节点 8.217.246.219
  └── Nginx 反向代理回 114.55.9.27
```

### 关键文件

| 文件 | 作用 |
|------|------|
| `/opt/bookboy-cloud/cloud_server.py` | 生产入口，Supervisor 直接运行它 |
| `/opt/bookboy-cloud/云端数据区/accounts.db` | 账号数据库 |
| `/opt/bookboy-cloud/06-对接区/前端页面/` | 前端页面目录 |
| `/etc/nginx/sites-enabled/*` | Nginx 反向代理配置 |
| `/etc/supervisor/conf.d/bookboy-cloud.conf` | Supervisor 配置 |

### 已知历史 bug

`cloud_server.py` 中 `_find_project_root()` 曾错误地把 `/opt` 当成项目根，导致数据库和页面目录找错。已在源码修复：优先检查 `cloud_server.py` 所在目录是否包含 `03-引擎区`。

---

## 三、变更铁律

1. **工作时间不折腾基础设施**：DNS、负载均衡、SSL、服务器部署等变更，必须在用户明确同意且确认有回滚方案后进行。
2. **先备份再改数据库**：accounts.db、subscriptions.json、家庭数据等不可随意删除或覆盖。
3. **DNS 改动必须可回滚**：修改前先记录原记录，准备好恢复命令。
4. **改完必须验证真实用户路径**：不能只看本机 curl，要让用户从目标网络实测。
5. **不改不动的东西**：不要为修 A 问题去动 B 配置。
6. **SSH 上不去自己多试**：换用户、端口、密钥、清 known_hosts，确认不行再汇报。

---

## 四、当前运行状态（由代理维护）

- `bookkidai.com` DNS 通过 **Cloudflare Load Balancer** 智能分流：
  - 中国大陆用户 → `114.55.9.27`（大陆主站）
  - 海外用户（含台湾、东南亚） → `8.217.246.219`（香港 Nginx 反向代理回大陆）
- 两池健康检查均正常。
- 根目录定位 bug 已修复，`cloud_server.py` 能正确识别 `/opt/bookboy-cloud` 为项目根。
