FROM python:3.10-slim

WORKDIR /app

# Copiar requirements e instalar dependências
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copiar o código
COPY main.py .

# Expor a porta
EXPOSE 8080

# Comando para rodar o app
CMD ["python", "main.py"]
