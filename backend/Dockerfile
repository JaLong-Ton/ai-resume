FROM python:3.12-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY app.py .

EXPOSE 9000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
