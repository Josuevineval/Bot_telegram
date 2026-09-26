import os
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
    return "Bot FutBet VIP está online e a funcionar!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Arranca o servidor Web numa thread secundária sem bloquear o bot
threading.Thread(target=run_flask, daemon=True).start()


# ==========================================
# 2. CONFIGURAÇÃO DAS CHAVES E DO BOT
# ==========================================
# Utiliza o token das variáveis do Render ou este token novo como padrão:
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8874128452:AAExQzgiLh-_YskfkPtrlKm41og_NN0F5Aw")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)


# ==========================================
# 3. COMANDOS DO BOT DO TELEGRAM
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = (
        "⚽ *Bem-vindo ao Bot FutBet VIP!*\n\n"
        "Escolha uma das opções abaixo:\n"
        "• /palpites_hoje - Receber análise e palpites do dia\n"
        "• /analisar <Jogo> - Analisar um jogo (Ex: `/analisar Real Madrid vs Barcelona`)\n"
        "• /gestao - Dicas de gestão de banca\n"
        "• /vip - Aceder ao nosso canal VIP"
    )
    bot.reply_to(message, text, parse_mode="Markdown")


@bot.message_handler(commands=['gestao'])
def send_gestao(message):
    text = (
        "📊 *Gestão de Banca Recomendada:*\n\n"
        "1. Use apenas 1% a 2% da sua banca por aposta (Unidade Fixa).\n"
        "2. Nunca tente recuperar perdas na emoção.\n"
        "3. Defina metas diárias de ganho (Stop Green) e limite de perda (Stop Loss)."
    )
    bot.reply_to(message, text, parse_mode="Markdown")


@bot.message_handler(commands=['vip'])
def send_vip(message):
    text = "🔥 *Aceda ao nosso Grupo/Canal VIP exclusivo:* https://t.me/seu_link_aqui"
    bot.reply_to(message, text)


@bot.message_handler(commands=['palpites_hoje'])
def send_palpites(message):
    bot.reply_to(message, "🔍 A pesquisar e a analisar os jogos de hoje com IA... Aguarde uns segundos.")
    try:
        prompt = "Forneça os melhores palpites de futebol para hoje com análises estatísticas sucintas, odds estimadas e nível de confiança."
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        bot.send_message(message.chat.id, response.text)
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao gerar palpites: {str(e)}")


@bot.message_handler(commands=['analisar'])
def send_analise(message):
    jogo = message.text.replace('/analisar', '').strip()
    if not jogo:
        bot.reply_to(message, "⚠️ Por favor, informe as equipas. Exemplo: `/analisar Benfica vs Porto`", parse_mode="Markdown")
        return
    
    bot.reply_to(message, f"⚽ A analisar a partida: *{jogo}*...", parse_mode="Markdown")
    try:
        prompt = f"Analise detalhadamente o jogo de futebol '{jogo}'. Forneça probabilidade de vitória, ambas marcam, golos esperados e sugestão de aposta."
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        bot.send_message(message.chat.id, response.text)
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao analisar o jogo: {str(e)}")


# ==========================================
# 4. INICIAR O BOT NO TELEGRAM
# ==========================================
if __name__ == "__main__":
    print("🤖 Bot FutBet VIP iniciado e pronto no Telegram!")
    bot.infinity_polling()
    
