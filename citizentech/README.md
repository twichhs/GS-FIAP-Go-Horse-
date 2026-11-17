> Este README cobre o **módulo IoT**. A visão geral dos três módulos está em [../README.md](../README.md).

# CitizenTech · Monitor de Pavimento — Módulo IoT

Um ESP32 instalado em um veículo de serviço municipal (ônibus, viatura da zeladoria) mede a via enquanto circula. Ele detecta buracos e registra a condição climática de cada trecho da via. Os dados vão por MQTT para um banco compartilhado. Esse banco também recebe as detecções do módulo de **Visão Computacional** e é consultado pelo **agente GenAI**, que monta o ranking de inspeção.

```
 VL53L0X ─┐                                   ┌─> alertas (console / Telegram)
 DHT22   ─┼─> ESP32 ──MQTT──> Broker ──> receptor_mqtt.py ──> citizentech.db ──> Agente GenAI
 Botão   ─┘    ▲                          │                       ▲
 LEDs        ◄─┘ comandos "alerta" / "trecho" (GPS simulado)      │
                                              App de Visão (YOLO) ┘
```

## Papel de cada sensor

| Componente | O que mede | Por que importa para o problema |
|---|---|---|
| **VL53L0X** (ToF, I2C) | Distância até o solo | Diferença em relação à altura calibrada = **profundidade** do buraco. Classificado em *leve* (≥ 15 mm) ou *grave* (≥ 40 mm) na escala da maquete |
| **DHT22** | Temperatura e umidade | A infiltração de água é a principal causa de buracos. Umidade ≥ 85 % indica pista molhada, e a pontuação do trecho é multiplicada por 1,2 quando a umidade média passa de 80 % |
| **Botão** | Clique | Reporte manual do motorista ou agente |
| **LEDs** | — | Ação local: 🟢 ok · 🟡 irregularidade leve ou pista úmida · 🔴 buraco grave · 🔴 piscando = trecho crítico (comando vindo do servidor) · os 3 acesos por um instante = troca de trecho ou botão confirmados |

## Ligações (ESP32 DevKit)

| Componente | Pino do componente → ESP32 |
|---|---|
| VL53L0X | VIN → 3V3 · GND → GND · SDA → GPIO 21 · SCL → GPIO 22 |
| DHT22 | VCC → 3V3 · DATA → GPIO 4 (resistor 10 kΩ para 3V3, se o módulo não tiver) · GND → GND |
| Botão | um terminal → GPIO 13, outro → GND (usa pull-up interno) |
| LED verde / amarelo / vermelho | GPIO 25 / 26 / 33 → resistor 220 Ω → LED → GND |

**Montagem para a demo:** prenda o VL53L0X apontando para baixo num carrinho ou suporte a ~15 cm da mesa. Para simular buracos, use uma superfície plana com rebaixos (por exemplo, uma tampa de caixa com recortes de 2 cm e 5 cm de profundidade). Ao ligar, o ESP32 calibra a altura de referência por cerca de 1,5 s, então ele precisa estar sobre a parte plana.

**Trecho da via (GPS simulado):** o protótipo não tem GPS. Monte a maquete com 2 ou 3 "ruas" e, ao mover o carrinho de uma para outra, informe o trecho pelo computador com `python iot/definir_trecho.py SIM0002`. O ESP32 liga no trecho `SIM0001`.

## Como rodar

**1. Firmware**
- Arduino IDE com a placa *ESP32 Dev Module*.
- Bibliotecas: **PubSubClient**, **VL53L0X (Pololu)**, **DHT sensor library (Adafruit)** e **Adafruit Unified Sensor**.
- Edite `WIFI_SSID`, `WIFI_SENHA` e `TOPICO_BASE` em `iot/esp32_citizentech/esp32_citizentech.ino` e grave.
- O código foi compilado com sucesso para ESP32 (core 2.0.9).

**2. Back-end (no computador)**
```bash
pip install -r requirements.txt
# deixe TOPICO_BASE igual ao do firmware (config.py ou variável MQTT_BASE)
python iot/receptor_mqtt.py
```

**3. Trocar de trecho durante a demo (GPS simulado)**
```bash
python iot/definir_trecho.py --listar     # trechos cadastrados
python iot/definir_trecho.py SIM0002      # ESP32 passa a marcar leituras nesse trecho
python banco.py --cadastrar SIM0005 "Rua Vergueiro, 1400-1800" "Vila Mariana"   # criar outro
```

**4. Consultar o banco (evidências)**
```bash
python banco.py --resumo        # ranking de prioridade por trecho
python banco.py --ultimos 15    # últimos eventos
```

**Sem hardware?** O simulador publica os mesmos payloads do firmware:
```bash
python iot/simulador_esp32.py --cenario demo
```

**Alertas no Telegram (opcional).** Crie um bot com o @BotFather e defina `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` como variáveis de ambiente antes de iniciar o receptor.

## Comunicação MQTT

Broker padrão: `broker.hivemq.com:1883`. Os tópicos seguem o formato `<TOPICO_BASE>/<device_id>/<tipo>`:

| Tópico | Direção | Conteúdo |
|---|---|---|
| `…/leitura` | ESP32 → servidor | Telemetria a cada 5 s |
| `…/evento` | ESP32 → servidor | `buraco`, `reporte_manual`, `mudanca_trecho`, `calibracao`, `alerta_recebido` |
| `…/status` | ESP32 → servidor | `online` / `offline` (retido; `offline` via Last Will) |
| `…/comando` | servidor → ESP32 | `{"acao":"trecho","codigo":"SIM0002"}`, `{"acao":"alerta"}`, `{"acao":"calibrar"}`, `{"acao":"ping"}` |

Exemplos de payload:
```json
{"device":"esp32-01","trecho":"SIM0002","dist_mm":208,"prof_mm":58,"temp_c":27.2,"umid":62.8,"pista_umida":false,"status":"grave","ts":1794864941}
{"device":"esp32-01","tipo":"buraco","severidade":"grave","trecho":"SIM0002","prof_mm":63,"temp_c":27.0,"umid":62.0,"ts":1794864942}
```

## Banco de dados (`citizentech.db`, SQLite)

| Tabela / view | Quem grava | Conteúdo |
|---|---|---|
| `trechos` | cadastro | Código do trecho → nome da via, bairro, coordenadas |
| `leituras_iot` | receptor | Telemetria periódica |
| `eventos_iot` | receptor | Buracos, reportes, passagens por trecho |
| `deteccoes_visao` | módulo de Visão | Classe, confiança e bbox de cada detecção YOLO |
| `status_dispositivos` | receptor | Online/offline de cada ESP32 |
| **`vw_prioridade_trechos`** | (view) | Pontuação = 3×graves + 1×leves + 2×reportes + 2×detecções visuais (conf ≥ 0,5), ×1,2 se a umidade média ≥ 80 %. Nível: **alta** ≥ 8, **média** ≥ 4. É a fonte principal do agente GenAI |

## Situações de entrada demonstradas

| # | Entrada | Mensagem MQTT | Efeito na solução |
|---|---|---|---|
| 1 | Pista plana, umidade 58 % | `leitura` com `status: ok` | LED verde, leitura gravada |
| 2 | Rebaixo de 22 mm e de 58/63 mm | `evento buraco leve` e `evento buraco grave` | LED amarelo/vermelho. Alerta "Buraco GRAVE… Vistoria recomendada" |
| 3 | Umidade 92 % + irregularidades | `pista_umida: true` | LED amarelo, pontuação do trecho ×1,2 |
| 4 | Botão pressionado | `evento reporte_manual` | Alerta, e o trecho passa a prioridade **ALTA** (9,0) |
| 5 | Veículo volta ao trecho crítico | `comando trecho` → `evento mudanca_trecho` → servidor publica `comando alerta` | No ESP32, LED vermelho piscando: "trecho crítico à frente" |

O log completo da execução simulada está em `iot/evidencias/log_receptor_simulacao.txt`. Para a entrega, repita os cenários com o hardware e registre prints do Serial Monitor, do receptor, do `banco.py --resumo` e do Telegram.

## Implementado × simulado × limitações

- **Implementado:** firmware completo, MQTT bidirecional, gravação em banco, regras de prioridade, alertas e comando de volta ao dispositivo.
- **Simulado:**
  - A localização é um GPS simulado: o trecho atual é informado ao ESP32 por comando MQTT. Num veículo real, seria um módulo GPS (ex.: NEO-6M).
  - Os buracos são rebaixos numa maquete, e os limiares de mm estão em escala reduzida.
  - Os trechos `SIM0001`–`SIM0004` e as coordenadas são fictícios.
- **Limitações:**
  - O VL53L0X sofre com luz solar direta e superfícies escuras ou molhadas.
  - Num veículo real, a vibração e a suspensão exigiriam um acelerômetro e filtragem.
  - O DHT22 mede o ar, não o pavimento. É um indicador indireto de chuva.
  - O broker público não tem autenticação. Em produção seria necessário um broker próprio com TLS e usuário/senha.
  - A pontuação é uma heurística de triagem e **não substitui a vistoria técnica presencial**.

## ODS relacionados

- **ODS 11.2 / 11.7:** cidades seguras e acessíveis.
- **ODS 9.1:** infraestrutura de qualidade e resiliente.
- **ODS 3.6:** redução de mortes e lesões no trânsito.
