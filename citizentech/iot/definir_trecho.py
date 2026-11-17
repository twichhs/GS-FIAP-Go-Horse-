"""GPS simulado: informa ao ESP32 em qual trecho da via ele está.

No protótipo não há GPS. Durante a demo, você move o carrinho para outra
"rua" da maquete e roda este script com o código do trecho. O ESP32 passa a
marcar as leituras com esse trecho e publica um evento "mudanca_trecho".

Uso (na raiz do projeto):
    python iot/definir_trecho.py --listar
    python iot/definir_trecho.py SIM0002
    python iot/definir_trecho.py SIM0003 --device esp32-01
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paho.mqtt.client as mqtt  # noqa: E402

import banco  # noqa: E402
import config  # noqa: E402

p = argparse.ArgumentParser(description="Define o trecho atual do ESP32 (GPS simulado)")
p.add_argument("codigo", nargs="?", help="código do trecho, ex.: SIM0002")
p.add_argument("--device", default="esp32-01")
p.add_argument("--listar", action="store_true", help="mostra os trechos cadastrados")
a = p.parse_args()

conn = banco.conectar()
banco.inicializar(conn)

if a.listar or not a.codigo:
    for r in conn.execute("SELECT uid, nome, bairro FROM trechos ORDER BY uid"):
        print(f"{r['uid']}  {r['nome']}  ({r['bairro'] or '-'})")
    sys.exit(0)

if not conn.execute("SELECT 1 FROM trechos WHERE uid = ?", (a.codigo,)).fetchone():
    sys.exit(f"Trecho {a.codigo} não cadastrado. Use --listar ou cadastre com banco.py --cadastrar.")

cmd = json.dumps({"acao": "trecho", "codigo": a.codigo})
try:  # paho-mqtt 2.x
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"citizentech-gps-{uuid.uuid4().hex[:6]}")
except AttributeError:  # paho-mqtt 1.x
    cli = mqtt.Client(client_id=f"citizentech-gps-{uuid.uuid4().hex[:6]}")
cli.connect(config.MQTT_HOST, config.MQTT_PORTA, 30)
cli.loop_start()
info = cli.publish(config.topico(a.device, "comando"), cmd, qos=1)
info.wait_for_publish(timeout=10)
cli.loop_stop()
cli.disconnect()
if not info.is_published():
    sys.exit("Falha ao enviar o comando (verifique o broker).")
print(f"Enviado para {a.device}: {cmd}  ->  {banco.nome_trecho(conn, a.codigo)}")
