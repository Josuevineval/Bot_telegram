import datetime
import functools
import html
import io
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import requests
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
FREE_CHANNEL_ID = os.environ.get("FREE_CHANNEL_ID")
VIP_CHANNEL_ID = os.environ.get("VIP_CHANNEL_ID")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")  # opcional (api-football.com, plano grátis)
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}

BOT_TZ = ZoneInfo(os.environ.get("BOT_TZ", "Europe/Lisbon"))
POST_HOUR = int(os.environ.get("POST_HOUR", "8"))
SELF_URL = os.environ.get("SELF_URL") or os.environ.get("RENDER_EXTERNAL_URL")
CACHE_FILE = os.environ.get("CACHE_FILE", "/tmp/futbet_cache.json")

MODELS_TO_TRY = [
    m.strip() for m in os.environ.get(
        "GEMINI_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash"
    ).split(",") if m.strip()
]

if not TELEGRAM_TOKEN:
    log.critical("TELEGRAM_TOKEN não configurado!")
    sys.exit(1)

# num_threads alto: evita que um comando lento (IA) bloqueie todos os outros
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=True, num_threads=12)
client = (
    genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=120_000))
    if GEMINI_API_KEY else None
)

AVISO = "🔞 +18 | Aposte com responsabilidade. Odds indicativas: confirme na sua casa de apostas. Sem garantia de lucro."

# (tipo, título, odd alvo, mín jogos, máx jogos, odd mín/jogo, odd máx/jogo)
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
FIXTURES_CACHE = {"ts": 0.0, "data": None, "jogos": [], "fontes": {}}
FIXTURES_LOCK = threading.Lock()
LAST_ERROR = {"msg": "nenhum"}


def agora():
    return datetime.datetime.now(BOT_TZ)


# ==========================================
# 2. SERVIDOR WEB + KEEP-ALIVE (RENDER)
# ==========================================
app = Flask(__name__)


@app.route("/")
def home():
    return "FutBet VIP Bot online ✅"


@app.route("/health")
def health():
    return {"status": "ok", "cache_date": CACHE["data"], "bilhetes": len(CACHE["bilhetes"])}


def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


def keep_alive():
    """Evita que o Render (plano grátis) adormeça o serviço por inatividade."""
    if not SELF_URL:
        log.info("SELF_URL/RENDER_EXTERNAL_URL não definido: keep-alive desativado.")
        return
    while True:
        time.sleep(600)
        try:
            requests.get(SELF_URL.rstrip("/") + "/health", timeout=20)
        except Exception as e:  # noqa: BLE001
            log.warning("Keep-alive falhou: %s", e)


threading.Thread(target=run_flask, daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()


# ==========================================
# 3. JOGOS REAIS DO DIA
# ==========================================
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

ESPN_LIGAS = [
    "uefa.champions", "uefa.europa", "uefa.europa.conf", "uefa.nations", "fifa.world", "fifa.friendly",
    "uefa.euroq", "uefa.wcq", "conmebol.libertadores", "conmebol.sudamericana", "concacaf.nations.league",
    "eng.1", "eng.2", "eng.3", "eng.fa", "eng.league_cup", "esp.1", "esp.2", "ita.1", "ita.2", "ger.1", "ger.2",
    "fra.1", "fra.2", "por.1", "por.2", "ned.1", "bel.1", "sco.1", "tur.1", "gre.1", "rus.1", "aut.1", "sui.1",
    "den.1", "swe.1", "nor.1", "pol.1", "cze.1", "rou.1", "ukr.1", "cro.1", "srb.1",
    "bra.1", "bra.2", "arg.1", "col.1", "chi.1", "uru.1", "per.1", "ecu.1", "par.1", "usa.1", "mex.1",
    "jpn.1", "kor.1", "chn.1", "aus.1", "sau.1", "idn.1", "ind.1",
    "caf.nations", "caf.champions", "rsa.1", "egy.1", "mar.1", "ang.1",
]


def _espn_liga(code, intervalo):
    try:
        r = requests.get(f"{ESPN_BASE}/{code}/scoreboard", params={"dates": intervalo, "limit": 200},
                         headers=UA, timeout=12)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:  # noqa: BLE001
        return []

    liga = (data.get("leagues") or [{}])[0].get("name") or code
    jogos = []
    for ev in data.get("events", []):
        try:
            comp = ev["competitions"][0]
            estado = (comp.get("status") or ev.get("status") or {}).get("type", {}).get("state")
            if estado != "pre":
                continue
            casa = next(c for c in comp["competitors"] if c.get("homeAway") == "home")["team"]["displayName"]
            fora = next(c for c in comp["competitors"] if c.get("homeAway") == "away")["team"]["displayName"]
            dt = datetime.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(BOT_TZ)
            jogos.append({"dt": dt, "liga": liga, "jogo": f"{casa} vs {fora}", "prio": ESPN_LIGAS.index(code)})
        except Exception:  # noqa: BLE001
            continue
    return jogos


def _fontes_espn():
    hoje = agora().date()
    amanha = hoje + datetime.timedelta(days=1)
    intervalo = f"{hoje:%Y%m%d}-{amanha:%Y%m%d}"
    with ThreadPoolExecutor(max_workers=16) as ex:
        resultados = list(ex.map(lambda c: _espn_liga(c, intervalo), ESPN_LIGAS))
    return [j for r in resultados for j in r]


def _fonte_api_football():
    if not API_FOOTBALL_KEY:
        return []
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            params={"date": agora().strftime("%Y-%m-%d"), "timezone": BOT_TZ.key},
            headers={"x-apisports-key": API_FOOTBALL_KEY}, timeout=20,
        )
        jogos = []
        for f in r.json().get("response", []):
            if f["fixture"]["status"]["short"] != "NS":
                continue
            dt = datetime.datetime.fromisoformat(f["fixture"]["date"]).astimezone(BOT_TZ)
            liga = f"{f['league'].get('country', '')} - {f['league']['name']}".strip(" -")
            jogos.append({"dt": dt, "liga": liga, "jogo": f"{f['teams']['home']['name']} vs {f['teams']['away']['name']}",
                          "prio": 500})
        return jogos
    except Exception as e:  # noqa: BLE001
        log.warning("API-Football falhou: %s", e)
        return []


def obter_jogos_hoje(forcar=False):
    """Lista de jogos reais de hoje (cache de 30 min)."""
    with FIXTURES_LOCK:
        hoje = agora().strftime("%Y-%m-%d")
        if (not forcar and FIXTURES_CACHE["data"] == hoje and FIXTURES_CACHE["jogos"]
                and time.time() - FIXTURES_CACHE["ts"] < 1800):
            return FIXTURES_CACHE["jogos"]

        espn = _fontes_espn()
        apif = _fonte_api_football()
        agora_dt = agora()

        vistos, final = set(), []
        for j in espn + apif:
            if j["dt"].date() != agora_dt.date() or j["dt"] <= agora_dt:
                continue
            chave = re.sub(r"[^a-z]", "", j["jogo"].lower())
            if chave in vistos:
                continue
            vistos.add(chave)
            final.append(j)
        final.sort(key=lambda x: x["dt"])

        FIXTURES_CACHE.update(ts=time.time(), data=hoje, jogos=final,
                              fontes={"ESPN": len(espn), "API-Football": len(apif)})
        log.info("Jogos de hoje encontrados: %d (ESPN=%d, API-Football=%d)", len(final), len(espn), len(apif))
        return final


# ==========================================
# 4. IA (GEMINI + GOOGLE SEARCH)
# ==========================================
SYSTEM_INSTRUCTION = (
    "És um analista profissional de apostas em futebol. Usas a pesquisa Google (BetMines, SofaScore, "
    "FlashScore, sites de odds) para confirmar forma, desfalques e odds atuais. Nunca inventas jogos. "
    "Respondes SOMENTE no formato pedido."
)


def _config(usar_busca, sistema=SYSTEM_INSTRUCTION, temperatura=0.3):
    kw = {"system_instruction": sistema, "temperature": temperatura}
    if usar_busca:
        kw["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    return types.GenerateContentConfig(**kw)


def chamar_gemini(prompt, sistema=SYSTEM_INSTRUCTION, temperatura=0.3):
    if not client:
        raise RuntimeError("GEMINI_API_KEY não está configurada no Render.")

    ultimo_erro = None
    for model in MODELS_TO_TRY:
        for usar_busca in (True, False):  # se a pesquisa falhar, tenta sem ela
            try:
                resp = client.models.generate_content(
                    model=model, contents=prompt, config=_config(usar_busca, sistema, temperatura))
                try:
                    texto = resp.text
                except Exception:  # noqa: BLE001
                    texto = None
                if texto and texto.strip():
                    log.info("IA ok: modelo=%s busca=%s", model, usar_busca)
                    return texto
                ultimo_erro = f"{model} (busca={usar_busca}): resposta vazia/bloqueada"
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                ultimo_erro = f"{model} (busca={usar_busca}): {msg[:300]}"
                log.warning("Falha IA: %s", ultimo_erro)
                if "API key" in msg or "API_KEY" in msg or "UNAUTHENTICATED" in msg or "PERMISSION_DENIED" in msg:
                    raise RuntimeError(f"Chave Gemini inválida/sem permissão: {msg[:200]}")
                if "404" in msg or "NOT_FOUND" in msg:
                    break  # modelo não existe -> próximo modelo
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    time.sleep(5)
                    break  # cota -> próximo modelo
                time.sleep(2)
    LAST_ERROR["msg"] = ultimo_erro or "desconhecido"
    raise RuntimeError(f"IA indisponível. Último erro: {ultimo_erro}")


# ==========================================
# 5. PROMPT, PARSER E BILHETES
# ==========================================
def _bloco_prompt(cfg):
    tipo, titulo, alvo, jmin, jmax, omin, omax = cfg
    return (
        "=== INICIO BILHETE ===\n"
        f"TIPO: {tipo}\n"
        f"TITULO: {titulo} (ODD ~{alvo})\n"
        f"# Meta: odd total perto de {alvo}; {jmin} a {jmax} jogos; odd por jogo entre {omin:.2f} e {omax:.2f}\n"
        "JOGO: HH:MM | Liga | Time Casa vs Time Fora | Palpite | Odd\n"
        "=== FIM BILHETE ==="
    )


def gerar_prompt(jogos, incluir_quinta):
    hoje = agora().strftime("%d/%m/%Y")
    configs = list(BILHETES_CONFIG) + ([QUINTA_CONFIG] if incluir_quinta else [])
    blocos = "\n\n".join(_bloco_prompt(c) for c in configs)

    if jogos:
        lista = "\n".join(f"{j['dt']:%H:%M} | {j['liga']} | {j['jogo']}"
                          for j in sorted(sorted(jogos, key=lambda x: x["prio"])[:150], key=lambda x: x["dt"]))
        origem = (f"LISTA OFICIAL DE JOGOS DE HOJE (horário {BOT_TZ.key}). Use SOMENTE jogos desta lista, "
                  f"com os nomes exatamente como aparecem:\n{lista}")
    else:
        origem = (f"Pesquise na internet (BetMines, FlashScore, SofaScore) os jogos que acontecem hoje, {hoje}, "
                  f"e use SOMENTE jogos reais confirmados de hoje.")

    return f"""
DATA DE HOJE: {hoje}.

{origem}

TAREFA: monte os bilhetes abaixo. Pesquise no BetMines/SofaScore/FlashScore a forma recente, desfalques e as odds
de mercado para escolher palpites seguros (Dupla Chance, Mais de 1.5 gols, Empate Anula, favoritos claros).

REGRAS:
1. Jogos que ainda não começaram. Nunca repita o mesmo jogo dentro do mesmo bilhete.
2. Odd decimal com ponto (ex: 1.25), baseada na odd real de mercado quando encontrada.
3. Não escreva ODD_TOTAL (o sistema calcula) nem nenhum texto fora dos blocos.
4. Linhas iniciadas por # são instruções internas: NÃO as repita.
5. Se não houver jogos suficientes para um bilhete, faça-o menor em vez de inventar jogos.

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
        tipo, titulo, jogos, vistos = "NORMAL", "BILHETE FUTBET", [], set()
        for linha in (l.strip().lstrip("*-• ").strip() for l in bloco.splitlines() if l.strip()):
            up = linha.upper()
            if up.startswith("TIPO:"):
                tipo = linha.split(":", 1)[1].strip().upper()
            elif up.startswith("TITULO:"):
                titulo = linha.split(":", 1)[1].strip()
            elif up.startswith("JOGO:"):
                p = [x.strip() for x in linha.split(":", 1)[1].split("|")]
                if len(p) < 5:
                    continue
                odd = _parse_odd(p[4])
                chave = re.sub(r"[^a-z]", "", p[2].lower())
                if odd is None or chave in vistos:
                    continue
                vistos.add(chave)
                jogos.append({"hora": p[0], "liga": p[1], "jogo": p[2], "palpite": p[3], "odd": odd})
        if jogos:
            total = 1.0
            for j in jogos:
                total *= j["odd"]
            bilhetes.append({"tipo": tipo, "titulo": titulo, "jogos": jogos, "odd_total": round(total, 2)})
    return bilhetes


def salvar_cache():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(CACHE, f, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        log.warning("Não foi possível salvar o cache: %s", e)


def carregar_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("data") == agora().strftime("%Y-%m-%d"):
            CACHE.update(data)
            log.info("Cache do dia restaurado (%d bilhetes).", len(CACHE["bilhetes"]))
    except Exception:  # noqa: BLE001
        pass


def obter_bilhetes(forcar=False):
    with CACHE_LOCK:
        hoje = agora().strftime("%Y-%m-%d")
        if not forcar and CACHE["data"] == hoje and CACHE["bilhetes"]:
            return CACHE["bilhetes"]

        jogos = obter_jogos_hoje()
        prompt = gerar_prompt(jogos, incluir_quinta=(agora().weekday() == 3))

        bilhetes = []
        for tentativa in range(2):  # 2 tentativas caso o formato venha inválido
            texto = chamar_gemini(prompt)
            bilhetes = extrair_bilhetes(texto)
            if bilhetes:
                break
            log.warning("Tentativa %d sem bilhetes válidos. Resposta: %s", tentativa + 1, texto[:400])

        if not bilhetes:
            raise RuntimeError("A IA respondeu, mas sem bilhetes no formato esperado (tente novamente).")

        CACHE["data"], CACHE["bilhetes"] = hoje, bilhetes
        salvar_cache()
        return bilhetes


# ==========================================
# 6. IMAGEM DO BILHETE
# ==========================================
def _fonte(tamanho, negrito=False):
    nome = "DejaVuSans-Bold.ttf" if negrito else "DejaVuSans.ttf"
    for c in (f"/usr/share/fonts/truetype/dejavu/{nome}", nome):
        try:
            return ImageFont.truetype(c, tamanho)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tamanho)
    except TypeError:
        return ImageFont.load_default()


def _cortar(draw, texto, fonte, largura_max):
    while len(texto) > 3 and draw.textlength(texto, font=fonte) > largura_max:
        texto = texto[:-2]
    return texto


def gerar_imagem(titulo, jogos, odd_total):
    if not HAS_PILLOW:
        return None
    try:
        W, m = 1000, 30
        h_head, h_card, gap, h_foot = 100, 100, 14, 90
        H = h_head + len(jogos) * (h_card + gap) + h_foot + 50
        img = Image.new("RGB", (W, H), "#F1F5F9")
        d = ImageDraw.Draw(img)
        f_t, f_b, f_n, f_s = _fonte(28, True), _fonte(22, True), _fonte(20), _fonte(18)

        d.rectangle([m, 20, W - m, h_head], fill="#0F172A")
        d.text((m + 20, 45), _cortar(d, f"FUTBET  |  {titulo.upper()}", f_t, W - 2 * m - 40), fill="#F59E0B", font=f_t)

        y = h_head + 20
        for j in jogos:
            d.rectangle([m, y, W - m, y + h_card], fill="#FFFFFF", outline="#CBD5E1", width=2)
            d.text((m + 20, y + 10), _cortar(d, f"{j['hora']}  |  {j['liga']}", f_s, W - 2 * m - 40), fill="#64748B", font=f_s)
            d.text((m + 20, y + 36), _cortar(d, j["jogo"], f_b, W - 2 * m - 40), fill="#0F172A", font=f_b)
            d.text((m + 20, y + 66), _cortar(d, f"Palpite: {j['palpite']}", f_n, 640), fill="#2563EB", font=f_n)
            d.text((W - m - 190, y + 66), f"Odd {j['odd']:.2f}", fill="#059669", font=f_b)
            y += h_card + gap

        d.rectangle([m, y, W - m, y + h_foot], fill="#0F172A")
        d.text((m + 20, y + 30), "ODD TOTAL ACUMULADA", fill="#FFFFFF", font=f_t)
        d.text((W - m - 230, y + 30), f"{odd_total:,.2f}", fill="#10B981", font=f_t)

        buf = io.BytesIO()
        buf.name = "bilhete_futbet.png"
        img.save(buf, "PNG")
        buf.seek(0)
        return buf
    except Exception as e:  # noqa: BLE001
        log.error("Erro ao gerar imagem: %s", e)
        return None


# ==========================================
# 7. ENVIO DE MENSAGENS
# ==========================================
def esc(x):
    return html.escape(str(x))


def md_html(t):
    """Converte o markdown do Gemini para HTML seguro do Telegram."""
    t = html.escape(t)
    t = re.sub(r"^\s*[\*\-]\s+", "• ", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    t = re.sub(r"^#+\s*(.+)$", r"<b>\1</b>", t, flags=re.M)
    return t.replace("*", "")


def enviar_texto(chat_id, texto, reply_to=None):
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
        if tipo and b["tipo"] !
