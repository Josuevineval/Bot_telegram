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
    """ Chama a API do Gemini com retentativas automáticas """
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
# 4. GERADOR DE IMAGENS ESTILO TABELA LIMPA
# ==========================================
def gerar_imagem_tabela(titulo, jogos, odd_total):
    """
    Gera uma imagem estilizada em tabela limpa (fundo branco / texto escuro),
    incluindo Hora, Liga, Partida, Palpite e Cotação (Odd).
    """
    if not HAS_PILLOW:
        return None

    try:
        num_jogos = len(jogos)
        largura = 920
        altura_cabecalho = 80
        altura_linha_tabela = 40
        altura_rodape = 60
        margem = 20

        altura_total = altura_cabecalho + 40 + (num_jogos * altura_linha_tabela) + altura_rodape + (margem * 2)

        # Fundo Branco Puro (#FFFFFF)
        img = Image.new('RGB', (largura, altura_total), color='#FFFFFF')
        draw = ImageDraw.Draw(img)

        # Moldura Exterior em Cinza Elegante
        draw.rectangle([10, 10, largura - 10, altura_total - 10], outline='#CBD5E1', width=3)

        # Banner de Cabeçalho (Escuro para Destaque)
        draw.rectangle([20, 20, largura - 20, altura_cabecalho], fill='#0F172A')
        font = ImageFont.load_default()
        
        titulo_limpo = titulo.replace('*', '').replace('_', '').replace('`', '').upper()
        draw.text((margem + 15, 40), f"⚽ FUTBET VIP — {titulo_limpo}", fill='#F59E0B', font=font)

        # Cabeçalho da Tabela
        y_tabela = altura_cabecalho + 10
        draw.rectangle([20, y_tabela, largura - 20, y_tabela + 35], fill='#F1F5F9', outline='#E2E8F0')
        draw.text((30, y_tabela + 10), "HORA / LIGA", fill='#475569', font=font)
        draw.text((250, y_tabela + 10), "PARTIDA (MATCHES)", fill='#475569', font=font)
        draw.text((560, y_tabela + 10), "PALPITE (CHOICES)", fill='#475569', font=font)
        draw.text((790, y_tabela + 10), "ODD (VALUES)", fill='#475569', font=font)

        y = y_tabela + 35

        # Linhas dos Jogos
        for idx, jogo in enumerate(jogos):
            bg_cor = '#FFFFFF' if idx % 2 == 0 else '#F8FAFC'
            draw.rectangle([20, y, largura - 20, y + altura_linha_tabela], fill=bg_cor, outline='#F1F5F9')

            hora_liga = f"{jogo.get('hora', '')} | {jogo.get('liga', '')}"
            partida = jogo.get('jogo', '')
            palpite = jogo.get('palpite', '')
            odd = str(jogo.get('odd', ''))

            draw.text((30, y + 12), hora_liga[:26], fill='#334155', font=font)
            draw.text((250, y + 12), partida[:36], fill='#0F172A', font=font)
            draw.text((560, y + 12), palpite[:25], fill='#0284C7', font=font)
            draw.text((790, y + 12), odd, fill='#059669', font=font)

            y += altura_linha_tabela

        # Rodapé com ODD TOTAL
        draw.rectangle([20, y, largura - 20, y + altura_rodape], fill='#0F172A')
        draw.text((30, y + 20), "ODD TOTAL ACUMULADA:", fill='#FFFFFF', font=font)
        draw.text((760, y + 20), f"{odd_total}", fill='#10B981', font=font)

        buffer = io.BytesIO()
        buffer.name = 'bilhete_futbet.png'
        img.save(buffer, 'PNG')
        buffer.seek(0)
        return buffer
    except Exception as img_err:
        print(f"⚠️ Erro ao desenhar imagem da tabela: {img_err}")
        return None


# ==========================================
# 5. GERADOR E PARSER DE PROMPTS DA IA
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
        (Monte um bilhete especial acumulado com exatamente 12 a 15 jogos reais marcados para HOJE)
        JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
        ... (repita para até 15 jogos)
        ODD_TOTAL: [Soma/Produto total ex: 485.50]
        === FIM BILHETE ===
        """

    return f"""
    ATENÇÃO: HOJE É DIA {today_str}.
    Você é o Tipster Oficial do FutBet. Monte bilhetes com jogos reais que acontecem EXCLUSIVAMENTE HOJE ({today_str}). Não inclua jogos de ontem ou de amanhã.

    ESTRUTURA DE RESPOSTA OBRIGATÓRIA (Siga o formato exato com pipes |):

    === INICIO BILHETE ===
    TIPO: NORMAL
    TITULO: BILHETE NORMAL 1 (ODD ~5.00)
    ODD_ALVO: 5.00
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
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ODD_TOTAL: ~15.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: NORMAL
    TITULO: BILHETE NORMAL 3 (ODD ~50.00)
    ODD_ALVO: 50.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ODD_TOTAL: ~50.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: NORMAL
    TITULO: BILHETE NORMAL 4 (ODD ~100.00)
    ODD_ALVO: 100.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ODD_TOTAL: ~100.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: VIP
    TITULO: BILHETE VIP 1 (ODD ~10.00)
    ODD_ALVO: 10.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ODD_TOTAL: ~10.00
    === FIM BILHETE ===

    === INICIO BILHETE ===
    TIPO: VIP
    TITULO: BILHETE VIP 2 (ODD ~40.00)
    ODD_ALVO: 40.00
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    JOGO: [HH:MM] | [Liga] | [Casa vs Fora] | [Palpite] | [Odd]
    ODD_TOTAL: ~40.00
    === FIM BILHETE ===

    {instrucao_quinta}
    """


def extrair_e_processar_bilhetes(texto_gerado):
    """ Separa e estrutura os dados de cada bilhete gerado pela IA """
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
                        "odd": partes[4].strip() if len(partes) > 4 else "1.30"
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
    """ Envia cada bilhete com a sua imagem em tabela e o resumo em texto """
    for b in bilhetes:
        if apenas_tipo and b["tipo"] != apenas_tipo:
            continue

        # Gerar Imagem Tabela
        img_buffer = gerar_imagem_tabela(b["titulo"], b["jogos"], b["odd_total"])
        caption_txt = f"⚽ *FUTBET — {b['titulo']}*"

        if img_buffer:
            try:
                bot.send_photo(chat_id, photo=img_buffer, caption=caption_txt, parse_mode="Markdown")
            except Exception:
                bot.send_photo(chat_id, photo=img_buffer, caption=f"⚽ FUTBET — {b['titulo']}")

        # Enviar Texto Detalhado
        texto_detalhes = f"📋 *{b['titulo']}*\n"
        texto_detalhes += f"🗓️ *Data:* {datetime.date.today().strftime('%d/%m/%Y')} (Jogos de Hoje)\n\n"
        
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
                print("⏰ A gerar bilhetes automáticos para o Canal VIP...")
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
        "Palpites diários com tabelas claras e visíveis dos jogos de HOJE.\n\n"
        "📌 *Comandos Disponíveis:*\n"
        "👉 /palpites_normais — 4 Bilhetes Gratuitos (Odds 5, 15, 50, 100)\n"
        "👉 /palpites_vip — 2 Bilhetes VIP (Odds 10 e 40)\n"
        "👉 /super_quinta — Bilhete de Jogos Corridos (Odd 400+)\n"
        "👉 /palpites_hoje — Todos os Bilhetes de Hoje\n"
        "👉 /analisar <Jogo> — Analisar partida individual\n"
        "👉 /gestao — Regras de Gestão de Banca\n"
        "👉 /vip — Subscrição do Canal VIP"
    )
    enviar_mensagem_segura(message.chat.id, text, reply_to_id=message.message_id)


@bot.message_handler(commands=['palpites_normais'])
def send_normais(message):
    enviar_mensagem_segura(message.chat.id, "📊 *A gerar os 4 Bilhetes Normais de Hoje (Odds 5, 15, 50, 100)... Aguarde.*")
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
    enviar_mensagem_segura(message.chat.id, "🔥 *A gerar os 2 Bilhetes VIP de Hoje (Odds 10 e 40)... Aguarde.*")
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
    enviar_mensagem_segura(message.chat.id, "🚀 *A gerar o Bilhete Especial de Jogos Corridos (Até 15 jogos | Odd 400+)... Aguarde.*")
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
    enviar_mensagem_segura(message.chat.id, "⚽ *A analisar e desenhar as tabelas de TODOS os bilhetes do dia...*")
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
    
    enviar_mensagem_segura(message.chat.id, f"⚽ *A analisar a partida:* `{jogo}`...")
    
    prompt = f"""
    Analise o jogo '{jogo}' programado para HOJE.
    Formatado com emojis:
    📊 ANÁLISE DETALHADA: {jogo}
    🏆 Campeonato: [Nome]
    ⏰ Horário: [HH:MM]
    📈 Probabilidade: [Casa X% | Empate X% | Fora X%]
    ⚽ Média de Golos: [Ex: Mais de 2.5 golos]
    💡 Sugestão Principal: [Mercado + Seleção]
    📊 Odd Recomendada: [Ex: 1.75]
    📝 Resumo: [2 frases de justificativa técnica].
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
        "Acesso diário aos bilhetes exclusivos de Odd 10 e 40!\n\n"
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
      
