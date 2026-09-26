import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from google import genai
from google.genai import types

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- SERVIDOR WEB SIMPLES (EXIGIDO PELO PLANO FREE DO RENDER) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot FutBet VIP Online!")

def iniciar_servidor_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# Inicia o servidor em segundo plano para o Render não dar erro
threading.Thread(target=iniciar_servidor_web, daemon=True).start()
# -----------------------------------------------------------------

# LEITURA SEGURA DAS CHAVES
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
Você é o FutBet VIP AI, um especialista em inteligência estatística de futebol, análise tática e automação para canais do Telegram. Sua missão é realizar pesquisas diárias no mercado esportivo, analisar dados probabilísticos das partidas e gerar palpites completos, profissionais e formatados para envio direto aos membros.

Sempre formate suas respostas utilizando Markdown simples compatível com o Telegram (use *negrito*, emojis e espaçamentos limpos).

Estrutura Padrão de Palpite:
🔥 *PALPITE VIP DO DIA - [NOME DA LIGA]*
⚔️ *Confronto:* [Time Casa] vs [Time Fora]
⏰ *Horário:* [Horário Local]

📊 *Análise Rápida:*
- Momento atual e contexto da partida.
- Fator chave (desfalques, mando de campo ou motivação).

🎯 *Entrada Recomendada:*
- *Mercado Principal:* [Ex: Vitória Casa / Over 2.5 Gols / Ambas Marcam]
- *Odd Estimada Mínima:* [Ex: 1.75+]
- *Nível de Confiança:* 🟢 Alto | 🟡 Médio | 🔴 Especulativo
- *Gestão de Banca:* [Ex: 1 a 2 unidades]

Nunca faça promessas irrealistas de 'lucro 100% garantido'. Enfatize a gestão de risco.
"""

def consultar_gemini(user_prompt: str, usar_busca_web: bool = True) -> str:
    try:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
        )
        if usar_busca_web:
            config.tools = [{"google_search": {}}]

        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=config
        )
        return response.text
    except Exception as e:
        logging.error(f"Erro na requisição da IA: {e}")
        return "⚠️ Ocorreu um erro ao pesquisar as estatísticas dos jogos. Tente novamente em instantes."

@bot.message_handler(commands=['start', 'ajuda'])
def send_welcome(message):
    texto = (
        "🔥 *Bem-vindo ao FutBet VIP AI Bot!*\n\n"
        "Sou o teu assistente inteligente para análise estatística de futebol e palpites diários.\n\n"
        "📌 *Comandos disponíveis:*\n"
        "🔹 `/palpites_hoje` - Gera os melhores palpites para os jogos do dia.\n"
        "🔹 `/analisar [Jogo]` - Análise detalhada de um confronto específico.\n"
        "🔹 `/vip` - Acessar o Canal VIP / Planos de Assinatura.\n"
        "🔹 `/gestao` - Regras fundamentais de Gestão de Banca."
    )
    bot.reply_to(message, texto, parse_mode='Markdown')

@bot.message_handler(commands=['palpites_hoje'])
def palpites_hoje(message):
    msg_espera = bot.reply_to(message, "🔍 *A pesquisar os jogos de hoje, estatísticas recentes e desfalques na web... Aguarde alguns segundos.*", parse_mode='Markdown')
    prompt_usuario = "Pesquise os jogos de futebol mais relevantes acontecendo hoje. Escolha os 3 melhores confrontos e gere palpites completos seguindo o formato padrão."
    resposta_ia = consultar_gemini(prompt_usuario, usar_busca_web=True)
    bot.edit_message_text(resposta_ia, chat_id=msg_espera.chat.id, message_id=msg_espera.message_id, parse_mode='Markdown')

@bot.message_handler(commands=['analisar'])
def analisar_jogo(message):
    termo = message.text.replace('/analisar', '').strip()
    if not termo:
        bot.reply_to(message, "⚠️ *Por favor, informe as equipes.* Exemplo: `/analisar Real Madrid vs Barcelona`", parse_mode='Markdown')
        return
    msg_espera = bot.reply_to(message, f"📊 *A compilar dados, H2H e desfalques para:* `{termo}`...", parse_mode='Markdown')
    prompt_usuario = f"Pesquise e faça uma análise estatística completa para a partida: {termo}. Traga os dados mais recentes, prováveis escalações e a melhor entrada para este jogo."
    resposta_ia = consultar_gemini(prompt_usuario, usar_busca_web=True)
    bot.edit_message_text(resposta_ia, chat_id=msg_espera.chat.id, message_id=msg_espera.message_id, parse_mode='Markdown')

@bot.message_handler(commands=['vip'])
def vip_info(message):
    texto = (
        "⭐ *ÁREA VIP - FUTBET ANALYTICS*\n\n"
        "Quer receber entradas ao vivo, alertas de valor e suporte direto?\n\n"
        "✅ 8 a 12 palpites filtrados por dia\n"
        "✅ Relatórios semanais de desempenho\n"
        "✅ Gestão de banca acompanhada\n\n"
        "📲 *Clique abaixo para garantir a sua vaga:* \n"
        "👉 [Entrar no Canal VIP](https://t.me/seu_link_aqui)"
    )
    bot.reply_to(message, texto, parse_mode='Markdown', disable_web_page_preview=True)

@bot.message_handler(commands=['gestao'])
def gestao_info(message):
    texto = (
        "🛡️ *REGRAS DE GESTÃO DE BANCA*\n\n"
        "1. *Unidade Padrão:* Nunca invista mais do que 1% a 3% da sua banca total numa única aposta.\n"
        "2. *Controle Emocional:* Perdas fazem parte do processo. Não tente 'recuperar' no mesmo dia aumentando a stake.\n"
        "3. *Visão de Longo Prazo:* Avalie a sua lucratividade ao fim de cada mês, não por dia.\n"
        "4. *Múltiplas:* Mantenha as apostas múltiplas restritas a no máximo 2 ou 3 seleções de alta confiança."
    )
    bot.reply_to(message, texto, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def responder_chat_geral(message):
    resposta_ia = consultar_gemini(f"O usuário perguntou: '{message.text}'. Responda de forma concisa focando em análises e estatísticas de futebol.", usar_busca_web=False)
    bot.reply_to(message, resposta_ia, parse_mode='Markdown')

if __name__ == '__main__':
    print("🤖 Bot FutBet VIP iniciado e pronto no Telegram!")
    bot.infinity_polling()
