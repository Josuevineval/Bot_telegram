import os
import time
import datetime
import threading
from flask import Flask
import telebot
from google import genai

# ==========================================
# 1. SERVIDOR WEB EM SEGUNDO PLANO (RENDER)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot FutBet VIP está online e operacional!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()


# ==========================================
# 2. CONFIGURAÇÃO DAS CHAVES E DO BOT
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN não configurado no Render!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def generate_content_safe(prompt):
    """ Tenta gerar conteúdo usando os modelos ativos mais recentes """
    if not client:
        raise Exception("GEMINI_API_KEY não configurada.")
        
    # Modelos ativos mais recentes da Google
    models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.5-pro']
    
    last_err = None
    for model_name in models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"Aviso: Falha no modelo {model_name}: {e}")
            last_err = e
            
    raise last_err


# ==========================================
# 3. COMANDOS DO BOT DO TELEGRAM
# ==========================================

@bot.message_handler(commands=['start', 'ajuda', 'help'])
def send_welcome(message):
    text = (
        "⚽ *BEM-VINDO AO BOT FUTBET VIP!* 💎\n\n"
        "O seu assistente inteligente para análise e palpites de futebol.\n\n"
        "📌 *Comandos Disponíveis:*\n"
        "👉 /palpites_hoje — 4 Palpites VIP de hoje (2 Seguros + 2 Odds Altas)\n"
        "👉 /analisar <Jogo> — Analisar uma partida (Ex: `/analisar Benfica vs Porto`)\n"
        "👉 /gestao ou /gestão — Regras de Gestão de Banca\n"
        "👉 /vip — Aceder ao nosso Canal VIP"
    )
    bot.reply_to(message, text, parse_mode="Markdown")


@bot.message_handler(commands=['gestao', 'gestão'])
def send_gestao(message):
    text = (
        "📊 *REGRAS DE GESTÃO DE BANCA FUTBET VIP* 📊\n\n"
        "1️⃣ *Gestão de Unidade:* Aposte no máximo **1% a 2%** da sua banca total por entrada.\n"
        "2️⃣ *Evite Múltiplas Longas:* Foque em apostas simples ou duplas com valor estatístico.\n"
        "3️⃣ *Controlo Emocional:* Nunca tente recuperar perdas na emoção.\n"
        "4️⃣ *Metas Diárias:* Defina um *Stop Green* e um *Stop Loss*."
    )
    bot.reply_to(message, text, parse_mode="Markdown")


@bot.message_handler(commands=['vip'])
def send_vip(message):
    text = (
        "🔥 *CANAL VIP FUTBET* 🔥\n\n"
        "Quer receber entradas ao vivo, bilhetes prontos e análises detalhadas?\n\n"
        "👉 *Aceda já ao nosso grupo:* https://t.me/seu_link_aqui"
    )
    bot.reply_to(message, text)


@bot.message_handler(commands=['palpites_hoje'])
def send_palpites(message):
    bot.reply_to(message, "🔍 *A pesquisar os jogos de hoje e a analisar estatísticas com IA... Aguarde uns segundos.*", parse_mode="Markdown")
    
    today_str = datetime.date.today().strftime("%d/%m/%Y")
    
    prompt = f"""
    Hoje é dia {today_str}.
    Atue como um analista estatístico e tipster profissional de futebol do 'FutBet VIP'.
    Pesquise ou identifique os 4 principais jogos reais de futebol marcados para o dia de HOJE ({today_str}).

    ESTRUTURA OBRIGATÓRIA DA RESPOSTA (Use formatação Markdown do Telegram e Emojis):

    ⚽ *FUTBET VIP - PALPITES DE HOJE ({today_str})* ⚽

    ━━━━━ 🛡️ *ALTA PROBABILIDADE (SEGUROS)* ━━━━━

    1️⃣ 🏆 *[Nome da Liga/Campeonato]*
    🆚 *[Equipa Casa] vs [Equipa Fora]*
    ⏰ Horário: [HH:MM]
    🎯 *Palpite:* [Mercado e Seleção]
    📊 Odd Estimada: [Ex: 1.45] | Confiança: [Ex: 88%]
    💡 *Análise:* [Uma frase curta com dado estatístico]

    2️⃣ 🏆 *[Nome da Liga/Campeonato]*
    🆚 *[Equipa Casa] vs [Equipa Fora]*
    ⏰ Horário: [HH:MM]
    🎯 *Palpite:* [Mercado e Seleção]
    📊 Odd Estimada: [Ex: 1.52] | Confiança: [Ex: 85%]
    💡 *Análise:* [Uma frase curta com dado estatístico]

    ━━━━━ 🚀 *VALOR / ODDS MAIS ALTAS* ━━━━━

    3️⃣ 🏆 *[Nome da Liga/Campeonato]*
    🆚 *[Equipa Casa] vs [Equipa Fora]*
    ⏰ Horário: [HH:MM]
    🎯 *Palpite:* [Mercado e Seleção]
    📊 Odd Estimada: [Ex: 1.95] | Confiança: [Ex: 72%]
    💡 *Análise:* [Uma frase curta com dado estatístico]

    4️⃣ 🏆 *[Nome da Liga/Campeonato]*
    🆚 *[Equipa Casa] vs [Equipa Fora]*
    ⏰ Horário: [HH:MM]
    🎯 *Palpite:* [Mercado e Seleção]
    📊 Odd Estimada: [Ex: 2.10] | Confiança: [Ex: 68%]
    💡 *Análise:* [Uma frase curta com dado estatístico]

    ━━━━━━━━━━━━━━━━━━━━━━━━━
    ⚠️ *Aposte sempre com responsabilidade e respeite a sua banca!*
    """
    
    try:
        response_text = generate_content_safe(prompt)
        bot.send_message(message.chat.id, response_text, parse_mode="Markdown")
    except Exception as e:
        # Resposta amigável e limpa se o servidor da AI estiver temporariamente indisponível
        fallback_msg = (
            f"⚽ *FUTBET VIP - PALPITES DE HOJE ({today_str})* ⚽\n\n"
            "⚠️ *Nota:* A IA está a processar uma grande quantidade de dados estatísticos de momento.\n\n"
            "Por favor, envie o comando `/palpites_hoje` novamente dentro de 30 a 60 segundos para receber a lista atualizada."
        )
        bot.send_message(message.chat.id, fallback_msg, parse_mode="Markdown")


@bot.message_handler(commands=['analisar'])
def send_analise(message):
    jogo = message.text.replace('/analisar', '').strip()
    if not jogo:
        bot.reply_to(message, "⚠️ *Por favor, indique as equipas.* Exemplo:\n`/analisar Benfica vs Porto`", parse_mode="Markdown")
        return
    
    bot.reply_to(message, f"⚽ *A analisar a partida:* `{jogo}`...", parse_mode="Markdown")
    
    prompt = f"""
    Analise o jogo de futebol '{jogo}' para apostas desportivas.
    Forneça a análise formatada com emojis e Markdown do Telegram:
    
    📊 *ANÁLISE DETALHADA: {jogo}*
    
    🏆 Campeonato: [Nome]
    📈 Probabilidade de Vitória: [Casa X% | Empate X% | Fora X%]
    ⚽ Média de Golos: [Ex: Mais de 2.5 golos]
    💡 *Sugestão Principal:* [Mercado + Seleção]
    📊 Odd Recomendada: [Ex: 1.75]
    
    📝 *Resumo do Confronto:* [2 frases justificando o palpite].
    """
    
    try:
        response_text = generate_content_safe(prompt)
        bot.send_message(message.chat.id, response_text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "❌ Não foi possível analisar esta partida no momento. Tente novamente em 1 minuto.")


# ==========================================
# 4. EXECUÇÃO DO BOT
# ==========================================
if __name__ == "__main__":
    print("🤖 A iniciar o Bot FutBet VIP...")
    
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Aviso ao remover webhook: {e}")

    while True:
        try:
            print("🟢 Bot online e pronto a responder!")
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"⚠️ Reconexão automática: {e}")
            time.sleep(10)
