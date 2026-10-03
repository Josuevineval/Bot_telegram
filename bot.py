import datetime
import html
import io
import logging
import os
import re
import sys
import threading
import time
from zoneinfo import ZoneInfo

import telebot
from flask import Flask
from google import genai
from google.genai import types

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("futbet")


# ==========================================
# 1. CONFIGURAÇÃO
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FREE_CHANNEL_ID = os.environ.get("FREE_CHANNEL_ID")   # ex: -1001234567890
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID")     # ex: -1009876543210
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}

BOT_TZ = ZoneInfo(os.environ.get("BOT_TZ", "Europe/Lisbon"))   # fuso horário do bot
POST_HOUR = int(os.environ.get("POST_HOUR", "8"))              # hora da postagem diária

# gemini-1.5-* foi descontinuado (causa do erro 404). Pode sobrescrever via variável GEMINI_MODELS.
MODELS_TO_TRY = [
    m.strip() for m in os.environ.get(
        "GEMINI_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash"
    ).split(",") if m.strip()
]

if not TELEGRAM_TOKEN:
    log.critical("TELEGRAM_TOKEN não configurado!")
    sys.exit(1)

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

AVISO = "🔞 +18 | Aposte com responsabilidade. Não há garantia de lucro."

# Definição dos bilhetes: (tipo, título, odd alvo, mín jogos, máx jogos, odd mín/jogo, odd máx/jogo)
BILHETES_CONFIG = [
    ("NORMAL", "BILHETE NORMAL 1", 5,   5, 7,   1.15, 1.45),
    ("NORMAL", "BILHETE NORMAL 2", 15,  7, 9,   1.20, 1.50),
    ("NORMAL", "BILHETE NORMAL 3", 50,  9, 11,  1.25, 1.55),
    ("NORMAL", "BILHETE NORMAL 4", 100, 10, 12, 1.30, 1.60),
    ("VIP",    "BILHETE VIP 1",    10,  6, 8,   1.20, 1.50),
    ("VIP",    "BILHETE VIP 2",    40,  8, 10,  1.30, 1.60),
]
QUINTA_CONFIG = ("QUINTA_FEIRA", "SUPER QUINTA", 450, 12, 15, 1.35, 1.65)

CACHE = {"data": None, "bilhetes": []}
CACHE_LOCK = threading.Lock()


def agora():
    return datetime.datetime.now(BOT_TZ)


# ==========================================
# 2. SERVIDOR WEB (RENDER)
# ==========================================
app = Flask(__name__)


@app.route("/")
def home():
    return "FutBet VIP Bot online ✅"


@app.route("/health")
def health():
    return {"status": "ok", "cache_date": CACHE["data"], "bilhetes": len(CACHE["bilhetes"])}


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_flask, daemon=True).start()


# ==========================================
# 3. MÓDULO DE IA (GEMINI + GOOGLE SEARCH)
# ==========================================
SYSTEM_INSTRUCTION = (
    "És um analista profissional de apostas desportivas em futebol. "
    "Usas a pesquisa Google para confirmar jogos REAIS e odds de mercado atuais. "
    "Nunca inventas jogos, horários ou ligas. Se não houver jogos suficientes, "
    "montas bilhetes menores em vez de inventar. Respondes SOMENTE no formato pedido, "
    "sem comentários, sem markdown e sem texto fora dos blocos."
)


def chamar_gemini(prompt):
    if not client:
        raise RuntimeError("GEMINI_API_KEY não está configurada.")

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.3,
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )

    ultimo_erro = None
    for model in MODELS_TO_TRY:
        for tentativa in range(1, 3):
            try:
                resp = client.models.generate_content(model=model, contents=prompt, config=config)
                texto = getattr(resp, "text", None)
                if texto:
                    log.info("Resposta obtida com o modelo %s", model)
                    return texto
                ultimo_erro = f"{model}: resposta vazia"
            except Exception as e:  # noqa: BLE001
                ultimo_erro = f"{model}: {e}"
                msg = str(e)
                log.warning("Tentativa %d (%s) falhou: %s", tentativa, model, msg[:200])
                if "404" in msg or "NOT_FOUND" in msg:
                    break  # modelo inexistente/descontinuado → próximo modelo
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    time.sleep(8)
                    break
                if "API key" in msg or "401" in msg or "403" in msg or "PERMISSION" in msg:
                    raise RuntimeError(f"Chave Gemini inválida ou sem permissão: {msg[:200]}")
                time.sleep(3)
    raise RuntimeError(f"Todos os modelos falharam. Último erro: {ultimo_erro}")


# ==========================================
# 4. PROMPT E PARSER
# ==========================================
def _bloco_prompt(cfg):
    tipo, titulo, alvo, jmin, jmax, omin, omax = cfg
    return (
        f"=== INICIO BILHETE ===\n"
        f"TIPO: {tipo}\n"
        f"TITULO: {titulo} (ODD ~{alvo})\n"
        f"# Meta: odd total próxima de {alvo}, com {jmin} a {jmax} jogos, "
        f"odd por jogo entre {omin:.2f} e {omax:.2f}\n"
        f"JOGO: HH:MM | Liga | Time Casa vs Time Fora | Palpite | Odd\n"
        f"(uma linha JOGO por partida)\n"
        f"=== FIM BILHETE ==="
    )


def gerar_prompt(incluir_quinta=False):
    hoje = agora().strftime("%d/%m/%Y")
    configs = list(BILHETES_CONFIG) + ([QUINTA_CONFIG] if incluir_quinta else [])
    blocos = "\n\n".join(_bloco_prompt(c) for c in configs)

    return f"""
DATA DE HOJE: {hoje} (fuso {BOT_TZ.key}).

TAREFA: pesquise na internet (FlashScore, SofaScore, BetMines, sites de odds) os jogos de futebol
OFICIAIS que acontecem EXCLUSIVAMENTE hoje, {hoje}, e monte os bilhetes abaixo.

REGRAS OBRIGATÓRIAS:
1. Somente jogos de HOJE que ainda não começaram, com horário no fuso {BOT_TZ.key}.
2. Priorize mercados seguros: Dupla Chance, Mais de 1.5 gols, Empate Anula, Ambas Não Marcam em favoritos claros.
3. Nunca repita o mesmo jogo dentro do mesmo bilhete. Evite repetir o mesmo jogo em muitos bilhetes.
4. A odd do campo "Odd" deve ser decimal com ponto (ex: 1.25) e refletir o mercado real.
5. Não escreva ODD_TOTAL (o sistema calcula). Não escreva nada fora dos blocos.
6. Linhas que começam com # são instruções internas: NÃO as repita na resposta.
7. Use exatamente o formato abaixo, um bloco por bilhete.

{blocos}
""".strip()


def _parse_odd(txt):
    m = re.search(r"\d+[.,]?\d*", txt or "")
    if not m:
        return None
    try:
        v = float(m.group(0).replace(",", "."))
        return v if v > 1.0 else None
    except ValueError:
        return None


def extrair_bilhetes(texto):
    blocos = re.findall(r"=== INICIO BILHETE ===(.*?)=== FIM BILHETE ===", texto, re.DOTALL)
    bilhetes = []
    for bloco in blocos:
        tipo, titulo, jogos = "NORMAL", "BILHETE FUTBET", []
        vistos = set()
        for linha in (l.strip() for l in bloco.splitlines() if l.strip()):
            up = linha.upper()
            if up.startswith("TIPO:"):
                tipo = linha.split(":", 1)[1].strip().upper()
            elif up.startswith("TITULO:"):
                titulo = linha.split(":", 1)[1].strip()
            elif up.startswith("JOGO:"):
                partes = [p.strip() for p in linha.split(":", 1)[1].split("|")]
                if len(partes) < 5:
                    continue
                odd = _parse_odd(partes[4])
                chave = partes[2].lower()
                if odd is None or chave in vistos:
                    continue
                vistos.add(chave)
                jogos.append({"hora": partes[0], "liga": partes[1], "jogo": partes[2],
                              "palpite": partes[3], "odd": odd})
        if jogos:
            total = 1.0
            for j in jogos:
                total *= j["odd"]
            bilhetes.append({"tipo": tipo, "titulo": titulo, "jogos": jogos, "odd_total": round(total, 2)})
    return bilhetes


def obter_bilhetes(forcar=False):
    """Gera 1x por dia (thread-safe) e reutiliza do cache."""
    with CACHE_LOCK:
        hoje = agora().strftime("%Y-%m-%d")
        if not forcar and CACHE["data"] == hoje and CACHE["bilhetes"]:
            return CACHE["bilhetes"]

        is_quinta = agora().weekday() == 3
        texto = chamar_gemini(gerar_prompt(incluir_quinta=is_quinta))
        bilhetes = extrair_bilhetes(texto)
        if bilhetes:
            CACHE["data"], CACHE["bilhetes"] = hoje, bilhetes
        else:
            log.warning("Resposta da IA sem bilhetes válidos:\n%s", texto[:500])
        return bilhetes


# ==========================================
# 5. IMAGEM DO BILHETE
# ==========================================
def _fonte(tamanho, negrito=False):
    caminhos = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if negrito else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf" if negrito else "DejaVuSans.ttf",
    ]
    for c in caminhos:
        try:
            return ImageFont.truetype(c, tamanho)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tamanho)
    except TypeError:
        return ImageFont.load_default()


def _cortar(draw, texto, fonte, largura_max):
    while texto and draw.textlength(texto, font=fonte) > largura_max:
        texto = texto[:-2]
        if len(texto) < 4:
            break
    return texto


def gerar_imagem(titulo, jogos, odd_total):
    if not HAS_PILLOW:
        return None
    try:
        W, margem = 1000, 30
        h_head, h_card, gap, h_foot = 100, 100, 14, 90
        H = h_head + len(jogos) * (h_card + gap) + h_foot + 50

        img = Image.new("RGB", (W, H), "#F1F5F9")
        d = ImageDraw.Draw(img)
        f_tit, f_b, f_n, f_s = _fonte(28, True), _fonte(22, True), _fonte(20), _fonte(18)

        d.rectangle([margem, 20, W - margem, h_head], fill="#0F172A")
        d.text((margem + 20, 45), _cortar(d, f"FUTBET  |  {titulo.upper()}", f_tit, W - 2 * margem - 40),
               fill="#F59E0B", font=f_tit)

        y = h_head + 20
        for j in jogos:
            d.rectangle([margem, y, W - margem, y + h_card], fill="#FFFFFF", outline="#CBD5E1", width=2)
            d.text((margem + 20, y + 10), _cortar(d, f"{j['hora']}  |  {j['liga']}", f_s, W - 2 * margem - 40),
                   fill="#64748B", font=f_s)
            d.text((margem + 20, y + 36), _cortar(d, j["jogo"], f_b, W - 2 * margem - 40), fill="#0F172A", font=f_b)
            d.text((margem + 20, y + 66), _cortar(d, f"Palpite: {j['palpite']}", f_n, 640), fill="#2563EB", font=f_n)
            d.text((W - margem - 190, y + 66), f"Odd {j['odd']:.2f}", fill="#059669", font=f_b)
            y += h_card + gap

        d.rectangle([margem, y, W - margem, y + h_foot], fill="#0F172A")
        d.text((margem + 20, y + 30), "ODD TOTAL ACUMULADA", fill="#FFFFFF", font=f_tit)
        d.text((W - margem - 230, y + 30), f"{odd_total:,.2f}", fill="#10B981", font=f_tit)

        buf = io.BytesIO()
        buf.name = "bilhete_futbet.png"
        img.save(buf, "PNG")
        buf.seek(0)
        return buf
    except Exception as e:  # noqa: BLE001
        log.error("Erro ao gerar imagem: %s", e)
        return None


# ==========================================
# 6. ENVIO DE MENSAGENS
# ==========================================
def esc(x):
    return html.escape(str(x))


def enviar_texto(chat_id, texto, reply_to=None):
    """Divide em partes ≤ 3800 caracteres (limite do Telegram = 4096)."""
    partes, atual = [], ""
    for linha in texto.split("\n"):
        if len(atual) + len(linha) + 1 > 3800:
            partes.append(atual)
            atual = ""
        atual += linha + "\n"
    if atual.strip():
        partes.append(atual)

    ultima = None
    for i, p in enumerate(partes):
        try:
            ultima = bot.send_message(chat_id, p, reply_to_message_id=reply_to if i == 0 else None)
        except Exception:  # noqa: BLE001
            try:
                ultima = bot.send_message(chat_id, re.sub(r"<[^>]+>", "", p), parse_mode=None)
            except Exception as e2:  # noqa: BLE001
                log.error("Falha ao enviar para %s: %s", chat_id, e2)
    return ultima


def enviar_bilhetes(chat_id, bilhetes, tipo=None):
    enviados = 0
    for b in bilhetes:
        if tipo and b["tipo"] != tipo:
            continue
        enviados += 1

        img = gerar_imagem(b["titulo"], b["jogos"], b["odd_total"])
        if img:
            try:
                bot.send_photo(chat_id, img, caption=f"⚽ <b>FUTBET — {esc(b['titulo'])}</b>")
            except Exception as e:  # noqa: BLE001
                log.warning("Falha ao enviar foto: %s", e)

        linhas = [f"📋 <b>{esc(b['titulo'])}</b>",
                  f"🗓️ {agora().strftime('%d/%m/%Y')} — jogos de hoje\n"]
        for i, j in enumerate(b["jogos"], 1):
            linhas.append(f"{i}. ⏰ <b>{esc(j['hora'])}</b> · {esc(j['liga'])}")
            linhas.append(f"   🏟️ {esc(j['jogo'])} ➔ <b>{esc(j['palpite'])}</b> (Odd {j['odd']:.2f})")
        linhas.append(f"\n🎯 <b>ODD TOTAL:</b> <code>{b['odd_total']:,.2f}</code>")
        linhas.append(f"\n{AVISO}")
        enviar_texto(chat_id, "\n".join(linhas))
        time.sleep(1)
    return enviados


# ==========================================
# 7. AGENDADOR DIÁRIO
# ==========================================
def postar_nos_canais():
    bilhetes = obter_bilhetes()
    if not bilhetes:
        raise RuntimeError("A IA não devolveu bilhetes válidos.")
    if FREE_CHANNEL_ID:
        enviar_bilhetes(FREE_CHANNEL_ID, bilhetes, "NORMAL")
    if VIP_CHANNEL_ID:
        enviar_bilhetes(VIP_CHANNEL_ID, bilhetes, "VIP")
        if agora().weekday() == 3:
            enviar_bilhetes(VIP_CHANNEL_ID, bilhetes, "QUINTA_FEIRA")


def rotina_diaria():
    ultimo_post = None
    proxima_tentativa = 0.0
    while True:
        try:
            n = agora()
            if n.hour == POST_HOUR and ultimo_post != n.date() and time.time() >= proxima_tentativa:
                log.info("Iniciando postagem diária automática...")
                try:
                    postar_nos_canais()
                    ultimo_post = n.date()
                    log.info("Postagem diária concluída.")
                except Exception as e:  # noqa: BLE001
                    log.error("Falha na postagem diária: %s", e)
                    proxima_tentativa = time.time() + 300  # tenta de novo em 5 min
        except Exception as e:  # noqa: BLE001
            log.error("Erro no agendador: %s", e)
        time.sleep(30)


threading.Thread(target=rotina_diaria, daemon=True).start()


# ==========================================
# 8. COMANDOS
# ==========================================
def is_admin(message):
    return message.from_user and message.from_user.id in ADMIN_IDS


def pode_ver_vip(message):
    # Se ADMIN_IDS estiver definido, o VIP em chat privado é restrito aos admins.
    return not ADMIN_IDS or is_admin(message)


def entregar(message, tipo, rotulo):
    bot.send_chat_action(message.chat.id, "typing")
    enviar_texto(message.chat.id, f"📊 <b>A carregar {rotulo}...</b>")
    try:
        bilhetes = obter_bilhetes()
        if not bilhetes or enviar_bilhetes(message.chat.id, bilhetes, tipo) == 0:
            enviar_texto(message.chat.id, "⚠️ Nenhum bilhete disponível para esta categoria hoje.")
    except Exception as e:  # noqa: BLE001
        log.error("Erro em /%s: %s", message.text, e)
        enviar_texto(message.chat.id, "❌ Não foi possível gerar os palpites agora. Tente novamente em alguns minutos.")
        for admin in ADMIN_IDS:
            try:
                bot.send_message(admin, f"⚠️ Erro técnico: {esc(str(e)[:500])}", parse_mode="HTML")
            except Exception:  # noqa: BLE001
                pass


@bot.message_handler(commands=["start", "ajuda", "help"])
def cmd_start(m):
    enviar_texto(m.chat.id, (
        "⚽ <b>FUTBET VIP — BOT OFICIAL</b> 💎\n\n"
        f"Palpites automáticos todos os dias às {POST_HOUR:02d}:00 nos nossos canais.\n\n"
        "📌 <b>Comandos:</b>\n"
        "/palpites_hoje — Bilhetes normais de hoje\n"
        "/palpites_vip — Bilhetes VIP de hoje\n"
        "/super_quinta — Super Quinta (só às quintas)\n"
        "/status — Estado do bot\n\n"
        f"{AVISO}"
    ), reply_to=m.message_id)


@bot.message_handler(commands=["palpites_hoje", "palpites_normais"])
def cmd_normais(m):
    entregar(m, "NORMAL", "os Bilhetes Normais de hoje")


@bot.message_handler(commands=["palpites_vip", "palpitesvip"])
def cmd_vip(m):
    if not pode_ver_vip(m):
        enviar_texto(m.chat.id, "💎 Conteúdo exclusivo do canal VIP. Entre no canal para receber os bilhetes.")
        return
    entregar(m, "VIP", "os Bilhetes VIP de hoje")


@bot.message_handler(commands=["super_quinta"])
def cmd_quinta(m):
    if not pode_ver_vip(m):
        enviar_texto(m.chat.id, "💎 Conteúdo exclusivo do canal VIP.")
        return
    if agora().weekday() != 3:
        enviar_texto(m.chat.id, "⚠️ A Super Quinta só fica disponível às quintas-feiras.")
        return
    entregar(m, "QUINTA_FEIRA", "o Bilhete Super Quinta")


@bot.message_handler(commands=["forcar_postagem"])
def cmd_forcar(m):
    if not is_admin(m):
        enviar_texto(m.chat.id, "⛔ Comando restrito a administradores.")
        return
    enviar_texto(m.chat.id, "⚙️ <b>A gerar e enviar para os canais...</b>")
    try:
        obter_bilhetes(forcar=True)
        postar_nos_canais()
        enviar_texto(m.chat.id, "✅ Postagem concluída!")
    except Exception as e:  # noqa: BLE001
        enviar_texto(m.chat.id, f"❌ Erro: {esc(str(e)[:800])}")


@bot.message_handler(commands=["status"])
def cmd_status(m):
    enviar_texto(m.chat.id, (
        "🤖 <b>Status do Bot</b>\n"
        f"🕒 Hora local: {agora().strftime('%d/%m/%Y %H:%M')}\n"
        f"🧠 Modelos: <code>{esc(', '.join(MODELS_TO_TRY))}</code>\n"
        f"🔑 Gemini: {'✅' if client else '❌'}\n"
        f"🖼️ Pillow: {'✅' if HAS_PILLOW else '❌'}\n"
        f"📢 Canal Grátis: {'✅' if FREE_CHANNEL_ID else '❌'} | 💎 VIP: {'✅' if VIP_CHANNEL_ID else '❌'}\n"
        f"📦 Cache: {CACHE['data'] or 'vazio'} ({len(CACHE['bilhetes'])} bilhetes)"
    ))


# ==========================================
# 9. EXECUÇÃO
# ==========================================
if __name__ == "__main__":
    log.info("Bot FutBet VIP iniciado. Modelos: %s", MODELS_TO_TRY)
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:  # noqa: BLE001
        log.warning("Aviso webhook: %s", e)

    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20, skip_pending=True)
        except Exception as e:  # noqa: BLE001
            log.error("Reconectando: %s", e)
            time.sleep(5)
    
