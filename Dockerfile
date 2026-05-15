FROM python:3.11-alpine

WORKDIR /app

RUN apk add --no-cache curl

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install fastapi==0.109.0 uvicorn==0.27.0 python-dotenv==1.0.0 aiofiles==23.2.1 dashscope==1.20.0 -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

EXPOSE 8000

ENV PYTHONPATH=/app

CMD ["python", "main.py"]
