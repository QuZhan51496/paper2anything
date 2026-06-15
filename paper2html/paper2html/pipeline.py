"""Main pipeline for Paper2HTML conversion."""

import shutil
from pathlib import Path

from paper2html.mineru_client import MineruClient, MineruClientLite
from paper2html.html_generator import HTMLGenerator
from paper2html.config import default_output_root


def paper2html(
    pdf_path: str,
    output_dir: str = None,
    llm_api_key: str = None,
    llm_model: str = None,
    llm_base_url: str = None,
    use_lite: bool = False,
) -> str:
    """
    Convert an academic paper PDF to a beautiful HTML page.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory for output files. Defaults to '<pdf-dir>/.paper2anything/html/<pdf_name>/'.
        llm_api_key: API key for LLM service.
        llm_model: LLM model name.
        llm_base_url: LLM API base URL.
        use_lite: Use lightweight MinerU API (no token, but 10MB/20page limit).

    Returns:
        Path to the generated HTML file.
    """
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Setup output directory
    if output_dir is None:
        output_dir = default_output_root(pdf_path) / pdf_path.stem
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    parsed_dir = output_dir / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)

    # === Step 1: Parse PDF with MinerU ===
    print(f"\n{'='*60}")
    print(f"[Paper2HTML] Step 1: Parsing PDF with MinerU...")
    print(f"{'='*60}")

    try:
        if use_lite:
            client = MineruClientLite()
        else:
            client = MineruClient()
        parse_result = client.parse_pdf(str(pdf_path), str(parsed_dir))
        markdown_content = parse_result["markdown"]
        images = parse_result["images"]
        print(f"[Paper2HTML] Parsed successfully. Markdown length: {len(markdown_content)} chars")
    except Exception as e:
        print(f"[Paper2HTML] MinerU API failed: {e}")
        print(f"[Paper2HTML] Trying lightweight API as fallback...")
        try:
            client = MineruClientLite()
            parse_result = client.parse_pdf(str(pdf_path), str(parsed_dir))
            markdown_content = parse_result["markdown"]
            images = parse_result["images"]
        except Exception as e2:
            raise RuntimeError(f"Both MinerU APIs failed. Error: {e2}") from e

    # === Step 2: Generate HTML with LLM ===
    print(f"\n{'='*60}")
    print(f"[Paper2HTML] Step 2: Generating HTML with LLM...")
    print(f"{'='*60}")

    generator = HTMLGenerator(
        api_key=llm_api_key,
        model=llm_model,
        base_url=llm_base_url,
    )
    html_content = generator.generate(markdown_content)

    # === Step 3: Post-processing ===
    print(f"\n{'='*60}")
    print(f"[Paper2HTML] Step 3: Post-processing...")
    print(f"{'='*60}")

    # Copy images to output directory
    output_images_dir = output_dir / "images"
    if images:
        output_images_dir.mkdir(parents=True, exist_ok=True)
        for name, src_path in images.items():
            dst = output_images_dir / name
            shutil.copy2(src_path, dst)
        print(f"[Paper2HTML] Copied {len(images)} images.")

    # Inject MathJax if not already present
    if "mathjax" not in html_content.lower():
        mathjax_script = (
            '\n<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>\n'
        )
        html_content = html_content.replace("</head>", mathjax_script + "</head>")

    # Save HTML
    html_path = output_dir / f"{pdf_path.stem}.html"
    html_path.write_text(html_content, encoding="utf-8")

    # Save markdown for reference
    md_path = output_dir / f"{pdf_path.stem}.md"
    md_path.write_text(markdown_content, encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"[Paper2HTML] Done!")
    print(f"  HTML: {html_path}")
    print(f"  Markdown: {md_path}")
    print(f"{'='*60}\n")

    return str(html_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert academic paper PDF to HTML")
    parser.add_argument("pdf", help="Path to the input PDF file")
    parser.add_argument("-o", "--output", help="Output directory", default=None)
    parser.add_argument("--model", help="LLM model name", default=None)
    parser.add_argument("--api-key", help="LLM API key", default=None)
    parser.add_argument("--base-url", help="LLM API base URL", default=None)
    parser.add_argument("--lite", action="store_true", help="Use lightweight MinerU API")

    args = parser.parse_args()

    result = paper2html(
        pdf_path=args.pdf,
        output_dir=args.output,
        llm_api_key=args.api_key,
        llm_model=args.model,
        llm_base_url=args.base_url,
        use_lite=args.lite,
    )
    print(f"Output: {result}")
