# Dockerfile
FROM python:3.10-slim

# Define o diretório de trabalho
WORKDIR /app

# Copia os arquivos
COPY requirements.txt .
COPY main.py .

# Instala dependências com retry
RUN pip install --upgrade pip && \
    pip install -r requirements.txt || \
    (sleep 5 && pip install -r requirements.txt)

# Cria um usuário não-root (melhor prática de segurança)
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expõe a porta (necessário mesmo para apps sem web)
EXPOSE 8080

# Comando para rodar o app
CMD ["python", "main.py"]