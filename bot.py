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
# 1. SERVIDOR FLASK (HEALTH CHECK PARA O RENDER)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot FutBet VIP 100% Operacional (Gemini 3.x Anti-Silêncio Ativo)"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()


# ==========================================
# 2. CONFIGURAÇÃO DE VARIÁVEIS DE AMBIENTE
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FREE_CHANNEL_ID = os.environ.get("FREE_CHANNEL_ID")
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID")

if not TELEGRAM_TOKEN:
    print("❌ ERRO CRÍTICO: TELEGRAM_TOKEN não configurado!")
    sys.exit(1)

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Cache em memória para armazenar os palpites e o texto bruto do dia
CACHE_DIARIO = {
    "data": None,
    "bilhetes": [],
    "texto_raw": None
}


# ==========================================
# 3. ENGINE ANTI-ERRO DA IA (MODELOS GEMINI 3.X E FALLBACK)
# ==========================================
def chamar_gemini_com_fallback_profissional(prompt):
    """
    Executa chamadas à API do Gemini com:
    - Descoberta dinâmica de modelos para prevenir erros 404
    - Fallback em cadeia para garantir disponibilidade
    - Pausas progressivas para prevenir erros 429
    """
    if not client:
        raise Exception("A variável GEMINI_API_KEY não está configurada no Render.")

    # 1. Tenta obter a lista de modelos ativos diretamente da API do Google
    modelos_candidatos = []
    try:
        lista_api = client.models.list()
        for m in lista_api:
            nome = m.name.replace("models/", "")
            if ("flash" in nome or "pro" in nome or "3.5" in nome or "3.1" in nome) and "vision" not in nome:
                modelos_candidatos.append(nome)
    except Exception as err_list:
        print(f"⚠️ Não foi possível listar modelos automaticamente: {err_list}")

    # 2. Lista estática de modelos Gemini mais recentes (Servidores 3.x e 2.x)
    modelos_fallback_estatico = [
        'gemini-3.5-pro',            # Modelo Pro topo de gama atual
        'gemini-3.5-flash-lite',     # Modelo recomendado oficialmente para velocidade e cota
        'gemini-2.5-flash'           # Backup adicional de alta estabilidade
    ]
    
    for m in modelos_fallback_estatico:
        if m not in modelos_candidatos:
            modelos_candidatos.append(m)

    ultimo_erro = None

    # 3. Execução resiliente pelos modelos candidatos
    for model_name in modelos_candidatos:
        print(f"🔄 A testar o modelo: {model_name}...")
        
        for tentativa in range(2):
            try:
                config_busca = types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config_busca
                )
                
                if response and response.text:
                    print(f"✅ Sucesso com o modelo: {model_name}")
                    return response.text

            except Exception as e:
                err_str = str(e)
                ultimo_erro = e
                
                if "404" in err_str or "NOTFOUND" in err_str or "no longer available" in err_str:
                    print(f"❌ Modelo '{model_name}' indisponível (404). A saltar para o próximo...")
                    break 

                elif "429" in err_str or "RESOURCEEXHAUSTED" in err_str:
                    tempo_espera = 10 * (tentativa + 1)
                    print(f"⚠️ Cota atingida (429) em '{model_name}'. A aguardar {tempo_espera}s...")
                    time.sleep(tempo_espera)
                else:
                    print(f"⚠️️ Erro no modelo '{model_name}': {e}")
                    time.sleep(2)

    raise Exception(f"Não foi possível obter resposta da IA. Detalhe do último erro: {ultimo_erro}")


def enviar_mensagem_segura(chat_id, texto, reply_to_id=None):
    """ Envia mensagens com fallback para texto simples caso o Markdown falhe """
    try:
        return bot.send_message(chat_id, texto, parse_mode="Markdown", reply_to_message_id=reply_to_id)
    except Exception:
        try:
            texto_limpo = texto.replace('*', '').replace('_', '').replace('`', '')
            return bot.send_message(chat_id, texto_limpo, reply_to_message_id=reply_to_id)
        except Exception as e2:
            print(f"❌ Erro ao enviar mensagem para {chat_id}: {e2}")
            return None


# ==========================================
# 4. GERADOR DE IMAGENS EM CARTÕES VISÍVEIS
# ==========================================
def gerar_imagem_tabela(titulo, jogos, odd_total):
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

        img = Image.new('RGB', (largura, altura_total), color='#F1F5F9')
        draw = ImageDraw.Draw(img)

        draw.rectangle([margem, 20, largura - margem, altura_header], fill='#0F172A')
        titulo_limpo = titulo.replace('*', '').replace('_', '').replace('`', '').upper()
        draw.text((margem + 20, 35), f"⚽ FUTBET — {titulo_limpo}", fill='#F59E0B', font=font_titulo)

        y = altura_header + 20

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

        draw.rectangle([margem, y, largura - margem, y + altura_footer], fill='#0F172A')
        draw.text((margem + 20, y + 28), "🎯 ODD TOTAL ACUMULADA:", fill='#FFFFFF', font=font_titulo)
        draw.text((largura - margem - 220, y + 28), f"{odd_total}", fill='#10B981', font=font_titulo)

        buffer = io.BytesIO()
        buffer.name = 'bilhete_futbet.png'
        img.save(buffer, 'PNG', quality=95)
        buffer.seek(0)
        return buffer
    except Exception as img_err:
        print(f"⚠️ Erro ao gerar imagem do bilhete: {img_err}")
        return None


# ==========================================
# 5. GERADOR E PARSER DE PROMPTS
# ==========================================
def gerar_prompt_palpites(incluir_super_quinta=False):
    today_str = datetime.date.today().strftime("%d/%m/%Y")
    
    instrucao_quinta = ""
    if incluir_super_quinta:
        instrucao_quinta = """
        === INICIO BILHETE ===
        TIPO: QUINTA_FEIRA
        TITULO: SUPER QUINTA - JOGOS CORRIDOS (ODD 400+)
        ODD_ALVO: 450.00
        JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
        ...
        ODD_TOTAL: ~450.00
        === FIM BILHETE ===
        """

    return f"""
    SITUAÇÃO: HOJE É DIA {today_str}.
    Consulte a internet (FlashScore, BetMines, SofaScore) para obter partidas oficiais EXCLUSIVAMENTE de HOJE ({today_str}).

    ESTRUTURA DOS BILHETES:

    === INICIO BILHETE ===
    TIPO: NORMAL
    TITULO: BILHETE NORMAL 1 (ODD ~5.00)
    ODD_ALVO: 5.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ... (8 a 10 jogos)
    ODD_TOTAL: ~5.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: NORMAL
    TITULO: BILHETE NORMAL 2 (ODD ~15.00)
    ODD_ALVO: 15.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ... (8 a 10 jogos)
    ODD_TOTAL: ~15.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: VIP
    TITULO: BILHETE VIP 1 (ODD ~10.00)
    ODD_ALVO: 10.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ... (8 a 10 jogos)
    ODD_TOTAL: ~10.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: VIP
    TITULO: BILHETE VIP 2 (ODD ~40.00)
    ODD_ALVO: 40.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ... (10 a 12 jogos)
    ODD_TOTAL: ~40.00
    === FIM BILHETE ===

    {instrucao_quinta}
    """


def extrair_e_processar_bilhetes(texto_gerado):
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


def obter_ou_gerar_bilhetes_diarios():
    """ Garante consulta única à API por dia, utilizando cache em memória """
    hoje = datetime.date.today().strftime("%Y-%m-%d")
    
    if CACHE_DIARIO["data"] == hoje and (CACHE_DIARIO["bilhetes"] or CACHE_DIARIO["texto_raw"]):
        return CACHE_DIARIO["bilhetes"], CACHE_DIARIO["texto_raw"]

    is_quinta = (datetime.date.today().weekday() == 3)
    prompt = gerar_prompt_palpites(incluir_super_quinta=is_quinta)
    texto = chamar_gemini_com_fallback_profissional(prompt)
    bilhetes = extrair_e_processar_bilhetes(texto)

    CACHE_DIARIO["data"] = hoje
    CACHE_DIARIO["bilhetes"] = bilhetes
    CACHE_DIARIO["texto_raw"] = texto

    return bilhetes, texto


def enviar_bilhetes(chat_id, bilhetes, raw_text=None, apenas_tipo=None):
    """ Transmite os bilhetes formatados em imagem e texto. Se o parser falhar, envia o texto direto para EVITAR SILÊNCIO. """
    enviados = 0
    if bilhetes:
        for b in bilhetes:
            if apenas_tipo and b["tipo"] != apenas_tipo:
                continue

            enviados += 1
            img_buffer = gerar_imagem_tabela(b["titulo"], b["jogos"], b["odd_total"])
            caption_txt = f"⚽ *FUTBET — {b['titulo']}*"

            if img_buffer:
                try:
                    bot.send_photo(chat_id, photo=img_buffer, caption=caption_txt, parse_mode="Markdown")
                except Exception as e_img:
                    print(f"⚠️ Erro envio imagem: {e_img}")
                    try:
                        bot.send_photo(chat_id, photo=img_buffer, caption=f"⚽ FUTBET — {b['titulo']}")
                    except Exception:
                        pass

            texto_detalhes = f"📋 *{b['titulo']}*\n"
            texto_detalhes += f"🗓️ *Data:* {datetime.date.today().strftime('%d/%m/%Y')} (Jogos de Hoje)\n\n"
            
            for idx, j in enumerate(b["jogos"], 1):
                texto_detalhes += f"{idx}. ⏰ *{j['hora']}* [{j['liga']}]\n"
                texto_detalhes += f"   🏟️ {j['jogo']} ➔ *{j['palpite']}* (Odd {j['odd']})\n"
                
            texto_detalhes += f"\n🎯 *ODD TOTAL:* `{b['odd_total']}`"
            
            enviar_mensagem_segura(chat_id, texto_detalhes)
            time.sleep(1)

    # ANTI-SILÊNCIO: Se o parser não encontrou bilhetes no formato estrito, envia o texto bruto gerado pela IA
    if enviados == 0 and raw_text:
        print("⚠️ Parser de bilhetes estruturados não encontrou correspondência. Enviando resposta direta em texto...")
        enviar_mensagem_segura(chat_id, raw_text)


# ==========================================
# 6. AGENDADOR DIÁRIO AUTOMÁTICO (08:00 AM)
# ==========================================
def rotina_postagem_diaria():
    posted_today = False
    while True:
        try:
            agora = datetime.datetime.now()
            if agora.hour == 8 and agora.minute == 0 and not posted_today:
                print("⏰ A iniciar postagem automática diária...")
                
                bilhetes, raw_text = obter_ou_gerar_bilhetes_diarios()
                
                if FREE_CHANNEL_ID:
                    print("📢 A enviar bilhetes Normais para o Canal Grátis...")
                    enviar_bilhetes(FREE_CHANNEL_ID, bilhetes, raw_text=raw_text, apenas_tipo="NORMAL")

                if VIP_CHANNEL_ID:
                    print("💎 A enviar bilhetes VIP para o Canal VIP...")
                    enviar_bilhetes(VIP_CHANNEL_ID, bilhetes, raw_text=raw_text, apenas_tipo="VIP")
                    
                    if agora.weekday() == 3:
                        enviar_bilhetes(VIP_CHANNEL_ID, bilhetes, raw_text=raw_text, apenas_tipo="QUINTA_FEIRA")

                posted_today = True
                print("✅ Postagens diárias concluídas!")
            elif agora.hour != 8:
                posted_today = False
        except Exception as e:
            print(f"⚠️ Erro na rotina diária: {e}")
        time.sleep(30)

threading.Thread(target=rotina_postagem_diaria, daemon=True).start()


# ==========================================
# 7. COMANDOS DO TELEGRAM
# ==========================================

@bot.message_handler(commands=['start', 'ajuda', 'help'])
def send_welcome(message):
    text = (
        "⚽ *BOT FUTBET VIP OPERACIONAL!* 💎\n\n"
        "Os palpites são enviados automaticamente todos os dias às 08:00 para os canais.\n\n"
        "📌 *Comandos Disponíveis:*\n"
        "👉 /palpites_normais ou /palpites_hoje — Ver bilhetes normais de hoje\n"
        "👉 /palpites_vip ou /vip — Ver bilhetes VIP de hoje\n"
        "👉 /super_quinta — Ver bilhete de Quinta-Feira\n"
        "👉 /analisar TimeA vs TimeB — Analisar jogo específico\n"
        "👉 /forcar_postagem — Postar nos canais agora mesmo (Admin)"
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


@bot.message_handler(commands=['palpites_normais', 'palpites_hoje'])
def send_normais(message):
    msg_wait = bot.reply_to(message, "📊 *A carregar os Bilhetes Normais de Hoje...*", parse_mode="Markdown")
    try:
        bilhetes, raw_text = obter_ou_gerar_bilhetes_diarios()
        enviar_bilhetes(message.chat.id, bilhetes, raw_text=raw_text, apenas_tipo="NORMAL")
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao obter palpites: {e}")
    finally:
        try:
            bot.delete_message(message.chat.id, msg_wait.message_id)
        except Exception:
            pass


@bot.message_handler(commands=['palpites_vip', 'vip'])
def send_vip(message):
    msg_wait = bot.reply_to(message, "🔥 *A carregar os Bilhetes VIP de Hoje...*", parse_mode="Markdown")
    try:
        bilhetes, raw_text = obter_ou_gerar_bilhetes_diarios()
        enviar_bilhetes(message.chat.id, bilhetes, raw_text=raw_text, apenas_tipo="VIP")
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao obter palpites VIP: {e}")
    finally:
        try:
            bot.delete_message(message.chat.id, msg_wait.message_id)
        except Exception:
            pass


@bot.message_handler(commands=['super_quinta'])
def send_super_quinta(message):
    msg_wait = bot.reply_to(message, "🚀 *A carregar o Bilhete da Super Quinta...*", parse_mode="Markdown")
    try:
        bilhetes, raw_text = obter_ou_gerar_bilhetes_diarios()
        bilhetes_quinta = [b for b in bilhetes if b["tipo"] == "QUINTA_FEIRA"]
        if bilhetes_quinta:
            enviar_bilhetes(message.chat.id, bilhetes_quinta, raw_text=raw_text)
        else:
            enviar_mensagem_segura(message.chat.id, "⚠️ O bilhete da Super Quinta está disponível apenas às quintas-feiras ou quando gerado.")
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro: {e}")
    finally:
        try:
            bot.delete_message(message.chat.id, msg_wait.message_id)
        except Exception:
            pass


@bot.message_handler(commands=['analisar'])
def cmd_analisar(message):
    partida = message.text.replace('/analisar', '').strip()
    if not partida:
        enviar_mensagem_segura(message.chat.id, "⚠️ Por favor, especifique o jogo. Exemplo:\n`/analisar Dinamarca vs Portugal`")
        return

    msg_wait = bot.reply_to(message, f"⚽ *A pesquisar dados ao vivo para:* {partida}...", parse_mode="Markdown")
    try:
        prompt = f"Pesquise dados ao vivo na internet sobre a partida de futebol: {partida}. Forneça momento recente dos times, desfalques importantes e uma sugestão clara de palpite com Odd estimada. Formate com emojis para Telegram."
        resposta = chamar_gemini_com_fallback_profissional(prompt)
        enviar_mensagem_segura(message.chat.id, resposta)
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro na análise: {e}")
    finally:
        try:
            bot.delete_message(message.chat.id, msg_wait.message_id)
        except Exception:
            pass


@bot.message_handler(commands=['forcar_postagem'])
def force_post(message):
    enviar_mensagem_segura(message.chat.id, "⚙️ *A iniciar envio imediato para os canais Grátis e VIP...*")
    try:
        bilhetes, raw_text = obter_ou_gerar_bilhetes_diarios()
        if FREE_CHANNEL_ID:
            enviar_bilhetes(FREE_CHANNEL_ID, bilhetes, raw_text=raw_text, apenas_tipo="NORMAL")
        if VIP_CHANNEL_ID:
            enviar_bilhetes(VIP_CHANNEL_ID, bilhetes, raw_text=raw_text, apenas_tipo="VIP")
        enviar_mensagem_segura(message.chat.id, "✅ Postagem forçada concluída com sucesso!")
    except Exception as e:
        enviar_mensagem_segura(message.chat.id, f"❌ Erro ao forçar postagem: {e}")


# =======
