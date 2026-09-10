"""Generate multi-format icons (.png, .ico, .icns) using engine_a11y.packaging."""
from pathlib import Path
from engine_a11y.packaging.icons import generate_app_icons, THEME_COLORS


def main():
    icons_dir = Path(__file__).resolve().parent.parent / "icons"
    generated = generate_app_icons(
        app_name="pdf-a11y",
        bg_color=THEME_COLORS["pdf"],
        symbol_text="PDF",
        output_dir=icons_dir,
    )
    print("Generated icons:")
    for fmt, p in generated.items():
        print(f"  {fmt.upper()}: {p}")


if __name__ == "__main__":
    main()
