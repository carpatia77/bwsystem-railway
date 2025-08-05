# main.py
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime
import os
import warnings
from threading import Thread
from flask import Flask, jsonify
import random

# Suprimir warnings
warnings.filterwarnings("ignore", category=FutureWarning)
np.NaN = np.nan

# ===========================
# 🔧 CONFIGURAÇÕES
# ===========================
SYMBOLS = ["GC=F", "XAUUSD=X", "GLD"]  # Fallback
NAME = "XAUUSD"
CHECK_INTERVAL = 15 * 60  # 15 minutos
CSV_FILE = "/var/data/sinais_xauusd.csv"  # Pasta persistente no Render

# 📞 Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ===========================
# 🌐 SERVIDOR WEB LEVE (Flask)
# ===========================
app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>🧠 Brandon Wendell System - Render.com</h1><p>Status: Em execução</p>"

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
# 🔍 DOWNLOAD ROBUSTO
# ===========================
def download_robusto(period, interval, max_attempts=6):
    import random
    from requests import Session
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = Session()
    retry_strategy = Retry(
        total=max_attempts,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    for tentativa in range(max_attempts):
        for ticker in SYMBOLS:
            try:
                user_agent = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 120)}.0.0.0 Safari/537.36'
                session.headers.update({'User-Agent': user_agent})

                print(f"📥 Tentativa {tentativa+1}/{max_attempts} - {ticker} ({interval})...")
                df = yf.download(ticker, period=period, interval=interval, progress=False, session=session)

                if not df.empty and len(df) >= 15:
                    print(f"✅ Sucesso com {ticker}")
                    return df, ticker

            except Exception as e:
                print(f"❌ Falha com {ticker}: {e}")
                continue

            time.sleep(random.uniform(2, 5))

        if tentativa < max_attempts - 1:
            wait = (2 ** tentativa) + random.uniform(0, 10)
            print(f"🔁 Esperando {wait:.1f}s...")
            time.sleep(wait)

    print("❌ Falha crítica: Não foi possível baixar dados.")
    return pd.DataFrame(), None

# ===========================
# 🔍 ANÁLISE PRINCIPAL
# ===========================
def analisar_xauusd():
    print(f"\n🪙 {datetime.now().strftime('%H:%M:%S')} | Análise Estrutural: {NAME}")
    
    # === 1. ANÁLISE DE ZONAS ESTRUTURAIS ===
    timeframes = {
        'W1': {'interval': '1wk', 'period': '5y'},
        'D1': {'interval': '1d', 'period': '2y'},
        'H4': {'interval': '4h', 'period': '6mo'}
    }
    zonas_estruturais = {}
    for key, config in timeframes.items():
        df, ticker_usado = download_robusto(config['period'], config['interval'])
        if not df.empty:
            swing_lows = []
            swing_highs = []
            for i in range(3, len(df) - 3):
                low = df['low'].iloc[i]
                high = df['high'].iloc[i]
                if low == df['low'].iloc[i-3:i+4].min():
                    swing_lows.append({'price': low})
                if high == df['high'].iloc[i-3:i+4].max():
                    swing_highs.append({'price': high})
            zonas_estruturais[key] = {
                'suporte_recente': swing_lows[-1]['price'] if swing_lows else None,
                'resistencia_recente': swing_highs[-1]['price'] if swing_highs else None,
                'ticker': ticker_usado
            }

    # === 2. ANÁLISE TÉCNICA (W1, D1, H4, M15) ===
    timeframes_tec = {
        'w1': {'interval': '1wk', 'period': '5y'},
        'd1': {'interval': '1d', 'period': '3mo'},
        'h4': {'interval': '4h', 'period': '3mo'},
        'm15': {'interval': '15m', 'period': '6d'}
    }
    dados = {}
    for key, config in timeframes_tec.items():
        df, ticker_usado = download_robusto(config['period'], config['interval'])
        if df.empty or len(df) < 15:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = df.columns.str.lower().str.strip()
        
        # Cálculo RSI e EMA
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
        dados[key]['ticker'] = ticker_usado

    if 'd1' not in dados or 'h4' not in dados or 'm15' not in dados:
        print("⚠️ Dados insuficientes")
        return None

    d1_rsi = float(dados['d1']['rsi_14'])
    h4_rsi = float(dados['h4']['rsi_14'])
    m15_rsi = float(dados['m15']['rsi_14'])
    preco_atual = dados['m15']['close']

    # === 3. GERAÇÃO DE SINAL ===
    buy_zone = zonas_estruturais.get('H4', {}).get('suporte_recente') and dados['d1']['close'] > dados['d1']['ema_21']
    sell_zone = zonas_estruturais.get('H4', {}).get('resistencia_recente') and dados['d1']['close'] < dados['d1']['ema_21']

    sinal = "⚪ AGUARDAR: Estrutura não confirmada"
    if buy_zone and m15_rsi >= 40:
        sinal = "🟢 COMPRA: Zona de Acumulação"
    elif sell_zone and m15_rsi <= 60:
        sinal = "🔴 VENDA: Zona de Distribuição"

    # === 4. MENSAGEM ===
    msg = f"🪙 <b>{NAME}</b> | Análise Estrutural\n"
    msg += f"{'='*40}\n"
    msg += f"• D1 RSI: {d1_rsi:.1f}\n"
    msg += f"• H4 RSI: {h4_rsi:.1f}\n"
    msg += f"• M15 RSI: {m15_rsi:.1f}\n"
    msg += f"\n🎯 <b>{sinal}</b>\n"
    msg += f"💰 Preço: <b>{preco_atual:.2f}</b>\n"
    msg += f"📌 Fonte: Brandon Wendell\n"
    msg += f"⏱️ {datetime.now().strftime('%H:%M %d/%m')}"

    enviar_telegram(msg)
    print(f"✅ Análise concluída | Sinal: {sinal}")
    
    salvar_sinal({
        'symbol': NAME,
        'preco': preco_atual,
        'sinal': sinal,
        'tendencia': 'bullish' if dados['d1']['close'] > dados['d1']['ema_21'] else 'bearish',
        'rsi_m15': m15_rsi,
        'stop_loss': None,
        'zona_tipo': 'W_base' if buy_zone else 'M_base' if sell_zone else 'N/A',
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
    web_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=8080, debug=False))
    web_thread.daemon = True
    web_thread.start()
    loop_monitoramento()
