# 使用官方轻量级 Python 镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

#防止 Python 生成 pyc 文件，并让日志直接输出到控制台
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 更新 pip
RUN pip install --upgrade pip

# 复制依赖文件 (利用 Docker 缓存机制)
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有项目代码
COPY . .

# 暴露端口 (仅作声明，实际映射在 docker-compose 中)
EXPOSE 8000

# 启动命令
# 注意：这里假设 main.py 中有 uvicorn.run，或者你可以直接用 uvicorn 命令启动
CMD ["python", "main.py"]
