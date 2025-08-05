# main.py
import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
import os
from threading import Thread
from flask import Flask, jsonify

# ===========================
# 🔧 CONFIGURAÇÕES
# ===========================
API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "JX0AOXPZ01EL532N")  # Coloque sua chave
SYMBOL = "XAUUSD"
NAME = "XAUUSD"
CHECK_INTERVAL = 15 * 60  # 15 minutos
CSV_FILE = "/var/data/sinais_xauusd.csv"

# 📞 Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ===========================
# 🌐 SERVIDOR WEB LEVE (Flask)
# ===========================
app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>🧠 Brandon Wendell System - Alpha Vantage</h1><p>Status: Em execução</p>"

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
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
        print("✅ Telegram enviado")
    except Exception as e:
        print(f"❌ Falha ao enviar Telegram: {e}")

# Criar diretório e CSV
def criar_csv():
    os.makedirs("/var/data", exist_ok=True)
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
# 🔍 BUSCAR DADOS DA ALPHA VANTAGE
# ===========================
def obter_dados_tf(interval):
    """
    Busca dados do XAUUSD em um timeframe específico
    interval: 15min, 60min, daily
    """
    try:
        if interval == "daily":
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "FX_DAILY",
                "from_symbol": "XAU",
                "to_symbol": "USD",
                "apikey": API_KEY,
                "outputsize": "compact"
            }
        else:
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "FX_INTRADAY",
                "from_symbol": "XAU",
                "to_symbol": "USD",
                "interval": interval,
                "apikey": API_KEY,
                "outputsize": "compact"
            }

        print(f"📡 Buscando dados ({interval})...")
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if "Time Series FX" not in data:
            print(f"❌ Erro na API: {data.get('Information', 'Dados não disponíveis')}")
            return pd.DataFrame()

        key = list(data.keys())[1]  # Time Series (Xmin)
        df = pd.DataFrame.from_dict(data[key], orient='index')
        df = df.astype(float)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df.rename(columns={'1. open': 'open', '2. high': 'high', '3. low': 'low', '4. close': 'close'})
        df = df[['open', 'high', 'low', 'close']]
        return df

    except Exception as e:
        print(f"❌ Falha ao obter dados: {e}")
        return pd.DataFrame()

# ===========================
# 🔍 ANÁLISE PRINCIPAL
# ===========================
def analisar_xauusd():
    print(f"\n🪙 {datetime.now().strftime('%H:%M:%S')} | Análise Estrutural: {NAME}")

    # === 1. BUSCAR DADOS ===
    timeframes = {
        'w1': {'interval': '60min', 'period': '168h', 'nome': 'W1'},  # 7 dias x 24h
        'd1': {'interval': '60min', 'nome': 'D1'},
        'h4': {'interval': '60min', 'nome': 'H4'},
        'm15': {'interval': '15min', 'nome': 'M15'}
    }

    dados = {}
    for key, config in timeframes.items():
        df = obter_dados_tf(config['interval'])
        if df.empty or len(df) < 15:
            print(f"⚠️ Dados insuficientes para {config['nome']}")
            continue

        # Cálculo de RSI e EMA
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df.dropna(inplace=True)

        if df.empty:
            continue

        dados[key] = df.iloc[-1].copy()

    if 'd1' not in dados or 'h4' not in dados or 'm15' not in dados:
        print("⚠️ Dados insuficientes. Aguardando próxima verificação.")
        return None

    d1_rsi = float(dados['d1']['rsi_14'])
    h4_rsi = float(dados['h4']['rsi_14'])
    m15_rsi = float(dados['m15']['rsi_14'])
    preco_atual = dados['m15']['close']

    # Tendência
    d1_bullish = d1_rsi > 50 and dados['d1']['close'] > dados['d1']['ema_21']
    h4_bullish = h4_rsi > 50 and dados['h4']['close'] > dados['h4']['ema_21']

    # === 4. GERAÇÃO DE SINAL ===
    if d1_bullish and h4_bullish:
        if m15_rsi >= 40:
            sinal = "🟢 COMPRA: Tendência de alta confirmada"
        else:
            sinal = "🟡 AGUARDAR: RSI muito baixo (momentum fraco)"
    elif not d1_bullish and not h4_bullish:
        if m15_rsi <= 60:
            sinal = "🔴 VENDA: Tendência de baixa confirmada"
        else:
            sinal = "🟡 AGUARDAR: RSI muito alto (momentum forte)"
    else:
        sinal = "⚪ AGUARDAR: Estrutura não alinhada"

    # === 5. MENSAGEM ===
    msg = f"🪙 <b>{NAME}</b> | Análise Estrutural\n"
    msg += f"{'='*40}\n"
    msg += f"• D1 RSI: {d1_rsi:.1f}\n"
    msg += f"• H4 RSI: {h4_rsi:.1f}\n"
    msg += f"• M15 RSI: {m15_rsi:.1f}\n"
    msg += f"\n🎯 <b>{sinal}</b>\n"
    msg += f"💰 Preço: <b>{preco_atual:.2f}</b>\n"
    msg += f"📌 Fonte: Alpha Vantage + Brandon Wendell\n"
    msg += f"⏱️ {datetime.now().strftime('%H:%M %d/%m')}"

    enviar_telegram(msg)
    print(f"✅ Análise concluída | Sinal: {sinal}")

    salvar_sinal({
        'symbol': NAME,
        'preco': preco_atual,
        'sinal': sinal,
        'tendencia': 'bullish' if d1_bullish and h4_bullish else 'bearish',
        'rsi_m15': m15_rsi,
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
        enviar_telegram("🟢 Sistema iniciado com Alpha Vantage!")
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
    web_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=8080, debug=False))
    web_thread.daemon = True
    web_thread.start()
    loop_monitoramento()
