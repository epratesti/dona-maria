"""Dona Maria: ofertas femininas → Telegram.
Filtro: bloqueia masculino + limpeza + itens genéricos de casa.
Mostra preço original e com desconto quando o ML informar (de R$ X por R$ Y).
Anti-repetição: ID, item_id e fingerprint de título (14 dias).
Horário SP: 07h–22h
"""
import os, json, html, re, random, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

AFF_ID = os.getenv("ML_AFFILIATE_ID", "71970283")
AFF_PARAMS = os.getenv("ML_AFFILIATE_PARAMS", "matt_tool={id}")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
POSTS_POR_GRUPO = int(os.getenv("POSTS_POR_GRUPO", "1"))
MAX_POSTS = int(os.getenv("MAX_POSTS", "4"))
REPETIR_APOS_DIAS = int(os.getenv("REPETIR_APOS_DIAS", "14"))
API = "https://api.mercadolibre.com"
ROOT = Path(__file__).parent
TRENDS = ROOT / "docs" / "trends.json"
STATE = ROOT / "state" / "posted.json"
TZ = ZoneInfo("America/Sao_Paulo")

STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "em", "com", "para", "por", "um", "uma",
    "o", "a", "os", "as", "no", "na", "nos", "nas", "ao", "à", "ou", "x", "un",
    "unidades", "unidade", "kit", "original", "novo", "nova", "preto", "branco",
    "azul", "vermelho", "cor", "tamanho", "ml", "kg", "g", "cm", "mm", "w",
    "feminino", "feminina", "femininos", "femininas",
}

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
            "camisola feminina", "pijama feminino", "kit calcinha", "kit sutiã",
            "sutiã push up", "baby doll", "body lingerie",
        ],
    },
    {
        "nome": "Calçados & Bolsas",
        "cats": ["MLB1430"],
        "queries": [
            "tênis feminino", "sandália feminina", "bolsa feminina", "chinelo feminino",
            "scarpin feminino", "sapatilha feminina", "bota feminina",
            "rasteirinha feminina", "mochila feminina", "carteira feminina",
        ],
    },
    {
        "nome": "Beleza & Cuidados",
        "cats": ["MLB1246"],
        "queries": [
            "maquiagem", "perfume feminino", "batom", "kit maquiagem", "esmalte",
            "skincare", "shampoo feminino", "secador de cabelo", "chapinha",
            "máscara cílios", "base maquiagem", "hidratante facial",
        ],
    },
    {
        "nome": "Acessórios Femininos",
        "cats": ["MLB3937", "MLB1430"],
        "queries": [
            "colar feminino", "brinco feminino", "pulseira feminina",
            "anel feminino", "relógio feminino", "cinto feminino",
            "óculos de sol feminino", "tiara feminina", "lenço feminino",
            "organizador maquiagem", "nécessaire feminina",
        ],
    },
]

CAT_NOMES = {
    "MLB1430": "Moda", "MLB1246": "Beleza", "MLB1574": "Casa", "MLB3937": "Joias",
}

BLOQUEIO = re.compile(
    r"\b("
    r"masculin[oa]|para homem|para homens|menino|meninos|"
    r"cueca masculina|barbeador|"
    r"camiseta masculina|bermuda masculina|tênis masculino|"
    r"perfume masculino|relógio masculino|carteira masculina|"
    r"cinto masculino|jaqueta masculina|calça masculina|"
    r"sapato social masculino|chinelo masculino|camisa social masculina|"
    r"detergente|sabão|sabao|amaciante|desinfetante|água sanitária|agua sanitaria|"
    r"papel higi[eê]nico|papel toalha|esponja|multiuso|limpador|"
    r"alvejante|cloro|yp[eê]|omo\b|vanish|ajax|"
    r"ducha eletr[oô]nica|chuveiro el[eé]trico|torneira|"
    r"vassoura|rodo|balde|pano de ch[aã]o|chave de fenda|furadeira|"
    r"barbeador|máquina de cortar cabelo|aparador de barba|drag[aã]o"
    r")\b",
    re.I,
)

S = requests.Session()
S.headers.update({"User-Agent": "dona-maria/2.0", "Accept": "application/json"})


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
    return t[:100]


def fingerprint(t: str) -> str:
    nt = normalizar_titulo(t)
    palavras = []
    for w in nt.split():
        if len(w) < 3 or w in STOPWORDS or w.isdigit():
            continue
        palavras.append(w)
    chave = " ".join(sorted(palavras[:8]))
    return chave[:90] if chave else nt[:60]


def titulo_ok(titulo: str) -> bool:
    if not titulo:
        return False
    return not BLOQUEIO.search(titulo)


def extrair_precos(obj) -> tuple:
    try:
        preco = float(obj.get("price") or 0)
    except (TypeError, ValueError):
        preco = 0.0
    original = None
    for key in ("original_price", "base_price"):
        raw = obj.get(key)
        if raw is None:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val > preco > 0:
            original = val
            break
    return preco, original


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


def incorporar_trends(estado, agora):
    if REPETIR_APOS_DIAS <= 0:
        return estado
    try:
        if not TRENDS.exists():
            return estado
        data = json.loads(TRENDS.read_text(encoding="utf-8") or "{}")
        itens = data.get("itens") or []
        ts = data.get("atualizado") or agora.isoformat()
        for it in itens:
            pid = str(it.get("id") or "")
            titulo = it.get("titulo") or ""
            if pid:
                estado["ids"][pid] = ts
            for key in (normalizar_titulo(titulo), fingerprint(titulo)):
                if key:
                    estado["titulos"][key] = ts
        print(f"Trends incorporados: {len(itens)} itens")
    except Exception as e:
        print("Aviso ao ler trends:", e)
    return estado


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


def ja_postado(estado, pid, titulo, item_id=None):
    if REPETIR_APOS_DIAS <= 0:
        return False
    ids = estado.get("ids", {})
    if str(pid) in ids:
        return True
    if item_id and str(item_id) in ids:
        return True
    for cand in (str(pid), str(item_id or "")):
        if not cand:
            continue
        if cand.startswith("MLB") and "-" not in cand:
            alt = cand[:3] + "-" + cand[3:]
            if alt in ids:
                return True
        if "-" in cand:
            alt = cand.replace("-", "")
            if alt in ids:
                return True
    titulos = estado.get("titulos", {})
    nt = normalizar_titulo(titulo)
    fp = fingerprint(titulo)
    if nt and nt in titulos:
        return True
    if fp and fp in titulos:
        return True
    if fp:
        fp_tokens = set(fp.split())
        if len(fp_tokens) >= 3:
            for t in titulos:
                other = set(t.split())
                if len(fp_tokens & other) >= min(4, len(fp_tokens)):
                    return True
    return False


def registrar_postado(estado, pid, titulo, agora, item_id=None):
    if REPETIR_APOS_DIAS <= 0:
        return
    ts = agora.isoformat()
    estado.setdefault("ids", {})[str(pid)] = ts
    if item_id:
        mid = str(item_id)
        estado["ids"][mid] = ts
        if mid.startswith("MLB") and "-" not in mid:
            estado["ids"][mid[:3] + "-" + mid[3:]] = ts
    nt = normalizar_titulo(titulo)
    fp = fingerprint(titulo)
    if nt:
        estado.setdefault("titulos", {})[nt] = ts
    if fp:
        estado.setdefault("titulos", {})[fp] = ts


def escolher_oferta(results):
    if not results:
        return None
    validos = []
    for it in results:
        preco, original = extrair_precos(it)
        if preco <= 0:
            continue
        frete = (it.get("shipping") or {}).get("free_shipping", False)
        validos.append({
            "item": it, "preco": preco, "original": original, "frete": frete,
        })
    if not validos:
        return None
    com_desc = [v for v in validos if v["original"] and v["original"] > v["preco"]]
    pool_base = com_desc if com_desc else validos
    precos = sorted(v["preco"] for v in pool_base)
    mediana = precos[len(precos) // 2]
    piso = mediana * 0.30 if mediana > 0 else 0
    pool_base = [v for v in pool_base if v["preco"] >= piso] or pool_base
    com_frete = [v for v in pool_base if v["frete"]]
    pool = com_frete if com_frete else pool_base
    return min(pool, key=lambda x: x["preco"])


def montar_produto(pid, h, categoria):
    titulo, foto = "", ""
    preco, original, frete = 0.0, None, False
    item_id = None
    try:
        rp = S.get(f"{API}/products/{pid}", headers=h or {}, timeout=15)
        if rp.status_code == 200:
            d = rp.json()
            titulo = d.get("name") or d.get("title") or ""
            pics = d.get("pictures") or []
            if pics:
                foto = (pics[0].get("url") or pics[0].get("secure_url") or "").replace("http://", "https://")
    except Exception as e:
        print(f"  products/{pid}:", e)
    if not titulo_ok(titulo):
        return None
    try:
        ri = S.get(f"{API}/products/{pid}/items", headers=h or {}, timeout=15)
        if ri.status_code == 200:
            escolha = escolher_oferta(ri.json().get("results") or [])
            if escolha:
                preco = escolha["preco"]
                original = escolha.get("original")
                frete = escolha["frete"]
                item_id = escolha["item"].get("id") or escolha["item"].get("item_id")
                if item_id and not original:
                    try:
                        rd = S.get(f"{API}/items/{item_id}", headers=h or {}, timeout=12)
                        if rd.status_code == 200:
                            _, original = extrair_precos(rd.json())
                    except Exception:
                        pass
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
        "id": str(pid), "titulo": titulo, "preco": preco, "preco_original": original,
        "imagem": foto, "frete_gratis": frete, "categoria": categoria,
        "link": link, "item_id": item_id,
    }


def produto_search(item, label, h=None):
    titulo = item.get("title") or ""
    if not titulo_ok(titulo):
        return None
    preco, original = extrair_precos(item)
    if preco <= 0:
        return None
    frete = (item.get("shipping") or {}).get("free_shipping", False)
    foto = (item.get("thumbnail") or "").replace("http://", "https://")
    mid = str(item.get("id", ""))
    pid = item.get("catalog_product_id") or mid
    mid_fmt = (mid[:3] + "-" + mid[3:]) if mid.startswith("MLB") and "-" not in mid else mid
    permalink = item.get("permalink") or f"https://produto.mercadolivre.com.br/{mid_fmt}"
    if mid and not original:
        try:
            rd = S.get(f"{API}/items/{mid}", headers=h or {}, timeout=12)
            if rd.status_code == 200:
                d = rd.json()
                p2, o2 = extrair_precos(d)
                if p2 > 0:
                    preco = p2
                if o2:
                    original = o2
        except Exception:
            pass
    return {
        "id": str(pid), "titulo": titulo, "preco": preco, "preco_original": original,
        "imagem": foto, "frete_gratis": frete, "categoria": label,
        "link": link_afiliado(permalink), "item_id": mid,
    }


def ml_get(url, h, params=None):
    r = S.get(url, headers=h or {}, params=params, timeout=25)
    if r.status_code == 403 and h:
        r = S.get(url, headers={"User-Agent": "dona-maria/2.0", "Accept": "application/json"},
                  params=params, timeout=25)
    return r


def _marcar_visto(vistos_ids, vistos_fps, p):
    vistos_ids.add(str(p["id"]))
    if p.get("item_id"):
        vistos_ids.add(str(p["item_id"]))
    fp = fingerprint(p["titulo"])
    nt = normalizar_titulo(p["titulo"])
    if fp:
        vistos_fps.add(fp)
    if nt:
        vistos_fps.add(nt)


def _ja_visto(vistos_ids, vistos_fps, pid, mid, titulo):
    if pid in vistos_ids or (mid and mid in vistos_ids):
        return True
    fp = fingerprint(titulo)
    nt = normalizar_titulo(titulo)
    if fp and fp in vistos_fps:
        return True
    if nt and nt in vistos_fps:
        return True
    if fp:
        tokens = set(fp.split())
        if len(tokens) >= 3:
            for t in vistos_fps:
                if len(tokens & set(t.split())) >= min(4, len(tokens)):
                    return True
    return False


def buscar_varios_query(query, cat_id, h, vistos_ids, vistos_fps, label, quantos):
    achados = []
    try:
        offset = random.choice([20, 30, 40, 50, 60, 80, 100])
        params = {
            "q": query, "limit": 50, "offset": offset,
            "sort": random.choice(["relevance", "price_asc", "sold_quantity_desc"]),
        }
        if cat_id:
            params["category"] = cat_id
        r = ml_get(f"{API}/sites/MLB/search", h, params)
        if r.status_code != 200:
            print(f"  Search '{query}' status={r.status_code}")
            return achados
        results = list(r.json().get("results") or [])
        if not results:
            return achados
        results.sort(
            key=lambda it: 0 if (it.get("original_price") and float(it.get("original_price") or 0) > float(it.get("price") or 0)) else 1
        )
        random.shuffle(results[:25])
        for item in results:
            if len(achados) >= quantos:
                break
            pid = str(item.get("catalog_product_id") or item.get("id") or "")
            mid = str(item.get("id") or "")
            titulo = item.get("title") or ""
            if not pid or _ja_visto(vistos_ids, vistos_fps, pid, mid, titulo):
                continue
            p = produto_search(item, label, h=h)
            if not p:
                continue
            if _ja_visto(vistos_ids, vistos_fps, p["id"], str(p.get("item_id") or ""), p["titulo"]):
                continue
            _marcar_visto(vistos_ids, vistos_fps, p)
            achados.append(p)
            desc = f" (de {p['preco_original']:.2f})" if p.get("preco_original") else ""
            print(f"  OK [{label}] R$ {p['preco']:.2f}{desc} — {p['titulo'][:45]}")
    except Exception as e:
        print(f"Erro search '{query}':", e)
    return achados


def buscar_varios_highlights(cat_id, h, vistos_ids, vistos_fps, quantos, label):
    nome = label or CAT_NOMES.get(cat_id, cat_id)
    achados = []
    try:
        r = ml_get(f"{API}/highlights/MLB/category/{cat_id}", h)
        if r.status_code != 200:
            print(f"  Highlights {cat_id} status={r.status_code}")
            return achados
        items = list(r.json().get("content", [])[:40])
        random.shuffle(items)
        for item in items:
            if len(achados) >= quantos:
                break
            pid = str(item.get("id") or "")
            if not pid or pid in vistos_ids:
                continue
            p = montar_produto(pid, h, nome)
            if not p:
                continue
            if _ja_visto(vistos_ids, vistos_fps, p["id"], str(p.get("item_id") or ""), p["titulo"]):
                continue
            _marcar_visto(vistos_ids, vistos_fps, p)
            achados.append(p)
            print(f"  OK [{nome}/hl] R$ {p['preco']:.2f} — {p['titulo'][:45]}")
    except Exception as e:
        print(f"Erro highlights {cat_id}:", e)
    return achados


def varios_do_grupo(grupo, h, vistos_ids, vistos_fps, quantos):
    achados = []
    queries = list(grupo.get("queries", []))
    random.shuffle(queries)
    for q in queries[:6]:
        if len(achados) >= quantos:
            break
        falta = quantos - len(achados)
        cat = random.choice(grupo["cats"]) if grupo.get("cats") else None
        novos = buscar_varios_query(q, cat, h, vistos_ids, vistos_fps, grupo["nome"], falta)
        achados.extend(novos)
    if len(achados) < quantos:
        for cat_id in grupo.get("cats", []):
            if len(achados) >= quantos:
                break
            falta = quantos - len(achados)
            novos = buscar_varios_highlights(
                cat_id, h, vistos_ids, vistos_fps, falta, grupo["nome"]
            )
            achados.extend(novos)
    return achados


def montar_diversificado(h, estado):
    vistos_ids = set(str(k) for k in estado.get("ids", {}).keys())
    vistos_fps = set(estado.get("titulos", {}).keys())
    escolhidos = []
    grupos = list(GRUPOS)
    random.shuffle(grupos)
    for grupo in grupos:
        if len(escolhidos) >= MAX_POSTS:
            break
        n = min(POSTS_POR_GRUPO, MAX_POSTS - len(escolhidos))
        print(f"Grupo {grupo['nome']}: buscando até {n} (bloqueados: {len(vistos_ids)} ids)")
        novos = varios_do_grupo(grupo, h, vistos_ids, vistos_fps, n)
        escolhidos.extend(novos)
    return escolhidos


def preco_br(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_preco_linha(p):
    atual = p["preco"]
    original = p.get("preco_original")
    if original and original > atual:
        pct = int(round((1 - atual / original) * 100))
        linha = f"💰 De <s>{preco_br(original)}</s> por <b>{preco_br(atual)}</b>"
        if pct >= 5:
            linha += f" · <b>-{pct}%</b>"
        return linha
    return f"💰 <b>{preco_br(atual)}</b>"


def postar(p):
    cat = html.escape(p.get("categoria", ""))
    titulo = html.escape(p["titulo"][:120])
    link = html.escape(p["link"])
    frete_linha = "🚚 <b>Frete grátis</b>\n" if p.get("frete_gratis") else ""
    preco_linha = formatar_preco_linha(p)
    texto = (
        f"💕 <b>Dona Maria indica — {cat}</b>\n\n"
        f"📦 {titulo}\n\n"
        f"{preco_linha}\n"
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
    return 7 <= agora.hour <= 22


def salvar_estado(estado):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    agora = dt.datetime.now(TZ)
    print("Iniciando Dona Maria", agora.isoformat())
    print(f"Meta: {POSTS_POR_GRUPO}/grupo, máx {MAX_POSTS} | bloqueio {REPETIR_APOS_DIAS} dias")
    h = headers_ml()
    if not h:
        return
    estado = limpar_estado(carregar_estado(), agora)
    estado = incorporar_trends(estado, agora)
    print(f"Bloqueados: {len(estado.get('ids', {}))} ids, {len(estado.get('titulos', {}))} fingerprints")
    ranking = montar_diversificado(h, estado)
    ranking = [p for p in ranking if not ja_postado(estado, p["id"], p["titulo"], p.get("item_id"))]
    print("Selecionados após filtro:", len(ranking))
    TRENDS.parent.mkdir(parents=True, exist_ok=True)
    trends_itens = [{k: v for k, v in p.items() if k != "item_id"} for p in ranking]
    TRENDS.write_text(json.dumps({"atualizado": agora.isoformat(), "itens": trends_itens},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    if not ranking:
        print("Nada novo para postar")
        salvar_estado(estado)
        return
    if not (TG_TOKEN and TG_CHAT):
        print("Falta Telegram")
        salvar_estado(estado)
        return
    if not pode_postar_agora(agora):
        print(f"Fora do horário ({agora.hour}h) — sem postar")
        salvar_estado(estado)
        return
    enviados = 0
    for p in ranking:
        if enviados >= MAX_POSTS:
            break
        if ja_postado(estado, p["id"], p["titulo"], p.get("item_id")):
            print(f"  Pula: {p['titulo'][:50]}")
            continue
        if postar(p):
            registrar_postado(estado, p["id"], p["titulo"], agora, p.get("item_id"))
            enviados += 1
            salvar_estado(estado)
    salvar_estado(estado)
    print("Postagens enviadas:", enviados)
    print(f"Estado: {len(estado.get('ids', {}))} ids bloqueados")


if __name__ == "__main__":
    main()
