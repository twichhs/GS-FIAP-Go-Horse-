"""Ajuste fino (transfer learning) do YOLO11n para detecção de buracos.

Parte dos pesos pré-treinados no COCO (yolo11n.pt) e ajusta todas as camadas
na base preparada por preparar_dados.py. Ao final copia o melhor checkpoint
para modelos/best.pt, que é o arquivo usado pelo detector.

Uso (na raiz do projeto):
    python citizentech/visao/treinar.py --epochs 30 --batch 8 --imgsz 640
"""
import argparse
import shutil
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--modelo", default="yolo11n.pt", help="pesos de partida (COCO)")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--device", default="cpu")
    p.add_argument("--nome", default="yolo11n_buracos")
    p.add_argument("--patience", type=int, default=10)
    a = p.parse_args()

    from ultralytics import YOLO

    t0 = time.time()
    model = YOLO(a.modelo)
    model.train(
        data=str(AQUI / "dataset" / "data.yaml"),
        epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, workers=a.workers, device=a.device,
        project=str(AQUI / "runs"), name=a.nome, exist_ok=True,
        patience=a.patience, close_mosaic=5, cache=False, plots=True, seed=42, deterministic=True,
        pretrained=True, optimizer="auto", verbose=True,
    )
    melhor = AQUI / "runs" / a.nome / "weights" / "best.pt"
    (AQUI / "modelos").mkdir(exist_ok=True)
    shutil.copy2(melhor, AQUI / "modelos" / "best.pt")
    print(f"\nTreino concluído em {(time.time() - t0) / 60:.1f} min. Melhor checkpoint copiado para {AQUI / 'modelos' / 'best.pt'}")
