"""Dona Maria: ofertas femininas → Telegram.
Produtos por grupo (moda, calçados, beleza, íntimos, casa).
Filtro leve: bloqueia só títulos masculinos (queries já são femininas).
Sem bloqueio entre runs (só evita duplicata na mesma execução).
Horário SP: 07h–22h | madrugada 23h, 02h, 05h
"""
import os, json, html, re, random, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

AFF_ID = os.getenv("ML_AFFILIATE_ID", "71970283")
AFF_PARAMS = os.getenv("ML_AFFILIATE_PARAMS", "matt_tool={id}")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
POSTS_POR_GRUPO = int(os.getenv("POSTS_POR_GRUPO", "4"))
MAX_POSTS = int(os.getenv("MAX_POSTS", "20"))
REPETIR_APOS_DIAS = int(os.getenv("REPETIR_APOS_DIAS", "0"))
API = "https://api.mercadolibre.com"
ROOT = Path(__file__).parent
TRENDS = ROOT / "docs" / "trends.json"
STATE = ROOT / "state" / "posted.json"
TZ = ZoneInfo("America/Sao_Paulo")

GRUPOS = [
    {
        "nome": "Moda Feminina",
        "cats": ["MLB1430"],
        "queries": [
            "vestido feminino", "blusa feminina", "calça feminina", "saia feminina",
            "conjunto feminino", "jaqueta feminina", "legging feminina",
            "cropped feminino", "macaquinho feminino", "cardigan feminino",
            "shorts feminino", "body feminino", "camiseta feminina",
        ],
    },
    {
        "nome": "Íntimos & Lingerie",
        "cats": ["MLB1430"],
        "queries": [
            "lingerie feminina", "conjunto lingerie", "sutiã", "calcinha feminina",
            "soutien", "camisola feminina", "robe feminino", "baby doll",
            "body lingerie", "meia-calça feminina", "kit calcinha", "kit sutiã",
            "pijama feminino", "short doll", "sutiã push up", "calcinha fio dental",
        ],
    },
    {
        "nome": "Calçados & Bolsas",
        "cats": ["MLB1430"],
        "queries": [
            "tênis feminino", "sandália feminina", "bolsa feminina", "chinelo feminino",
            "scarpin feminino", "mocassim feminino", "carteira feminina",
            "rasteirinha feminina", "bota feminina", "sapatilha feminina",
            "mochila feminina", "clutch feminina",
        ],
    },
    {
        "nome": "Beleza & Cuidados",
        "cats": ["MLB1246"],
        "queries": [
            "maquiagem", "skincare", "perfume feminino", "batom",
            "kit maquiagem", "esmalte", "base maquiagem", "máscara de cílios",
            "hidratante corporal", "shampoo", "condicionador",
            "secador de cabelo", "chapinha", "escova modeladora",
        ],
    },
    {
        "nome": "Casa & Acessórios Femininos",
        "cats": ["MLB1574", "MLB3937"],
        "queries": [
            "colar feminino", "brinco feminino", "pulseira feminina",
            "anel feminino", "relógio feminino", "organizador maquiagem",
            "nécessaire", "jogo de lençol", "toalha de banho", "cortina",
            "air fryer", "liquidificador",
        ],
    },
]

# Só bloqueia o que for claramente masculino
BLOQUEIO = re.compile(
    r"\b("
    r"masculin[oa]|para homem|para homens|menino|meninos|"
    r"cueca masculina|barbeador|barba|"
    r"camiseta masculina|bermuda masculina|tênis masculino|"
    r"perfume masculino|relógio masculino|carteira masculina|"
    r"cinto masculino|jaqueta masculina|calça masculina|"
    r"sapato social masculino|chinelo masculino|"
    r"camisa social masculina"
    r")\b",
    re.I,
)

S = requests.Session()
S.headers.update({"User-Agent": "dona-maria/1.6", "Accept": "application/json"})


def headers_ml():
    cid, sec = os.getenv("ML_CLIENT_ID"), os.getenv("ML_CLIENT_SECRET")
    if not (cid and sec):
        print("ERRO: secrets ML ausentes")
        return {}
    r = S.post(f"{API}/oauth/token", data={
        "grant_type": "client_credentials", "client_id": cid, "client_secret": sec
    }, timeout=20)
    r.raise_for_status()
    print("Token ML OK")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def link_afiliado(url):
    sep = "&" if "?" in url else "?"
    return url + sep + AFF_PARAMS.format(id=AFF_ID)


def normalizar_titulo(t: str) -> str:
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9áéíóúâêôãõç\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:80]


def titulo_ok(titulo: str) -> bool:
    """Rejeita só títulos claramente masculinos."""
    if not titulo:
        return False
    if BLOQUEIO.search(titulo):
        return False
    return True


def carregar_estado():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw = STATE.read_text(encoding="utf-8").strip() or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"ids": {}, "titulos": {}}
        if data and "ids" not in data:
            return {"ids": data, "titulos": {}}
        data.setdefault("ids", {})
        data.setdefault("titulos", {})
        return data
    except Exception as e:
        print("Aviso: estado inválido, reiniciando:", e)
        return {"ids": {}, "titulos": {}}


def limpar_estado(estado, agora):
    if REPETIR_APOS_DIAS <= 0:
        return {"ids": {}, "titulos": {}}
    limite = agora - dt.timedelta(days=REPETIR_APOS_DIAS)
    ids_limpos, titulos_limpos = {}, {}
    for k, v in estado.get("ids", {}).items():
        try:
            if dt.datetime.fromisoformat(v) > limite:
                ids_limpos[k] = v
        except Exception:
            continue
    for k, v in estado.get("titulos", {}).items():
        try:
            if dt.datetime.fromisoformat(v) > limite:
                titulos_limpos[k] = v
        except Exception:
            continue
    return {"ids": ids_limpos, "titulos": titulos_limpos}


def ja_postado(estado, pid, titulo):
    if REPETIR_APOS_DIAS <= 0:
        return False
    if pid in estado["ids"]:
        return True
    nt = normalizar_titulo(titulo)
    return bool(nt and nt in estado["titulos"])


def registrar_postado(estado, pid, titulo, agora):
    if REPETIR_APOS_DIAS <= 0:
        return
    estado["ids"][pid] = agora.isoformat()
    nt = normalizar_titulo(titulo)
    if nt:
        estado["titulos"][nt] = agora.isoformat()


def produto_search(item, label):
    titulo = item.get("title") or ""
    if not titulo_ok(titulo):
        return None
    try:
        preco = float(item.get("price") or 0)
    except (TypeError, ValueError):
        return None
    if preco <= 0:
        return None
    frete = (item.get("shipping") or {}).get("free_shipping", False)
    foto = (item.get("thumbnail") or "").replace("http://", "https://")
    mid = str(item.get("id", ""))
    pid = item.get("catalog_product_id") or mid
    mid_fmt = (mid[:3] + "-" + mid[3:]) if mid.startswith("MLB") and "-" not in mid else mid
    permalink = item.get("permalink") or f"https://produto.mercadolivre.com.br/{mid_fmt}"
    return {
        "id": str(pid), "titulo": titulo, "preco": preco, "imagem": foto,
        "frete_gratis": frete, "categoria": label,
        "link": link_afiliado(permalink),
        "item_id": mid,
    }


def buscar_varios_query(query, cat_id, h, vistos_ids, vistos_titulos, label, quantos):
    achados = []
    try:
        offset = random.choice([0, 0, 10, 20, 30, 40])
        params = {
            "q": query,
            "limit": 50,
            "offset": offset,
            "sort": random.choice(["relevance", "price_asc", "sold_quantity_desc"]),
        }
        if cat_id:
            params["category"] = cat_id
        r = S.get(f"{API}/sites/MLB/search", headers=h, params=params, timeout=25)
        if r.status_code != 200:
            print(f"  Search '{query}' status={r.status_code}")
            return achados
        results = list(r.json().get("results") or [])
        if not results:
            print(f"  Search '{query}': 0 resultados")
            return achados
        random.shuffle(results)
        for item in results:
            if len(achados) >= quantos:
                break
            pid = item.get("catalog_product_id") or item.get("id")
            if not pid or str(pid) in vistos_ids:
                continue
            nt = normalizar_titulo(item.get("title") or "")
            if nt and nt in vistos_titulos:
                continue
            p = produto_search(item, label)
            if not p:
                continue
            vistos_ids.add(p["id"])
            if nt:
                vistos_titulos.add(nt)
            achados.append(p)
            print(f"  OK [{label}] R$ {p['preco']:.2f} — {p['titulo'][:50]}")
    except Exception as e:
        print(f"Erro search '{query}':", e)
    return achados


def varios_do_grupo(grupo, h, vistos_ids, vistos_titulos, quantos):
    achados = []
    queries = list(grupo.get("queries", []))
    random.shuffle(queries)
    for q in queries:
        if len(achados) >= quantos:
            break
        falta = quantos - len(achados)
        cat = random.choice(grupo["cats"]) if grupo.get("cats") else None
        novos = buscar_varios_query(q, cat, h, vistos_ids, vistos_titulos, grupo["nome"], falta)
        achados.extend(novos)
    return achados


def montar_diversificado(h, estado):
    if REPETIR_APOS_DIAS <= 0:
        vistos_ids, vistos_titulos = set(), set()
    else:
        vistos_ids = set(estado["ids"].keys())
        vistos_titulos = set(estado["titulos"].keys())
    escolhidos = []
    for grupo in GRUPOS:
        if len(escolhidos) >= MAX_POSTS:
            break
        n = min(POSTS_POR_GRUPO, MAX_POSTS - len(escolhidos))
        print(f"Grupo {grupo['nome']}: buscando até {n}")
        novos = varios_do_grupo(grupo, h, vistos_ids, vistos_titulos, n)
        escolhidos.extend(novos)
    return escolhidos


def preco_br(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def postar(p):
    cat = html.escape(p.get("categoria", ""))
    titulo = html.escape(p["titulo"][:120])
    preco = preco_br(p["preco"])
    link = html.escape(p["link"])
    frete_linha = "🚚 <b>Frete grátis</b>\n" if p.get("frete_gratis") else ""
    preco_label = f"a partir de <b>{preco}</b>" if p.get("item_id") else f"<b>{preco}</b>"
    texto = (
        f"💕 <b>Dona Maria indica — {cat}</b>\n\n"
        f"📦 {titulo}\n\n"
        f"💰 {preco_label}\n"
        f"{frete_linha}"
        f"\n👉 <a href=\"{link}\">Ver oferta no Mercado Livre</a>\n\n"
        f"<i>Selecionado para você · Link de afiliado · Preços podem variar</i>"
    )
    if not TG_TOKEN or not TG_CHAT:
        print("Telegram não configurado")
        return False
    data = {"chat_id": TG_CHAT, "parse_mode": "HTML"}
    if p.get("imagem"):
        data["photo"] = p["imagem"]
        data["caption"] = texto
        r = S.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto", data=data, timeout=30)
    else:
        data["text"] = texto
        r = S.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, timeout=30)
    print("Telegram:", r.status_code, r.text[:150])
    return r.ok


def pode_postar_agora(agora: dt.datetime) -> bool:
    h = agora.hour
    return (7 <= h <= 22) or h in (23, 2, 5)


def salvar_estado(estado):
    STATE.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    agora = dt.datetime.now(TZ)
    print("Iniciando Dona Maria", agora.isoformat())
    print(f"Meta: {POSTS_POR_GRUPO} por grupo, máx {MAX_POSTS} total")
    print(f"Bloqueio entre runs: {'DESLIGADO' if REPETIR_APOS_DIAS <= 0 else f'{REPETIR_APOS_DIAS} dias'}")
    print("Filtro: bloqueia só títulos masculinos (afrouxado)")
    h = headers_ml()
    if not h:
        return
    estado = limpar_estado(carregar_estado(), agora)
    print(f"Bloqueados: {len(estado['ids'])}")
    ranking = montar_diversificado(h, estado)
    print("Produtos selecionados:", len(ranking))
    TRENDS.parent.mkdir(parents=True, exist_ok=True)
    trends_itens = [{k: v for k, v in p.items() if k != "item_id"} for p in ranking]
    TRENDS.write_text(json.dumps({"atualizado": agora.isoformat(), "itens": trends_itens},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    if not ranking:
        print("Nada a postar")
        salvar_estado(estado)
        return
    if not (TG_TOKEN and TG_CHAT):
        print("Falta Telegram")
        return
    if not pode_postar_agora(agora):
        print(f"Fora do horário ({agora.hour}h)")
        salvar_estado(estado)
        return
    enviados = 0
    for p in ranking:
        if enviados >= MAX_POSTS:
            break
        if ja_postado(estado, p["id"], p["titulo"]):
            continue
        if postar(p):
            registrar_postado(estado, p["id"], p["titulo"], agora)
            enviados += 1
            salvar_estado(estado)
    salvar_estado(estado)
    print("Postagens enviadas:", enviados)


if __name__ == "__main__":
    main()
