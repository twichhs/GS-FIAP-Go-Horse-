"""Detector de buracos do CitizenTech (YOLO, Ultralytics).

Encapsula o modelo ajustado (modelos/best.pt) e oferece:
  - detectar_imagem(): caixas + confiança + latência para UMA imagem;
  - processar_video(): monitoramento contínuo com rastreamento (ByteTrack),
    vídeo anotado de saída, FPS/latência medidos e UM registro por buraco
    rastreado no banco compartilhado (não um por quadro).

Usado pelo notebook, por processar_video.py e pelo app Gradio do módulo GenAI.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))          # para importar banco/config da raiz do citizentech

PESOS_PADRAO = AQUI / "modelos" / "best.pt"
CLASSE = "buraco"
CONF_EXIBICAO = 0.25   # mostra a caixa (amarelo = incerta)
CONF_REGISTRO = 0.50   # grava no banco e conta na prioridade (vermelho = confirmada)

COR_CONFIRMADA = (40, 40, 220)    # BGR
COR_INCERTA = (0, 190, 255)
COR_TEXTO = (255, 255, 255)


@dataclass
class Deteccao:
    classe: str
    confianca: float
    bbox: list[int]            # [x1, y1, x2, y2] em pixels da imagem original
    track_id: int | None = None


@dataclass
class ResultadoImagem:
    deteccoes: list[Deteccao]
    latencia_ms: float
    imagem_anotada: np.ndarray
    largura: int
    altura: int

    @property
    def confirmadas(self):
        return [d for d in self.deteccoes if d.confianca >= CONF_REGISTRO]


@dataclass
class ResultadoVideo:
    arquivo: str
    saida: str | None
    frames_lidos: int
    frames_processados: int
    largura: int
    altura: int
    fps_video: float
    latencia_media_ms: float
    fps_processamento: float
    tempo_total_s: float
    buracos_rastreados: dict[int, Deteccao] = field(default_factory=dict)
    registros_banco: int = 0

    @property
    def buracos_confirmados(self):
        return {k: d for k, d in self.buracos_rastreados.items() if d.confianca >= CONF_REGISTRO}


def desenhar(img: np.ndarray, dets: list[Deteccao], hud: str | None = None) -> np.ndarray:
    out = img.copy()
    esc = max(0.5, out.shape[1] / 1280)
    esp = max(1, int(2 * esc))
    for d in dets:
        x1, y1, x2, y2 = d.bbox
        cor = COR_CONFIRMADA if d.confianca >= CONF_REGISTRO else COR_INCERTA
        cv2.rectangle(out, (x1, y1), (x2, y2), cor, esp)
        rotulo = f"{d.classe} {d.confianca:.2f}" + (f" #{d.track_id}" if d.track_id is not None else "")
        (tw, th), _ = cv2.getTextSize(rotulo, cv2.FONT_HERSHEY_SIMPLEX, 0.6 * esc, esp)
        y_txt = max(th + 6, y1)
        cv2.rectangle(out, (x1, y_txt - th - 6), (x1 + tw + 6, y_txt), cor, -1)
        cv2.putText(out, rotulo, (x1 + 3, y_txt - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.6 * esc, COR_TEXTO, esp, cv2.LINE_AA)
    if hud:
        (tw, th), _ = cv2.getTextSize(hud, cv2.FONT_HERSHEY_SIMPLEX, 0.7 * esc, esp)
        cv2.rectangle(out, (8, 8), (16 + tw, 20 + th), (0, 0, 0), -1)
        cv2.putText(out, hud, (12, 14 + th), cv2.FONT_HERSHEY_SIMPLEX, 0.7 * esc, COR_TEXTO, esp, cv2.LINE_AA)
    return out


class DetectorBuracos:
    def __init__(self, pesos: str | Path | None = None, imgsz: int = 640, device: str = "cpu"):
        from ultralytics import YOLO

        self.pesos = Path(pesos) if pesos else PESOS_PADRAO
        if not self.pesos.exists():
            raise FileNotFoundError(
                f"Pesos não encontrados em {self.pesos}. Treine com treinar.py ou copie best.pt para modelos/.")
        self.model = YOLO(str(self.pesos))
        self.imgsz = imgsz
        self.device = device
        self.nome_modelo = f"yolo:{self.pesos.name}"
        self.classes = self.model.names

    # ------------------------------------------------------------------ imagem
    def _converter(self, r, track: bool = False) -> list[Deteccao]:
        dets = []
        if r.boxes is None or len(r.boxes) == 0:
            return dets
        xyxy = r.boxes.xyxy.cpu().numpy().astype(int)
        conf = r.boxes.conf.cpu().numpy()
        cls = r.boxes.cls.cpu().numpy().astype(int)
        ids = r.boxes.id.cpu().numpy().astype(int) if (track and r.boxes.id is not None) else [None] * len(conf)
        for (x1, y1, x2, y2), c, k, tid in zip(xyxy, conf, cls, ids):
            dets.append(Deteccao(self.classes.get(int(k), CLASSE), float(c), [int(x1), int(y1), int(x2), int(y2)],
                                 None if tid is None else int(tid)))
        return dets

    def detectar_imagem(self, imagem: str | Path | np.ndarray, conf: float = CONF_EXIBICAO) -> ResultadoImagem:
        img = cv2.imread(str(imagem)) if isinstance(imagem, (str, Path)) else imagem
        if img is None:
            raise ValueError(f"Não foi possível ler a imagem {imagem}")
        t0 = time.perf_counter()
        r = self.model.predict(img, imgsz=self.imgsz, conf=conf, device=self.device, verbose=False)[0]
        lat = (time.perf_counter() - t0) * 1000
        dets = self._converter(r)
        hud = f"{len([d for d in dets if d.confianca >= CONF_REGISTRO])} buraco(s) confirmados | {lat:.0f} ms"
        return ResultadoImagem(dets, lat, desenhar(img, dets, hud), img.shape[1], img.shape[0])

    # ------------------------------------------------------------------- vídeo
    def processar_video(self, caminho: str | Path, saida: str | Path | None = None, *, conf: float = CONF_EXIBICAO,
                        stride: int = 1, max_frames: int | None = None, largura_saida: int | None = 960,
                        trecho: str | None = None, conn=None, tracker: str = "bytetrack.yaml",
                        progresso: bool = True) -> ResultadoVideo:
        """Processa um vídeo quadro a quadro com rastreamento.

        stride: processa 1 a cada N quadros (os demais repetem a última anotação no vídeo de saída).
        trecho + conn: grava no banco UMA detecção por buraco rastreado (confiança máxima observada).
        """
        cap = cv2.VideoCapture(str(caminho))
        if not cap.isOpened():
            raise ValueError(f"Não foi possível abrir o vídeo {caminho}")
        fps_in = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w_in, h_in = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

        writer = None
        if saida:
            Path(saida).parent.mkdir(parents=True, exist_ok=True)
            if largura_saida and w_in > largura_saida:
                w_out = largura_saida
                h_out = int(h_in * largura_saida / w_in) // 2 * 2
            else:
                w_out, h_out = w_in, h_in
            writer = cv2.VideoWriter(str(saida), cv2.VideoWriter_fourcc(*"mp4v"), fps_in, (w_out, h_out))

        rastreados: dict[int, Deteccao] = {}
        latencias = []
        lidos = processados = 0
        ultimas: list[Deteccao] = []
        t_inicio = time.perf_counter()
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                lidos += 1
                if max_frames and processados >= max_frames:
                    break
                if (lidos - 1) % stride == 0:
                    t0 = time.perf_counter()
                    r = self.model.track(frame, imgsz=self.imgsz, conf=conf, device=self.device, persist=True,
                                         tracker=tracker, verbose=False)[0]
                    latencias.append((time.perf_counter() - t0) * 1000)
                    processados += 1
                    ultimas = self._converter(r, track=True)
                    for d in ultimas:
                        if d.track_id is None:
                            continue
                        atual = rastreados.get(d.track_id)
                        if atual is None or d.confianca > atual.confianca:
                            rastreados[d.track_id] = d
                    if progresso and processados % 25 == 0:
                        print(f"  quadro {lidos}/{total or '?'} | {len(rastreados)} rastreados | "
                              f"{np.mean(latencias[-25:]):.0f} ms/quadro", flush=True)
                if writer is not None:
                    confirmados = len([d for d in rastreados.values() if d.confianca >= CONF_REGISTRO])
                    hud = (f"CitizenTech | buracos: {confirmados} confirmados / {len(rastreados)} rastreados | "
                           f"{(1000 / np.mean(latencias[-25:])) if latencias else 0:.1f} FPS (CPU)")
                    anot = desenhar(frame, ultimas, hud)
                    if (anot.shape[1], anot.shape[0]) != (w_out, h_out):
                        anot = cv2.resize(anot, (w_out, h_out))
                    writer.write(anot)
        finally:
            cap.release()
            if writer is not None:
                writer.release()
            # zera o estado do rastreador para o próximo vídeo
            if getattr(self.model, "predictor", None) is not None:
                self.model.predictor = None

        tempo = time.perf_counter() - t_inicio
        res = ResultadoVideo(
            arquivo=str(caminho), saida=str(saida) if saida else None,
            frames_lidos=lidos, frames_processados=processados, largura=w_in, altura=h_in, fps_video=fps_in,
            latencia_media_ms=float(np.mean(latencias)) if latencias else 0.0,
            fps_processamento=(processados / tempo) if tempo > 0 else 0.0, tempo_total_s=tempo,
            buracos_rastreados=rastreados,
        )
        if conn is not None and trecho:
            res.registros_banco = self.registrar_no_banco(conn, trecho, Path(caminho).name,
                                                          list(res.buracos_confirmados.values()))
        return res

    # ------------------------------------------------------------------- banco
    def registrar_no_banco(self, conn, trecho: str, arquivo: str, dets: list[Deteccao]) -> int:
        """Grava cada detecção confirmada em deteccoes_visao (integração com IoT/GenAI)."""
        import banco

        n = 0
        for d in dets:
            if d.confianca < CONF_REGISTRO:
                continue
            banco.inserir_deteccao_visao(conn, trecho, arquivo, d.classe, d.confianca, d.bbox, self.nome_modelo)
            n += 1
        return n


def medir_latencia(det: DetectorBuracos, imagens: list, imgsz: int | None = None, repeticoes: int = 1) -> dict:
    """Latência média por imagem e FPS (inferência pura, batch 1)."""
    imgsz = imgsz or det.imgsz
    det.model.predict(imagens[0], imgsz=imgsz, device=det.device, verbose=False)  # aquecimento
    tempos = []
    for _ in range(repeticoes):
        for im in imagens:
            t0 = time.perf_counter()
            det.model.predict(im, imgsz=imgsz, device=det.device, verbose=False)
            tempos.append((time.perf_counter() - t0) * 1000)
    media = float(np.mean(tempos))
    return {"imgsz": imgsz, "n": len(tempos), "latencia_media_ms": media, "latencia_p95_ms": float(np.percentile(tempos, 95)),
            "fps": 1000 / media}
