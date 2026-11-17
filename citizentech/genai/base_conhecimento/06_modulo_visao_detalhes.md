# Módulo de Visão Computacional — como o detector de buracos funciona

## Nicho e tarefa
Nicho escolhido: **Infraestrutura e Pavimentação** (detecção de buracos e danos severos na
pavimentação viária). Tarefa: **localização de objetos por caixas delimitadoras** (bounding
boxes) com uma única classe, `buraco`. Cada detecção vem com uma **confiança** entre 0 e 1.

## Modelo
- Arquitetura: **YOLO11n** (Ultralytics), a menor versão da família YOLO11, escolhida para
  rodar em CPU comum e em dispositivos de borda. Pesos iniciais pré-treinados no COCO e
  ajustados (transfer learning, todas as camadas) na base de buracos.
- Entrada: imagens redimensionadas para 640×640 pixels, valores normalizados para 0–1.
- Saída: caixas `[x1, y1, x2, y2]` em pixels da imagem original + confiança.

## Dados de treinamento
- Base principal (treino/validação/teste): 715 imagens públicas de buracos (Roboflow
  "pothole", licença MIT, 640×640), divididas **por imagem de origem** para que variações
  aumentadas da mesma foto nunca fiquem em conjuntos diferentes.
- Base externa (só teste): 88 imagens de outra base pública (Roboflow "Potholes
  Detection", CC BY 4.0), usada para medir a generalização.

## Limiares de confiança
| Limiar | Uso |
|---|---|
| **0,25** | Exibição: a caixa aparece em amarelo (detecção incerta) na imagem/vídeo anotado |
| **0,50** | Registro: a caixa aparece em vermelho (detecção confirmada), é gravada no banco e conta na prioridade do trecho (peso 2) |

## Monitoramento contínuo (vídeo)
No vídeo, o detector roda com rastreamento (ByteTrack). Cada buraco recebe um identificador
de rastreio e é gravado **uma única vez** no banco, com a maior confiança observada ao longo
dos quadros, para não inflar a pontuação com uma detecção por quadro.

## Métricas obtidas
METRICAS_PLACEHOLDER

## Limitações e falsos positivos conhecidos
- Sombras fortes, manchas de óleo, remendos escuros, tampas de bueiro e poças podem ser
  confundidos com buracos.
- Buracos pequenos ou distantes, parcialmente cobertos por água ou por outros veículos, podem
  não ser detectados.
- A base de treino tem poucas imagens à noite ou sob chuva; a confiança cai nessas condições.
- A detecção indica **onde olhar**; não mede profundidade nem risco estrutural. Isso exige
  vistoria presencial (ou a medição do sensor IoT no local).
