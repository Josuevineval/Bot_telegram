import os
import time
import datetime
import threading
import io
import sys
from flask import Flask
import telebot
from google import genai

# Tenta importar Pillow para gerar as imagens estilizadas dos bilhetes
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


# ==========================================
# 1. SERVIDOR WEB EM SEGUNDO PLANO (RENDER)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot FutBet VIP está online, estável e operacional!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()


# ==========================================
# 2. CONFIGURAÇÃO DAS CHAVES E DO BOT
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID")

if not TELEGRAM_TOKEN:
    print("❌ ERRO CRÍTICO: TELEGRAM_TOKEN não foi configurado nas variáveis de ambiente do Render!")
    sys.exit(1)

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Modelo único mais recente e recomendado
MODELS_TO_TRY = ['gemini-3.8-flash']


# ==========================================
# 3. MÓDULO INTELIGENTE DE COMUNICAÇÃO (IA)
# ==========================================
def chamar_gemini_com_fallback(prompt):
    """ Chama a API da Google com retentativas automáticas no modelo gemini-3.8-flash """
    if not client:
        raise Exception("A variável GEMINI_API_KEY não está configurada no Render.")
        
    last_err = None
    model = MODELS_TO_TRY[0]
    
    # Tenta até 3 vezes em caso de pico temporário de carga (Erro 503)
    for tentativa in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            if response and response.text:
                return response.text
        except Exception as e:
            last_err = e
            err_msg = str(e)
            print(f"⚠️ Tentativa {tentativa + 1} no modelo '{model}' falhou: {err_msg}")
            time.sleep(2)
            
    raise Exception(f"Erro na IA ({model}): {last_err}")


def enviar_mensagem_segura(chat_id, texto, reply_to_id=None):
    """ 
    Garante o envio da mensagem. 
    Se o Telegram rejeitar devido a erro de formatação Markdown (Erro 400), envia em texto simples.
    """
    try:
        return bot.send_message(chat_id, texto, parse_mode="Markdown", reply_to_message_id=reply_to_id)
    except Exception as e:
        print(f"⚠️ Falha ao enviar com Markdown (Erro 400). A reenviar em texto simples: {e}")
        try:
            return bot.send_message(chat_id, texto, reply_to_message_id=reply_to_id)
        except Exception as e2:
            print(f"❌ Erro crítico ao enviar mensagem para {chat_id}: {e2}")
            return None


# ==========================================
# 4. GERADOR DE IMAGEM DESIGNER VIP (PILLOW)
# ==========================================
def gerar_imagem_bilhete(texto_palpites):
    """ Converte o texto dos bilhetes numa imagem estilizada Dark Mode VIP """
    if not HAS_PILLOW:
        return None

    try:
        linhas = texto_palpites.strip().split('\n')
        
        largura = 900
        altura_linha = 26
        margem = 40
        altura = max(750, len(linhas) * altura_linha + margem * 2 + 60)

        # Fundo Dark (#0F172A)
        img = Image.new('RGB', (largura, altura), color='#0F172A')
        draw = ImageDraw.Draw(img)

        # Faixa decorativa superior Verde Neon (#10B981)
        draw.rectangle([0, 0, largura, 14], fill='#10B981')

        # Retângulo de Cabeçalho
        draw.rectangle([20, 30, largura - 20, 85], fill='#1E293B', outline='#334155', width=2)
        draw.text((margem, 45), "⚽ FUTBET VIP - BILHETES DO DIA ⚽", fill='#F59E0B')

        y = 105
        font = ImageFont.load_default()

        for linha in linhas:
            if "FUTBET VIP" in linha:
                continue
                
            cor = '#F3F4F6' # Branco padrão
            
            if "BILHETE 1" in linha or "BILHETE 2" in linha:
                cor = '#10B981' # Verde
            elif "BILHETE 3" in linha:
                cor = '#3B82F6' # Azul
            elif "BILHETE 4" in linha or "BOMBA" in linha:
                cor = '#EF4444' # Vermelho
            elif "ODD TOTAL" in linha:
                cor = '#FACC15' # Amarelo Dourado
            elif "━━━" in linha or "---" in linha:
                cor = '#475569' # Cinza

            # Remove carateres de Markdown para desenhar texto limpo na imagem
            linha_limpa = linha.replace('*', '').replace('_', '').replace('`', '')
            draw.text((margem, y), linha_limpa, fill=cor, font=font)
            y += altura_linha

        buffer = io.BytesIO()
        buffer.name = 'bilhetes_futbet_vip.png'
        img.save(buffer, 'PNG')
        buffer.seek(0)
        return buffer
    except Exception as img_err:
        print(f"⚠️ Erro interno ao desenhar imagem: {img_err}")
        return None


def gerar_prompt_palpites():
    today_str = datetime.date.today().strftime("%d/%m/%Y")
    return f"""
    Hoje é dia {today_str}.
    Atue como um analista estatístico e tipster profissional de futebol do 'FutBet VIP'.
    Monte 4 BILHETES PRONTOS (MÚLTIPLAS) com jogos reais marcados para o dia de HOJE ({today_str}).
    Cada bilhete deve conter em média 10 seleções/jogos reais com horários e ligas reais.

    ESTRUTURA OBRIGATÓRIA DA RESPOSTA:

    ⚽ FUTBET VIP - BILHETES DO DIA ({today_str}) ⚽

    ━━━━━ 🟢 BILHETE 1: ODD ~5.00 (ALTA PROBABILIDADE) ━━━━━
    (Múltipla de 10 jogos ultra seguros - Odds individuais entre 1.15 e 1.25)
    1. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.18)
    2. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.16)
    3. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.20)
    4. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.17)
    5. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.19)
    6. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.15)
    7. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.22)
    8. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.18)
    9. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.20)
    10. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.16)
    🎯 ODD TOTAL ACUMULADA: ~5.00

    ━━━━━ 🟡 BILHETE 2: ODD ~10.00 (MODERADO / RETORNO SEGURO) ━━━━━
    (Múltipla de 10 jogos equilibrados - Odds individuais entre 1.22 e 1.32)
    1. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.25)
    ... (complete com 10 jogos)
    🎯 ODD TOTAL ACUMULADA: ~10.00

    ━━━━━ 🟠 BILHETE 3: ODD 50.00 A 100.00 (VALOR / ALAVANCAGEM) ━━━━━
    (Múltipla de 10 jogos com excelente valor - Odds individuais entre 1.45 e 1.60)
    1. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.50)
    ... (complete com 10 jogos)
    🎯 ODD TOTAL ACUMULADA: ~75.00

    ━━━━━ 💣 BILHETE 4: ODD ATÉ 500.00 (BOMBA VIP / JACKPOT) ━━━━━
    (Múltipla de 10 jogos para busca de cotação gigante - Odds individuais entre 1.80 e 2.10)
    1. ⏰ [HH:MM] [Liga] - [Casa vs Fora] ➔ [Palpite] (Odd ~1.90)
    ... (complete com 10 jogos)
    🎯 ODD TOTAL ACUMULADA: ~450.00

    ━━━━━━━━━━━━━━━━━━━━━━━━━
    ⚠️ Gestão de Banca: Aposte valores fracionados nas múltiplas maiores!
    """


# ==========================================
# 5. ENVIO AUTOMÁTICO DIÁRIO PARA O CANAL VIP
# ==========================================
def agendador_diario():
    posted_today = False
    while True:
        try:
            agora = datetime.datetime.now()
            if agora.hour == 8 and agora.minute == 0 and not posted_today:
                print("⏰ A executar envio automático de bilhetes para o Canal VIP...")
                if VIP_CHANNEL_ID and client:
                    prompt = gerar_prompt_palpites()
                    texto = chamar_gemini_com_fallback(prompt)
                    
                    imagem_buffer = gerar_imagem_bilhete(texto)
                    if imagem_buffer:
                        try:
                            bot.send_photo(VIP_CHANNEL_ID, photo=imagem_buffer, caption="🔥 *BILHETES VIP DO DIA DISPONÍVEIS!*", parse_mode="Markdown")
                        except Exception:
                            bot.send_photo(VIP_CHANNEL_ID, photo=imagem_buffer, caption="🔥 BILHETES VIP DO DIA DISPONÍVEIS!")
                    
                    enviar_mensagem_segura(VIP_CHANNEL_ID, texto)
                    print("✅ Bilhetes diários publicados com sucesso no Canal VIP!")
                posted_today = True
            elif agora.hour != 8:
                posted_today = False
        except Exception as e:
            print(f"⚠️ Erro no envio automático diário: {e}")
        time.sleep(30)

threading.Thread(target=agendador_diario, daemon=True).start()


# ==========================================
# 6. COMANDOS DO BOT DO TELEGRAM
# ==========================================

@bot.message_handler(commands=['start', 'ajuda', 'help'])
def send_welcome(message):
    text = (
        "⚽ *BEM-VINDO AO BOT FUTBET VIP!* 💎\n\n"
        "O seu assistente inteligente para bilhetes e múltiplas de futebol.\n\n"
        "📌 *Comandos Disponíveis:*\n"
        "👉 /palpites_hoje — Gerar os 4 Bilhetes Múltiplos do dia em imagem e texto\n"
        "👉 /analisar <Jogo> — Analisar uma partida individual (Ex: `/analisar Benfica vs Porto`)\n"
        "👉 /gestao ou /gestão — Regras de Gestão de Banca\n"
        "👉 /vip — Preços e acesso ao Canal VIP"
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


@bot.message_handler(commands=['gestao', 'gestão'])
def send_gestao(message):
    text = (
        "📊 *REGRAS DE GESTÃO DE BANCA FUTBET VIP* 📊\n\n"
        "1️⃣ *Múltiplas de Odd 5 e 10:* Entrar com **1% a 2%** da banca.\n"
        "2️⃣ *Múltiplas de Odd 50 a 100:* Entrar com **0.5%** da banca.\n"
        "3️⃣ *Múltipla Bomba (Odd até 500):* Entrar apenas com moedas ou **0.1%** da banca.\n"
        "4️⃣ *Disciplina:* Nunca tente recuperar perdas na emoção."
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


@bot.message_handler(commands=['vip'])
def send_vip(message):
    text = (
        "🔥 *CANAL VIP FUTBET* 🔥\n\n"
        "Receba diariamente às 08:00 AM bilhetes prontos em imagem e texto com 10 jogos nas melhores odds!\n\n"
        "💎 *PLANOS DE SUBSCRIÇÃO:*\n"
        "📌 *Subscrição Semanal:* 3.000 Kz\n"
        "📌 *Subscrição Mensal:* 5.000 Kz\n\n"
        "📱 *Pagamento via Express / BAI Directo*\n\n"
        "Para obter acesso imediato e convite privado, contacte o suporte oficial."
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


@bot.message_handler(commands=['palpites_hoje'])
def send_palpites(message):
    enviar_mensagem_segura(message.chat.id, "🔍 *A analisar jogos e a desenhar a imagem dos 4 bilhetes... Aguarde uns segundos.*")
    
    try:
        prompt = gerar_prompt_palpites()
        texto = chamar_gemini_com_fallback(prompt)
        
        try:
            imagem_buffer = gerar_imagem_bilhete(texto)
            if imagem_buffer:
                bot.send_photo(message.chat.id, photo=imagem_buffer, caption="🖼️ *BILHETES DO DIA - FUTBET VIP*", parse_mode="Markdown")
        except Exception as img_err:
            print(f"Aviso ao enviar imagem: {img_err}")

        enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        print(f"Erro ao gerar palpites: {e}")
        enviar_mensagem_segura(message.chat.id, f"❌ Não foi possível gerar os bilhetes no momento: {str(e)}")


@bot.message_handler(commands=['analisar'])
def send_analise(message):
    jogo = message.text.replace('/analisar', '').strip()
    if not jogo:
        enviar_mensagem_segura(message.chat.id, "⚠️ *Por favor, indique as equipas.* Exemplo:\n`/analisar Benfica vs Porto`")
        return
    
    enviar_mensagem_segura(message.chat.id, f"⚽ *A analisar a partida:* `{jogo}`...")
    
    prompt = f"""
    Analise o jogo de futebol '{jogo}' para apostas desportivas.
    Forneça a análise formatada com emojis:
    
    📊 ANÁLISE DETALHADA: {jogo}
    
    🏆 Campeonato: [Nome]
    📈 Probabilidade: [Casa X% | Empate X% | Fora X%]
    ⚽ Média de Golos: [Ex: Mais de 2.5 golos]
    💡 Sugestão Principal: [Mercado + Seleção]
    📊 Odd Recomendada: [Ex: 1.75]
    
    📝 Resumo: [2 frases justificando a análise].
    """
    
    try:
        texto = chamar_gemini_com_fallback(prompt)
        enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Não foi possível analisar a partida no momento: {str(e)}")


@bot.message_handler(commands=['postar_vip'])
def postar_vip_manual(message):
    if not VIP_CHANNEL_ID:
        enviar_mensagem_segura(message.chat.id, "⚠️ A variável `VIP_CHANNEL_ID` não está configurada no Render.")
        return
        
    enviar_mensagem_segura(message.chat.id, "🚀 *A gerar imagem e a publicar no Canal VIP...*")
    try:
        prompt = gerar_prompt_palpites()
        texto = chamar_gemini_com_fallback(prompt)
        
        try:
            imagem_buffer = gerar_imagem_bilhete(texto)
            if imagem_buffer:
                bot.send_photo(VIP_CHANNEL_ID, photo=imagem_buffer, caption="🔥 *BILHETES VIP DO DIA DISPONÍVEIS!*", parse_mode="Markdown")
        except Exception as img_err:
            print(f"Aviso ao publicar imagem no VIP: {img_err}")
            
        enviar_mensagem_segura(VIP_CHANNEL_ID, texto)
        enviar_mensagem_segura(message.chat.id, "✅ *Bilhetes e Imagem publicados no Canal VIP com sucesso!*")
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao publicar no VIP: {str(e)}")


# ==========================================
# 7. EXECUÇÃO CONTÍNUA E ESTÁVEL DO BOT
# ==========================================
if __name__ == "__main__":
    print("🤖 A iniciar o Bot FutBet VIP com o modelo gemini-3.8-flash...")
    
    # Remove webhooks anteriores para evitar conflitos de instâncias (Erro 409)
    try:
        bot.remove_webhook(drop_pending_updates=True)
        time.sleep(1)
    except Exception as e:
        print(f"Aviso ao limpar webhook: {e}")

    # Loop Infinito de Execução sem crash
    while True:
        try:
            print("🟢 Bot operacional e a escutar mensagens!")
            bot.infinity_polling(timeout=20, long_polling_timeout=20, skip_pending=True)
        except Exception as e:
            print(f"⚠️ Instabilidade detetada no polling: {e}. A reconectar em 5 segundos...")
            time.sleep(5)
