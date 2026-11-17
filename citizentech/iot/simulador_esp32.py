"""Simulador do ESP32 do CitizenTech.

Publica EXATAMENTE os mesmos tópicos e payloads do firmware, para:
  - testar o receptor/banco sem o hardware;
  - gerar dados de demonstração para o agente GenAI;
  - registrar as situações de entrada pedidas no enunciado.

Cenários:
  normal   - pista em bom estado (SIM0001)
  buraco   - irregularidade leve + 2 buracos graves (SIM0002)
  chuva    - umidade alta + irregularidades leves (SIM0003)
  reporte  - motorista aperta o botão (SIM0002)
  critico  - veículo volta a um trecho de prioridade alta e recebe o comando
  demo     - todos os anteriores em sequência

Uso:
    python iot/simulador_esp32.py --cenario demo
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paho.mqtt.client as mqtt  # noqa: E402

import config  # noqa: E402

BASELINE_MM = 150  # altura do sensor até o solo plano na maquete


class EspSimulado:
    def __init__(self, device_id: str, intervalo: float):
        self.device = device_id
        self.intervalo = intervalo
        self.trecho = None
        self.temp, self.umid = 26.0, 60.0
        try:
            self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{device_id}-{random.randint(0, 9999)}")
        except AttributeError:
            self.c = mqtt.Client(client_id=f"{device_id}-{random.randint(0, 9999)}")
        self.c.will_set(config.topico(device_id, "status"), "offline", qos=1, retain=True)
        self.c.on_message = self._comando
        self.c.connect(config.MQTT_HOST, config.MQTT_PORTA, 60)
        self.c.loop_start()
        self.c.subscribe(config.topico(device_id, "comando"), qos=1)
        self.c.publish(config.topico(device_id, "status"), "online", qos=1, retain=True)
        time.sleep(0.5)

    def _comando(self, client, userdata, msg):
        texto = msg.payload.decode()
        print(f"   [{self.device}] COMANDO RECEBIDO: {texto}")
        if "alerta" in texto:
            print("   -> LED vermelho piscando por 5 s")
            self.evento("alerta_recebido", "info", 0)

    def _pub(self, tipo: str, payload: dict):
        js = json.dumps(payload)
        self.c.publish(config.topico(self.device, tipo), js, qos=1)
        print(f"[{tipo.upper():7}] {js}")
        time.sleep(self.intervalo)

    def leitura(self, prof: int, status: str = "ok"):
        self._pub("leitura", {
            "device": self.device, "trecho": self.trecho,
            "dist_mm": BASELINE_MM + prof, "prof_mm": prof,
            "temp_c": round(self.temp + random.uniform(-0.3, 0.3), 1),
            "umid": round(self.umid + random.uniform(-1, 1), 1),
            "pista_umida": self.umid >= 85, "status": status, "ts": int(time.time()),
        })

    def evento(self, tipo: str, severidade: str, prof: int):
        self._pub("evento", {
            "device": self.device, "tipo": tipo, "severidade": severidade,
            "trecho": self.trecho, "prof_mm": prof,
            "temp_c": round(self.temp, 1), "umid": round(self.umid, 1), "ts": int(time.time()),
        })

    def entrar_trecho(self, uid: str):
        self.trecho = uid
        self.evento("mudanca_trecho", "info", 0)

    def buraco(self, prof: int):
        sev = "grave" if prof >= 40 else "leve"
        self.leitura(prof, sev)
        self.evento("buraco", sev, prof)

    def fechar(self):
        time.sleep(1.5)  # tempo para chegar um eventual comando de volta
        self.c.publish(config.topico(self.device, "status"), "offline", qos=1, retain=True)
        self.c.loop_stop()
        self.c.disconnect()


def titulo(t):
    print(f"\n===== {t} =====")


def cenario_normal(e):
    titulo("Situação 1 — pista em bom estado")
    e.temp, e.umid = 25.5, 58.0
    e.entrar_trecho("SIM0001")
    for _ in range(4):
        e.leitura(random.randint(0, 4))


def cenario_buraco(e):
    titulo("Situação 2 — buracos na pista")
    e.temp, e.umid = 27.0, 62.0
    e.entrar_trecho("SIM0002")
    e.leitura(2)
    e.buraco(22)
    e.leitura(1)
    e.buraco(58)
    e.leitura(3)
    e.buraco(63)


def cenario_chuva(e):
    titulo("Situação 3 — chuva / pista úmida")
    e.temp, e.umid = 19.0, 92.0
    e.entrar_trecho("SIM0003")
    e.leitura(3)
    e.buraco(18)
    e.buraco(27)
    e.leitura(2)


def cenario_reporte(e):
    titulo("Situação 4 — reporte manual (botão)")
    e.temp, e.umid = 26.5, 63.0
    e.entrar_trecho("SIM0002")
    e.evento("reporte_manual", "info", 0)


def cenario_critico(e):
    titulo("Situação 5 — veículo entra em trecho de prioridade ALTA")
    e.entrar_trecho("SIM0002")
    time.sleep(1.5)


CENARIOS = {
    "normal": [cenario_normal],
    "buraco": [cenario_buraco],
    "chuva": [cenario_chuva],
    "reporte": [cenario_reporte],
    "critico": [cenario_critico],
    "demo": [cenario_normal, cenario_buraco, cenario_chuva, cenario_reporte, cenario_critico],
}

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cenario", choices=CENARIOS, default="demo")
    p.add_argument("--device", default="esp32-sim")
    p.add_argument("--intervalo", type=float, default=1.0, help="segundos entre mensagens")
    a = p.parse_args()

    esp = EspSimulado(a.device, a.intervalo)
    for f in CENARIOS[a.cenario]:
        f(esp)
    esp.fechar()
    print("\nSimulação concluída.")
