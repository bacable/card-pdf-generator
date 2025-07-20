import os
import re
import uuid
import argparse
from io import BytesIO
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

# Constants
CARD_WIDTH, CARD_HEIGHT = 2.5 * inch, 3.5 * inch
PAGE_WIDTH, PAGE_HEIGHT = letter
CARDS_PER_ROW = int(PAGE_WIDTH // CARD_WIDTH)
CARDS_PER_COL = int(PAGE_HEIGHT // CARD_HEIGHT)

# === Quantity Handling ===
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
        files = sorted(files, key=lambda x: x.lower())
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

# === Image Handling ===
def normalize_orientation(img):
    return img.rotate(90, expand=True) if img.width > img.height else img

def save_pdf(cards, output_path, cards_per_part=None, part_index=None):
    if cards_per_part:
        cards = cards[part_index * cards_per_part:(part_index + 1) * cards_per_part]
        output_path = output_path.replace(".pdf", f"-part{part_index + 1}.pdf")

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    total_grid_width = CARDS_PER_ROW * CARD_WIDTH
    total_grid_height = CARDS_PER_COL * CARD_HEIGHT
    margin_x = (PAGE_WIDTH - total_grid_width) / 2
    margin_y = (PAGE_HEIGHT - total_grid_height) / 2
    x_idx = y_idx = 0

    for img in cards:
        x_pos = margin_x + x_idx * CARD_WIDTH
        y_pos = PAGE_HEIGHT - margin_y - (y_idx + 1) * CARD_HEIGHT
        c.drawImage(img['path'], x_pos, y_pos, width=CARD_WIDTH, height=CARD_HEIGHT, preserveAspectRatio=False)

        # Only delete temp files after final output (part_index is set)
        if part_index is not None:
            os.remove(img['path'])

        x_idx += 1
        if x_idx >= CARDS_PER_ROW:
            x_idx = 0
            y_idx += 1
            if y_idx >= CARDS_PER_COL:
                c.showPage()
                y_idx = 0

    c.save()
    pdf_data = buffer.getvalue()
    buffer.close()

    with open(output_path, "wb") as f:
        f.write(pdf_data)

    return len(pdf_data)

def generate_pdf_with_size_limit(image_paths, output_path="output.pdf", scale_images=True, max_size_mb=None):
    all_cards = []
    for img_path in image_paths:
        img = Image.open(img_path).convert("RGB")
        img = normalize_orientation(img)

        if scale_images:
            img = img.resize((750, 1050), Image.Resampling.LANCZOS)

        temp_path = img_path + f"_{uuid.uuid4().hex[:6]}_temp.png"
        img.save(temp_path, format="PNG")
        all_cards.append({'path': temp_path})

    if not max_size_mb:
        save_pdf(all_cards, output_path)
        print(f"✅ PDF saved to: {output_path}")
        return

    # Try full file size in-memory
    size = save_pdf(all_cards, output_path)
    if size <= max_size_mb * 1024 * 1024:
        print(f"✅ PDF saved to: {output_path}")
        # Cleanup temp files after success
        for img in all_cards:
            if os.path.exists(img['path']):
                os.remove(img['path'])
        return

    # Too large, split into parts
    avg_card_size = size / len(all_cards)
    cards_per_part = int((max_size_mb * 1024 * 1024) // avg_card_size)
    total_parts = (len(all_cards) + cards_per_part - 1) // cards_per_part

    print(f"⚠️ File too large ({size/1024/1024:.2f}MB), splitting into {total_parts} parts...")

    for i in range(total_parts):
        save_pdf(all_cards, output_path, cards_per_part=cards_per_part, part_index=i)

    print(f"✅ PDF split into {total_parts} parts under {max_size_mb}MB each.")

# === CLI ===
def main():
    parser = argparse.ArgumentParser(description="Generate a printable card PDF from image files.")
    parser.add_argument("folder", help="Folder containing image files (JPG/PNG).")
    parser.add_argument("--output", default=None, help="Output PDF filename (default: auto-generated from folder name)")
    parser.add_argument("--no-scale", action="store_true", help="Disable scaling of images to card size")
    parser.add_argument("--no-subfolders", action="store_true", help="Ignore subfolders")
    parser.add_argument("--max-size-mb", type=int, default=None, help="Maximum size of output file in MB (optional)")

    args = parser.parse_args()

    folder_path = args.folder
    image_paths = collect_images(folder_path, include_subfolders=not args.no_subfolders)

    if not image_paths:
        print("⚠️ No valid image files found.")
        return

    # Create output filename if not provided
    if args.output is None:
        rel_path = os.path.relpath(args.folder)
        parts = [p for p in rel_path.split(os.sep) if p not in ('.', '..')]
        sanitized = "-".join(part.replace(" ", "") for part in parts)
        args.output = f"{sanitized}.pdf"

    generate_pdf_with_size_limit(
        image_paths,
        output_path=args.output,
        scale_images=not args.no_scale,
        max_size_mb=args.max_size_mb
    )

if __name__ == "__main__":
    main()
