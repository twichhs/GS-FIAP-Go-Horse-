"""Gera os PDFs dos módulos de Visão e GenAI a partir dos Markdown desta pasta.

    python citizentech/relatorios/gerar_relatorios.py

Visão: preenche os marcadores {{...}} com evidencias/metricas_visao.json (gerado pelo notebook).
GenAI: insere evidencias/avaliacao_resultados.md (gerado por avaliacao.py) se existir.
"""
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
sys.path.insert(0, str(AQUI))
from _md_para_pdf import main as md_para_pdf  # noqa: E402


def f3(x):
    return f"{float(x):.3f}".replace(".", ",")


def relatorio_visao():
    m = json.loads((RAIZ / "citizentech" / "visao" / "evidencias" / "metricas_visao.json").read_text())
    t, e, l05, h = m["teste"], m["teste_externo"], m["limiar"]["em_0_5"], m["hardware"]
    lat = {r["imgsz"]: r for r in m["latencia"]}
    v = m["video"]
    val = {
        "PARAMS_M": str(m["parametros_M"]).replace(".", ","), "GFLOPS": str(m["gflops"]).replace(".", ","),
        "EPOCAS": m["epocas"], "MELHOR_EPOCA": m["melhor_epoca"],
        "P_TESTE": f3(t["precisão"]), "R_TESTE": f3(t["recall"]), "MAP50_TESTE": f3(t["mAP@0,5"]), "MAP5095_TESTE": f3(t["mAP@0,5:0,95"]),
        "VP_TESTE": t["VP"], "FP_TESTE": t["FP"], "FN_TESTE": t["FN"],
        "P_EXT": f3(e["precisão"]), "R_EXT": f3(e["recall"]), "MAP50_EXT": f3(e["mAP@0,5"]), "MAP5095_EXT": f3(e["mAP@0,5:0,95"]),
        "VP_EXT": e["VP"], "FP_EXT": e["FP"], "FN_EXT": e["FN"],
        "MELHOR_F1": f3(m["limiar"]["melhor_f1"]["F1"]), "MELHOR_F1_LIMIAR": str(m["limiar"]["melhor_f1"]["limiar"]).replace(".", ","),
        "P_05": f3(l05["precisão"]), "R_05": f3(l05["recall"]), "F1_05": f3(l05["F1"]),
        "CPU": h["cpu"], "NUCLEOS": h["nucleos_fisicos"], "THREADS": h["threads"], "RAM": str(h["ram_gb"]).replace(".", ","), "SO": h["so"],
        "PYTHON": h["python"], "TORCH": h["torch"], "ULTRALYTICS": h["ultralytics"], "OPENCV": h["opencv"],
        **{f"LAT_{s}": f"{lat[s]['latencia_media_ms']:.0f}" for s in (320, 480, 640)},
        **{f"P95_{s}": f"{lat[s]['latencia_p95_ms']:.0f}" for s in (320, 480, 640)},
        **{f"FPS_{s}": f"{lat[s]['fps']:.1f}".replace(".", ",") for s in (320, 480, 640)},
        "VID_FRAMES": v["quadros processados"], "VID_FPS": str(v["FPS de processamento"]).replace(".", ","),
        "VID_LAT": str(v["latência média (ms/quadro)"]).replace(".", ","), "VID_RES": v["resolução"], "VID_STRIDE": v["stride"],
        "VID_PONTUACAO": f"{v['trecho']}: {v['pontuação antes → depois']}",
    }
    texto = (AQUI / "RELATORIO_VISAO.md").read_text(encoding="utf-8")
    texto = re.sub(r"\{\{(\w+)\}\}", lambda mm: str(val[mm.group(1)]), texto)
    tmp = AQUI / "_visao_preenchido.md"
    tmp.write_text(texto, encoding="utf-8")
    md_para_pdf(str(tmp), str(RAIZ / "CitizenTech_Modulo_Visao.pdf"), "Monitor de Pavimento",
                "Módulo de Visão Computacional — detecção de buracos com YOLO", "Visão Computacional")
    tmp.unlink()


def relatorio_genai():
    texto = (AQUI / "RELATORIO_GENAI.md").read_text(encoding="utf-8")
    res = RAIZ / "citizentech" / "genai" / "evidencias" / "avaliacao_resultados.md"
    if res.exists():
        corpo = res.read_text(encoding="utf-8")
        # mantém só a tabela-resumo e as 3 primeiras respostas para o PDF não ficar longo
        partes = corpo.split("## Perguntas e respostas")
        tabela = partes[0].split("\n", 2)[2] if len(partes) else corpo
        exemplos = ""
        if len(partes) > 1:
            blocos = [b for b in partes[1].split("### ") if b.strip()][:4]
            exemplos = "\n\n#### Exemplos de entrada e saída\n\n" + "\n\n".join("##### " + b.strip() for b in blocos)
        bloco = tabela.strip() + exemplos
    else:
        bloco = ("> Resultados a preencher: execute `python citizentech/genai/avaliacao.py` com a chave do modelo "
                 "configurada e gere este PDF novamente. O arquivo `evidencias/avaliacao_resultados.md` será incorporado aqui.")
    texto = texto.replace("RESULTADOS_AVALIACAO", bloco)
    tmp = AQUI / "_genai_preenchido.md"
    tmp.write_text(texto, encoding="utf-8")
    md_para_pdf(str(tmp), str(RAIZ / "CitizenTech_Modulo_GenAI.pdf"), "Monitor de Pavimento",
                "Módulo de IA Generativa — agente com ferramentas e RAG", "Generative AI and Advanced Nets")
    tmp.unlink()


if __name__ == "__main__":
    quais = sys.argv[1:] or ["visao", "genai"]
    if "genai" in quais:
        relatorio_genai()
    if "visao" in quais:
        relatorio_visao()
