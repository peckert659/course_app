from flask import Flask, request, render_template, send_file
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextLine, LTChar, LAParams
from PyPDF2 import PdfReader, PdfWriter
import tempfile

app = Flask(__name__, template_folder="../templates")

PDF_ORIG = Path("formulaire_original.pdf")

laparams = LAParams()

def iter_chars(text_line):
    for obj in getattr(text_line, "_objs", []):
        if isinstance(obj, LTChar):
            yield obj

def find_colon(label):
    for page in extract_pages(PDF_ORIG, laparams=laparams):
        for element in page:
            if isinstance(element, LTTextContainer):
                for line in element:
                    if (isinstance(line, LTTextLine)
                            and label.lower() in line.get_text().lower()):
                        for ch in iter_chars(line):
                            if ch.get_text() == ":":
                                return ch.bbox
    raise RuntimeError(f"Deux-points non trouvé pour « {label} »")

def find_checkbox(label):
    for page in extract_pages(PDF_ORIG, laparams=laparams):
        for element in page:
            if isinstance(element, LTTextContainer):
                for line in element:
                    txt = line.get_text()
                    if label.lower() in txt.lower():
                        for ch in iter_chars(line):
                            if ch.get_text() == "☐":
                                return ch.bbox
    raise RuntimeError(f"Case à cocher non trouvée pour « {label} »")

def draw_string(canv, x, y, text, y_shift=4):
    canv.drawString(x + 5, y + y_shift, text)

def draw_cross(canv, bbox):
    x0, y0, x1, y1 = bbox
    canv.setFont("Helvetica-Bold", 12)
    canv.drawString((x0 + x1) / 2 - 3, (y0 + y1) / 2 - 4, "X")
    canv.setFont("Helvetica", 10)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        vals = {
            "name": request.form["name"],
            "title": request.form["title"],
            "group1_detail": request.form["group1_detail"],
            "group2_detail": request.form.get("group2_detail", ""),
            "transport": request.form["transport"],
            "meal": request.form["meal"],
            "aller_dep": request.form["aller_dep"],
            "aller_arr": request.form["aller_arr"],
            "retour_dep": request.form["retour_dep"],
            "retour_arr": request.form["retour_arr"],
            "unavailable": request.form["unavailable"],
            "url": request.form["url"],
            "saison_jas": "saison_jas" in request.form,
        }

        # Trouver les positions des éléments
        colon_pos = {
            "name": find_colon("Prénom"),
            "title": find_colon("Titre de la course"),
            "group1_detail": find_colon("Groupe 1"),
            "group2_detail": find_colon("Groupe 2"),
            "dep_aller": find_colon("Heure de départ"),
            "arr_aller": find_colon("Heure d’arrivée"),
            "dep_retour": find_colon("Heure de départ"),
            "arr_retour": find_colon("Heure d’arrivée"),
            "unavailable": find_colon("Non disponibilité"),
        }

        colon_pos["dep_retour"] = [b for b in extract_positions("Heure de départ") if b != colon_pos["dep_aller"]][0]
        colon_pos["arr_retour"] = [b for b in extract_positions("Heure d’arrivée") if b != colon_pos["arr_aller"]][0]

        checkbox = {
            "group1": find_checkbox("Groupe 1"),
            "group2": find_checkbox("Groupe 2"),
            "trajet_train": find_checkbox("Trajet en train"),
            "trajet_voiture": find_checkbox("Trajet en voiture"),
            "picnic": find_checkbox("Pique"),
            "restaurant": find_checkbox("Restaurant"),
            "saison_jas": find_checkbox("juillet"),
        }

        def extract_positions(label):
            found = []
            for page in extract_pages(PDF_ORIG, laparams=laparams):
                for element in page:
                    if isinstance(element, LTTextContainer):
                        for line in element:
                            if label.lower() in line.get_text().lower():
                                for ch in iter_chars(line):
                                    if ch.get_text() == ":":
                                        found.append(ch.bbox)
            return found

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_overlay:
            c = canvas.Canvas(tmp_overlay.name, pagesize=A4)
            c.setFont("Helvetica", 10)
            c.setFillColorRGB(0, 0, 0)

            for key in ["name", "title", "group1_detail", "group2_detail",
                        "dep_aller", "arr_aller", "dep_retour", "arr_retour", "unavailable"]:
                if vals.get(key):
                    draw_string(c, colon_pos[key][0], colon_pos[key][1], vals[key])

            draw_cross(c, checkbox["group1"])
            if vals["group2_detail"]:
                draw_cross(c, checkbox["group2"])
            if vals["transport"] == "train":
                draw_cross(c, checkbox["trajet_train"])
            elif vals["transport"] == "voiture":
                draw_cross(c, checkbox["trajet_voiture"])
            if vals["meal"] == "picnic":
                draw_cross(c, checkbox["picnic"])
            elif vals["meal"] == "restaurant":
                draw_cross(c, checkbox["restaurant"])
            if vals.get("saison_jas"):
                draw_cross(c, checkbox["saison_jas"])

            c.save()

        output_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        reader_base = PdfReader(str(PDF_ORIG))
        reader_ovl = PdfReader(tmp_overlay.name)
        writer = PdfWriter()
        for i in range(len(reader_base.pages)):
            page = reader_base.pages[i]
            page.merge_page(reader_ovl.pages[i])
            writer.add_page(page)

        with open(output_pdf.name, "wb") as f:
            writer.write(f)

        return send_file(output_pdf.name, as_attachment=True, download_name="formulaire_rempli.pdf")

    return render_template("form.html")