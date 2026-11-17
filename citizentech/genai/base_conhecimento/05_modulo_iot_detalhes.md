# Módulo IoT — como o dispositivo mede a via

## Hardware
- **ESP32 DevKit**: microcontrolador com Wi-Fi; roda o firmware e publica por MQTT.
- **VL53L0X** (sensor de distância por tempo de voo, I2C): apontado para o solo, mede a
  distância em milímetros cerca de 20 vezes por segundo. A **profundidade** é a diferença
  entre a distância medida e a altura de referência calibrada ao ligar (30 leituras sobre
  superfície plana).
- **DHT22**: temperatura (°C) e umidade relativa (%) a cada 5 segundos. Umidade ≥ 85%
  indica pista possivelmente molhada.
- **Botão**: reporte manual do motorista ou agente ("passei num buraco aqui").
- **3 LEDs**: verde = via ok; amarelo = irregularidade leve ou pista úmida; vermelho =
  buraco grave; vermelho piscando por 5 s = trecho crítico (comando vindo do servidor);
  os três acesos por um instante = troca de trecho ou botão confirmados.

## Regras embarcadas
- Uma irregularidade começa quando a profundidade passa de **15 mm** em pelo menos 2
  leituras seguidas e termina quando volta abaixo de 10 mm (histerese de 5 mm). É
  publicado **um único evento por passagem**, com a profundidade máxima: `leve` abaixo de
  40 mm, `grave` a partir de 40 mm. Os limiares estão em escala de maquete.
- Telemetria a cada 5 s: distância, profundidade, temperatura, umidade, pista úmida e
  status (ok / leve / grave).
- O trecho atual chega por comando MQTT (GPS simulado). O ESP32 liga no trecho `SIM0001`.

## Comunicação MQTT
Broker público `broker.hivemq.com:1883`. Tópicos no formato `<base>/<device_id>/<tipo>`:
| Tópico | Direção | Conteúdo |
|---|---|---|
| `…/leitura` | ESP32 → servidor | telemetria periódica |
| `…/evento` | ESP32 → servidor | `buraco` (leve/grave), `reporte_manual`, `mudanca_trecho`, `calibracao`, `alerta_recebido` |
| `…/status` | ESP32 → servidor | `online` / `offline` (retido; `offline` via Last Will) |
| `…/comando` | servidor → ESP32 | `{"acao":"alerta"}`, `{"acao":"trecho","codigo":"SIM0002"}`, `{"acao":"calibrar"}`, `{"acao":"ping"}` |

## Banco de dados compartilhado (`citizentech.db`, SQLite)
| Tabela / view | Conteúdo |
|---|---|
| `trechos` | código → nome da via, bairro, coordenadas |
| `leituras_iot` | telemetria periódica |
| `eventos_iot` | buracos, reportes, trocas de trecho, calibrações |
| `deteccoes_visao` | classe, confiança e caixa de cada detecção do YOLO |
| `status_dispositivos` | online/offline de cada ESP32 |
| `vw_prioridade_trechos` | pontuação e nível de prioridade de cada trecho (fonte principal do agente) |

## Limitações conhecidas
| Limitação | Impacto | Mitigação / evolução |
|---|---|---|
| VL53L0X sensível a luz solar direta e a superfícies escuras ou molhadas | leituras ruidosas ao ar livre | sensor com proteção óptica ou LiDAR automotivo; filtro de mediana |
| Vibração e suspensão de um veículo real | falsos positivos | acelerômetro (MPU6050) e fusão de sensores |
| DHT22 mede o ar, não o pavimento | indicador indireto de chuva | sensor de chuva ou dados meteorológicos abertos |
| Sem GPS real | localização manual na demo | módulo GPS (ex.: NEO-6M) |
| Broker público sem autenticação | qualquer um pode ler ou publicar | broker próprio com TLS, usuário/senha e ACL |
| Pontuação heurística | pesos não calibrados com dados reais | ajustar os pesos com o histórico de vistorias |
