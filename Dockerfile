FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY main.py .

RUN mkdir -p /var/data

EXPOSE 8080

CMD ["python", "main.py"]
