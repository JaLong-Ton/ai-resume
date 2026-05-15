# AI 智能简历分析系统

基于 DeepSeek AI 的简历智能解析与岗位匹配系统。上传 PDF 简历，自动提取关键信息并计算与岗位需求的匹配度评分。

## 系统架构

```
┌──────────────────────────────────────────────────┐
│                    用户/浏览器                      │
│            https://jalong-ton.github.io           │
└──────────────────────┬───────────────────────────┘
                       │ HTTPS
┌──────────────────────▼───────────────────────────┐
│              GitHub Pages (docs/)                  │
│              index.html + CSS + JS                │
└──────────────────────┬───────────────────────────┘
                       │ API 调用
┌──────────────────────▼───────────────────────────┐
│      阿里云函数计算 FC (python3.10)                 │
│    https://resume-analyzer-xxx.fcapp.run          │
│                                                    │
│  ┌──────────────────────────────────────────────┐ │
│  │  mini.py — FC 事件适配器 (HTTP → WSGI)       │ │
│  │  app.py  — Flask 应用 + 业务逻辑              │ │
│  └──────────────────────────────────────────────┘ │
│                       │                            │
│         ┌─────────────┼─────────────┐             │
│         ▼             ▼             ▼             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ PyMuPDF  │  │  httpx   │  │  Flask   │  │  Redis   │ │
│  │ PDF 解析  │  │ LLM 调用  │  │ Web 框架  │  │  缓存    │ │
│  └──────────┘  └────┬─────┘  └──────────┘  └────┬─────┘ │
└──────────────────────┼───────────────────────────────────┘
                       │                    │
              ┌────────▼────────┐  ┌────────▼────────┐
              │  DeepSeek API    │  │  Upstash Redis   │
              │ deepseek-v4-pro  │  │  免费套餐         │
              └─────────────────┘  └─────────────────┘
```

## 技术选型

| 层级 | 技术 | 说明 |
|------|------|------|
| **后端框架** | Flask 3.x | WSGI 原生兼容 FC Python runtime |
| **PDF 解析** | PyMuPDF 1.27 | 支持多页 PDF，中文编码 |
| **AI 模型** | DeepSeek V4 Pro | 推理模型，中文语义理解精准 |
| **HTTP 客户端** | httpx | 轻量替代 openai SDK |
| **缓存** | Upstash Redis | 免费套餐，命中 <100ms |
| **后端部署** | 阿里云函数计算 FC (python3.10) | Serverless，按量付费 |
| **前端** | HTML + CSS + JS | 零框架，拖拽上传，响应式 |
| **前端部署** | GitHub Pages | 免费静态托管 |

## API 文档

Base URL: `https://resume-analyzer-spucnjlkdu.cn-hangzhou.fcapp.run`

### `GET /health`

健康检查。

```bash
curl https://resume-analyzer-spucnjlkdu.cn-hangzhou.fcapp.run/health
# {"status":"ok","version":"1.0.0"}
```

### `POST /api/upload`

上传 PDF 简历并提取结构化信息（不含岗位匹配）。

```bash
curl -X POST -F "file=@简历.pdf" \
  https://resume-analyzer-spucnjlkdu.cn-hangzhou.fcapp.run/api/upload
```

响应：

```json
{
  "success": true,
  "data": {
    "file_name": "简历.pdf",
    "parsed_text": "张三\n求职意向：Java开发工程师...",
    "extracted_info": {
      "name": "张三",
      "phone": "13800138000",
      "email": "zhangsan@email.com",
      "address": "北京市海淀区",
      "job_intention": "Java开发工程师",
      "expected_salary": null,
      "work_years": 5,
      "education": {
        "level": "本科",
        "school": "清华大学",
        "major": "计算机科学",
        "graduation_date": "2020-06"
      },
      "skills": ["Java", "SpringBoot", "MySQL", "Redis"],
      "awards": ["CET6证书", "计算机二级"],
      "work_experience": [
        {"company": "某科技公司", "position": "高级工程师", "start_date": "2020-06", "end_date": "至今", "responsibilities": "..."}
      ],
      "project_experience": [...]
    },
    "from_cache": false,
    "processing_time_ms": 12000
  }
}
```

### `POST /api/analyze`

上传 PDF 简历并进行岗位匹配评分。

```bash
curl -X POST \
  -F "file=@简历.pdf" \
  -F "job_description=负责后端业务系统的设计与开发..." \
  https://resume-analyzer-spucnjlkdu.cn-hangzhou.fcapp.run/api/analyze
```

响应额外包含：

```json
{
  "matching": {
    "job_keywords": ["Java", "SpringBoot", "微服务"],
    "match_score": 0.85,
    "skill_match_rate": 0.80,
    "experience_relevance": 0.90,
    "education_match": true,
    "overall_feedback": "候选人Java后端经验丰富，技能高度匹配...",
    "strengths": ["熟练掌握SpringBoot框架", "..."],
    "weaknesses": ["微服务架构经验不足"]
  },
  "from_cache": false,
  "processing_time_ms": 16500
}
```

## 项目结构

```
ai-resume/
├── backend/
│   ├── app.py              # Flask 应用（PDF解析 + LLM提取 + 匹配评分）
│   ├── mini.py             # FC 事件→WSGI 适配器（含冷启动自动 pip install）
│   ├── requirements.txt    # flask, pymupdf, httpx, redis
│   └── .env.example
│   └── s.yaml              # Serverless Devs 部署配置
├── docs/                   # GitHub Pages 前端
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── 简历案例/               # 测试用 PDF 简历 + 岗位描述
└── README.md
```

## 本地开发

```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 3. 启动后端
source .env
python app.py

# 4. 启动前端
cd ../docs
python -m http.server 3000
# 打开 http://localhost:3000
```

## 部署

### 后端 — 阿里云 FC

```bash
cd backend
# 安装 Serverless Devs
npm install @serverless-devs/s -g

# 配置账号
s config add

# 部署
s deploy -y
```

首次冷启动约 30 秒（自动 pip install），后续热请求 8-12 秒（两次 LLM 调用），缓存命中 <100ms。

### 前端 — GitHub Pages

推送代码到 `main` 分支，在仓库 Settings → Pages 中选择 `main` 分支的 `/docs` 目录即可。

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | (必填) |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-v4-pro` |
| `REDIS_URL` | Redis 连接地址 | (可选，不设则跳过缓存) |

## 前端使用说明

1. 打开 `https://jalong-ton.github.io/ai-resume/`
2. 拖拽或点击上传 PDF 简历
3. 可选：粘贴岗位描述文本（填入后会计算匹配度）
4. 点击"开始分析"
5. 查看提取结果和匹配评分

## 许可证

MIT
