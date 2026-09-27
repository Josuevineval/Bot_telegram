import os
import time
import datetime
import threading
import io
import sys
import re
from flask import Flask
import telebot
from google import genai

# Tenta importar Pillow para gerar as imagens dos bilhetes
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
    return "Bot FutBet está online, estável e operacional!"

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
    print("❌ ERRO CRÍTICO: TELEGRAM_TOKEN não configurado!")
    sys.exit(1)

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Apenas o modelo exigido pela API
MODELS_TO_TRY = ['gemini-3.8-flash']



# ==========================================
# 3. MÓDULO INTELIGENTE DE COMUNICAÇÃO (IA)
# ==========================================
def chamar_gemini_com_fallback(prompt):
    """ Chama a API do Gemini com retentativas e alternância automática de modelos """
    if not client:
        raise Exception("A variável GEMINI_API_KEY não está configurada no Render.")
        
    last_err = None
    for model in MODELS_TO_TRY:
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
                print(f"⚠️ Tentativa {tentativa + 1} no modelo '{model}' falhou: {e}")
                time.sleep(2)
    raise Exception(f"Erro na IA: {last_err}")


def enviar_mensagem_segura(chat_id, texto, reply_to_id=None):
    """ Envia mensagens com proteção contra erros de formatação Markdown """
    try:
        return bot.send_message(chat_id, texto, parse_mode="Markdown", reply_to_message_id=reply_to_id)
    except Exception as e:
        print(f"⚠️ Reenviando em texto simples (Erro Markdown): {e}")
        try:
            return bot.send_message(chat_id, texto, reply_to_message_id=reply_to_id)
        except Exception as e2:
            print(f"❌ Erro ao enviar mensagem para {chat_id}: {e2}")
            return None


# ==========================================
# 4. GERADOR DE IMAGEM INDIVIDUAL (FUNDO BRANCO)
# ==========================================
def gerar_imagem_bilhete_individual(titulo, conteudo_bilhete):
    """
    Gera uma imagem INDIVIDUAL para cada bilhete.
    Fundo: Branco (#FFFFFF)
    Texto: Preto / Escuro (#0F172A)
    """
    if not HAS_PILLOW:
        return None

    try:
        linhas = [l.strip() for l in conteudo_bilhete.strip().split('\n') if l.strip()]
        
        largura = 850
        altura_linha = 28
        margem = 40
        altura = max(520, len(linhas) * altura_linha + margem * 2 + 90)

        # Fundo Branco Puro (#FFFFFF)
        img = Image.new('RGB', (largura, altura), color='#FFFFFF')
        draw = ImageDraw.Draw(img)

        # Moldura exterior cinza suave
        draw.rectangle([10, 10, largura - 10, altura - 10], outline='#CBD5E1', width=3)

        # Caixa de Cabeçalho Escura para Contraste
        draw.rectangle([20, 20, largura - 20, 80], fill='#0F172A')
        
        titulo_limpo = titulo.replace('*', '').replace('_', '').replace('`', '').upper()
        font = ImageFont.load_default()
        draw.text((margem, 42), f"⚽ FUTBET - {titulo_limpo}", fill='#F59E0B', font=font)

        y = 105
        for linha in linhas:
            cor_texto = '#0F172A' # Texto Preto Padrão
            
            if "ODD TOTAL" in linha.upper():
                cor_texto = '#047857' # Verde Escuro para destaques de odd
            elif "━━━" in linha or "---" in linha:
                cor_texto = '#94A3B8' # Cinza

            linha_limpa = linha.replace('*', '').replace('_', '').replace('`', '')
            draw.text((margem, y), linha_limpa, fill=cor_texto, font=font)
            y += altura_linha

        # Rodapé com aviso
        draw.rectangle([20, altura - 45, largura - 20, altura - 20], fill='#F1F5F9')
        draw.text((margem, altura - 37), "⚠️ Aposte com responsabilidade | Gestão de Banca FutBet", fill='#475569', font=font)

        buffer = io.BytesIO()
        buffer.name = 'bilhete_futbet.png'
        img.save(buffer, 'PNG')
        buffer.seek(0)
        return buffer
    except Exception as img_err:
        print(f"⚠️ Erro ao desenhar imagem individual: {img_err}")
        return None


# ==========================================
# 5. ESTRUTURAÇÃO E PARSER DE PALPITES
# ==========================================
def gerar_prompt_palpites():
    today_str = datetime.date.today().strftime("%d/%m/%Y")
    return f"""
    Hoje é dia {today_str}.
    Atue como tipster profissional do 'FutBet'.
    Gere 4 bilhetes distintos organizados estritamente com os delimitadores '=== INICIO BILHETE ===' e '=== FIM BILHETE ==='.

    DIVISÃO DOS BILHETES:
    - 2 BILHETES NORMAIS (GRÁTIS)
    - 2 BILHETES VIP (EXCLUSIVOS)

    FORMATO OBRIGATÓRIO EXATO:

    === INICIO BILHETE ===
    📌 TÍTULO: PALPITE NORMAL 1 (ODD ~3.00)
    1. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.20)
    2. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.25)
    3. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.30)
    4. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.22)
    5. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.25)
    🎯 ODD TOTAL ACUMULADA: ~3.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    📌 TÍTULO: PALPITE NORMAL 2 (ODD ~5.00)
    1. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.30)
    2. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.35)
    3. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.28)
    4. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.32)
    5. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.25)
    🎯 ODD TOTAL ACUMULADA: ~5.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    📌 TÍTULO: PALPITE VIP 1 (ODD ~15.00)
    1. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.40)
    2. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.45)
    3. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.50)
    4. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.42)
    5. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.38)
    6. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.45)
    7. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.50)
    🎯 ODD TOTAL ACUMULADA: ~15.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    📌 TÍTULO: PALPITE VIP 2 (BOMBA ODD ~100.00)
    1. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.65)
    2. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.70)
    3. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.60)
    4. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.75)
    5. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.68)
    6. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.80)
    7. ⏰ [HH:MM] [Liga] - [Jogo] ➔ [Palpite] (Odd ~1.70)
    🎯 ODD TOTAL ACUMULADA: ~100.00
    === FIM BILHETE ===
    """


def extrair_bilhetes(texto_gerado):
    """ Separa a resposta da IA nos blocos individuais de cada bilhete """
    padrao = r"=== INICIO BILHETE ===(.*?)=== FIM BILHETE ==="
    blocos = re.findall(padrao, texto_gerado, re.DOTALL)
    
    bilhetes = []
    for bloco in blocos:
        bloco_str = bloco.strip()
        if not bloco_str:
            continue
        
        lines = bloco_str.split('\n')
        titulo = "BILHETE FUTBET"
        for l in lines:
            if "TÍTULO:" in l or "TITULO:" in l:
                titulo = l.replace("📌 TÍTULO:", "").replace("📌 TITULO:", "").strip()
                break
        
        bilhetes.append({
            "titulo": titulo,
            "texto": bloco_str
        })
    return bilhetes


def enviar_bilhetes_individuais(chat_id, bilhetes, apenas_vip=False, apenas_normais=False):
    """ Envia cada bilhete com a sua imagem em fundo branco de forma individual """
    for b in bilhetes:
        eh_vip = "VIP" in b["titulo"].upper() or "BOMBA" in b["titulo"].upper()
        
        if apenas_vip and not eh_vip:
            continue
        if apenas_normais and eh_vip:
            continue

        # Gerar imagem individual em fundo branco
        img_buffer = gerar_imagem_bilhete_individual(b["titulo"], b["texto"])
        caption_txt = f"⚽ *FUTBET - {b['titulo']}*"
        
        if img_buffer:
            try:
                bot.send_photo(chat_id, photo=img_buffer, caption=caption_txt, parse_mode="Markdown")
            except Exception:
                bot.send_photo(chat_id, photo=img_buffer, caption=f"⚽ FUTBET - {b['titulo']}")
        
        enviar_mensagem_segura(chat_id, f"📋 *DETALHES DO BILHETE:*\n\n{b['texto']}")
        time.sleep(1)


# ==========================================
# 6. ENVIO AUTOMÁTICO DIÁRIO PARA O CANAL VIP
# ==========================================
def agendador_diario():
    posted_today = False
    while True:
        try:
            agora = datetime.datetime.now()
            if agora.hour == 8 and agora.minute == 0 and not posted_today:
                print("⏰ A enviar bilhetes diários automáticos para o Canal VIP...")
                if VIP_CHANNEL_ID and client:
                    prompt = gerar_prompt_palpites()
                    texto = chamar_gemini_com_fallback(prompt)
                    bilhetes = extrair_bilhetes(texto)
                    
                    if bilhetes:
                        enviar_bilhetes_individuais(VIP_CHANNEL_ID, bilhetes, apenas_vip=True)
                    print("✅ Bilhetes VIP publicados no canal!")
                posted_today = True
            elif agora.hour != 8:
                posted_today = False
        except Exception as e:
            print(f"⚠️ Erro no envio automático VIP: {e}")
        time.sleep(30)

threading.Thread(target=agendador_diario, daemon=True).start()


# ==========================================
# 7. COMANDOS DO BOT DO TELEGRAM
# ==========================================

@bot.message_handler(commands=['start', 'ajuda', 'help'])
def send_welcome(message):
    text = (
        "⚽ *BEM-VINDO AO BOT FUTBET!* 💎\n\n"
        "O seu assistente inteligente para palpites e bilhetes de futebol.\n\n"
        "📌 *Comandos Disponíveis:*\n"
        "👉 /palpites_normais — Ver Palpites Gratuitos / Normais\n"
        "👉 /palpites_vip — Ver Palpites VIP e Exclusivos\n"
        "👉 /palpites_hoje — Gerar TODOS os Bilhetes (Normais + VIP)\n"
        "👉 /analisar <Jogo> — Analisar uma partida individual\n"
        "👉 /gestao — Regras de Gestão de Banca\n"
        "👉 /vip — Informações e Acesso ao Canal VIP"
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


@bot.message_handler(commands=['palpites_normais', 'normais'])
def send_normais(message):
    enviar_mensagem_segura(message.chat.id, "🟢 *A analisar os Palpites Normais e a desenhar as imagens em fundo branco... Aguarde.*")
    try:
        prompt = gerar_prompt_palpites()
        texto = chamar_gemini_com_fallback(prompt)
        bilhetes = extrair_bilhetes(texto)
        if bilhetes:
            enviar_bilhetes_individuais(message.chat.id, bilhetes, apenas_normais=True)
        else:
            enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao gerar palpites: {e}")


@bot.message_handler(commands=['palpites_vip', 'vip_palpites'])
def send_vip_palpites(message):
    enviar_mensagem_segura(message.chat.id, "🔥 *A analisar os Palpites VIP e a desenhar as imagens em fundo branco... Aguarde.*")
    try:
        prompt = gerar_prompt_palpites()
        texto = chamar_gemini_com_fallback(prompt)
        bilhetes = extrair_bilhetes(texto)
        if bilhetes:
            enviar_bilhetes_individuais(message.chat.id, bilhetes, apenas_vip=True)
        else:
            enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao gerar palpites VIP: {e}")


@bot.message_handler(commands=['palpites_hoje', 'palpites'])
def send_todos_palpites(message):
    enviar_mensagem_segura(message.chat.id, "⚽ *A preparar todos os Bilhetes (Normais + VIP) com imagens individuais em fundo branco...*")
    try:
        prompt = gerar_prompt_palpites()
        texto = chamar_gemini_com_fallback(prompt)
        bilhetes = extrair_bilhetes(texto)
        if bilhetes:
            enviar_bilhetes_individuais(message.chat.id, bilhetes)
        else:
            enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao gerar palpites: {e}")


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
        enviar_mensagem_segura(message.chat.id, f"❌ Erro na análise: {e}")


@bot.message_handler(commands=['gestao', 'gestão'])
def send_gestao(message):
    text = (
        "📊 *REGRAS DE GESTÃO DE BANCA FUTBET* 📊\n\n"
        "1️⃣ *Palpites Normais:* Entrar com **2% a 3%** da banca.\n"
        "2️⃣ *Palpites VIP (Odd 15+):* Entrar com **1%** da banca.\n"
        "3️⃣ *Palpite Bomba VIP (Odd 100+):* Entrar com **0.2% a 0.5%** da banca."
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


@bot.message_handler(commands=['vip'])
def send_vip_info(message):
    text = (
        "🔥 *CANAL VIP FUTBET* 🔥\n\n"
        "Receba diariamente palpites de alta probabilidade e bilhetes alavancados!\n\n"
        "💎 *PLANOS DE SUBSCRIÇÃO:*\n"
        "📌 *Subscrição Semanal:* 3.000 Kz\n"
        "📌 *Subscrição Mensal:* 5.000 Kz\n\n"
        "📱 *Pagamento via Express / BAI Directo*\n\n"
        "Contacte o suporte oficial para ativar o seu acesso."
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


# ==========================================
# 8. EXECUÇÃO DO BOT
# ==========================================
if __name__ == "__main__":
    print("🤖 A iniciar Bot FutBet...")
    try:
        bot.remove_webhook(drop_pending_updates=True)
        time.sleep(1)
    except Exception as e:
        print(f"Aviso webhook: {e}")

    while True:
        try:
            print("🟢 Bot operacional e a escutar mensagens!")
            bot.infinity_polling(timeout=20, long_polling_timeout=20, skip_pending=True)
        except Exception as e:
            print(f"⚠️ Instabilidade no polling: {e}. A reconectar em 5 segundos...")
            time.sleep(5)
