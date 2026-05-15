# 生图 WebUI

基于 FastAPI + HTML 的文生图和图像编辑 WebUI，支持阿里云百炼 API。

## 功能特性

- 文生图：输入提示词生成图片
- 图像编辑：选择历史图片作为参考进行多轮编辑
- 多会话管理：支持创建、切换、删除对话
- 图片管理：图库功能，支持预览、下载、删除
- 本地存储：所有图片自动保存在本地

## 快速开始

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置 API Key，编辑 `.env` 文件：
```
DASHSCOPE_API_KEY=your_api_key_here
```

3. 启动服务：
```bash
python main.py
```

4. 打开浏览器访问 `http://localhost:8000`

## 项目结构

```
webui_project/
├── main.py              # FastAPI 后端
├── requirements.txt     # Python 依赖
├── .env                 # API Key 配置
├── static/
│   └── index.html       # 前端页面
├── outputs/             # 生成的图片
├── sessions/            # 对话数据
└── uploads/            # 上传的图片
```
