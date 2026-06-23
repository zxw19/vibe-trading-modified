# Vibe-Trading — A股深度研究 Agent

基于多智能体协作的 A 股上市公司深度研究工具，支持单 Agent 快速分析和 Swarm 多 Agent 团队深度研究。

## 功能

- **个股深度研究**：公司业务、财务质量、行业地位、订单客户、风险提示
- **产业链分析**：AI 算力产业链各节点竞争力量化排名（6 维度加权评分）
- **财报分析**：季度/年度财务数据（默认 2025 年起，AI 高开支时代）
- **多 Agent 团队**：6 角色 Swarm 协作（公司事实 → 财务质量 → 产业链 → 订单客户 → 来源审计 → 报告编辑）

## 数据源

全部免费，无需积分：

| 数据 | 来源 | 说明 |
|---|---|---|
| 实时行情 | 腾讯 qt.gtimg.cn | 最新价、最高/最低、PE、市值 |
| 历史K线 | 腾讯/mootdx/东方财富/baostock | 日线，自动 fallback |
| 财务报表 | 东方财富 datacenter | 三大报表 + 关键指标 |
| 公告 | 巨潮资讯 cninfo.com.cn | 中国证监会指定披露平台 |
| 研报/新闻 | 东方财富 | 机构观点，非事实 |
| 行业/板块 | 东方财富 push2 | 成分股、排名 |

## 快速开始

### 1. 环境准备

```bash
# Python 3.12+
python -m venv vibe-env

# Windows
vibe-env\Scripts\activate

# Mac/Linux
source vibe-env/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 LLM

复制 `.env.example` 为 `.env`，填入你的 LLM API Key：

```env
LANGCHAIN_PROVIDER=deepseek
LANGCHAIN_MODEL_NAME=deepseek-v4-pro
DEEPSEEK_API_KEY=sk-your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

支持的提供商：DeepSeek / OpenAI / OpenRouter / Gemini / Groq / Moonshot / Zhipu / Ollama

### 3. 创建用户目录

```bash
# Windows
mkdir %USERPROFILE%\.vibe-trading\skills\user
xcopy skills\user %USERPROFILE%\.vibe-trading\skills\user\ /E

# Mac/Linux
mkdir -p ~/.vibe-trading/skills/user
cp -r skills/user/* ~/.vibe-trading/skills/user/
```

### 4. 启动

```bash
# 交互式对话（主入口）
python -m cli

# MCP 服务（可接入 Claude Desktop）
python mcp_server.py

# HTTP API 服务
python api_server.py
```

## 使用示例

```
分析 中际旭创          → 个股深度研究报告
财报 中际旭创          → 最新季度财报分析
产业 光模块            → 产业链竞争力量化排名
对比 中际旭创 新易盛   → 多标的横向对比
```

## 项目结构

```
vibe-trading/
  cli/              → 命令行入口
  src/
    agent/          → Agent 循环、技能、工具、上下文
    swarm/          → 多 Agent 团队编排
      presets/      → 团队预设（ashare_company_research_team 等）
    tools/          → ~50 个 A 股研究工具
    providers/      → LLM 提供商适配
    config/         → 配置加载
    memory/         → 跨会话记忆
  backtest/         → 数据加载层（腾讯/东财/mootdx/baostock）
  skills/           → 内置技能
    user/           → 用户自定义技能
  api_server.py     → HTTP API 入口
  mcp_server.py     → MCP 协议入口
  run.py            → Windows 启动辅助
```

## 免责声明

本工具仅供研究学习，不构成投资建议。所有数据来自公开来源，不保证完整性和准确性。AI 生成的分析结论需用户自行判断。
