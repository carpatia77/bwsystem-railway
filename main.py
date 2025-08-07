# main.py - Sistema no Render.com (Versão Final)
import gspread
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime
import os
from threading import Thread
from flask import Flask, jsonify

# ===========================
# 🔧 CONFIGURAÇÕES
# ===========================
SHEET_NAME = "XAUUSD_Data"
NAME = "XAUUSD"
CHECK_INTERVAL = 15 * 60  # 15 minutos
CSV_FILE = "/app/sinais_xauusd.csv"

# 📞 Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ===========================
# 🌐 SERVIDOR WEB LEVE (Flask)
# ===========================
app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>🧠 Brandon Wendell System - Google Sheets</h1><p>Status: Em execução</p>"

@app.route('/status')
def status():
    if os.path.exists(CSV_FILE):
        try:
            log = pd.read_csv(CSV_FILE)
            ultimo = log.iloc[-1]
            return jsonify({
                "status": "running",
                "last_signal": ultimo['sinal'],
                "price": ultimo['preco'],
                "timestamp": ultimo['timestamp']
            })
        except:
            pass
    return jsonify({"status": "running", "last_signal": "Aguardando sinal"})

# ===========================
# 📡 FUNÇÕES DE APOIO
# ===========================
def enviar_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ℹ️ Telegram desativado")
        return
    try:
        # ✅ URL corrigida (sem espaços extras)
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
        print("✅ Telegram enviado")
    except Exception as e:
        print(f"❌ Falha ao enviar Telegram: {e}")

# Criar CSV
def criar_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w") as f:
            f.write("timestamp,symbol,preco,sinal,tendencia,rsi_m15,stop_loss,zona_tipo,confianca\n")
        print("✅ Arquivo CSV criado")

def salvar_sinal(sinal_data):
    with open(CSV_FILE, "a") as f:
        stop_loss_str = f"{sinal_data['stop_loss']:.2f}" if sinal_data['stop_loss'] is not None else "N/A"
        zona_str = sinal_data.get('zona_tipo', 'N/A')
        confianca_str = sinal_data.get('confianca', 'N/A')
        row = f"{pd.Timestamp.now()},{sinal_data['symbol']},{sinal_data['preco']:.2f},"
        row += f"{sinal_data['sinal']},{sinal_data['tendencia']},{sinal_data['rsi_m15']:.2f},"
        row += f"{stop_loss_str},{zona_str},{confianca_str}\n"
        f.write(row)
    print(f"💾 Sinal salvo: {sinal_data['sinal']}")

# ===========================
# 🔍 LER DADOS DO GOOGLE SHEETS
# ===========================
def ler_dados_sheets():
    try:
        # ✅ Scope correto (sem espaços extras)
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_file("/app/secrets.json", scopes=scope)
        client = gspread.authorize(creds)
        
        sheet = client.open(SHEET_NAME).sheet1
        dados = sheet.get_all_records()[-1]
        
        return {
            'preco': dados['preco'],
            'rsi_m15': dados['rsi_m15'],
            'ema21_m15': dados['ema21_m15'],
            'rsi_h4': dados['rsi_h4'],
            'ema21_h4': dados['ema21_h4'],
            'rsi_d1': dados['rsi_d1'],
            'ema21_d1': dados['ema21_d1'],
        }
    except Exception as e:
        print(f"❌ Falha ao ler Google Sheets: {e}")
        return None

# ===========================
# 🔍 ANÁLISE MULTITIMEFRAME (com contexto estrutural)
# ===========================
def analisar_xauusd():
    print(f"\n🪙 {datetime.now().strftime('%H:%M:%S')} | Análise Estrutural: {NAME}")
    
    dados = ler_dados_sheets()
    if not dados:
        print("⚠️ Dados não disponíveis no Google Sheets")
        return None

    try:
        preco_atual = float(dados['preco'])
        rsi_m15 = float(dados['rsi_m15'])
        rsi_h4 = float(dados['rsi_h4'])
        rsi_d1 = float(dados['rsi_d1'])
    except (ValueError, TypeError) as e:
        print(f"❌ Erro ao converter dados: {e}")
        return None

    # Tendência
    tend_m15 = "🟢 Bullish" if preco_atual > dados['ema21_m15'] and rsi_m15 > 50 else "🔴 Bearish"
    tend_h4 = "🟢 Bullish" if preco_atual > dados['ema21_h4'] and rsi_h4 > 50 else "🔴 Bearish"
    tend_d1 = "🟢 Bullish" if preco_atual > dados['ema21_d1'] and rsi_d1 > 50 else "🔴 Bearish"

    # Alinhamento D1/H4
    alinhado = (tend_d1 == "🟢 Bullish" and tend_h4 == "🟢 Bullish") or \
               (tend_d1 == "🔴 Bearish" and tend_h4 == "🔴 Bearish")

    # Geração de sinal com contexto
    if alinhado and tend_d1 == "🟢 Bullish" and rsi_m15 >= 40:
        sinal = "🟢 COMPRA: Tendência de alta confirmada"
    elif alinhado and tend_d1 == "🔴 Bearish" and rsi_m15 <= 60:
        sinal = "🔴 VENDA: Tendência de baixa confirmada"
    else:
        sinal = "🟡 AGUARDAR: Estrutura não alinhada"

    # Mensagem
    msg = f"🪙 <b>{NAME}</b> | Análise Estrutural\n"
    msg += f"{'='*40}\n"
    msg += f"• D1: {tend_d1} (RSI={rsi_d1:.1f})\n"
    msg += f"• H4: {tend_h4} (RSI={rsi_h4:.1f})\n"
    msg += f"• M15: {tend_m15} (RSI={rsi_m15:.1f})\n"
    msg += f"\n🎯 <b>{sinal}</b>\n"
    msg += f"💰 Preço: <b>{preco_atual:.2f}</b>\n"
    msg += f"📌 Fonte: Google Sheets + Brandon Wendell\n"
    msg += f"⏱️ {datetime.now().strftime('%H:%M %d/%m')}"

    enviar_telegram(msg)
    print(f"✅ Análise concluída | Sinal: {sinal}")

    salvar_sinal({
        'symbol': NAME,
        'preco': preco_atual,
        'sinal': sinal,
        'tendencia': 'bullish' if tend_d1 == "🟢 Bullish" else 'bearish',
        'rsi_m15': rsi_m15,
        'stop_loss': None,
        'zona_tipo': 'N/A',
        'confianca': 'média'
    })

    return sinal

# ===========================
# 🚀 LOOP PRINCIPAL
# ===========================
def loop_monitoramento():
    print("🟢 Sistema de monitoramento iniciado...")
    print(f"🔔 Intervalo: {CHECK_INTERVAL//60} minutos")
    print(f"📊 Ativo: {NAME}")
    criar_csv()
    if TELEGRAM_TOKEN:
        enviar_telegram("🟢 Sistema iniciado!")
    else:
        print("ℹ️ Telegram desativado")

    while True:
        try:
            analisar_xauusd()
            print(f"⏳ Próxima verificação em {CHECK_INTERVAL//60} minutos...")
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"❌ Erro no loop: {e}")
            time.sleep(60)


# ===========================
# ▶️ EXECUTAR
# ===========================
if __name__ == "__main__":
    # Iniciar o servidor web em uma thread separada
    web_thread = Thread(target=lambda: app.run(
        host='0.0.0.0',
        port=8080,
        debug=False,
        use_reloader=False
    ), daemon=True)
    
    web_thread.start()
    
    # O loop principal roda na thread principal
    loop_monitoramento()  # ou iniciar_monitoramento()
