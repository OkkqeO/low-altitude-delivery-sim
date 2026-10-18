"""Optional Windows offline OCR. Images stay local; failure leaves geometry usable."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def read_labels(image):
    if sys.platform != "win32":
        return [], "unavailable"
    executable = Path(os.environ.get("SystemRoot", "C:/Windows"))/"System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        with tempfile.TemporaryDirectory(prefix="campus-ocr-") as directory:
            path = Path(directory)/"map.png"
            image.save(path)
            result = subprocess.run([str(executable), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                     "-File", str(Path(__file__).with_suffix(".ps1")), "-ImagePath", str(path)],
                                    capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            return [], "unavailable"
        data = json.loads(result.stdout.decode("utf-8-sig"))
        labels = []
        for line in data["lines"]:
            groups = []
            for word in line["words"]:
                if groups and word["x"]-(groups[-1][-1]["x"]+groups[-1][-1]["w"]) <= max(word["h"], groups[-1][-1]["h"])*.85:
                    groups[-1].append(word)
                else:
                    groups.append([word])
            for group in groups:
                x, y = min(w["x"] for w in group), min(w["y"] for w in group)
                right, bottom = max(w["x"]+w["w"] for w in group), max(w["y"]+w["h"] for w in group)
                text = "".join(w["text"] for w in group).replace(" ", "")
                if len(text) >= 2:
                    labels.append({"text": text, "x": x, "y": y, "w": right-x, "h": bottom-y})
        return labels, data["engine"]
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return [], "unavailable"


def label_for(item, labels, sx, sy, keywords=None):
    """Associate a nearby printed label; never synthesize a measured attribute."""
    from map_geometry import contains
    choices = []
    for label in labels:
        text = label["text"]
        if not any(c in text for c in (keywords or ("楼", "园", "馆", "中心", "院", "所", "基地", "场", "系"))):
            continue
        x, y = (label["x"]+label["w"]/2)*sx, (label["y"]+label["h"]/2)*sy
        if not contains(item, (x, y), label["h"]*sy*.6):
            continue
        distance = ((x-item["x"]-item["w"]/2)**2+(y-item["y"]-item["h"]/2)**2)**.5
        choices.append((distance, text))
    return min(choices)[1] if choices else None
