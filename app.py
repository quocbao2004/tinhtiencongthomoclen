import os
import re
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from PIL import Image
import pytesseract
import subprocess
print(">>> Checking if tesseract is in PATH:")
print(subprocess.run(["which", "tesseract"], capture_output=True, text=True).stdout)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

# -------------------------
# Function: Parse stitches with log (fixed duplication issue)
# -------------------------
def parse_stitches(text):
    stitch_counts = {}
    calculation_log = []
    lines = text.split('\n')

    for line in lines:
        log_line = []
        consumed_spans = []

        # Match pattern like "11–22 rnd (12 rounds): 60 sc"
        range_match = re.search(r'(\d+)[-–](\d+).*?(\d+)\s*(sc|inc|dec|hdc|dc)', line)
        if range_match:
            rounds = int(range_match.group(2)) - int(range_match.group(1)) + 1
            count = int(range_match.group(3)) * rounds
            stitch = range_match.group(4)
            stitch_counts[stitch] = stitch_counts.get(stitch, 0) + count
            log_line.append(f"{rounds} rounds x {range_match.group(3)} {stitch} = {count} {stitch}")
            consumed_spans.append(range_match.span())

        # Match group repeats like (2 sc; inc)*3 or (2 sc, inc)*3
        groups = re.finditer(r'\((.*?)\)\*(\d+)', line)
        for group_match in groups:
            group, repeat = group_match.group(1), int(group_match.group(2))
            group_span = group_match.span()
            consumed_spans.append(group_span)

            for part in re.split(r'[;,]', group):
                match = re.match(r'(\d+)?\s*(sc|inc|dec|hdc|dc)', part.strip())
                if match:
                    count = int(match.group(1)) if match.group(1) else 1
                    stitch = match.group(2)
                    total = count * repeat
                    stitch_counts[stitch] = stitch_counts.get(stitch, 0) + total
                    log_line.append(f"({count} {stitch}) * {repeat} = {total} {stitch}")

        # Get positions not inside any consumed span
        singles = re.finditer(r'(\d+)\s*(sc|inc|dec|hdc|dc)', line)
        for match in singles:
            start, end = match.span()
            in_group = any(start >= s and end <= e for s, e in consumed_spans)
            if not in_group:
                count = int(match.group(1))
                stitch = match.group(2)
                stitch_counts[stitch] = stitch_counts.get(stitch, 0) + count
                log_line.append(f"{count} {stitch}")

        if log_line:
            calculation_log.append(f"Line: {line}\n  => " + ", ".join(log_line))

    return stitch_counts, calculation_log

# --------------------------
# Function: Calculate total
# --------------------------
def calculate_total(stitch_counts, prices):
    total = 0
    for stitch, count in stitch_counts.items():
        price = prices.get(stitch, 0)
        total += count * price
    return total

# ------------------
# Route: Home
# ------------------
@app.route("/", methods=["GET", "POST"])
def index():
    extracted_text = ""
    stitch_counts = {}
    total_price = 0
    image_url = None
    prices = {"sc": 0, "inc": 0, "dec": 0, "hdc": 0, "dc": 0}
    calculation_log = []

    if request.method == "POST":
        # Lấy giá người dùng nhập
        for stitch in prices.keys():
            prices[stitch] = int(request.form.get(f"price_{stitch}", 0))

        # Xử lý ảnh
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_url = url_for('static', filename='uploads/' + filename)

                image = Image.open(filepath)
                extracted_text = pytesseract.image_to_string(image, lang='eng')
                stitch_counts, calculation_log = parse_stitches(extracted_text)
                total_price = calculate_total(stitch_counts, prices)

    return render_template("index.html",
                           extracted_text=extracted_text,
                           stitch_counts=stitch_counts,
                           total_price=total_price,
                           image_url=image_url,
                           prices=prices,
                           calculation_log=calculation_log)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
