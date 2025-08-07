FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY main.py .

EXPOSE 8080

CMD ["python", "main.py"]
