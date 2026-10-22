"""Dona Maria: ofertas para mulheres → Telegram.
Foco: moda feminina, calçados, beleza, acessórios, casa e cozinha.
Evita repetições por 14 dias (ID + título).
Horário (America/Sao_Paulo):
  - 07h–22h: a cada 1 hora
  - 23h, 02h e 05h: a cada 3 horas (madrugada)
"""
import os, json, html, re, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

AFF_ID = os.getenv("ML_AFFILIATE_ID", "71970283")
AFF_PARAMS = os.getenv("ML_AFFILIATE_PARAMS", "matt_tool={id}")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
MAX_POSTS = int(os.getenv("MAX_POSTS", "4"))
REPETIR_APOS_DIAS = 14
API = "https://api.mercadolibre.com"
ROOT = Path(__file__).parent
TRENDS = ROOT / "docs" / "trends.json"
STATE = ROOT / "state" / "posted.json"
TZ = ZoneInfo("America/Sao_Paulo")

# Grupos 100% alinhados ao público feminino
GRUPOS = [
    {
        "nome": "Moda Feminina",
        "cats": ["MLB1430"],  # Calçados, Roupas e Bolsas
        "queries": ["vestido feminino", "blusa feminina", "calça feminina"],
    },
    {
        "nome": "Calçados & Bolsas",
        "cats": ["MLB1430"],
        "queries": ["tênis feminino", "sandália feminina", "bolsa feminina"],
    },
    {
        "nome": "Beleza & Cuidados",
        "cats": ["MLB1246"],  # Beleza e Cuidado Pessoal
        "queries": ["maquiagem", "skincare", "perfume feminino"],
    },
    {
        "nome": "Casa, Cozinha & Acessórios",
        "cats": ["MLB1574", "MLB5726", "MLB3937"],  # Casa / Eletro / Joias e Relógios
        "queries": ["utensílio cozinha", "organização casa", "colar feminino"],
    },
]

CAT_NOMES = {
    "MLB1430": "Moda",
    "MLB1246": "Beleza",
    "MLB1574": "Casa",
    "MLB5726": "Eletrodomésticos",
    "MLB3937": "Joias e Relógios",
}

# Filtra produtos claramente masculinos / infantis meninos
BLOQUEIO = re.compile(
    r"\b(masculin[oa]|homem|homens|menino|meninos|boy|man\b|men'?s|"
    r"camisa social masculina|cueca|barbeador|barba|"
    r"camiseta masculina|bermuda masculina|tênis masculino)\b",
    re.I,
)

# Sinais de produto feminino / dona de casa (ajuda em categorias mistas)
SINAL_FEM = re.compile(
    r"\b(feminin[oa]|mulher|mulheres|dama|ladies|woman|women|"
    r"vestido|blusa|saia|sutiã|sutia|calcinha|batom|maquiagem|"
    r"sandália|sandalia|scarpin|bolsa|colares?|brinco|"
    r"cozinha|air fryer|liquidificador|organizador|panela)\b",
    re.I,
)

S = requests.Session()
S.headers.update({"User-Agent": "dona-maria/1.2", "Accept": "application/json"})


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


def titulo_ok_feminino(titulo: str, exigir_sinal: bool = False) -> bool:
    if not titulo:
        return False
    if BLOQUEIO.search(titulo):
        return False
    if exigir_sinal and not SINAL_FEM.search(titulo):
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
    if pid in estado["ids"]:
        return True
    nt = normalizar_titulo(titulo)
    return bool(nt and nt in estado["titulos"])


def registrar_postado(estado, pid, titulo, agora):
    estado["ids"][pid] = agora.isoformat()
    nt = normalizar_titulo(titulo)
    if nt:
        estado["titulos"][nt] = agora.isoformat()


def escolher_oferta(results):
    if not results:
        return None
    validos = []
    for it in results:
        try:
            preco = float(it.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if preco <= 0:
            continue
        frete = (it.get("shipping") or {}).get("free_shipping", False)
        validos.append({"item": it, "preco": preco, "frete": frete})
    if not validos:
        return None
    precos = sorted(v["preco"] for v in validos)
    mediana = precos[len(precos) // 2]
    piso = mediana * 0.30 if mediana > 0 else 0
    validos = [v for v in validos if v["preco"] >= piso] or validos
    com_frete = [v for v in validos if v["frete"]]
    pool = com_frete if com_frete else validos
    return min(pool, key=lambda x: x["preco"])


def montar_produto(pid, h, categoria, exigir_sinal=False):
    titulo, foto = "", ""
    preco, frete = 0.0, False
    item_id = None

    try:
        rp = S.get(f"{API}/products/{pid}", headers=h, timeout=15)
        if rp.status_code == 200:
            d = rp.json()
            titulo = d.get("name") or d.get("title") or ""
            pics = d.get("pictures") or []
            if pics:
                foto = (pics[0].get("url") or pics[0].get("secure_url") or "").replace("http://", "https://")
    except Exception as e:
        print(f"  products/{pid}:", e)

    if not titulo_ok_feminino(titulo, exigir_sinal=exigir_sinal):
        return None

    try:
        ri = S.get(f"{API}/products/{pid}/items", headers=h, timeout=15)
        if ri.status_code == 200:
            results = ri.json().get("results") or []
            escolha = escolher_oferta(results)
            if escolha:
                preco = escolha["preco"]
                frete = escolha["frete"]
                item_id = escolha["item"].get("id") or escolha["item"].get("item_id")
    except Exception as e:
        print(f"  items/{pid}:", e)

    if not titulo or preco <= 0:
        return None

    if item_id:
        mid = str(item_id)
        mid_fmt = (mid[:3] + "-" + mid[3:]) if mid.startswith("MLB") and "-" not in mid else mid
        link = link_afiliado(f"https://produto.mercadolivre.com.br/{mid_fmt}")
    else:
        link = link_afiliado(f"https://www.mercadolivre.com.br/p/{pid}")

    return {
        "id": pid,
        "titulo": titulo,
        "preco": preco,
        "imagem": foto,
        "frete_gratis": frete,
        "categoria": categoria,
        "link": link,
        "item_id": item_id,
    }


def buscar_highlights(cat_id, h, vistos_ids, vistos_titulos, exigir_sinal=False):
    nome = CAT_NOMES.get(cat_id, cat_id)
    try:
        r = S.get(f"{API}/highlights/MLB/category/{cat_id}", headers=h, timeout=20)
        if r.status_code != 200:
            print(f"Highlights {nome}: {r.status_code}")
            return None
        for item in r.json().get("content", [])[:20]:
            pid = item.get("id")
            if not pid or pid in vistos_ids:
                continue
            p = montar_produto(pid, h, nome, exigir_sinal=exigir_sinal)
            if not p:
                continue
            nt = normalizar_titulo(p["titulo"])
            if nt and nt in vistos_titulos:
                continue
            print(f"  OK [{nome}/highlight] R$ {p['preco']:.2f} — {p['titulo'][:50]}"
                  + (" 🚚" if p.get("frete_gratis") else ""))
            return p
    except Exception as e:
        print(f"Erro highlights {nome}:", e)
    return None


def buscar_por_query(query, h, vistos_ids, vistos_titulos, categoria_label):
    """Fallback: busca no site com termo feminino."""
    try:
        r = S.get(
            f"{API}/sites/MLB/search",
            headers=h,
            params={"q": query, "limit": 20, "sort": "relevance"},
            timeout=20,
        )
        if r.status_code != 200:
            print(f"Search '{query}': {r.status_code}")
            return None
        for item in r.json().get("results", []):
            # prefer catalog product id quando existir
            pid = item.get("catalog_product_id") or item.get("id")
            if not pid or pid in vistos_ids:
                continue
            titulo = item.get("title") or ""
            if not titulo_ok_feminino(titulo, exigir_sinal=True):
                continue
            nt = normalizar_titulo(titulo)
            if nt and nt in vistos_titulos:
                continue

            # se for item (MLB123), monta direto sem /products
            if str(pid).startswith("MLB") and not str(pid).startswith("MLB") is False:
                pass

            # tenta via product catalog
            if item.get("catalog_product_id"):
                p = montar_produto(item["catalog_product_id"], h, categoria_label, exigir_sinal=True)
                if p:
                    print(f"  OK [{categoria_label}/search] R$ {p['preco']:.2f} — {p['titulo'][:50]}")
                    return p

            # fallback: dados do próprio search result
            try:
                preco = float(item.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if preco <= 0:
                continue
            frete = (item.get("shipping") or {}).get("free_shipping", False)
            foto = ""
            thumbs = item.get("thumbnail") or ""
            if thumbs:
                foto = thumbs.replace("http://", "https://")
            mid = str(item.get("id", ""))
            mid_fmt = (mid[:3] + "-" + mid[3:]) if mid.startswith("MLB") and "-" not in mid else mid
            p = {
                "id": str(pid),
                "titulo": titulo,
                "preco": preco,
                "imagem": foto,
                "frete_gratis": frete,
                "categoria": categoria_label,
                "link": link_afiliado(f"https://produto.mercadolivre.com.br/{mid_fmt}"),
                "item_id": mid,
            }
            print(f"  OK [{categoria_label}/search] R$ {p['preco']:.2f} — {p['titulo'][:50]}")
            return p
    except Exception as e:
        print(f"Erro search '{query}':", e)
    return None


def um_do_grupo(grupo, h, vistos_ids, vistos_titulos):
    # 1) highlights das categorias (moda exige sinal feminino no título)
    exigir = grupo["nome"] in ("Moda Feminina", "Calçados & Bolsas")
    for cat_id in grupo["cats"]:
        p = buscar_highlights(cat_id, h, vistos_ids, vistos_titulos, exigir_sinal=exigir)
        if p:
            return p
    # 2) fallback por busca textual
    for q in grupo.get("queries", []):
        p = buscar_por_query(q, h, vistos_ids, vistos_titulos, grupo["nome"])
        if p:
            return p
    return None


def montar_diversificado(h, estado):
    vistos_ids = set(estado["ids"].keys())
    vistos_titulos = set(estado["titulos"].keys())
    escolhidos = []
    for grupo in GRUPOS:
        p = um_do_grupo(grupo, h, vistos_ids, vistos_titulos)
        if p:
            vistos_ids.add(p["id"])
            nt = normalizar_titulo(p["titulo"])
            if nt:
                vistos_titulos.add(nt)
            escolhidos.append(p)
        if len(escolhidos) >= MAX_POSTS:
            break
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
    if 7 <= h <= 22:
        return True
    if h in (23, 2, 5):
        return True
    return False


def salvar_estado(estado):
    STATE.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    agora = dt.datetime.now(TZ)
    print("Iniciando Dona Maria", agora.isoformat())
    h = headers_ml()
    if not h:
        return

    estado = limpar_estado(carregar_estado(), agora)
    print(f"Produtos já postados (últimos {REPETIR_APOS_DIAS} dias):", len(estado["ids"]))

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
        print(f"Fora do horário de postagem (hora atual: {agora.hour}h). "
              "Dia: 7h–22h | Madrugada: 23h, 2h e 5h")
        salvar_estado(estado)
        return

    enviados = 0
    for p in ranking:
        if enviados >= MAX_POSTS:
            break
        if ja_postado(estado, p["id"], p["titulo"]):
            print(f"  Já postado recentemente, pulando: {p['id']}")
            continue
        if postar(p):
            registrar_postado(estado, p["id"], p["titulo"], agora)
            enviados += 1
            salvar_estado(estado)

    salvar_estado(estado)
    print("Postagens enviadas:", enviados)


if __name__ == "__main__":
    main()
