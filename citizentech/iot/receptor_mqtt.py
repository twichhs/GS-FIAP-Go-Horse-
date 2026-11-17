"""Receptor MQTT do CitizenTech.

Assina os tópicos publicados pelo ESP32, grava tudo no banco compartilhado e
transforma os dados em AÇÃO:
  - buraco grave ou reporte manual  -> alerta (console + Telegram, se configurado)
  - trecho atinge prioridade ALTA   -> alerta para a equipe de zeladoria
  - veículo entra num trecho crítico -> comando MQTT de volta ao ESP32
                                        (LED vermelho piscando)

Execução (na raiz do projeto):
    python iot/receptor_mqtt.py
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paho.mqtt.client as mqtt  # noqa: E402

import banco  # noqa: E402
import config  # noqa: E402

conn = banco.conectar()
banco.inicializar(conn)


# ----------------------------- alertas --------------------------------------
def enviar_telegram(texto: str) -> None:
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    dados = urllib.parse.urlencode({"chat_id": config.TELEGRAM_CHAT_ID, "text": texto}).encode()
    try:
        urllib.request.urlopen(url, data=dados, timeout=10)
    except Exception as e:  # o alerta não pode derrubar o receptor
        print(f"   (falha ao enviar Telegram: {e})")


def alertar(texto: str) -> None:
    print(f"[ALERTA] {texto}")
    enviar_telegram(f"CitizenTech - alerta de pavimento\n{texto}")


def fmt(v, sufixo=""):
    return "n/d" if v is None else f"{v}{sufixo}"


# ----------------------------- regras ---------------------------------------
def tratar_evento(client, device: str, d: dict) -> None:
    antes = banco.prioridade_do_trecho(conn, d.get("trecho")) if d.get("trecho") else None
    banco.inserir_evento(conn, device, d)

    tipo, sev, uid = d.get("tipo"), d.get("severidade"), d.get("trecho")
    trecho = banco.nome_trecho(conn, uid)
    clima = f"umidade {fmt(d.get('umid'), '%')}, {fmt(d.get('temp_c'), '°C')}"

    if tipo == "buraco" and sev == "grave":
        alertar(f"Buraco GRAVE em {trecho}: profundidade ~{d.get('prof_mm')} mm ({clima}). "
                "Vistoria recomendada.")
    elif tipo == "buraco":
        print(f"[LEVE]   Irregularidade leve em {trecho}: ~{d.get('prof_mm')} mm ({clima})")
    elif tipo == "reporte_manual":
        alertar(f"Reporte manual do veículo {device} em {trecho} ({clima}).")
    elif tipo == "mudanca_trecho":
        print(f"[TRECHO] {device} entrou em: {trecho}")
        p = banco.prioridade_do_trecho(conn, uid)
        if p and p["nivel"] == "alta":
            cmd = {"acao": "alerta", "motivo": f"trecho crítico: {trecho}", "pontuacao": p["pontuacao"]}
            client.publish(config.topico(device, "comando"), json.dumps(cmd, ensure_ascii=False))
            print(f"[CMD]    comando enviado ao {device}: {cmd}")
    else:
        print(f"[INFO]   evento {tipo} de {device}")

    # Mudança de nível de prioridade do trecho -> avisa a zeladoria
    if uid and tipo in ("buraco", "reporte_manual"):
        depois = banco.prioridade_do_trecho(conn, uid)
        if depois and depois["nivel"] == "alta" and (not antes or antes["nivel"] != "alta"):
            alertar(f"{trecho} atingiu prioridade ALTA (pontuação {depois['pontuacao']}: "
                    f"{depois['graves']} graves, {depois['leves']} leves, "
                    f"{depois['reportes']} reportes, {depois['deteccoes_visao']} detecções visuais).")


def tratar_leitura(device: str, d: dict) -> None:
    banco.inserir_leitura(conn, device, d)
    icone = {"ok": "[OK]   ", "leve": "[LEVE] ", "grave": "[GRAVE]"}.get(d.get("status"), "[?]    ")
    umida = " · pista úmida" if d.get("pista_umida") else ""
    print(f"{icone} leitura {device} | {banco.nome_trecho(conn, d.get('trecho'))} | "
          f"prof {fmt(d.get('prof_mm'), ' mm')} | {fmt(d.get('temp_c'), '°C')} "
          f"{fmt(d.get('umid'), '%')}{umida}")


# ----------------------------- MQTT -----------------------------------------
def on_connect(client, userdata, flags, rc, properties=None):
    filtro = f"{config.TOPICO_BASE}/+/+"
    client.subscribe(filtro, qos=1)
    print(f"[MQTT] Conectado a {config.MQTT_HOST}:{config.MQTT_PORTA} — assinando {filtro}")
    print(f"   Banco: {config.DB_PATH}\n")


def on_message(client, userdata, msg):
    resto = msg.topic[len(config.TOPICO_BASE) + 1:].split("/")
    if len(resto) != 2:
        return
    device, tipo = resto
    texto = msg.payload.decode("utf-8", errors="replace")

    if tipo == "status":
        banco.atualizar_status(conn, device, texto)
        print(f"[STATUS] {device}: {texto}")
        return
    if tipo == "comando":          # comandos que nós mesmos enviamos
        return
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError:
        print(f"Mensagem inválida em {msg.topic}: {texto!r}")
        return

    if tipo == "leitura":
        tratar_leitura(device, dados)
    elif tipo == "evento":
        tratar_evento(client, device, dados)


def criar_cliente(client_id: str) -> mqtt.Client:
    try:  # paho-mqtt 2.x
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except AttributeError:  # paho-mqtt 1.x
        return mqtt.Client(client_id=client_id)


def main():
    import uuid
    client = criar_cliente(f"citizentech-receptor-{uuid.uuid4().hex[:6]}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.MQTT_HOST, config.MQTT_PORTA, keepalive=60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
