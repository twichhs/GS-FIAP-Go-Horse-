"""Configuração compartilhada do CitizenTech (IoT, Visão e GenAI).

Todos os valores podem ser sobrescritos por variáveis de ambiente.
"""
import os
from pathlib import Path

try:  # variáveis do arquivo .env na raiz do repositório (opcional)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

RAIZ = Path(__file__).resolve().parent

# ---- MQTT ----
MQTT_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORTA = int(os.getenv("MQTT_PORTA", "1883"))
# Troque "grupoX" por algo único do seu grupo (broker público é compartilhado!)
# e use o MESMO valor em TOPICO_BASE no firmware do ESP32.
TOPICO_BASE = os.getenv("MQTT_BASE", "fiap/citizentech/grupoX")


def topico(device_id: str, tipo: str) -> str:
    """Ex.: fiap/citizentech/grupoX/esp32-01/evento"""
    return f"{TOPICO_BASE}/{device_id}/{tipo}"


# ---- Banco de dados (SQLite compartilhado pelos 3 módulos) ----
DB_PATH = os.getenv("CITIZENTECH_DB", str(RAIZ / "citizentech.db"))

# ---- Telegram (opcional: deixe vazio para só imprimir os alertas) ----
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---- Regras de prioridade (usadas pelo receptor e pela view do banco) ----
LIMIAR_PRIORIDADE_ALTA = 8
LIMIAR_PRIORIDADE_MEDIA = 4
