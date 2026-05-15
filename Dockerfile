FROM python:3.11-alpine

WORKDIR /app

RUN apk add --no-cache curl

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

EXPOSE 8000

ENV PYTHONPATH=/app

CMD ["python", "main.py"]
