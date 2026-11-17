"""Banco de dados compartilhado do CitizenTech (SQLite).

Quem usa:
  - Receptor IoT (iot/receptor_mqtt.py) ...... grava leituras e eventos do ESP32
  - Módulo de Visão (app/notebook) ............ grava detecções de buracos (YOLO)
  - Agente GenAI ............................... consulta vw_prioridade_trechos

Uso pela linha de comando:
  python banco.py --resumo                 # ranking de prioridade por trecho
  python banco.py --ultimos 15             # últimos eventos IoT
  python banco.py --cadastrar SIM0005 "Rua X, 100-300" "Bairro"   # novo trecho
"""
import argparse
import json
import sqlite3
from datetime import datetime

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS trechos (
    uid     TEXT PRIMARY KEY,          -- código do trecho (GPS simulado)
    nome    TEXT NOT NULL,
    bairro  TEXT,
    lat     REAL,
    lon     REAL
);

CREATE TABLE IF NOT EXISTS leituras_iot (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT,
    trecho_uid      TEXT,
    distancia_mm    INTEGER,
    profundidade_mm INTEGER,
    temperatura_c   REAL,
    umidade_pct     REAL,
    pista_umida     INTEGER,
    status          TEXT,              -- ok | leve | grave
    ts_dispositivo  INTEGER,
    recebido_em     TEXT
);

CREATE TABLE IF NOT EXISTS eventos_iot (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT,
    trecho_uid      TEXT,
    tipo            TEXT,              -- buraco | reporte_manual | mudanca_trecho | calibracao | alerta_recebido | online
    severidade      TEXT,              -- leve | grave | info
    profundidade_mm INTEGER,
    temperatura_c   REAL,
    umidade_pct     REAL,
    ts_dispositivo  INTEGER,
    recebido_em     TEXT,
    descricao       TEXT               -- texto livre (reporte do cidadão pelo agente GenAI)
);

CREATE TABLE IF NOT EXISTS deteccoes_visao (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trecho_uid  TEXT,
    arquivo     TEXT,
    classe      TEXT,                  -- ex.: pothole, crack
    confianca   REAL,
    bbox        TEXT,                  -- JSON [x1, y1, x2, y2] em pixels
    modelo      TEXT,
    criado_em   TEXT
);

CREATE TABLE IF NOT EXISTS status_dispositivos (
    device_id     TEXT PRIMARY KEY,
    status        TEXT,                -- online | offline
    atualizado_em TEXT
);

CREATE INDEX IF NOT EXISTS ix_eventos_trecho  ON eventos_iot(trecho_uid);
CREATE INDEX IF NOT EXISTS ix_leituras_trecho ON leituras_iot(trecho_uid);
CREATE INDEX IF NOT EXISTS ix_visao_trecho    ON deteccoes_visao(trecho_uid);
"""

# Pontuação de prioridade por trecho (fonte principal do agente GenAI):
#   3 x buraco grave + 1 x irregularidade leve + 2 x reporte manual
#   + 2 x detecção visual (confiança >= 0,5), x 1,2 se a umidade média >= 80 %
VIEW_PRIORIDADE = f"""
DROP VIEW IF EXISTS vw_prioridade_trechos;
CREATE VIEW vw_prioridade_trechos AS
WITH ev AS (
    SELECT trecho_uid,
           SUM(tipo = 'buraco' AND severidade = 'grave')       AS graves,
           SUM(tipo = 'buraco' AND severidade = 'leve')        AS leves,
           SUM(tipo = 'reporte_manual')                        AS reportes,
           MAX(CASE WHEN tipo = 'buraco' THEN profundidade_mm END) AS prof_max_mm,
           AVG(umidade_pct)                                    AS umidade_media,
           MAX(CASE WHEN tipo IN ('buraco', 'reporte_manual') THEN recebido_em END) AS ultimo_evento
    FROM eventos_iot
    WHERE trecho_uid IS NOT NULL
    GROUP BY trecho_uid
),
vi AS (
    SELECT trecho_uid,
           COUNT(*)        AS deteccoes,
           AVG(confianca)  AS conf_media,
           MAX(criado_em)  AS ultima_deteccao
    FROM deteccoes_visao
    WHERE confianca >= 0.5 AND trecho_uid IS NOT NULL
    GROUP BY trecho_uid
),
base AS (
    SELECT t.uid, t.nome, t.bairro, t.lat, t.lon,
           COALESCE(ev.graves, 0)     AS graves,
           COALESCE(ev.leves, 0)      AS leves,
           COALESCE(ev.reportes, 0)   AS reportes,
           COALESCE(vi.deteccoes, 0)  AS deteccoes_visao,
           ROUND(vi.conf_media, 2)    AS conf_media_visao,
           ev.prof_max_mm,
           ROUND(ev.umidade_media, 1) AS umidade_media,
           ev.ultimo_evento,
           vi.ultima_deteccao
    FROM trechos t
    LEFT JOIN ev ON ev.trecho_uid = t.uid
    LEFT JOIN vi ON vi.trecho_uid = t.uid
),
pont AS (
    SELECT *,
           ROUND((3 * graves + leves + 2 * reportes + 2 * deteccoes_visao)
                 * CASE WHEN umidade_media >= 80 THEN 1.2 ELSE 1.0 END, 1) AS pontuacao
    FROM base
)
SELECT *,
       CASE WHEN pontuacao >= {config.LIMIAR_PRIORIDADE_ALTA}  THEN 'alta'
            WHEN pontuacao >= {config.LIMIAR_PRIORIDADE_MEDIA} THEN 'media'
            WHEN pontuacao > 0 THEN 'baixa'
            ELSE 'sem_registro' END AS nivel
FROM pont
ORDER BY pontuacao DESC;
"""

# Trechos de EXEMPLO (dados fictícios), usados pelo simulador e pela demo física.
# Cada "rua" da maquete corresponde a um código; o trecho atual é informado ao
# ESP32 por iot/definir_trecho.py (GPS simulado). Para criar outros:
#   python banco.py --cadastrar SIM0005 "Rua Vergueiro, 1400-1800" "Vila Mariana"
TRECHOS_EXEMPLO = [
    ("SIM0001", "Rua Vergueiro, 1000-1400", "Vila Mariana", -23.5779, -46.6395),
    ("SIM0002", "Av. Lins de Vasconcelos, 800-1200", "Cambuci", -23.5700, -46.6230),
    ("SIM0003", "Rua Domingos de Morais, 2000-2400", "Vila Mariana", -23.5930, -46.6370),
    ("SIM0004", "Av. Jabaquara, 500-900", "Saúde", -23.6120, -46.6390),
]


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conectar(caminho: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(caminho or config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # migração leve: bancos criados antes da coluna 'descricao'
    colunas = {r["name"] for r in conn.execute("PRAGMA table_info(eventos_iot)")}
    if "descricao" not in colunas:
        conn.execute("ALTER TABLE eventos_iot ADD COLUMN descricao TEXT")
    conn.executescript(VIEW_PRIORIDADE)
    conn.executemany(
        "INSERT OR IGNORE INTO trechos (uid, nome, bairro, lat, lon) VALUES (?, ?, ?, ?, ?)",
        TRECHOS_EXEMPLO,
    )
    conn.commit()


def garantir_trecho(conn, uid):
    """Código desconhecido vira um trecho 'não cadastrado' (para não perder o dado)."""
    if not uid:
        return None
    conn.execute(
        "INSERT OR IGNORE INTO trechos (uid, nome) VALUES (?, ?)",
        (uid, f"Trecho não cadastrado ({uid})"),
    )
    return uid


def cadastrar_trecho(conn, uid, nome, bairro=None, lat=None, lon=None):
    conn.execute(
        """INSERT INTO trechos (uid, nome, bairro, lat, lon) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(uid) DO UPDATE SET nome=excluded.nome, bairro=excluded.bairro,
                                          lat=excluded.lat, lon=excluded.lon""",
        (uid, nome, bairro, lat, lon),
    )
    conn.commit()


def inserir_leitura(conn, device_id: str, d: dict) -> None:
    uid = garantir_trecho(conn, d.get("trecho"))
    conn.execute(
        """INSERT INTO leituras_iot (device_id, trecho_uid, distancia_mm, profundidade_mm,
               temperatura_c, umidade_pct, pista_umida, status, ts_dispositivo, recebido_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (device_id, uid, d.get("dist_mm"), d.get("prof_mm"), d.get("temp_c"), d.get("umid"),
         int(bool(d.get("pista_umida"))), d.get("status"), d.get("ts"), agora()),
    )
    conn.commit()


def inserir_evento(conn, device_id: str, d: dict) -> None:
    uid = garantir_trecho(conn, d.get("trecho"))
    conn.execute(
        """INSERT INTO eventos_iot (device_id, trecho_uid, tipo, severidade, profundidade_mm,
               temperatura_c, umidade_pct, ts_dispositivo, recebido_em, descricao)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (device_id, uid, d.get("tipo"), d.get("severidade"), d.get("prof_mm"),
         d.get("temp_c"), d.get("umid"), d.get("ts"), agora(), d.get("descricao")),
    )
    conn.commit()


def inserir_reporte_cidadao(conn, trecho_uid: str, descricao: str, origem: str = "cidadao-app") -> None:
    """Reporte feito pelo cidadão via agente GenAI: conta como reporte_manual na prioridade."""
    inserir_evento(conn, origem, {"tipo": "reporte_manual", "severidade": "info", "trecho": trecho_uid,
                                  "descricao": descricao})


def trecho_existe(conn, uid) -> bool:
    return conn.execute("SELECT 1 FROM trechos WHERE uid = ?", (uid,)).fetchone() is not None


def listar_trechos(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT uid, nome, bairro, lat, lon FROM trechos ORDER BY uid")]


def eventos_do_trecho(conn, uid, n: int = 10) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT recebido_em, device_id, tipo, severidade, profundidade_mm, umidade_pct, descricao
           FROM eventos_iot WHERE trecho_uid = ? AND tipo IN ('buraco', 'reporte_manual')
           ORDER BY id DESC LIMIT ?""", (uid, n))]


def deteccoes_do_trecho(conn, uid, n: int = 10) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT criado_em, arquivo, classe, confianca, bbox, modelo
           FROM deteccoes_visao WHERE trecho_uid = ? ORDER BY id DESC LIMIT ?""", (uid, n))]


def status_dispositivos(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT device_id, status, atualizado_em FROM status_dispositivos")]


def inserir_deteccao_visao(conn, trecho_uid, arquivo, classe, confianca, bbox, modelo) -> None:
    """Chamada pelo módulo de Visão Computacional para cada caixa detectada."""
    garantir_trecho(conn, trecho_uid)
    conn.execute(
        """INSERT INTO deteccoes_visao (trecho_uid, arquivo, classe, confianca, bbox, modelo, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (trecho_uid, arquivo, classe, float(confianca), json.dumps(bbox), modelo, agora()),
    )
    conn.commit()


def atualizar_status(conn, device_id: str, status: str) -> None:
    conn.execute(
        """INSERT INTO status_dispositivos (device_id, status, atualizado_em) VALUES (?, ?, ?)
           ON CONFLICT(device_id) DO UPDATE SET status=excluded.status, atualizado_em=excluded.atualizado_em""",
        (device_id, status, agora()),
    )
    conn.commit()


def prioridades(conn, apenas_com_registro: bool = True) -> list[dict]:
    sql = "SELECT * FROM vw_prioridade_trechos"
    if apenas_com_registro:
        sql += " WHERE pontuacao > 0"
    return [dict(r) for r in conn.execute(sql)]


def prioridade_do_trecho(conn, uid) -> dict | None:
    r = conn.execute("SELECT * FROM vw_prioridade_trechos WHERE uid = ?", (uid,)).fetchone()
    return dict(r) if r else None


def nome_trecho(conn, uid) -> str:
    if not uid:
        return "trecho não identificado"
    r = conn.execute("SELECT nome FROM trechos WHERE uid = ?", (uid,)).fetchone()
    return r["nome"] if r else uid


def ultimos_eventos(conn, n: int = 15) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT e.recebido_em, e.device_id, e.tipo, e.severidade, e.profundidade_mm,
                  e.umidade_pct, t.nome AS trecho
           FROM eventos_iot e LEFT JOIN trechos t ON t.uid = e.trecho_uid
           ORDER BY e.id DESC LIMIT ?""", (n,))]


def _imprimir_tabela(linhas: list[dict], colunas: list[str]) -> None:
    if not linhas:
        print("(sem registros)")
        return
    larg = {c: max(len(c), *(len(str(l.get(c, ""))) for l in linhas)) for c in colunas}
    print("  ".join(c.ljust(larg[c]) for c in colunas))
    print("  ".join("-" * larg[c] for c in colunas))
    for l in linhas:
        print("  ".join(str(l.get(c, "") if l.get(c) is not None else "-").ljust(larg[c]) for c in colunas))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Consultas ao banco CitizenTech")
    p.add_argument("--resumo", action="store_true", help="ranking de prioridade por trecho")
    p.add_argument("--ultimos", type=int, metavar="N", help="últimos N eventos IoT")
    p.add_argument("--cadastrar", nargs="+", metavar=("UID", "NOME"),
                   help='UID "nome do trecho" ["bairro"]')
    a = p.parse_args()

    c = conectar()
    inicializar(c)
    if a.cadastrar:
        if len(a.cadastrar) < 2:
            p.error("--cadastrar exige UID e nome")
        cadastrar_trecho(c, a.cadastrar[0], a.cadastrar[1], a.cadastrar[2] if len(a.cadastrar) > 2 else None)
        print(f"Trecho {a.cadastrar[0]} cadastrado.")
    if a.ultimos:
        _imprimir_tabela(ultimos_eventos(c, a.ultimos),
                         ["recebido_em", "device_id", "tipo", "severidade", "profundidade_mm", "umidade_pct", "trecho"])
    if a.resumo or not (a.ultimos or a.cadastrar):
        _imprimir_tabela(prioridades(c),
                         ["nome", "graves", "leves", "reportes", "deteccoes_visao", "prof_max_mm",
                          "umidade_media", "pontuacao", "nivel"])
