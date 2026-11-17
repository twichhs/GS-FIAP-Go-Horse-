"""Preparação dos dados do módulo de Visão Computacional (CitizenTech).

Baixa duas bases públicas de buracos (Hugging Face Hub), agrupa as imagens
pela IMAGEM DE ORIGEM (as exportações do Roboflow contêm variações
aumentadas da mesma foto, identificadas pelo sufixo ".rf.<hash>") e monta os
conjuntos de treino / validação / teste SEM distribuir variações da mesma foto
entre conjuntos diferentes.

Bases usadas
------------
1. Base principal (treino/val/teste): rupesh002/pothole-detection-dataset
   (MIT, 715 imagens 640x640, 1 classe, formato YOLO). Origem: Roboflow
   "pothole.v1i". É a base em que o modelo é ajustado.
2. Base externa (só teste): Ryukijano/Pothole-detection-Yolov8 (CC BY 4.0,
   amostra de 300 imagens da base "Potholes Detection" do Roboflow). Usamos
   apenas o split de teste, deduplicado por imagem de origem, para medir a
   generalização do modelo em uma base que ele nunca viu.

Uso (na raiz do projeto, com o ambiente ativado):
    python citizentech/visao/preparar_dados.py            # baixa e prepara
    python citizentech/visao/preparar_dados.py --sem-download   # só reprocessa
"""
import argparse
import collections
import random
import re
import shutil
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAW = AQUI / "dataset" / "_raw"
OUT = AQUI / "dataset"
SEED = 42
FRACOES = {"train": 0.70, "val": 0.15, "test": 0.15}

RE_FONTE = re.compile(r"(?:_jpg|_png|_jpeg)?\.rf\.[0-9a-f]+\.(?:jpg|png|jpeg)$", re.I)


def fonte(nome: str) -> str:
    """'Pothole-615_jpg.rf.ab12....jpg' -> 'Pothole-615' (imagem de origem)."""
    return RE_FONTE.sub("", nome)


def baixar():
    from huggingface_hub import hf_hub_download, snapshot_download

    RAW.mkdir(parents=True, exist_ok=True)
    print("[1/2] Base principal: rupesh002/pothole-detection-dataset (zip ~57 MB)")
    zip_path = hf_hub_download("rupesh002/pothole-detection-dataset", "pothole_dataset.zip",
                               repo_type="dataset", local_dir=RAW / "principal_zip")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(RAW / "principal")
    print("[2/2] Base externa: Ryukijano/Pothole-detection-Yolov8 (~23 MB)")
    snapshot_download("Ryukijano/Pothole-detection-Yolov8", repo_type="dataset",
                      local_dir=RAW / "externa", allow_patterns=["test/*", "data.yaml"])


def pares(img_dir: Path, lbl_dir: Path):
    """Lista (imagem, rótulo) existentes nas duas pastas."""
    out = []
    for img in sorted(img_dir.glob("*.jpg")):
        lbl = lbl_dir / (img.stem + ".txt")
        if lbl.exists():
            out.append((img, lbl))
    return out


def copiar(lista, destino: Path):
    (destino / "images").mkdir(parents=True, exist_ok=True)
    (destino / "labels").mkdir(parents=True, exist_ok=True)
    for img, lbl in lista:
        shutil.copy2(img, destino / "images" / img.name)
        shutil.copy2(lbl, destino / "labels" / lbl.name)


def contar_caixas(lista):
    return sum(len([l for l in open(lbl).read().splitlines() if l.strip()]) for _, lbl in lista)


def preparar():
    # ---------- base principal: agrupa por fonte e divide 70/15/15 ----------
    base = RAW / "principal" / "pothole.v1i.yolov4pytorch"
    todos = pares(base / "train" / "images", base / "train" / "labels") + \
            pares(base / "valid" / "images", base / "valid" / "labels")
    grupos = collections.defaultdict(list)
    for img, lbl in todos:
        grupos[fonte(img.name)].append((img, lbl))

    fontes = sorted(grupos)
    random.Random(SEED).shuffle(fontes)
    n = len(fontes)
    n_train = int(n * FRACOES["train"])
    n_val = int(n * FRACOES["val"])
    divisao = {
        "train": fontes[:n_train],
        "val": fontes[n_train:n_train + n_val],
        "test": fontes[n_train + n_val:],
    }

    for split in ("train", "val", "test"):
        if (OUT / split).exists():
            shutil.rmtree(OUT / split)
    linhas = []
    for split, fs in divisao.items():
        lista = [p for f in fs for p in grupos[f]]
        if split != "train":
            # validação e teste: uma única variante por foto de origem
            lista = [grupos[f][0] for f in fs]
        copiar(lista, OUT / split)
        linhas.append((split, len(fs), len(lista), contar_caixas(lista)))

    # ---------- base externa: só o teste, deduplicado por fonte ----------
    ext = RAW / "externa" / "test"
    vistos = {}
    for img, lbl in pares(ext / "images", ext / "labels"):
        vistos.setdefault(fonte(img.name), (img, lbl))
    if (OUT / "test_externo").exists():
        shutil.rmtree(OUT / "test_externo")
    copiar(list(vistos.values()), OUT / "test_externo")
    linhas.append(("test_externo", len(vistos), len(vistos), contar_caixas(list(vistos.values()))))

    # ---------- data.yaml ----------
    (OUT / "data.yaml").write_text(
        f"# Gerado por preparar_dados.py (seed {SEED}); divisão por imagem de origem\n"
        f"path: {OUT}\n"
        "train: train/images\n"
        "val: val/images\n"
        "test: test/images\n"
        "nc: 1\n"
        "names: ['buraco']\n"
    )
    (OUT / "data_externo.yaml").write_text(
        f"path: {OUT}\n"
        "train: train/images\n"
        "val: test_externo/images\n"
        "nc: 1\n"
        "names: ['buraco']\n"
    )

    print("\nConjunto       fontes  imagens  caixas")
    for split, nf, ni, nc in linhas:
        print(f"{split:13}  {nf:6}  {ni:7}  {nc:6}")
    inter = set(divisao["train"]) & set(divisao["val"]) | set(divisao["train"]) & set(divisao["test"]) \
        | set(divisao["val"]) & set(divisao["test"])
    print(f"\nFontes compartilhadas entre conjuntos: {len(inter)} (deve ser 0)")
    print(f"data.yaml: {OUT / 'data.yaml'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sem-download", action="store_true", help="não baixa de novo as bases")
    a = p.parse_args()
    if not a.sem_download:
        baixar()
    preparar()
