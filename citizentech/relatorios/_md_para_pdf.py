"""Markdown -> PDF (A4) com capa, no estilo do relatório do módulo IoT.
Uso: python gerar_pdf.py entrada.md saida.pdf "Título" "Subtítulo" "Disciplina"
"""
import re, sys
from pathlib import Path
import markdown
from weasyprint import HTML

CSS = """
@page { size: A4; margin: 22mm 18mm 20mm 18mm;
  @bottom-left { content: "CitizenTech · Monitor de Pavimento — %(rodape)s"; font-size: 8pt; color: #777; }
  @bottom-right { content: "página " counter(page); font-size: 8pt; color: #777; } }
body { font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; font-size: 10pt; color: #1a1a1a; line-height: 1.42; }
h1 { font-size: 17pt; color: #0d366b; border-bottom: 2px solid #2a78d6; padding-bottom: 3pt; margin-top: 18pt; page-break-after: avoid; }
h2 { font-size: 13pt; color: #184f95; margin-top: 16pt; page-break-after: avoid; }
h3 { font-size: 11pt; color: #1c5cab; margin-top: 12pt; page-break-after: avoid; }
p { margin: 5pt 0; text-align: justify; }
table { border-collapse: collapse; width: 100%; margin: 7pt 0 9pt 0; font-size: 8.8pt; page-break-inside: auto; }
th { background: #e8f0fb; color: #0d366b; text-align: left; padding: 4pt 5pt; border: 1px solid #c9d6e8; }
td { padding: 3.5pt 5pt; border: 1px solid #d9e0ea; vertical-align: top; }
tr { page-break-inside: avoid; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.4pt; background: #f3f4f6; padding: 0 2pt; }
pre { background: #f3f4f6; border: 1px solid #e1e4ea; padding: 6pt 8pt; font-size: 7.2pt; line-height: 1.3; white-space: pre; overflow: hidden; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3px solid #2a78d6; margin: 8pt 0; padding: 4pt 10pt; background: #f5f8fd; color: #333; }
img { max-width: 100%; display: block; margin: 8pt auto; page-break-inside: avoid; }
.legenda { font-size: 8.5pt; color: #555; text-align: center; margin-top: -4pt; margin-bottom: 10pt; }
ul, ol { margin: 4pt 0 6pt 0; padding-left: 18pt; } li { margin: 2pt 0; }
.capa { page-break-after: always; text-align: center; padding-top: 70mm; }
.capa .gs { font-size: 11pt; color: #555; letter-spacing: 1pt; }
.capa h1 { font-size: 28pt; border: none; color: #0d366b; margin: 20pt 0 6pt 0; }
.capa .sub { font-size: 14pt; color: #184f95; margin-bottom: 36pt; }
.capa .tema { font-size: 11pt; color: #333; margin-bottom: 60pt; }
.capa table { width: 70%; margin: 0 auto; font-size: 10pt; } .capa th, .capa td { padding: 7pt; }
.capa .data { margin-top: 50pt; color: #555; }
.sumario { page-break-after: always; } .sumario ol { line-height: 1.9; }
"""

def main(md_path, pdf_path, titulo, subtitulo, disciplina):
    texto = Path(md_path).read_text(encoding="utf-8")
    # legendas: linhas "Figura N. ..." viram parágrafos de legenda
    texto = re.sub(r"^(Figura \d+\..*)$", r'<p class="legenda">\1</p>', texto, flags=re.M)
    html_corpo = markdown.markdown(texto, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    capa = f"""
<div class="capa">
  <div class="gs">Global Solution 2026.2 · CitizenTech</div>
  <h1>{titulo}</h1>
  <div class="sub">{subtitulo}</div>
  <div class="tema">Protótipo Integrado CitizenTech com IA para Apoiar o Cidadão<br>Relatório técnico da disciplina de {disciplina}</div>
  <table><tr><th>Nome completo</th><th>RM</th></tr>
  <tr><td>[preencher]</td><td>[preencher]</td></tr><tr><td>[preencher]</td><td>[preencher]</td></tr><tr><td>[preencher]</td><td>[preencher]</td></tr></table>
  <div class="data">São Paulo, novembro de 2026</div>
</div>"""
    html = f"<html><head><meta charset='utf-8'><style>{CSS.replace("%(rodape)s", disciplina)}</style></head><body>{capa}{html_corpo}</body></html>"
    HTML(string=html, base_url=str(Path(md_path).resolve().parent)).write_pdf(pdf_path)
    print("PDF gerado:", pdf_path)

if __name__ == "__main__":
    main(*sys.argv[1:6])
