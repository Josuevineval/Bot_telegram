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
from google.genai import types

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
    return "Bot FutBet VIP com busca em Tempo Real está operacional!"

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

# Lista de modelos atualizados e ativos na API do Gemini
MODELS_TO_TRY = [
    'gemini-3.5-flash-lite', # Modelo recomendado na mensagem da API
    'gemini-2.5-flash',      # Modelo rápido para fallback
    'gemini-2.5-pro'         # Modelo avançado
]

def chamar_gemini_com_fallback(prompt):
    """ Chama a API do Gemini testando os modelos ativos com busca na web """
    if not client:
        raise Exception("A variável GEMINI_API_KEY não está configurada no Render.")
        
    last_err = None
    for model in MODELS_TO_TRY:
        try:
            config_busca = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
            
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config_busca
            )
            if response and response.text:
                return response.text
        except Exception as e:
            last_err = e
            print(f"⚠️ Erro ao tentar o modelo '{model}': {e}")
            time.sleep(2)
            
    raise Exception(f"Erro na IA: {last_err}")




# ==========================================
# 3. MÓDULO INTELIGENTE COM PESQUISA EM TEMPO REAL
# ==========================================
def chamar_gemini_com_fallback(prompt):
    """ Chama a API do Gemini ativando a busca de jogos em tempo real na Web """
    if not client:
        raise Exception("A variável GEMINI_API_KEY não está configurada no Render.")
        
    last_err = None
    for model in MODELS_TO_TRY:
        for tentativa in range(3):
            try:
                # Ativa o Google Search Grounding para consultar jogos ao vivo na web
                config_busca = types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
                
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config_busca
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                last_err = e
                print(f"⚠️ Tentativa {tentativa + 1} no modelo '{model}' falhou: {e}")
                time.sleep(2)
    raise Exception(f"Erro na IA: {last_err}")


def enviar_mensagem_segura(chat_id, texto, reply_to_id=None):
    """ Envia mensagens prevenindo erros de formatação no Telegram """
    try:
        return bot.send_message(chat_id, texto, parse_mode="Markdown", reply_to_message_id=reply_to_id)
    except Exception:
        try:
            return bot.send_message(chat_id, texto, reply_to_message_id=reply_to_id)
        except Exception as e2:
            print(f"❌ Erro ao enviar mensagem para {chat_id}: {e2}")
            return None


# ==========================================
# 4. GERADOR DE IMAGENS EM CARTÕES DE ALTA VISIBILIDADE
# ==========================================
def gerar_imagem_tabela(titulo, jogos, odd_total):
    """
    Gera uma imagem estilizada em cartões verticais com fonte grande.
    Fundo Claro de alta legibilidade em qualquer dispositivo móvel.
    """
    if not HAS_PILLOW:
        return None

    try:
        largura = 1000
        
        try:
            font_titulo = ImageFont.load_default(size=28)
            font_bold = ImageFont.load_default(size=22)
            font_normal = ImageFont.load_default(size=20)
            font_sub = ImageFont.load_default(size=18)
        except TypeError:
            font_titulo = font_bold = font_normal = font_sub = ImageFont.load_default()

        altura_header = 100
        altura_card = 95
        espaco_card = 14
        altura_footer = 90
        margem = 30

        num_jogos = len(jogos)
        altura_total = altura_header + (num_jogos * (altura_card + espaco_card)) + altura_footer + 40

        # Fundo Cinza Claro
        img = Image.new('RGB', (largura, altura_total), color='#F1F5F9')
        draw = ImageDraw.Draw(img)

        # Cabeçalho Escuro
        draw.rectangle([margem, 20, largura - margem, altura_header], fill='#0F172A')
        titulo_limpo = titulo.replace('*', '').replace('_', '').replace('`', '').upper()
        draw.text((margem + 20, 35), f"⚽ FUTBET VIP — {titulo_limpo}", fill='#F59E0B', font=font_titulo)

        y = altura_header + 20

        # Cartões de cada partida
        for idx, jogo in enumerate(jogos):
            draw.rectangle([margem, y, largura - margem, y + altura_card], fill='#FFFFFF', outline='#CBD5E1', width=2)
            
            hora_liga = f"⏰ {jogo.get('hora', '')}   |   🏆 {jogo.get('liga', '')}"
            draw.text((margem + 20, y + 12), hora_liga, fill='#64748B', font=font_sub)

            partida = f"⚔️  {jogo.get('jogo', '')}"
            draw.text((margem + 20, y + 38), partida, fill='#0F172A', font=font_bold)

            palpite = f"💡 Palpite: {jogo.get('palpite', '')}"
            odd_str = f"Odd: {jogo.get('odd', '')}"
            draw.text((margem + 20, y + 65), palpite, fill='#2563EB', font=font_normal)
            draw.text((largura - margem - 180, y + 65), odd_str, fill='#059669', font=font_bold)

            y += altura_card + espaco_card

        # Rodapé
        draw.rectangle([margem, y, largura - margem, y + altura_footer], fill='#0F172A')
        draw.text((margem + 20, y + 28), "🎯 ODD TOTAL ACUMULADA:", fill='#FFFFFF', font=font_titulo)
        draw.text((largura - margem - 220, y + 28), f"{odd_total}", fill='#10B981', font=font_titulo)

        buffer = io.BytesIO()
        buffer.name = 'bilhete_futbet.png'
        img.save(buffer, 'PNG', quality=95)
        buffer.seek(0)
        return buffer
    except Exception as img_err:
        print(f"⚠️ Erro ao desenhar imagem: {img_err}")
        return None


# ==========================================
# 5. GERADOR E PARSER DE PROMPTS
# ==========================================
def gerar_prompt_palpites(incluir_super_quinta=False):
    today_str = datetime.date.today().strftime("%d/%m/%Y")
    dia_semana = datetime.date.today().weekday() # 3 representa Quinta-feira
    
    instrucao_quinta = ""
    if incluir_super_quinta or dia_semana == 3:
        instrucao_quinta = """
        === INICIO BILHETE ===
        TIPO: QUINTA_FEIRA
        TITULO: SUPER QUINTA - JOGOS CORRIDOS (ODD 400+)
        ODD_ALVO: 450.00
        (Pesquise na Web e monte um bilhete especial com 12 a 15 jogos reais que ocorrem HOJE)
        JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
        ...
        ODD_TOTAL: ~450.00
        === FIM BILHETE ===
        """

    return f"""
    INSTRUÇÃO DE BUSCA EM TEMPO REAL:
    Consulte a internet (Flashscore, SofaScore, BetMines) para encontrar a lista de jogos de futebol REAIS e OFICIAIS agendados para HOJE ({today_str}).
    É estritamente proibido inventar jogos ou utilizar datas passadas/futuras.

    ESTRUTURA DE REDUÇÃO DE RISCO:
    Monte os bilhetes combinando entre 8 a 12 jogos ultrasseguros de hoje (Odds individuais de 1.15 a 1.28) para garantir alta taxa de acerto e atingir a Odd Total desejada.

    FORMATO OBRIGATÓRIO (Respeite rigorosamente as barras verticais |):

    === INICIO BILHETE ===
    TIPO: NORMAL
    TITULO: BILHETE NORMAL 1 (ODD ~5.00)
    ODD_ALVO: 5.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ODD_TOTAL: ~5.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: NORMAL
    TITULO: BILHETE NORMAL 2 (ODD ~15.00)
    ODD_ALVO: 15.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ...
    ODD_TOTAL: ~15.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: NORMAL
    TITULO: BILHETE NORMAL 3 (ODD ~50.00)
    ODD_ALVO: 50.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ...
    ODD_TOTAL: ~50.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: NORMAL
    TITULO: BILHETE NORMAL 4 (ODD ~100.00)
    ODD_ALVO: 100.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ...
    ODD_TOTAL: ~100.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: VIP
    TITULO: BILHETE VIP 1 (ODD ~10.00)
    ODD_ALVO: 10.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ...
    ODD_TOTAL: ~10.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: VIP
    TITULO: BILHETE VIP 2 (ODD ~40.00)
    ODD_ALVO: 40.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ...
    ODD_TOTAL: ~40.00
    === FIM BILHETE ===

    {instrucao_quinta}
    """


def extrair_e_processar_bilhetes(texto_gerado):
    """ Separa e estrutura os dados de cada bilhete """
    padrao = r"=== INICIO BILHETE ===(.*?)=== FIM BILHETE ==="
    blocos = re.findall(padrao, texto_gerado, re.DOTALL)
    
    bilhetes = []
    for bloco in blocos:
        linhas = [l.strip() for l in bloco.strip().split('\n') if l.strip()]
        
        tipo = "NORMAL"
        titulo = "BILHETE FUTBET"
        odd_total = "1.00"
        jogos = []

        for linha in linhas:
            if linha.startswith("TIPO:"):
                tipo = linha.replace("TIPO:", "").strip()
            elif linha.startswith("TITULO:"):
                titulo = linha.replace("TITULO:", "").strip()
            elif linha.startswith("ODD_TOTAL:"):
                odd_total = linha.replace("ODD_TOTAL:", "").strip()
            elif linha.startswith("JOGO:"):
                partes = linha.replace("JOGO:", "").split('|')
                if len(partes) >= 4:
                    jogos.append({
                        "hora": partes[0].strip(),
                        "liga": partes[1].strip(),
                        "jogo": partes[2].strip(),
                        "palpite": partes[3].strip(),
                        "odd": partes[4].strip() if len(partes) > 4 else "1.20"
                    })

        if jogos:
            bilhetes.append({
                "tipo": tipo,
                "titulo": titulo,
                "odd_total": odd_total,
                "jogos": jogos
            })
            
    return bilhetes


def enviar_bilhetes(chat_id, bilhetes, apenas_tipo=None):
    """ Envia cada bilhete com a imagem estilizada e resumo textual """
    for b in bilhetes:
        if apenas_tipo and b["tipo"] != apenas_tipo:
            continue

        img_buffer = gerar_imagem_tabela(b["titulo"], b["jogos"], b["odd_total"])
        caption_txt = f"⚽ *FUTBET — {b['titulo']}*"

        if img_buffer:
            try:
                bot.send_photo(chat_id, photo=img_buffer, caption=caption_txt, parse_mode="Markdown")
            except Exception:
                bot.send_photo(chat_id, photo=img_buffer, caption=f"⚽ FUTBET — {b['titulo']}")

        texto_detalhes = f"📋 *{b['titulo']}*\n"
        texto_detalhes += f"🗓️ *Data:* {datetime.date.today().strftime('%d/%m/%Y')} (Jogos em Tempo Real)\n\n"
        
        for idx, j in enumerate(b["jogos"], 1):
            texto_detalhes += f"{idx}. ⏰ *{j['hora']}* [{j['liga']}]\n"
            texto_detalhes += f"   🏟️ {j['jogo']} ➔ *{j['palpite']}* (Odd {j['odd']})\n"
            
        texto_detalhes += f"\n🎯 *ODD TOTAL:* `{b['odd_total']}`"
        
        enviar_mensagem_segura(chat_id, texto_detalhes)
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
                print("⏰ A pesquisar jogos ao vivo e enviar bilhetes diários...")
                if VIP_CHANNEL_ID and client:
                    prompt = gerar_prompt_palpites()
                    texto = chamar_gemini_com_fallback(prompt)
                    bilhetes = extrair_e_processar_bilhetes(texto)
                    
                    if bilhetes:
                        enviar_bilhetes(VIP_CHANNEL_ID, bilhetes, apenas_tipo="VIP")
                    print("✅ Bilhetes VIP diários enviados com sucesso!")
                posted_today = True
            elif agora.hour != 8:
                posted_today = False
        except Exception as e:
            print(f"⚠️ Erro no envio automático diário: {e}")
        time.sleep(30)

threading.Thread(target=agendador_diario, daemon=True).start()


# ==========================================
# 7. COMANDOS DO BOT DO TELEGRAM
# ==========================================

@bot.message_handler(commands=['start', 'ajuda', 'help'])
def send_welcome(message):
    text = (
        "⚽ *BEM-VINDO AO BOT FUTBET VIP!* 💎\n\n"
        "Palpites diários com consulta em tempo real aos jogos de HOJE.\n\n"
        "📌 *Comandos Disponíveis:*\n"
        "👉 /palpites_normais — 4 Bilhetes Gratuitos (Odds 5, 15, 50, 100)\n"
        "👉 /palpites_vip — 2 Bilhetes VIP (Odds 10 e 40)\n"
        "👉 /super_quinta — Bilhete de Jogos Corridos (Odd 400+)\n"
        "👉 /palpites_hoje — Todos os Bilhetes do Dia\n"
        "👉 /analisar <Jogo> — Analisar partida individual\n"
        "👉 /gestao — Regras de Gestão de Banca\n"
        "👉 /vip — Subscrição do Canal VIP"
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


@bot.message_handler(commands=['palpites_normais'])
def send_normais(message):
    enviar_mensagem_segura(message.chat.id, "🔍 *A pesquisar na Web os jogos reais de HOJE e a gerar 4 Bilhetes Normais... Aguarde.*")
    try:
        prompt = gerar_prompt_palpites()
        texto = chamar_gemini_com_fallback(prompt)
        bilhetes = extrair_e_processar_bilhetes(texto)
        if bilhetes:
            enviar_bilhetes(message.chat.id, bilhetes, apenas_tipo="NORMAL")
        else:
            enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao gerar bilhetes: {e}")


@bot.message_handler(commands=['palpites_vip'])
def send_vip(message):
    enviar_mensagem_segura(message.chat.id, "🔥 *A consultar jogos em tempo real e a gerar os 2 Bilhetes VIP (Odds 10 e 40)... Aguarde.*")
    try:
        prompt = gerar_prompt_palpites()
        texto = chamar_gemini_com_fallback(prompt)
        bilhetes = extrair_e_processar_bilhetes(texto)
        if bilhetes:
            enviar_bilhetes(message.chat.id, bilhetes, apenas_tipo="VIP")
        else:
            enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao gerar bilhetes VIP: {e}")


@bot.message_handler(commands=['super_quinta'])
def send_super_quinta(message):
    enviar_mensagem_segura(message.chat.id, "🚀 *A consultar jogos de hoje na Web e a gerar o Bilhete da Super Quinta (Odd 400+)... Aguarde.*")
    try:
        prompt = gerar_prompt_palpites(incluir_super_quinta=True)
        texto = chamar_gemini_com_fallback(prompt)
        bilhetes = extrair_e_processar_bilhetes(texto)
        bilhetes_quinta = [b for b in bilhetes if b["tipo"] == "QUINTA_FEIRA"]
        
        if bilhetes_quinta:
            enviar_bilhetes(message.chat.id, bilhetes_quinta)
        else:
            enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao gerar o bilhete da Super Quinta: {e}")


@bot.message_handler(commands=['palpites_hoje', 'palpites'])
def send_todos(message):
    enviar_mensagem_segura(message.chat.id, "⚽ *A fazer busca ao vivo na Web e a gerar TODOS os bilhetes do dia...*")
    try:
        prompt = gerar_prompt_palpites()
        texto = chamar_gemini_com_fallback(prompt)
        bilhetes = extrair_e_processar_bilhetes(texto)
        if bilhetes:
            enviar_bilhetes(message.chat.id, bilhetes)
        else:
            enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao gerar bilhetes: {e}")


@bot.message_handler(commands=['analisar'])
def send_analise(message):
    jogo = message.text.replace('/analisar', '').strip()
    if not jogo:
        enviar_mensagem_segura(message.chat.id, "⚠️ *Indique o jogo.* Exemplo:\n`/analisar Benfica vs Porto`")
        return
    
    enviar_mensagem_segura(message.chat.id, f"⚽ *A pesquisar dados ao vivo para:* `{jogo}`...")
    
    prompt = f"""
    Pesquise na Web informações em tempo real sobre o jogo de futebol '{jogo}' programado para HOJE.
    Forneça uma análise com o formato:
    📊 ANÁLISE DETALHADA: {jogo}
    🏆 Campeonato: [Nome]
    ⏰ Horário: [HH:MM]
    📈 Probabilidade: [Casa X% | Empate X% | Fora X%]
    ⚽ Média de Golos: [Ex: Mais de 2.5 golos]
    💡 Sugestão Principal: [Mercado + Seleção]
    📊 Odd Recomendada: [Ex: 1.75]
    📝 Resumo: [2 frases com justificativa técnica recente].
    """
    try:
        texto = chamar_gemini_com_fallback(prompt)
        enviar_mensagem_segura(message.chat.id, texto)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro na análise: {e}")


@bot.message_handler(commands=['gestao', 'gestão'])
def send_gestao(message):
    text = (
        "📊 *GESTÃO DE BANCA RECOMENDADA* 📊\n\n"
        "1️⃣ *Odd 5 a 10:* Apostar **2% a 3%** da banca.\n"
        "2️⃣ *Odd 15 a 50:* Apostar **1%** da banca.\n"
        "3️⃣ *Odd 100 ou Quinta-Feira (Odd 400+):* Apostar apenas moedas ou **0.1% a 0.2%**."
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


@bot.message_handler(commands=['vip'])
def send_vip_info(message):
    text = (
        "🔥 *CANAL VIP FUTBET* 🔥\n\n"
        "Acesso diário aos bilhetes exclusivos de Odd 10 e 40 com pesquisas ao vivo!\n\n"
        "📌 *Semanal:* 3.000 Kz\n"
        "📌 *Mensal:* 5.000 Kz\n\n"
        "Contacte o suporte oficial para ativar a sua subscrição."
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


# ==========================================
# 8. EXECUÇÃO DO BOT
# ==========================================
if __name__ == "__main__":
    print("🤖 A iniciar Bot FutBet VIP...")
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
