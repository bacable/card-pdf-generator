import os
import re
import argparse
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import uuid

# Constants for card and page sizes
CARD_WIDTH, CARD_HEIGHT = 2.5 * inch, 3.5 * inch
PAGE_WIDTH, PAGE_HEIGHT = letter
CARDS_PER_ROW = int(PAGE_WIDTH // CARD_WIDTH)
CARDS_PER_COL = int(PAGE_HEIGHT // CARD_HEIGHT)

def parse_quantity_from_name(filename):
    match = re.search(r'-x(\d+)', filename)
    return int(match.group(1)) if match else 1

def parse_quantity_file(path):
    qty_map = {}
    try:
        with open(path, 'r') as f:
            for line in f:
                if ',' in line:
                    name, qty = line.strip().split(',')
                    qty_map[name.strip()] = int(qty.strip())
    except Exception as e:
        print(f"Warning: Failed to parse quantity file {path}: {e}")
    return qty_map

def collect_images(folder, include_subfolders=True):
    image_entries = []

    for root, _, files in os.walk(folder):
        if not include_subfolders and root != folder:
            continue

        # Sort files alphabetically
        files = sorted(files, key=lambda x: x.lower())

        # Check for quantity override file
        quantity_file = next(
            (f for f in files if f.lower().startswith(("cards", "quantities")) and f.lower().endswith(".txt")),
            None
        )
        qty_map = parse_quantity_file(os.path.join(root, quantity_file)) if quantity_file else {}

        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                name, _ = os.path.splitext(f)
                qty = qty_map.get(name, parse_quantity_from_name(f))
                for _ in range(qty):
                    image_entries.append(os.path.join(root, f))

    return image_entries

def fit_image_to_card(img):
    img_width, img_height = img.size
    target_width, target_height = int(CARD_WIDTH), int(CARD_HEIGHT)

    scale = min(target_width / img_width, target_height / img_height)
    new_size = (int(img_width * scale), int(img_height * scale))

    return img.resize(new_size, Image.Resampling.LANCZOS)

def normalize_orientation(img):
    """Rotate landscape images to portrait orientation."""
    return img.rotate(90, expand=True) if img.width > img.height else img

def generate_pdf(image_paths, output_path="output.pdf", scale_images=True):
    import uuid
    c = canvas.Canvas(output_path, pagesize=letter)

    total_grid_height = CARDS_PER_COL * CARD_HEIGHT
    total_grid_width = CARDS_PER_ROW * CARD_WIDTH
    margin_x = (PAGE_WIDTH - total_grid_width) / 2
    margin_y = (PAGE_HEIGHT - total_grid_height) / 2

    x_idx = y_idx = 0
    row_images = []

    def flush_row(images_in_row):
        nonlocal y_idx
        y_pos = PAGE_HEIGHT - margin_y - (y_idx + 1) * CARD_HEIGHT
        for i, entry in enumerate(images_in_row):
            x_pos = margin_x + i * CARD_WIDTH
            c.drawImage(entry['path'], x_pos, y_pos,
                        width=CARD_WIDTH, height=CARD_HEIGHT, preserveAspectRatio=False)
            os.remove(entry['path'])

        y_idx += 1
        if y_idx >= CARDS_PER_COL:
            c.showPage()
            y_idx = 0

    for img_path in image_paths:
        img = Image.open(img_path).convert("RGB")
        img = normalize_orientation(img)

        if scale_images:
            img = img.resize((750, 1050), Image.Resampling.LANCZOS)

        temp_path = img_path + f"_{uuid.uuid4().hex[:6]}_temp.png"
        img.save(temp_path, format="PNG")

        row_images.append({
            'path': temp_path,
        })

        x_idx += 1
        if x_idx >= CARDS_PER_ROW:
            flush_row(row_images)
            row_images = []
            x_idx = 0

    if row_images:
        flush_row(row_images)

    c.save()
    print(f"✅ PDF saved to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate a printable card PDF from image files.")
    parser.add_argument("folder", help="Folder containing image files (JPG/PNG).")
    parser.add_argument("--output", default=None, help="Output PDF filename (default: auto-generated from folder name)")
    parser.add_argument("--no-scale", action="store_true", help="Disable scaling of images to card size")
    parser.add_argument("--no-subfolders", action="store_true", help="Ignore subfolders")

    args = parser.parse_args()

    folder_path = args.folder
    image_paths = collect_images(folder_path, include_subfolders=not args.no_subfolders)

    if not image_paths:
        print("⚠️ No valid image files found. Make sure you're using JPG or PNG files with optional -xN or cards.txt.")
        return

    if args.output is None:
        rel_path = os.path.relpath(args.folder)
        parts = [p for p in rel_path.split(os.sep) if p not in ('.', '..')]
        sanitized = "-".join(part.replace(" ", "") for part in parts)
        args.output = f"{sanitized}.pdf"

    generate_pdf(image_paths, output_path=args.output, scale_images=not args.no_scale)

if __name__ == "__main__":
    main()
