"""Monitoramento contínuo: processa um vídeo da via e integra com o CitizenTech.

Exemplo (na raiz do projeto):
    python citizentech/visao/processar_video.py --video midia/rua.mp4 --trecho SIM0005 \
        --saida citizentech/visao/saida/rua_anotado.mp4 --stride 2 --gravar-banco

Saída: vídeo anotado (caixas + confiança + FPS), resumo em JSON e, com
--gravar-banco, um registro por buraco rastreado em deteccoes_visao.
"""
import argparse
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

from detector import DetectorBuracos  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--saida", default=None, help="mp4 anotado (padrão: saida/<nome>_anotado.mp4)")
    p.add_argument("--pesos", default=None)
    p.add_argument("--trecho", default=None, help="código do trecho, ex.: SIM0005")
    p.add_argument("--gravar-banco", action="store_true", help="grava as detecções confirmadas em citizentech.db")
    p.add_argument("--stride", type=int, default=1, help="processa 1 a cada N quadros")
    p.add_argument("--max-frames", type=int, default=None)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=640)
    a = p.parse_args()

    saida = a.saida or str(AQUI / "saida" / (Path(a.video).stem + "_anotado.mp4"))
    conn = None
    if a.gravar_banco:
        import banco
        conn = banco.conectar()
        banco.inicializar(conn)
        if not a.trecho:
            sys.exit("--gravar-banco exige --trecho")

    det = DetectorBuracos(a.pesos, imgsz=a.imgsz)
    print(f"Modelo: {det.pesos.name} | vídeo: {a.video}")
    r = det.processar_video(a.video, saida, conf=a.conf, stride=a.stride, max_frames=a.max_frames,
                            trecho=a.trecho, conn=conn)
    resumo = {
        "video": r.arquivo, "saida": r.saida, "resolucao": f"{r.largura}x{r.altura}", "fps_video": round(r.fps_video, 2),
        "frames_lidos": r.frames_lidos, "frames_processados": r.frames_processados, "stride": a.stride,
        "latencia_media_ms": round(r.latencia_media_ms, 1), "fps_processamento": round(r.fps_processamento, 2),
        "tempo_total_s": round(r.tempo_total_s, 1), "buracos_rastreados": len(r.buracos_rastreados),
        "buracos_confirmados": len(r.buracos_confirmados), "registros_banco": r.registros_banco, "trecho": a.trecho,
        "confirmados": [{"track_id": k, "confianca": round(d.confianca, 3), "bbox": d.bbox}
                         for k, d in sorted(r.buracos_confirmados.items())],
    }
    Path(saida).with_suffix(".json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in resumo.items() if k != "confirmados"}, indent=2, ensure_ascii=False))
    print(f"Resumo salvo em {Path(saida).with_suffix('.json')}")
