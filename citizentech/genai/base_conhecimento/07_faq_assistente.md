# Perguntas frequentes sobre o assistente CitizenTech

**O assistente é da Prefeitura?**
Não. O CitizenTech Monitor de Pavimento é um protótipo acadêmico da FIAP (Global Solution
2026.2). Ele não tem vínculo com a Prefeitura de São Paulo nem substitui os canais oficiais
(SP156).

**O que o assistente consegue fazer?**
- Explicar o ranking de prioridade dos trechos monitorados e quais evidências o sustentam.
- Gerar um relatório de inspeção para a equipe de zeladoria, com sugestão de rota.
- Responder dúvidas do cidadão sobre como reportar buracos, segurança e direitos, usando a
  base de conhecimento do projeto (RAG).
- Registrar um reporte de cidadão em um trecho monitorado.
- Analisar uma foto enviada pelo cidadão com o detector de buracos (visão computacional).
- Enviar um alerta ao dispositivo IoT instalado no veículo (comando MQTT).

**O que o assistente NÃO faz?**
- Não confirma a gravidade real de um buraco: isso exige vistoria presencial.
- Não abre protocolos no SP156 nem fala em nome de órgãos públicos.
- Não inventa trechos, pontuações ou estatísticas: quando o dado não existe no banco ou
  na base de conhecimento, ele diz que não sabe.
- Não dá parecer jurídico para casos concretos; apenas orientações gerais.

**De onde vêm os dados que o assistente usa?**
Do banco compartilhado `citizentech.db` (leituras e eventos do ESP32, detecções do
modelo de visão, reportes) e dos documentos desta base de conhecimento. Toda resposta
sobre trechos deve ser baseada em consulta ao banco, nunca em memória do modelo.

**Os dados pessoais do cidadão são guardados?**
O protótipo não pede nem armazena nome, CPF, telefone ou localização precisa do cidadão.
Um reporte guarda apenas o trecho e a descrição informada. Fotos enviadas são processadas
localmente pelo detector e não são enviadas a terceiros.

**Como o assistente evita respostas erradas?**
- Usa ferramentas para consultar o banco em vez de "lembrar" números.
- Responde perguntas sobre procedimentos com trechos recuperados dos documentos e cita o
  documento de origem.
- Tem instruções para declarar incerteza e para recomendar validação humana em decisões
  de reparo, sinalização e indenização.

**Quais decisões continuam exigindo validação humana?**
Confirmar a gravidade de um buraco, decidir o reparo, instalar sinalização, responder a um
pedido de indenização e qualquer comunicação oficial ao cidadão.
