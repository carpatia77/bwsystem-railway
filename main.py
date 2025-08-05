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

# Suprimir warnings chatos
warnings.filterwarnings("ignore", category=FutureWarning)
np.NaN = np.nan

# ===========================
# 🔧 CONFIGURAÇÕES
# ===========================
SYMBOLS = ["GC=F", "XAUUSD=X", "GLD"]  # Múltiplos tickers
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
    return """
    <h1>🧠 Brandon Wendell System - Ativo</h1>
    <p>Sistema de monitoramento 24/7 para XAUUSD</p>
    <p><strong>Status:</strong> Em execução</p>
    <p><a href="/status">Ver último sinal</a></p>
    """

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
    return jsonify({"status": "running", "last_signal": "Aguardando primeiro sinal"})

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
# 🔍 DOWNLOAD ROBUSTO COM RETRY
# ===========================
def download_robusto(period, interval, max_attempts=6):
    """
    Baixa dados com múltiplos tickers, retries e User-Agent rotativo
    """
    import random
    from requests import Session
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    # Configuração de sessão com retry
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
                # User-Agent aleatório
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

        # Backoff exponencial
        if tentativa < max_attempts - 1:
            wait = (2 ** tentativa) + random.uniform(0, 10)
            print(f"🔁 Esperando {wait:.1f}s...")
            time.sleep(wait)

    print("❌ Falha crítica: Não foi possível baixar dados.")
    return pd.DataFrame(), None

# ===========================
# 🔍 DETECÇÃO DE ZONAS ESTRUTURAIS
# ===========================
def detectar_zonas(df, window=3, min_distance=3):
    """Detecta suportes e resistências com base em swing points"""
    swing_lows = []
    swing_highs = []
    for i in range(window, len(df) - window):
        low = df['low'].iloc[i]
        high = df['high'].iloc[i]
        if low == df['low'].iloc[i-window:i+window+1].min():
            swing_lows.append({
                'index': i,
                'price': low,
                'type': 'support',
                'candle': df.index[i]
            })
        if high == df['high'].iloc[i-window:i+window+1].max():
            swing_highs.append({
                'index': i,
                'price': high,
                'type': 'resistance',
                'candle': df.index[i]
            })

    def filtrar_proximos(zonas):
        if not zonas:
            return []
        zonas_ordenadas = sorted(zonas, key=lambda x: x['index'])
        filtradas = [zonas_ordenadas[0]]
        for zona in zonas_ordenadas[1:]:
            ultima = filtradas[-1]
            if abs(zona['index'] - ultima['index']) >= min_distance and \
               abs(zona['price'] - ultima['price']) / ultima['price'] > 0.001:
                filtradas.append(zona)
        return filtradas

    return {
        'suportes': filtrar_proximos(swing_lows),
        'resistencias': filtrar_proximos(swing_highs)
    }

def detectar_padroes_zona(df, zonas, tf):
    """Detecta padrões W base (buy) e M base (sell)"""
    padroes = []
    suportes = zonas['suportes']
    resistencias = zonas['resistencias']
    # Padrão W base (accumulation)
    if len(suportes) >= 2:
        ultimo = suportes[-1]
        penultimo = suportes[-2]
        if ultimo['price'] > penultimo['price'] and ultimo['index'] - penultimo['index'] > 5:
            volatilidade = df['close'].iloc[penultimo['index']:ultimo['index']].std() / df['close'].mean()
            if volatilidade < 0.015:
                confianca = 'alta' if volatilidade < 0.01 else 'média'
                padroes.append({
                    'tipo': 'W_base',
                    'zona': ultimo['price'],
                    'confianca': confianca,
                    'periodo': f"{penultimo['candle'].strftime('%d/%m')} → {ultimo['candle'].strftime('%d/%m')}",
                    'tf': tf
                })
    # Padrão M base (distribution)
    if len(resistencias) >= 2:
        ultimo = resistencias[-1]
        penultimo = resistencias[-2]
        if ultimo['price'] < penultimo['price'] and ultimo['index'] - penultimo['index'] > 5:
            volatilidade = df['close'].iloc[penultimo['index']:ultimo['index']].std() / df['close'].mean()
            if volatilidade < 0.015:
                confianca = 'alta' if volatilidade < 0.01 else 'média'
                padroes.append({
                    'tipo': 'M_base',
                    'zona': ultimo['price'],
                    'confianca': confianca,
                    'periodo': f"{penultimo['candle'].strftime('%d/%m')} → {ultimo['candle'].strftime('%d/%m')}",
                    'tf': tf
                })
    return padroes

def analisar_zonas_estruturais():
    """Analisa zonas em W1, D1, H4"""
    timeframes = {
        'W1': {'interval': '1wk', 'period': '5y', 'nome': 'W1'},
        'D1': {'interval': '1d', 'period': '2y', 'nome': 'D1'},
        'H4': {'interval': '4h', 'period': '6mo', 'nome': 'H4'}
    }
    resultados = {}
    for key, config in timeframes.items():
        try:
            df, ticker_usado = download_robusto(config['period'], config['interval'])
            if df.empty or len(df) < 10:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = df.columns.str.lower().str.strip()
            zonas = detectar_zonas(df)
            padroes = detectar_padroes_zona(df, zonas, config['nome'])
            resultados[key] = {
                'df': df,
                'zonas': zonas,
                'padroes': padroes,
                'suporte_recente': zonas['suportes'][-1]['price'] if zonas['suportes'] else None,
                'resistencia_recente': zonas['resistencias'][-1]['price'] if zonas['resistencias'] else None,
                'ticker': ticker_usado
            }
        except Exception as e:
            print(f"❌ Erro na análise de zonas ({key}): {e}")
            continue
    return resultados

# ===========================
# 🔍 ANÁLISE MULTITIMEFRAME (PRINCIPAL)
# ===========================
def analisar_xauusd():
    print(f"\n🪙 {datetime.now().strftime('%H:%M:%S')} | Análise Estrutural: {NAME}")
    
    # === 1. ANÁLISE DE ZONAS ESTRUTURAIS (W1, D1, H4) ===
    zonas_estruturais = analisar_zonas_estruturais()
    
    if not zonas_estruturais:
        print("⚠️ Falha ao analisar zonas estruturais")
        return None
    
    # Extrair padrões
    w1_padroes = zonas_estruturais.get('W1', {}).get('padroes', [])
    d1_padroes = zonas_estruturais.get('D1', {}).get('padroes', [])
    h4_padroes = zonas_estruturais.get('H4', {}).get('padroes', [])
    
    # Verificar convergência de zonas
    buy_zone_convergente = any(p['tipo'] == 'W_base' for p in w1_padroes + d1_padroes + h4_padroes)
    sell_zone_convergente = any(p['tipo'] == 'M_base' for p in w1_padroes + d1_padroes + h4_padroes)
    
    # === 2. ANÁLISE TÉCNICA (W1, D1, H4, M15) ===
    timeframes = {
        'w1': {'interval': '1wk', 'period': '5y', 'nome': 'W1'},
        'd1': {'interval': '1d', 'period': '3mo', 'nome': 'D1'},
        'h4': {'interval': '4h', 'period': '3mo', 'nome': 'H4'},
        'm15': {'interval': '15m', 'period': '6d', 'nome': 'M15'}
    }
    
    dados = {}
    for key, config in timeframes.items():
        try:
            df, ticker_usado = download_robusto(config['period'], config['interval'])
            
            if df.empty or len(df) < 15:
                print(f"⚠️ Dados insuficientes para {config['nome']}")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = df.columns.str.lower().str.strip()

            # Cálculo manual de RSI e EMA
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

            # Divergência (só no M15)
            df['divergencia'] = None
            if key == 'm15':
                close = df['close'].tail(5).values
                rsi_vals = df['rsi_14'].tail(5).values
                if len(close) == 5:
                    if close[-1] < close[-2] and rsi_vals[-1] > rsi_vals[-2]:
                        df['divergencia'] = "bullish_divergence"
                    elif close[-1] > close[-2] and rsi_vals[-1] < rsi_vals[-2]:
                        df['divergencia'] = "bearish_divergence"

            dados[key] = df.iloc[-1].copy()
            dados[key]['ticker'] = ticker_usado

        except Exception as e:
            print(f"❌ Erro no timeframe {key}: {e}")
            continue

    # Verificar se temos os dados principais
    if 'd1' not in dados or 'h4' not in dados or 'm15' not in dados:
        print("⚠️ Dados insuficientes. Aguardando próxima verificação.")
        return None

    w1 = dados.get('w1')
    d1 = dados['d1']
    h4 = dados['h4']
    m15 = dados['m15']

    try:
        d1_rsi = float(d1['rsi_14'])
        h4_rsi = float(h4['rsi_14'])
        m15_rsi = float(m15['rsi_14'])
        w1_rsi = float(w1['rsi_14']) if w1 is not None else None
    except:
        print("❌ Erro ao ler RSI")
        return None

    preco_atual = m15['close']
    stop_buy = m15['low'] * 0.995 if pd.notna(m15['low']) else None
    stop_sell = m15['high'] * 1.005 if pd.notna(m15['high']) else None
    sinal = None
    zona_info = {}

    # === 3. DETECÇÃO DE TENDÊNCIA POR TIMEFRAME ===
    def tendencia_descricao(preco, ema, rsi):
        if preco > ema and rsi > 50:
            return "🟢 Bullish (momentum positivo)"
        elif preco < ema and rsi < 50:
            return "🔴 Bearish (momentum negativo)"
        else:
            return "🟡 Neutro (sem direção clara)"

    w1_tendencia = tendencia_descricao(w1['close'], w1['ema_21'], w1_rsi) if w1 is not None else "N/A"
    d1_tendencia = tendencia_descricao(d1['close'], d1['ema_21'], d1_rsi)
    h4_tendencia = tendencia_descricao(h4['close'], h4['ema_21'], h4_rsi)
    m15_tendencia = tendencia_descricao(m15['close'], m15['ema_21'], m15_rsi)

    # Tendência principal
    d1_bullish = d1_rsi > 50 and d1['close'] > d1['ema_21']
    d1_bearish = d1_rsi < 50 and d1['close'] < d1['ema_21']
    h4_bullish = h4_rsi > 50 and h4['close'] > h4['ema_21']
    h4_bearish = h4_rsi < 50 and h4['close'] < h4['ema_21']

    # === 4. GERAÇÃO DE SINAL COM CONTEXTO ===
    if d1_bullish and h4_bullish and buy_zone_convergente:
        distancia_suporte = abs(preco_atual - zonas_estruturais['H4']['suporte_recente']) / zonas_estruturais['H4']['suporte_recente'] if zonas_estruturais['H4']['suporte_recente'] else 1
        
        if distancia_suporte < 0.008 and m15_rsi >= 40:
            sinal = "🟢 COMPRA: Zona de Acumulação (W Base) Confirmada"
            zona_info = {
                'zona_tipo': 'W_base',
                'confianca': 'alta' if any(p['confianca'] == 'alta' for p in h4_padroes + d1_padroes) else 'média'
            }
            if m15['divergencia'] == "bullish_divergence":
                sinal += " + DIVERGÊNCIA BULLISH"
        elif distancia_suporte >= 0.008:
            sinal = "🟡 AGUARDAR: Preço distante da zona de suporte estrutural (pullback necessário)"
        else:
            sinal = "❌ NÃO COMPRAR: Momentum muito fraco (RSI < 40)"
            
    elif d1_bearish and h4_bearish and sell_zone_convergente:
        distancia_resistencia = abs(preco_atual - zonas_estruturais['H4']['resistencia_recente']) / zonas_estruturais['H4']['resistencia_recente'] if zonas_estruturais['H4']['resistencia_recente'] else 1
        
        if distancia_resistencia < 0.008 and m15_rsi <= 60:
            sinal = "🔴 VENDA: Zona de Distribuição (M Base) Confirmada"
            zona_info = {
                'zona_tipo': 'M_base',
                'confianca': 'alta' if any(p['confianca'] == 'alta' for p in h4_padroes + d1_padroes) else 'média'
            }
            if m15['divergencia'] == "bearish_divergence":
                sinal += " + DIVERGÊNCIA BEARISH"
        elif distancia_resistencia >= 0.008:
            sinal = "🟡 AGUARDAR: Preço distante da zona de resistência estrutural (rally necessário)"
        else:
            sinal = "❌ NÃO VENDER: Momentum muito forte (RSI > 60)"
            
    else:
        sinal = "⚪ AGUARDAR: Estrutura de mercado não confirmada"

    # === 5. MENSAGEM COM CONTEXTO E TENDÊNCIAS ===
    msg = f"🪙 <b>{NAME}</b> | Análise Estrutural\n"
    msg += f"{'='*40}\n"
    
    # Resumo de tendência por timeframe
    msg += "📊 <b>TENDÊNCIAS POR TIMEFRAME</b>\n"
    if w1 is not None:
        msg += f"• W1: {w1_tendencia} (RSI={w1_rsi:.1f}) [{w1.get('ticker', 'N/A')}]\n"
    msg += f"• D1: {d1_tendencia} (RSI={d1_rsi:.1f}) [{d1.get('ticker', 'N/A')}]\n"
    msg += f"• H4: {h4_tendencia} (RSI={h4_rsi:.1f}) [{h4.get('ticker', 'N/A')}]\n"
    msg += f"• M15: {m15_tendencia} (RSI={m15_rsi:.1f}) [{m15.get('ticker', 'N/A')}]\n"
    
    msg += f"\n🎯 <b>{sinal}</b>\n"
    msg += f"💰 Preço atual: <b>{preco_atual:.2f}</b>\n"
    
    # Contexto das zonas
    if buy_zone_convergente:
        msg += f"\n🔍 <b>ZONA DE ACUMULAÇÃO (W BASE)</b>\n"
        msg += "• Estrutura de suporte identificada em múltiplos timeframes\n"
        msg += "• Alta probabilidade de reversão para cima\n"
        msg += "• Ideal para entrada com RSI ≥ 40\n"
    
    if sell_zone_convergente:
        msg += f"\n🔍 <b>ZONA DE DISTRIBUIÇÃO (M BASE)</b>\n"
        msg += "• Estrutura de resistência identificada em múltiplos timeframes\n"
        msg += "• Alta probabilidade de reversão para baixo\n"
        msg += "• Ideal para entrada com RSI ≤ 60\n"
    
    # Recomendações
    if "COMPRA" in sinal:
        suporte = zonas_estruturais['H4']['suporte_recente']
        msg += f"\n✅ <b>RECOMENDAÇÃO DE COMPRA</b>\n"
        msg += f"• Entrar próximo a <b>{suporte:.2f}</b>\n"
        msg += f"• Stop-loss: {stop_buy:.2f} (abaixo do suporte)\n"
        msg += f"• Confiança: <b>{zona_info.get('confianca', 'média').upper()}</b>\n"
    elif "VENDA" in sinal:
        resistencia = zonas_estruturais['H4']['resistencia_recente']
        msg += f"\n✅ <b>RECOMENDAÇÃO DE VENDA</b>\n"
        msg += f"• Entrar próximo a <b>{resistencia:.2f}</b>\n"
        msg += f"• Stop-loss: {stop_sell:.2f} (acima da resistência)\n"
        msg += f"• Confiança: <b>{zona_info.get('confianca', 'média').upper()}</b>\n"
    elif "AGUARDAR" in sinal:
        msg += f"\nℹ️ <b>ESTRATÉGIA</b>\n"
        msg += "• Não force entrada\n"
        msg += "• Aguarde o preço retornar à zona estrutural\n"
        msg += "• Confirme com RSI e divergência\n"
    
    msg += f"\n📌 Fonte: Brandon Wendell + Análise Estrutural\n"
    msg += f"⏱️ Atualizado: {datetime.now().strftime('%H:%M %d/%m')}"

    # Enviar alerta
    enviar_telegram(msg)
    print(f"✅ Análise concluída | Sinal: {sinal}")
    
    # Salvar
    salvar_sinal({
        'symbol': NAME,
        'preco': preco_atual,
        'sinal': sinal,
        'tendencia': 'bullish' if d1_bullish and h4_bullish else 'bearish' if d1_bearish and h4_bearish else 'neutro',
        'rsi_m15': m15_rsi,
        'stop_loss': stop_buy if "COMPRA" in sinal else stop_sell if "VENDA" in sinal else None,
        'zona_tipo': zona_info.get('zona_tipo', 'N/A'),
        'confianca': zona_info.get('confianca', 'N/A')
    })

    return sinal

# ===========================
# 🚀 LOOP PRINCIPAL 24/7
# ===========================
def loop_monitoramento():
    print("🟢 Sistema de monitoramento iniciado...")
    print(f"🔔 Intervalo: {CHECK_INTERVAL//60} minutos")
    print(f"📊 Ativo: {NAME}")
    criar_csv()
    
    if TELEGRAM_TOKEN:
        enviar_telegram("🟢 Sistema de monitoramento XAUUSD iniciado!\nAnálise Estrutural Ativada")
    else:
        print("ℹ️ Telegram desativado (configure TELEGRAM_TOKEN e TELEGRAM_CHAT_ID)")

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
    # Iniciar o servidor web em uma thread
    web_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=8080))
    web_thread.daemon = True
    web_thread.start()
    
    # Iniciar o loop de monitoramento
    loop_monitoramento()
