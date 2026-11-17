# midia/ — vídeos e fotos reais da via

Coloque aqui o vídeo gravado na rua (ex.: `rua_buracos.mp4`) e fotos avulsas.
Os arquivos `.mp4`/`.mov` desta pasta são usados automaticamente pelo notebook de
Visão Computacional e pelo script de monitoramento contínuo:

```bash
# 1) cadastre o trecho real da rua filmada (uma vez)
.venv/bin/python citizentech/banco.py --cadastrar SIM0005 "Rua da gravação, 100-400" "Bairro"

# 2) processe o vídeo (vídeo anotado + JSON de métricas + detecções no banco)
.venv/bin/python citizentech/visao/processar_video.py --video midia/rua_buracos.mp4 \
    --trecho SIM0005 --stride 2 --gravar-banco

# 3) veja o efeito no ranking que o agente GenAI consulta
.venv/bin/python citizentech/banco.py --resumo
```

Dicas de gravação: celular na horizontal, 1080p, 30 fps, câmera apontada para a pista
alguns metros à frente (ângulo parecido com o das fotos de treino), 1 a 3 minutos.
Vídeos grandes podem ser processados com `--stride 3` para acelerar na CPU.
