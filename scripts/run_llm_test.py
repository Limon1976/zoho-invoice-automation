import os
import sys
import json
import logging

from pathlib import Path


def main():
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        filename=str(logs_dir / "ai_enhanced_server.log"),
        filemode="a",
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Ensure project root on sys.path
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from functions.agent_invoice_parser import analyze_proforma_via_agent

    files = [
        "/Users/macos/my_project/inbox/Contract G63.pdf",
        "/Users/macos/my_project/inbox/Invoice-99A2547C-0001.pdf",
    ]

    if len(sys.argv) > 1:
        files = sys.argv[1:]

    results = {}
    for f in files:
        if not os.path.exists(f):
            results[f] = {"error": "file not found"}
            continue
        try:
            results[f] = analyze_proforma_via_agent(f)
        except Exception as e:
            results[f] = {"error": str(e)}

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


